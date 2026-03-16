"""三角对账引擎 — Order ↔ Payment ↔ Bank Statement ↔ Invoice 四方自动匹配"""

import uuid
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import Date, and_, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.bank_reconciliation import BankStatement
from src.models.e_invoice import EInvoice
from src.models.order import Order
from src.models.payment_reconciliation import PaymentRecord
from src.models.tri_reconciliation import TriReconciliationRecord


class TriReconcileService:
    """三角对账核心引擎：自动匹配四方数据，生成匹配记录"""

    # 匹配容差：金额允许1%偏差，时间窗口±5分钟
    AMOUNT_TOLERANCE = 0.01
    TIME_WINDOW_MINUTES = 5

    # ── 执行对账 ────────────────────────────────────────────────────────────────

    @staticmethod
    async def run_reconciliation(
        db: AsyncSession,
        brand_id: str,
        target_date: date,
        store_id: Optional[str] = None,
    ) -> dict:
        """
        对指定日期执行四方对账。
        Phase 1: 按单号精确匹配
        Phase 2: 按金额+时间窗口模糊匹配
        Phase 3: 剩余标记为 single
        返回: {"total": int, "full_match": int, "triple_match": int,
               "double_match": int, "single": int, "total_discrepancy_yuan": float}
        """
        # 1) 拉取当日全部数据
        orders = await _fetch_orders(db, brand_id, target_date, store_id)
        payments = await _fetch_payments(db, brand_id, target_date, store_id)
        bank_stmts = await _fetch_bank_statements(db, brand_id, target_date)
        invoices = await _fetch_invoices(db, brand_id, target_date, store_id)

        # 构建索引（用于快速查找）
        order_by_id: dict[str, dict] = {str(o["id"]): o for o in orders}
        payment_by_order: dict[str, dict] = {}
        for p in payments:
            key = p.get("matched_order_id") or p.get("out_trade_no") or ""
            if key:
                payment_by_order[key] = p
        bank_by_ref: dict[str, dict] = {}
        for b in bank_stmts:
            if b.get("reference_number"):
                bank_by_ref[b["reference_number"]] = b
            if b.get("matched_order_id"):
                bank_by_ref[b["matched_order_id"]] = b
        invoice_by_order: dict[str, dict] = {str(inv["order_id"]): inv for inv in invoices if inv.get("order_id")}

        matched_records: list[TriReconciliationRecord] = []
        used_order_ids: set[str] = set()
        used_payment_ids: set[str] = set()
        used_bank_ids: set[str] = set()
        used_invoice_ids: set[str] = set()

        # ── Phase 1: 精确匹配（按 order_id 关联） ──────────────────────────

        for oid, order in order_by_id.items():
            payment = payment_by_order.get(oid)
            bank = bank_by_ref.get(oid)
            invoice = invoice_by_order.get(oid)

            sides = []
            if order:
                sides.append("order")
            if payment:
                sides.append("payment")
            if bank:
                sides.append("bank")
            if invoice:
                sides.append("invoice")

            if len(sides) < 2:
                continue  # 只有订单自身，Phase 3 再处理

            amounts = []
            rec = TriReconciliationRecord(
                id=uuid.uuid4(),
                brand_id=brand_id,
                store_id=store_id or order.get("store_id"),
                match_date=target_date,
                order_id=oid,
                order_amount_fen=order.get("final_amount"),
                matched_at=datetime.utcnow(),
            )
            amounts.append(order.get("final_amount") or 0)

            if payment:
                rec.payment_id = str(payment["id"])
                rec.payment_amount_fen = payment["amount_fen"]
                amounts.append(payment["amount_fen"])
                used_payment_ids.add(str(payment["id"]))

            if bank:
                rec.bank_statement_id = str(bank["id"])
                rec.bank_amount_fen = bank["amount_fen"]
                amounts.append(bank["amount_fen"])
                used_bank_ids.add(str(bank["id"]))

            if invoice:
                rec.invoice_id = str(invoice["id"])
                rec.invoice_amount_fen = invoice["total_amount_fen"]
                amounts.append(invoice["total_amount_fen"])
                used_invoice_ids.add(str(invoice["id"]))

            rec.match_level = _calc_match_level(len(sides))
            rec.discrepancy_fen = max(amounts) - min(amounts) if amounts else 0
            rec.status = "auto_matched"

            matched_records.append(rec)
            used_order_ids.add(oid)

        # ── Phase 2: 模糊匹配（金额+时间窗口） ─────────────────────────────

        remaining_payments = [p for p in payments if str(p["id"]) not in used_payment_ids]
        remaining_banks = [b for b in bank_stmts if str(b["id"]) not in used_bank_ids]
        remaining_invoices = [inv for inv in invoices if str(inv["id"]) not in used_invoice_ids]

        # 尝试把未匹配的支付与银行流水按金额配对
        for pay in remaining_payments:
            pay_amount = pay["amount_fen"]
            best_bank = None
            best_diff = float("inf")

            for bank in remaining_banks:
                if str(bank["id"]) in used_bank_ids:
                    continue
                bank_amount = bank["amount_fen"]
                diff = abs(pay_amount - bank_amount)
                tolerance = max(1, int(pay_amount * TriReconcileService.AMOUNT_TOLERANCE))
                if diff <= tolerance and diff < best_diff:
                    best_bank = bank
                    best_diff = diff

            if best_bank is None:
                continue

            # 尝试找匹配的发票
            matched_inv = None
            for inv in remaining_invoices:
                if str(inv["id"]) in used_invoice_ids:
                    continue
                inv_amount = inv["total_amount_fen"]
                diff = abs(pay_amount - inv_amount)
                tolerance = max(1, int(pay_amount * TriReconcileService.AMOUNT_TOLERANCE))
                if diff <= tolerance:
                    matched_inv = inv
                    break

            sides_count = 2  # payment + bank
            amounts = [pay_amount, best_bank["amount_fen"]]

            rec = TriReconciliationRecord(
                id=uuid.uuid4(),
                brand_id=brand_id,
                store_id=store_id or pay.get("store_id"),
                match_date=target_date,
                payment_id=str(pay["id"]),
                payment_amount_fen=pay_amount,
                bank_statement_id=str(best_bank["id"]),
                bank_amount_fen=best_bank["amount_fen"],
                matched_at=datetime.utcnow(),
            )
            used_payment_ids.add(str(pay["id"]))
            used_bank_ids.add(str(best_bank["id"]))

            if matched_inv:
                rec.invoice_id = str(matched_inv["id"])
                rec.invoice_amount_fen = matched_inv["total_amount_fen"]
                amounts.append(matched_inv["total_amount_fen"])
                sides_count += 1
                used_invoice_ids.add(str(matched_inv["id"]))

            rec.match_level = _calc_match_level(sides_count)
            rec.discrepancy_fen = max(amounts) - min(amounts) if amounts else 0
            rec.status = "auto_matched"
            matched_records.append(rec)

        # ── Phase 3: 标记剩余为 single ─────────────────────────────────────

        for oid, order in order_by_id.items():
            if oid in used_order_ids:
                continue
            rec = TriReconciliationRecord(
                id=uuid.uuid4(),
                brand_id=brand_id,
                store_id=store_id or order.get("store_id"),
                match_date=target_date,
                order_id=oid,
                order_amount_fen=order.get("final_amount"),
                match_level="single",
                discrepancy_fen=0,
                status="auto_matched",
                matched_at=datetime.utcnow(),
            )
            matched_records.append(rec)

        for pay in payments:
            if str(pay["id"]) in used_payment_ids:
                continue
            rec = TriReconciliationRecord(
                id=uuid.uuid4(),
                brand_id=brand_id,
                store_id=store_id or pay.get("store_id"),
                match_date=target_date,
                payment_id=str(pay["id"]),
                payment_amount_fen=pay["amount_fen"],
                match_level="single",
                discrepancy_fen=0,
                status="auto_matched",
                matched_at=datetime.utcnow(),
            )
            matched_records.append(rec)

        for bank in bank_stmts:
            if str(bank["id"]) in used_bank_ids:
                continue
            rec = TriReconciliationRecord(
                id=uuid.uuid4(),
                brand_id=brand_id,
                store_id=store_id,
                match_date=target_date,
                bank_statement_id=str(bank["id"]),
                bank_amount_fen=bank["amount_fen"],
                match_level="single",
                discrepancy_fen=0,
                status="auto_matched",
                matched_at=datetime.utcnow(),
            )
            matched_records.append(rec)

        for inv in invoices:
            if str(inv["id"]) in used_invoice_ids:
                continue
            rec = TriReconciliationRecord(
                id=uuid.uuid4(),
                brand_id=brand_id,
                store_id=store_id or inv.get("store_id"),
                match_date=target_date,
                invoice_id=str(inv["id"]),
                invoice_amount_fen=inv["total_amount_fen"],
                match_level="single",
                discrepancy_fen=0,
                status="auto_matched",
                matched_at=datetime.utcnow(),
            )
            matched_records.append(rec)

        # 批量写入
        db.add_all(matched_records)
        await db.commit()

        # 汇总
        counts = {"full_match": 0, "triple_match": 0, "double_match": 0, "single": 0}
        total_disc = 0
        for r in matched_records:
            counts[r.match_level] = counts.get(r.match_level, 0) + 1
            total_disc += r.discrepancy_fen

        return {
            "total": len(matched_records),
            "full_match": counts["full_match"],
            "triple_match": counts["triple_match"],
            "double_match": counts["double_match"],
            "single": counts["single"],
            "total_discrepancy_yuan": round(total_disc / 100, 2),
        }

    # ── 分页查询记录列表 ──────────────────────────────────────────────────────

    @staticmethod
    async def get_records(
        db: AsyncSession,
        brand_id: str,
        target_date: Optional[date] = None,
        match_level: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """分页返回对账记录"""
        conditions = [TriReconciliationRecord.brand_id == brand_id]
        if target_date:
            conditions.append(TriReconciliationRecord.match_date == target_date)
        if match_level:
            conditions.append(TriReconciliationRecord.match_level == match_level)
        if status:
            conditions.append(TriReconciliationRecord.status == status)

        where = and_(*conditions)

        # 总数
        count_q = select(func.count()).select_from(TriReconciliationRecord).where(where)
        total = (await db.execute(count_q)).scalar() or 0

        # 分页
        q = (
            select(TriReconciliationRecord)
            .where(where)
            .order_by(TriReconciliationRecord.matched_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await db.execute(q)).scalars().all()

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [_record_to_dict(r) for r in rows],
        }

    # ── 单条详情 ──────────────────────────────────────────────────────────────

    @staticmethod
    async def get_record_detail(
        db: AsyncSession,
        record_id: str,
    ) -> Optional[dict]:
        """获取单条对账记录详情，含四方实体摘要"""
        q = select(TriReconciliationRecord).where(TriReconciliationRecord.id == record_id)
        rec = (await db.execute(q)).scalar_one_or_none()
        if not rec:
            return None

        detail = _record_to_dict(rec)

        # 拉取关联实体摘要
        if rec.order_id:
            oq = select(Order).where(Order.id == rec.order_id)
            order = (await db.execute(oq)).scalar_one_or_none()
            if order:
                detail["order_detail"] = {
                    "id": str(order.id),
                    "status": order.status,
                    "total_amount_yuan": round((order.final_amount or 0) / 100, 2),
                    "order_time": order.order_time.isoformat() if order.order_time else None,
                    "channel": order.sales_channel,
                }

        if rec.payment_id:
            pq = select(PaymentRecord).where(PaymentRecord.id == rec.payment_id)
            pay = (await db.execute(pq)).scalar_one_or_none()
            if pay:
                detail["payment_detail"] = {
                    "id": str(pay.id),
                    "channel": pay.channel,
                    "trade_no": pay.trade_no,
                    "amount_yuan": round(pay.amount_fen / 100, 2),
                    "fee_yuan": round(pay.fee_fen / 100, 2),
                    "trade_time": pay.trade_time.isoformat() if pay.trade_time else None,
                }

        if rec.bank_statement_id:
            bq = select(BankStatement).where(BankStatement.id == rec.bank_statement_id)
            bank = (await db.execute(bq)).scalar_one_or_none()
            if bank:
                detail["bank_detail"] = {
                    "id": str(bank.id),
                    "bank_name": bank.bank_name,
                    "reference_number": bank.reference_number,
                    "amount_yuan": round(bank.amount_fen / 100, 2),
                    "counterparty": bank.counterparty,
                    "transaction_date": bank.transaction_date.isoformat() if bank.transaction_date else None,
                }

        if rec.invoice_id:
            iq = select(EInvoice).where(EInvoice.id == rec.invoice_id)
            inv = (await db.execute(iq)).scalar_one_or_none()
            if inv:
                detail["invoice_detail"] = {
                    "id": str(inv.id),
                    "invoice_number": inv.invoice_number,
                    "buyer_name": inv.buyer_name,
                    "amount_yuan": round(inv.total_amount_fen / 100, 2),
                    "status": inv.status,
                    "issued_at": inv.issued_at.isoformat() if inv.issued_at else None,
                }

        return detail

    # ── 手动匹配 ──────────────────────────────────────────────────────────────

    @staticmethod
    async def manual_match(
        db: AsyncSession,
        record_id: str,
        order_id: Optional[str] = None,
        payment_id: Optional[str] = None,
        bank_id: Optional[str] = None,
        invoice_id: Optional[str] = None,
    ) -> Optional[dict]:
        """手动关联实体到已有对账记录"""
        q = select(TriReconciliationRecord).where(TriReconciliationRecord.id == record_id)
        rec = (await db.execute(q)).scalar_one_or_none()
        if not rec:
            return None

        if order_id:
            rec.order_id = order_id
            oq = select(Order).where(Order.id == order_id)
            order = (await db.execute(oq)).scalar_one_or_none()
            if order:
                rec.order_amount_fen = order.final_amount

        if payment_id:
            rec.payment_id = payment_id
            pq = select(PaymentRecord).where(PaymentRecord.id == payment_id)
            pay = (await db.execute(pq)).scalar_one_or_none()
            if pay:
                rec.payment_amount_fen = pay.amount_fen

        if bank_id:
            rec.bank_statement_id = bank_id
            bq = select(BankStatement).where(BankStatement.id == bank_id)
            bank = (await db.execute(bq)).scalar_one_or_none()
            if bank:
                rec.bank_amount_fen = bank.amount_fen

        if invoice_id:
            rec.invoice_id = invoice_id
            iq = select(EInvoice).where(EInvoice.id == invoice_id)
            inv = (await db.execute(iq)).scalar_one_or_none()
            if inv:
                rec.invoice_amount_fen = inv.total_amount_fen

        # 重新计算匹配级别和差异
        sides = 0
        amounts: list[int] = []
        for amt in [rec.order_amount_fen, rec.payment_amount_fen, rec.bank_amount_fen, rec.invoice_amount_fen]:
            if amt is not None:
                sides += 1
                amounts.append(amt)

        rec.match_level = _calc_match_level(sides)
        rec.discrepancy_fen = (max(amounts) - min(amounts)) if amounts else 0
        rec.status = "manual_matched"
        rec.matched_at = datetime.utcnow()

        await db.commit()
        await db.refresh(rec)
        return _record_to_dict(rec)

    # ── 解决争议 ──────────────────────────────────────────────────────────────

    @staticmethod
    async def resolve_dispute(
        db: AsyncSession,
        record_id: str,
        notes: str,
    ) -> Optional[dict]:
        """标记争议记录为已解决"""
        q = select(TriReconciliationRecord).where(TriReconciliationRecord.id == record_id)
        rec = (await db.execute(q)).scalar_one_or_none()
        if not rec:
            return None

        rec.status = "resolved"
        rec.notes = notes
        await db.commit()
        await db.refresh(rec)
        return _record_to_dict(rec)

    # ── 汇总统计 ──────────────────────────────────────────────────────────────

    @staticmethod
    async def get_summary(
        db: AsyncSession,
        brand_id: str,
        start_date: date,
        end_date: date,
    ) -> dict:
        """指定周期内的对账汇总：匹配率、差异总额、按日趋势、未匹配Top"""
        base = and_(
            TriReconciliationRecord.brand_id == brand_id,
            TriReconciliationRecord.match_date >= start_date,
            TriReconciliationRecord.match_date <= end_date,
        )

        # 总计+各级别计数
        count_q = select(
            func.count().label("total"),
            func.sum(case((TriReconciliationRecord.match_level == "full_match", 1), else_=0)).label("full_match"),
            func.sum(case((TriReconciliationRecord.match_level == "triple_match", 1), else_=0)).label("triple_match"),
            func.sum(case((TriReconciliationRecord.match_level == "double_match", 1), else_=0)).label("double_match"),
            func.sum(case((TriReconciliationRecord.match_level == "single", 1), else_=0)).label("single"),
            func.sum(TriReconciliationRecord.discrepancy_fen).label("total_discrepancy_fen"),
        ).where(base)
        row = (await db.execute(count_q)).one()
        total = row.total or 0
        full = row.full_match or 0
        triple = row.triple_match or 0
        double = row.double_match or 0
        single = row.single or 0
        disc_fen = row.total_discrepancy_fen or 0

        # 按日趋势
        trend_q = (
            select(
                TriReconciliationRecord.match_date,
                func.count().label("total"),
                func.sum(case((TriReconciliationRecord.match_level == "full_match", 1), else_=0)).label("full_match"),
            )
            .where(base)
            .group_by(TriReconciliationRecord.match_date)
            .order_by(TriReconciliationRecord.match_date)
        )
        trend_rows = (await db.execute(trend_q)).all()
        trend = [
            {
                "date": str(r.match_date),
                "total": r.total,
                "full_match": r.full_match or 0,
                "match_rate": round((r.full_match or 0) / r.total * 100, 1) if r.total else 0,
            }
            for r in trend_rows
        ]

        # 未匹配Top（金额最大的single记录）
        top_q = (
            select(TriReconciliationRecord)
            .where(and_(base, TriReconciliationRecord.match_level == "single"))
            .order_by(
                func.coalesce(
                    TriReconciliationRecord.order_amount_fen,
                    TriReconciliationRecord.payment_amount_fen,
                    TriReconciliationRecord.bank_amount_fen,
                    TriReconciliationRecord.invoice_amount_fen,
                    0,
                ).desc()
            )
            .limit(10)
        )
        top_rows = (await db.execute(top_q)).scalars().all()

        return {
            "total": total,
            "full_match": full,
            "triple_match": triple,
            "double_match": double,
            "single": single,
            "full_match_rate": round(full / total * 100, 1) if total else 0,
            "triple_match_rate": round(triple / total * 100, 1) if total else 0,
            "double_match_rate": round(double / total * 100, 1) if total else 0,
            "single_rate": round(single / total * 100, 1) if total else 0,
            "total_discrepancy_yuan": round(disc_fen / 100, 2),
            "trend": trend,
            "top_unmatched": [_record_to_dict(r) for r in top_rows],
        }


# ── 内部辅助函数 ──────────────────────────────────────────────────────────────


def _calc_match_level(sides: int) -> str:
    """根据匹配的系统数量返回匹配级别"""
    if sides >= 4:
        return "full_match"
    elif sides == 3:
        return "triple_match"
    elif sides == 2:
        return "double_match"
    return "single"


def _record_to_dict(rec: TriReconciliationRecord) -> dict:
    """将ORM记录转为API响应字典"""
    return {
        "id": str(rec.id),
        "brand_id": rec.brand_id,
        "store_id": rec.store_id,
        "match_date": str(rec.match_date),
        "order_id": rec.order_id,
        "order_amount_yuan": round(rec.order_amount_fen / 100, 2) if rec.order_amount_fen else None,
        "payment_id": rec.payment_id,
        "payment_amount_yuan": round(rec.payment_amount_fen / 100, 2) if rec.payment_amount_fen else None,
        "bank_statement_id": rec.bank_statement_id,
        "bank_amount_yuan": round(rec.bank_amount_fen / 100, 2) if rec.bank_amount_fen else None,
        "invoice_id": rec.invoice_id,
        "invoice_amount_yuan": round(rec.invoice_amount_fen / 100, 2) if rec.invoice_amount_fen else None,
        "match_level": rec.match_level,
        "discrepancy_yuan": round(rec.discrepancy_fen / 100, 2),
        "status": rec.status,
        "notes": rec.notes,
        "matched_at": rec.matched_at.isoformat() if rec.matched_at else None,
    }


async def _fetch_orders(db: AsyncSession, brand_id: str, target_date: date, store_id: Optional[str]) -> list[dict]:
    """拉取指定日期的订单（已完成状态）"""
    conditions = [
        cast(Order.order_time, Date) == target_date,
        Order.status.in_(["completed", "served"]),
    ]
    if store_id:
        conditions.append(Order.store_id == store_id)

    q = select(Order).where(and_(*conditions))
    rows = (await db.execute(q)).scalars().all()
    return [
        {
            "id": str(r.id),
            "store_id": r.store_id,
            "final_amount": r.final_amount,
            "order_time": r.order_time,
            "channel": r.sales_channel,
        }
        for r in rows
    ]


async def _fetch_payments(db: AsyncSession, brand_id: str, target_date: date, store_id: Optional[str]) -> list[dict]:
    """拉取指定日期的支付流水"""
    conditions = [
        PaymentRecord.brand_id == brand_id,
        cast(PaymentRecord.trade_time, Date) == target_date,
    ]
    if store_id:
        conditions.append(PaymentRecord.store_id == store_id)

    q = select(PaymentRecord).where(and_(*conditions))
    rows = (await db.execute(q)).scalars().all()
    return [
        {
            "id": str(r.id),
            "store_id": r.store_id,
            "amount_fen": r.amount_fen,
            "trade_time": r.trade_time,
            "matched_order_id": r.matched_order_id,
            "out_trade_no": r.out_trade_no,
            "channel": r.channel,
        }
        for r in rows
    ]


async def _fetch_bank_statements(db: AsyncSession, brand_id: str, target_date: date) -> list[dict]:
    """拉取指定日期的银行流水（仅收入类）"""
    q = select(BankStatement).where(
        and_(
            BankStatement.brand_id == brand_id,
            BankStatement.transaction_date == target_date,
            BankStatement.transaction_type == "credit",
        )
    )
    rows = (await db.execute(q)).scalars().all()
    return [
        {
            "id": str(r.id),
            "amount_fen": r.amount_fen,
            "reference_number": r.reference_number,
            "matched_order_id": r.matched_order_id,
            "counterparty": r.counterparty,
        }
        for r in rows
    ]


async def _fetch_invoices(db: AsyncSession, brand_id: str, target_date: date, store_id: Optional[str]) -> list[dict]:
    """拉取指定日期的电子发票（已开具状态）"""
    conditions = [
        EInvoice.brand_id == brand_id,
        EInvoice.status.in_(["issued", "red_issued"]),
        cast(EInvoice.issued_at, Date) == target_date,
    ]
    if store_id:
        conditions.append(EInvoice.store_id == store_id)

    q = select(EInvoice).where(and_(*conditions))
    rows = (await db.execute(q)).scalars().all()
    return [
        {
            "id": str(r.id),
            "store_id": r.store_id,
            "order_id": str(r.order_id) if r.order_id else None,
            "total_amount_fen": r.total_amount_fen,
            "invoice_number": r.invoice_number,
        }
        for r in rows
    ]
