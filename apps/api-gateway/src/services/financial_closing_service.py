"""
日清日结服务 — FinancialClosingService
自动化每日对账：聚合营收、校验支付/银行/发票对账、检测异常
"""

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

import structlog
from sqlalchemy import and_, case, extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.bank_reconciliation import BankReconciliationBatch
from src.models.e_invoice import EInvoice
from src.models.financial_closing import DailyClosingReport
from src.models.order import Order
from src.models.payment_reconciliation import ReconciliationBatch
from src.models.supplier_b2b import B2BPurchaseOrder
from src.models.tri_reconciliation import TriReconciliationRecord

logger = structlog.get_logger()


class FinancialClosingService:
    """日清日结核心服务"""

    # ── 执行日结 ──────────────────────────────────────────────────────

    async def run_daily_closing(
        self,
        db: AsyncSession,
        brand_id: str,
        closing_date: date,
        store_id: Optional[str] = None,
    ) -> dict:
        """执行某日的日清日结"""
        logger.info(
            "开始日结",
            brand_id=brand_id,
            closing_date=str(closing_date),
            store_id=store_id,
        )

        # 查找已有报告（幂等）
        filters = [
            DailyClosingReport.brand_id == brand_id,
            DailyClosingReport.closing_date == closing_date,
        ]
        if store_id:
            filters.append(DailyClosingReport.store_id == store_id)
        else:
            filters.append(DailyClosingReport.store_id.is_(None))

        result = await db.execute(select(DailyClosingReport).where(and_(*filters)))
        report = result.scalar_one_or_none()

        if not report:
            report = DailyClosingReport(
                id=uuid.uuid4(),
                brand_id=brand_id,
                store_id=store_id,
                closing_date=closing_date,
                status="processing",
            )
            db.add(report)
        else:
            report.status = "processing"

        try:
            # 1) 聚合订单营收（按渠道）
            revenue_data = await self._aggregate_revenue(db, brand_id, closing_date, store_id)

            # 2) 检查支付对账状态
            payment_status = await self._check_payment_recon(db, brand_id, closing_date)

            # 3) 检查银行对账状态
            bank_status = await self._check_bank_recon(db, brand_id, closing_date)

            # 4) 三角对账匹配率
            tri_match_rate = await self._check_tri_recon(db, brand_id, closing_date)

            # 5) 发票状态
            invoice_status = await self._check_invoices(db, brand_id, closing_date, store_id)

            # 6) 计算成本（采购已收货金额）
            total_cost_fen = await self._calculate_costs(db, brand_id, closing_date, store_id)

            # 7) 汇总
            total_revenue_fen = revenue_data["total_revenue_fen"]
            gross_profit_fen = total_revenue_fen - total_cost_fen
            order_count = revenue_data["order_count"]
            avg_order_fen = total_revenue_fen // order_count if order_count > 0 else 0

            report.total_revenue_fen = total_revenue_fen
            report.total_cost_fen = total_cost_fen
            report.gross_profit_fen = gross_profit_fen
            report.order_count = order_count
            report.avg_order_fen = avg_order_fen
            report.channel_breakdown = revenue_data["channel_breakdown"]
            report.payment_recon_status = payment_status
            report.bank_recon_status = bank_status
            report.tri_recon_match_rate = tri_match_rate
            report.invoice_status = invoice_status

            # 8) 异常检测
            anomalies = await self._detect_anomalies(
                db,
                brand_id,
                closing_date,
                store_id,
                total_revenue_fen,
                total_cost_fen,
                payment_status,
                bank_status,
            )
            report.anomalies = anomalies if anomalies else None
            report.status = "warning" if anomalies else "completed"
            report.completed_at = datetime.utcnow()

            await db.commit()
            await db.refresh(report)

            logger.info("日结完成", report_id=str(report.id), status=report.status)
            return self._report_to_dict(report)

        except Exception as exc:
            report.status = "error"
            report.anomalies = [{"type": "system_error", "description": str(exc), "amount_fen": 0}]
            await db.commit()
            logger.error("日结异常", error=str(exc), exc_info=exc)
            raise

    # ── 子步骤：聚合营收 ──────────────────────────────────────────────

    async def _aggregate_revenue(
        self,
        db: AsyncSession,
        brand_id: str,
        closing_date: date,
        store_id: Optional[str],
    ) -> dict:
        """按渠道聚合当日订单营收"""
        day_start = datetime.combine(closing_date, datetime.min.time())
        day_end = datetime.combine(closing_date + timedelta(days=1), datetime.min.time())

        filters = [
            Order.order_time >= day_start,
            Order.order_time < day_end,
            Order.status == "completed",
        ]
        if store_id:
            filters.append(Order.store_id == store_id)

        rows = (
            await db.execute(
                select(
                    func.coalesce(Order.sales_channel, "dine_in").label("channel"),
                    func.count(Order.id).label("cnt"),
                    func.coalesce(func.sum(Order.final_amount), 0).label("revenue"),
                )
                .where(and_(*filters))
                .group_by("channel")
            )
        ).all()

        channel_breakdown: dict = {}
        total_revenue_fen = 0
        total_orders = 0

        for row in rows:
            ch = row.channel or "dine_in"
            rev_fen = int(row.revenue or 0)
            cnt = int(row.cnt or 0)
            channel_breakdown[ch] = {"revenue_fen": rev_fen, "orders": cnt}
            total_revenue_fen += rev_fen
            total_orders += cnt

        return {
            "total_revenue_fen": total_revenue_fen,
            "order_count": total_orders,
            "channel_breakdown": channel_breakdown,
        }

    # ── 子步骤：支付对账 ──────────────────────────────────────────────

    async def _check_payment_recon(self, db: AsyncSession, brand_id: str, closing_date: date) -> str:
        rows = (
            await db.execute(
                select(ReconciliationBatch.status, ReconciliationBatch.diff_fen).where(
                    and_(
                        ReconciliationBatch.brand_id == brand_id,
                        ReconciliationBatch.reconcile_date == closing_date,
                    )
                )
            )
        ).all()

        if not rows:
            return "pending"

        has_diff = any(r.diff_fen != 0 or r.status != "completed" for r in rows)
        return "has_diff" if has_diff else "matched"

    # ── 子步骤：银行对账 ──────────────────────────────────────────────

    async def _check_bank_recon(self, db: AsyncSession, brand_id: str, closing_date: date) -> str:
        rows = (
            await db.execute(
                select(BankReconciliationBatch.status, BankReconciliationBatch.diff_fen).where(
                    and_(
                        BankReconciliationBatch.brand_id == brand_id,
                        BankReconciliationBatch.period_start <= closing_date,
                        BankReconciliationBatch.period_end >= closing_date,
                    )
                )
            )
        ).all()

        if not rows:
            return "pending"

        has_diff = any(r.diff_fen != 0 or r.status != "completed" for r in rows)
        return "has_diff" if has_diff else "matched"

    # ── 子步骤：三角对账 ──────────────────────────────────────────────

    async def _check_tri_recon(self, db: AsyncSession, brand_id: str, closing_date: date) -> Optional[Decimal]:
        row = (
            await db.execute(
                select(
                    func.count(TriReconciliationRecord.id).label("total"),
                    func.sum(
                        case(
                            (TriReconciliationRecord.match_level.in_(["full_match", "triple_match"]), 1),
                            else_=0,
                        )
                    ).label("matched"),
                ).where(
                    and_(
                        TriReconciliationRecord.brand_id == brand_id,
                        TriReconciliationRecord.match_date == closing_date,
                    )
                )
            )
        ).one()

        if not row.total or row.total == 0:
            return None

        rate = Decimal(str(int(row.matched or 0))) / Decimal(str(row.total)) * 100
        return round(rate, 2)

    # ── 子步骤：发票状态 ──────────────────────────────────────────────

    async def _check_invoices(
        self,
        db: AsyncSession,
        brand_id: str,
        closing_date: date,
        store_id: Optional[str],
    ) -> str:
        day_start = datetime.combine(closing_date, datetime.min.time())
        day_end = datetime.combine(closing_date + timedelta(days=1), datetime.min.time())

        # 当日完成订单数
        order_filters = [
            Order.order_time >= day_start,
            Order.order_time < day_end,
            Order.status == "completed",
        ]
        if store_id:
            order_filters.append(Order.store_id == store_id)

        order_count = (await db.execute(select(func.count(Order.id)).where(and_(*order_filters)))).scalar() or 0

        if order_count == 0:
            return "none"

        # 已开票数
        inv_filters = [
            EInvoice.brand_id == brand_id,
            EInvoice.status == "issued",
            EInvoice.issued_at >= day_start,
            EInvoice.issued_at < day_end,
        ]
        if store_id:
            inv_filters.append(EInvoice.store_id == store_id)

        invoice_count = (await db.execute(select(func.count(EInvoice.id)).where(and_(*inv_filters)))).scalar() or 0

        if invoice_count == 0:
            return "none"
        if invoice_count >= order_count:
            return "all_issued"
        return "partial"

    # ── 子步骤：计算成本 ──────────────────────────────────────────────

    async def _calculate_costs(
        self,
        db: AsyncSession,
        brand_id: str,
        closing_date: date,
        store_id: Optional[str],
    ) -> int:
        """采购已收货金额作为当日成本"""
        filters = [
            B2BPurchaseOrder.brand_id == brand_id,
            B2BPurchaseOrder.status.in_(["received", "completed"]),
            B2BPurchaseOrder.actual_delivery_date == closing_date,
        ]
        if store_id:
            filters.append(B2BPurchaseOrder.store_id == store_id)

        total = (
            await db.execute(select(func.coalesce(func.sum(B2BPurchaseOrder.total_amount_fen), 0)).where(and_(*filters)))
        ).scalar() or 0

        return int(total)

    # ── 子步骤：异常检测 ──────────────────────────────────────────────

    async def _detect_anomalies(
        self,
        db: AsyncSession,
        brand_id: str,
        closing_date: date,
        store_id: Optional[str],
        revenue_fen: int,
        cost_fen: int,
        payment_status: str,
        bank_status: str,
    ) -> list:
        anomalies = []

        # 1) 营收骤降 >20%（对比前一日）
        prev_date = closing_date - timedelta(days=1)
        prev_filters = [
            DailyClosingReport.brand_id == brand_id,
            DailyClosingReport.closing_date == prev_date,
        ]
        if store_id:
            prev_filters.append(DailyClosingReport.store_id == store_id)
        else:
            prev_filters.append(DailyClosingReport.store_id.is_(None))

        prev = (await db.execute(select(DailyClosingReport.total_revenue_fen).where(and_(*prev_filters)))).scalar()

        if prev and prev > 0:
            drop_pct = (prev - revenue_fen) / prev * 100
            if drop_pct > 20:
                anomalies.append(
                    {
                        "type": "revenue_drop",
                        "description": f"营收较前日下降{drop_pct:.1f}%",
                        "amount_fen": prev - revenue_fen,
                        "severity": "high",
                    }
                )

        # 2) 支付/银行对账有差异
        if payment_status == "has_diff":
            anomalies.append(
                {
                    "type": "payment_mismatch",
                    "description": "支付对账存在差异，请检查支付流水",
                    "amount_fen": 0,
                    "severity": "medium",
                }
            )

        if bank_status == "has_diff":
            anomalies.append(
                {
                    "type": "bank_mismatch",
                    "description": "银行对账存在差异，请核实银行流水",
                    "amount_fen": 0,
                    "severity": "medium",
                }
            )

        # 3) 三角对账未匹配金额 > ¥1000 (100000分)
        unmatched_sum = (
            await db.execute(
                select(func.coalesce(func.sum(TriReconciliationRecord.discrepancy_fen), 0)).where(
                    and_(
                        TriReconciliationRecord.brand_id == brand_id,
                        TriReconciliationRecord.match_date == closing_date,
                        TriReconciliationRecord.match_level.in_(["single", "double_match"]),
                    )
                )
            )
        ).scalar() or 0

        if int(unmatched_sum) > 100000:
            anomalies.append(
                {
                    "type": "unreconciled_amount",
                    "description": f"未对账金额¥{int(unmatched_sum) / 100:.2f}，超过¥1000阈值",
                    "amount_fen": int(unmatched_sum),
                    "severity": "high",
                }
            )

        # 4) 成本异常（成本率 > 70%）
        if revenue_fen > 0:
            cost_ratio = cost_fen / revenue_fen * 100
            if cost_ratio > 70:
                anomalies.append(
                    {
                        "type": "cost_spike",
                        "description": f"成本率{cost_ratio:.1f}%，超过70%警戒线",
                        "amount_fen": cost_fen,
                        "severity": "high",
                    }
                )

        return anomalies

    # ── 报告列表 ──────────────────────────────────────────────────────

    async def get_reports(
        self,
        db: AsyncSession,
        brand_id: str,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> dict:
        filters = [DailyClosingReport.brand_id == brand_id]
        if status:
            filters.append(DailyClosingReport.status == status)
        if start_date:
            filters.append(DailyClosingReport.closing_date >= start_date)
        if end_date:
            filters.append(DailyClosingReport.closing_date <= end_date)

        total = (await db.execute(select(func.count(DailyClosingReport.id)).where(and_(*filters)))).scalar() or 0

        rows = (
            (
                await db.execute(
                    select(DailyClosingReport)
                    .where(and_(*filters))
                    .order_by(DailyClosingReport.closing_date.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            )
            .scalars()
            .all()
        )

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [self._report_to_dict(r) for r in rows],
        }

    # ── 报告详情 ──────────────────────────────────────────────────────

    async def get_report_detail(self, db: AsyncSession, report_id: str) -> Optional[dict]:
        report = (
            await db.execute(select(DailyClosingReport).where(DailyClosingReport.id == uuid.UUID(report_id)))
        ).scalar_one_or_none()

        if not report:
            return None
        return self._report_to_dict(report)

    # ── 月度汇总 ──────────────────────────────────────────────────────

    async def get_monthly_summary(
        self,
        db: AsyncSession,
        brand_id: str,
        year: int,
        month: int,
    ) -> dict:
        filters = [
            DailyClosingReport.brand_id == brand_id,
            extract("year", DailyClosingReport.closing_date) == year,
            extract("month", DailyClosingReport.closing_date) == month,
            DailyClosingReport.status.in_(["completed", "warning"]),
        ]

        row = (
            await db.execute(
                select(
                    func.coalesce(func.sum(DailyClosingReport.total_revenue_fen), 0).label("revenue"),
                    func.coalesce(func.sum(DailyClosingReport.total_cost_fen), 0).label("cost"),
                    func.coalesce(func.sum(DailyClosingReport.gross_profit_fen), 0).label("profit"),
                    func.coalesce(func.sum(DailyClosingReport.order_count), 0).label("orders"),
                    func.count(DailyClosingReport.id).label("days"),
                ).where(and_(*filters))
            )
        ).one()

        revenue = int(row.revenue)
        cost = int(row.cost)
        profit = int(row.profit)
        margin_pct = round(profit / revenue * 100, 2) if revenue > 0 else 0

        # 每日明细
        daily_rows = (
            (
                await db.execute(
                    select(DailyClosingReport).where(and_(*filters)).order_by(DailyClosingReport.closing_date.asc())
                )
            )
            .scalars()
            .all()
        )

        daily_data = [
            {
                "date": r.closing_date.isoformat(),
                "revenue_yuan": round(r.total_revenue_fen / 100, 2),
                "cost_yuan": round(r.total_cost_fen / 100, 2),
                "profit_yuan": round(r.gross_profit_fen / 100, 2),
                "order_count": r.order_count,
                "status": r.status,
            }
            for r in daily_rows
        ]

        # 渠道汇总
        channel_totals: dict = {}
        for r in daily_rows:
            breakdown = r.channel_breakdown or {}
            for ch, data in breakdown.items():
                if ch not in channel_totals:
                    channel_totals[ch] = {"revenue_fen": 0, "orders": 0}
                channel_totals[ch]["revenue_fen"] += data.get("revenue_fen", 0)
                channel_totals[ch]["orders"] += data.get("orders", 0)

        channel_summary = {
            ch: {
                "revenue_yuan": round(v["revenue_fen"] / 100, 2),
                "orders": v["orders"],
            }
            for ch, v in channel_totals.items()
        }

        return {
            "year": year,
            "month": month,
            "total_revenue_yuan": round(revenue / 100, 2),
            "total_cost_yuan": round(cost / 100, 2),
            "total_profit_yuan": round(profit / 100, 2),
            "gross_margin_pct": margin_pct,
            "total_orders": int(row.orders),
            "closing_days": int(row.days),
            "channel_summary": channel_summary,
            "daily": daily_data,
        }

    # ── 日历视图 ──────────────────────────────────────────────────────

    async def get_closing_calendar(
        self,
        db: AsyncSession,
        brand_id: str,
        year: int,
        month: int,
    ) -> list:
        filters = [
            DailyClosingReport.brand_id == brand_id,
            extract("year", DailyClosingReport.closing_date) == year,
            extract("month", DailyClosingReport.closing_date) == month,
        ]

        rows = (
            await db.execute(
                select(
                    DailyClosingReport.closing_date,
                    DailyClosingReport.status,
                    DailyClosingReport.total_revenue_fen,
                    DailyClosingReport.gross_profit_fen,
                    DailyClosingReport.order_count,
                    DailyClosingReport.id,
                )
                .where(and_(*filters))
                .order_by(DailyClosingReport.closing_date.asc())
            )
        ).all()

        return [
            {
                "date": r.closing_date.isoformat(),
                "status": r.status,
                "revenue_yuan": round(r.total_revenue_fen / 100, 2),
                "profit_yuan": round(r.gross_profit_fen / 100, 2),
                "order_count": r.order_count,
                "report_id": str(r.id),
            }
            for r in rows
        ]

    # ── 异常告警 ──────────────────────────────────────────────────────

    async def get_anomaly_alerts(self, db: AsyncSession, brand_id: str, limit: int = 50) -> list:
        rows = (
            (
                await db.execute(
                    select(DailyClosingReport)
                    .where(
                        and_(
                            DailyClosingReport.brand_id == brand_id,
                            DailyClosingReport.anomalies.isnot(None),
                        )
                    )
                    .order_by(DailyClosingReport.closing_date.desc())
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )

        alerts = []
        for r in rows:
            for a in r.anomalies or []:
                alerts.append(
                    {
                        **a,
                        "closing_date": r.closing_date.isoformat(),
                        "report_id": str(r.id),
                        "store_id": r.store_id,
                    }
                )
        return alerts

    # ── 重新执行 ──────────────────────────────────────────────────────

    async def rerun_closing(self, db: AsyncSession, report_id: str) -> dict:
        report = (
            await db.execute(select(DailyClosingReport).where(DailyClosingReport.id == uuid.UUID(report_id)))
        ).scalar_one_or_none()

        if not report:
            raise ValueError("报告不存在")

        return await self.run_daily_closing(
            db,
            report.brand_id,
            report.closing_date,
            report.store_id,
        )

    # ── 序列化 ────────────────────────────────────────────────────────

    @staticmethod
    def _report_to_dict(r: DailyClosingReport) -> dict:
        return {
            "id": str(r.id),
            "brand_id": r.brand_id,
            "store_id": r.store_id,
            "closing_date": r.closing_date.isoformat(),
            "status": r.status,
            "total_revenue_yuan": round(r.total_revenue_fen / 100, 2),
            "total_cost_yuan": round(r.total_cost_fen / 100, 2),
            "gross_profit_yuan": round(r.gross_profit_fen / 100, 2),
            "payment_recon_status": r.payment_recon_status,
            "bank_recon_status": r.bank_recon_status,
            "invoice_status": r.invoice_status,
            "tri_recon_match_rate": float(r.tri_recon_match_rate) if r.tri_recon_match_rate is not None else None,
            "order_count": r.order_count,
            "avg_order_yuan": round(r.avg_order_fen / 100, 2),
            "channel_breakdown": r.channel_breakdown,
            "anomalies": r.anomalies,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }


financial_closing_service = FinancialClosingService()
