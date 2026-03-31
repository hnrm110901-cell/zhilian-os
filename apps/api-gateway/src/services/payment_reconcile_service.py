"""
支付对账服务
Payment Reconciliation Service

核心功能：
- 导入第三方渠道账单（微信/支付宝 CSV）
- 执行对账匹配（trade_no 优先，金额+时间窗口兜底）
- 生成对账批次与差异明细
- 汇总统计
"""

import csv
import io
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, case, func, select
from sqlalchemy import exc as sa_exc
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db_session
from src.models.order import Order, OrderStatus
from src.models.payment_reconciliation import (
    MatchStatus,
    PaymentChannel,
    PaymentRecord,
    ReconciliationBatch,
    ReconciliationDiff,
)

logger = structlog.get_logger()

# 时间窗口容差（秒）
MATCH_TIME_WINDOW_SECONDS = 300  # ±5分钟


class PaymentReconcileService:
    """支付对账服务"""

    # ── 导入渠道账单 ──────────────────────────────────────────────────────────

    async def import_settlement_file(
        self,
        brand_id: str,
        channel: str,
        file_content: bytes,
        file_format: str = "csv",
    ) -> Dict[str, Any]:
        """
        解析渠道账单文件，写入 PaymentRecord 表

        支持格式：
        - wechat CSV: 交易时间,公众账号ID,商户号,特约商户号,设备号,微信订单号,商户订单号,
                      用户标识,交易类型,交易状态,付款银行,货币种类,应结订单金额,代金券金额,
                      微信退款单号,商户退款单号,退款金额,充值券退款金额,退款类型,退款状态,商品名称,
                      商户数据包,手续费,费率,订单金额,申请退款金额,费率备注
        - alipay CSV: 支付宝交易号,商户订单号,交易创建时间,付款时间,最近修改时间,交易来源地,类型,
                      商品名称,（元），服务费（元），成功退款（元），优惠（元），备注
        - generic CSV: trade_no,out_trade_no,amount,fee,trade_time,trade_type
        """
        batch_id = uuid.uuid4()
        records_created = 0
        errors: List[str] = []

        try:
            text = file_content.decode("utf-8-sig")  # 处理 BOM
            # 跳过微信/支付宝账单头部（通常以 # 或汉字开头的说明行）
            lines = text.strip().splitlines()
            data_lines = []
            header_found = False
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    continue
                if not header_found:
                    # 寻找 CSV 头行（包含 trade_no/交易时间/微信订单号 等关键词）
                    lower = stripped.lower()
                    if any(
                        kw in lower
                        for kw in [
                            "trade_no",
                            "交易时间",
                            "微信订单号",
                            "支付宝交易号",
                            "out_trade_no",
                            "商户订单号",
                        ]
                    ):
                        header_found = True
                        data_lines.append(stripped)
                    continue
                data_lines.append(stripped)

            if not header_found:
                # 回退：把所有行当作有表头的 CSV
                data_lines = [l.strip() for l in lines if l.strip()]

            if not data_lines:
                return {"batch_id": str(batch_id), "imported": 0, "errors": ["文件内容为空"]}

            reader = csv.DictReader(io.StringIO("\n".join(data_lines)))
            rows = list(reader)

            async with get_db_session() as session:
                for i, row in enumerate(rows):
                    try:
                        parsed = self._parse_row(row, channel)
                        if parsed is None:
                            continue
                        record = PaymentRecord(
                            brand_id=brand_id,
                            store_id=parsed.get("store_id"),
                            channel=channel,
                            trade_no=parsed["trade_no"],
                            out_trade_no=parsed.get("out_trade_no"),
                            amount_fen=parsed["amount_fen"],
                            fee_fen=parsed.get("fee_fen", 0),
                            settle_amount_fen=parsed.get("settle_amount_fen", 0),
                            trade_time=parsed["trade_time"],
                            settle_date=parsed.get("settle_date"),
                            trade_type=parsed.get("trade_type", "payment"),
                            import_batch_id=batch_id,
                        )
                        session.add(record)
                        records_created += 1
                    except (ValueError, KeyError, IndexError, TypeError) as row_err:
                        errors.append(f"行{i + 2}: {str(row_err)}")
                        if len(errors) > 50:
                            errors.append("错误过多，停止解析")
                            break

                await session.commit()

            logger.info(
                "账单导入完成",
                brand_id=brand_id,
                channel=channel,
                imported=records_created,
                error_count=len(errors),
            )

            return {
                "batch_id": str(batch_id),
                "imported": records_created,
                "errors": errors[:20],  # 最多返回20条错误
            }

        except Exception as e:
            logger.error("账单导入失败", error=str(e), exc_info=e)
            raise

    def _parse_row(self, row: Dict[str, str], channel: str) -> Optional[Dict[str, Any]]:
        """解析单行账单数据，返回标准化字典"""
        # 清理列名（去掉空格、反引号等）
        clean = {k.strip().strip("`").strip(): v.strip().strip("`").strip() for k, v in row.items() if k}

        trade_no = (
            clean.get("trade_no") or clean.get("微信订单号") or clean.get("支付宝交易号") or clean.get("交易号") or ""
        ).strip()

        if not trade_no or trade_no == "0":
            return None

        out_trade_no = (clean.get("out_trade_no") or clean.get("商户订单号") or "").strip()

        # 金额解析（元 → 分）
        amount_str = (
            clean.get("amount")
            or clean.get("应结订单金额")
            or clean.get("订单金额")
            or clean.get("收入（元）")
            or clean.get("总金额")
            or "0"
        )
        amount_fen = self._yuan_to_fen(amount_str)

        fee_str = clean.get("fee") or clean.get("手续费") or clean.get("服务费（元）") or "0"
        fee_fen = abs(self._yuan_to_fen(fee_str))

        settle_amount_fen = amount_fen - fee_fen

        # 交易时间
        time_str = (
            clean.get("trade_time") or clean.get("交易时间") or clean.get("交易创建时间") or clean.get("付款时间") or ""
        ).strip()
        trade_time = self._parse_datetime(time_str)

        # 交易类型
        trade_type_raw = (clean.get("trade_type") or clean.get("交易类型") or clean.get("类型") or "payment").strip()
        trade_type = "refund" if "退款" in trade_type_raw else "payment"

        return {
            "trade_no": trade_no,
            "out_trade_no": out_trade_no or None,
            "amount_fen": amount_fen,
            "fee_fen": fee_fen,
            "settle_amount_fen": settle_amount_fen,
            "trade_time": trade_time,
            "trade_type": trade_type,
        }

    @staticmethod
    def _yuan_to_fen(val: str) -> int:
        """元字符串转分（整数）"""
        val = val.replace(",", "").replace("¥", "").replace("￥", "").strip()
        if not val or val == "-":
            return 0
        return round(float(val) * 100)

    @staticmethod
    def _parse_datetime(val: str) -> datetime:
        """解析多种日期时间格式"""
        for fmt in [
            "%Y-%m-%d %H:%M:%S",
            "%Y/%m/%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y/%m/%d %H:%M",
            "%Y%m%d%H%M%S",
        ]:
            try:
                return datetime.strptime(val, fmt)
            except ValueError:
                continue
        raise ValueError(f"无法解析时间: {val}")

    # ── 执行对账 ──────────────────────────────────────────────────────────────

    async def run_reconciliation(
        self,
        brand_id: str,
        channel: str,
        reconcile_date: date,
    ) -> Dict[str, Any]:
        """
        执行对账：将 PaymentRecord 与 Order 表匹配

        匹配策略：
        1. 优先按 trade_no / out_trade_no 精确匹配
        2. 兜底按 金额 + 交易时间±5分钟 匹配
        """
        batch = ReconciliationBatch(
            brand_id=brand_id,
            channel=channel,
            reconcile_date=reconcile_date,
            status="running",
        )

        try:
            async with get_db_session() as session:
                session.add(batch)
                await session.flush()

                # 1. 获取渠道侧流水
                day_start = datetime.combine(reconcile_date, datetime.min.time())
                day_end = datetime.combine(reconcile_date, datetime.max.time())

                channel_records = (
                    (
                        await session.execute(
                            select(PaymentRecord).where(
                                and_(
                                    PaymentRecord.brand_id == brand_id,
                                    PaymentRecord.channel == channel,
                                    PaymentRecord.trade_time >= day_start,
                                    PaymentRecord.trade_time <= day_end,
                                )
                            )
                        )
                    )
                    .scalars()
                    .all()
                )

                # 2. 获取POS侧订单
                order_conditions = [
                    Order.created_at >= day_start,
                    Order.created_at <= day_end,
                    Order.status != OrderStatus.CANCELLED.value,
                ]
                if hasattr(Order, "brand_id"):
                    order_conditions.append(Order.brand_id == brand_id)

                pos_orders = (await session.execute(select(Order).where(and_(*order_conditions)))).scalars().all()

                # 3. 统计
                batch.channel_total_count = len(channel_records)
                batch.channel_total_fen = sum(r.amount_fen for r in channel_records)
                batch.channel_fee_fen = sum(r.fee_fen for r in channel_records)
                batch.pos_total_count = len(pos_orders)
                batch.pos_total_fen = sum(
                    getattr(o, "total_amount", 0) or getattr(o, "final_amount", 0) or 0 for o in pos_orders
                )

                # 4. 匹配
                matched_count = 0
                diffs: List[ReconciliationDiff] = []

                # 构建 POS 订单索引
                pos_by_trade_no: Dict[str, Any] = {}
                pos_by_amount_time: Dict[str, List[Any]] = {}
                for o in pos_orders:
                    oid = str(getattr(o, "id", ""))
                    trade_ref = getattr(o, "trade_no", None) or getattr(o, "payment_trade_no", None) or ""
                    if trade_ref:
                        pos_by_trade_no[trade_ref] = o
                    # 金额+时间窗口索引 key
                    amt = getattr(o, "total_amount", 0) or getattr(o, "final_amount", 0) or 0
                    amt_key = str(amt)
                    pos_by_amount_time.setdefault(amt_key, []).append(o)

                matched_order_ids = set()
                matched_channel_trade_nos = set()

                for pr in channel_records:
                    matched = False

                    # 策略1: trade_no 精确匹配
                    if pr.trade_no and pr.trade_no in pos_by_trade_no:
                        order = pos_by_trade_no[pr.trade_no]
                        pr.matched_order_id = str(order.id)
                        pr.match_status = MatchStatus.MATCHED.value
                        matched_order_ids.add(str(order.id))
                        matched_channel_trade_nos.add(pr.trade_no)
                        matched_count += 1
                        matched = True

                        # 检查金额差异
                        pos_amt = getattr(order, "total_amount", 0) or getattr(order, "final_amount", 0) or 0
                        if pos_amt != pr.amount_fen:
                            diffs.append(
                                ReconciliationDiff(
                                    batch_id=batch.id,
                                    diff_type="amount_mismatch",
                                    trade_no=pr.trade_no,
                                    pos_amount_fen=pos_amt,
                                    channel_amount_fen=pr.amount_fen,
                                    diff_amount_fen=pos_amt - pr.amount_fen,
                                    order_id=str(order.id),
                                    description=f"金额不符: POS={pos_amt / 100:.2f}元, 渠道={pr.amount_fen / 100:.2f}元",
                                )
                            )
                        continue

                    # 策略2: out_trade_no 匹配
                    if pr.out_trade_no and pr.out_trade_no in pos_by_trade_no:
                        order = pos_by_trade_no[pr.out_trade_no]
                        pr.matched_order_id = str(order.id)
                        pr.match_status = MatchStatus.MATCHED.value
                        matched_order_ids.add(str(order.id))
                        matched_channel_trade_nos.add(pr.trade_no)
                        matched_count += 1
                        matched = True
                        continue

                    # 策略3: 金额+时间窗口兜底
                    amt_key = str(pr.amount_fen)
                    candidates = pos_by_amount_time.get(amt_key, [])
                    for cand in candidates:
                        cand_id = str(cand.id)
                        if cand_id in matched_order_ids:
                            continue
                        cand_time = getattr(cand, "created_at", None) or getattr(cand, "order_time", None)
                        if cand_time and abs((cand_time - pr.trade_time).total_seconds()) <= MATCH_TIME_WINDOW_SECONDS:
                            pr.matched_order_id = cand_id
                            pr.match_status = MatchStatus.MATCHED.value
                            matched_order_ids.add(cand_id)
                            matched_channel_trade_nos.add(pr.trade_no)
                            matched_count += 1
                            matched = True
                            break

                    if not matched:
                        # 渠道有、POS无
                        pr.match_status = MatchStatus.UNMATCHED.value
                        diffs.append(
                            ReconciliationDiff(
                                batch_id=batch.id,
                                diff_type="channel_only",
                                trade_no=pr.trade_no,
                                channel_amount_fen=pr.amount_fen,
                                diff_amount_fen=pr.amount_fen,
                                description=f"渠道有POS无: {pr.trade_no}, 金额={pr.amount_fen / 100:.2f}元",
                            )
                        )

                # POS有、渠道无
                for o in pos_orders:
                    oid = str(o.id)
                    if oid not in matched_order_ids:
                        pos_amt = getattr(o, "total_amount", 0) or getattr(o, "final_amount", 0) or 0
                        diffs.append(
                            ReconciliationDiff(
                                batch_id=batch.id,
                                diff_type="pos_only",
                                pos_amount_fen=pos_amt,
                                diff_amount_fen=pos_amt,
                                order_id=oid,
                                description=f"POS有渠道无: 订单={oid}, 金额={pos_amt / 100:.2f}元",
                            )
                        )

                # 5. 更新批次统计
                batch.matched_count = matched_count
                batch.unmatched_channel_count = sum(1 for d in diffs if d.diff_type == "channel_only")
                batch.unmatched_pos_count = sum(1 for d in diffs if d.diff_type == "pos_only")
                batch.diff_fen = abs(batch.pos_total_fen - batch.channel_total_fen)
                total_possible = max(batch.pos_total_count, batch.channel_total_count, 1)
                batch.match_rate = round(matched_count / total_possible, 4)
                batch.status = "completed"

                for d in diffs:
                    session.add(d)

                await session.commit()
                await session.refresh(batch)

            logger.info(
                "对账完成",
                batch_id=str(batch.id),
                channel=channel,
                matched=matched_count,
                diffs=len(diffs),
                match_rate=batch.match_rate,
            )

            return {
                "batch_id": str(batch.id),
                "status": batch.status,
                "matched_count": batch.matched_count,
                "unmatched_pos_count": batch.unmatched_pos_count,
                "unmatched_channel_count": batch.unmatched_channel_count,
                "diff_fen": batch.diff_fen,
                "diff_yuan": round(batch.diff_fen / 100, 2),
                "match_rate": batch.match_rate,
                "diff_count": len(diffs),
            }

        except (sa_exc.SQLAlchemyError, ValueError, KeyError) as e:
            logger.error("对账执行失败", error=str(e), exc_info=e)
            try:
                async with get_db_session() as session:
                    batch.status = "failed"
                    batch.error_message = str(e)[:500]
                    session.add(batch)
                    await session.commit()
            except Exception:
                pass
            raise

    # ── 查询 ──────────────────────────────────────────────────────────────────

    async def get_batches(
        self,
        brand_id: str,
        channel: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """查询对账批次列表"""
        async with get_db_session() as session:
            conditions = [ReconciliationBatch.brand_id == brand_id]
            if channel:
                conditions.append(ReconciliationBatch.channel == channel)
            if start_date:
                conditions.append(ReconciliationBatch.reconcile_date >= start_date)
            if end_date:
                conditions.append(ReconciliationBatch.reconcile_date <= end_date)

            # 总数
            total = (
                await session.execute(select(func.count()).select_from(ReconciliationBatch).where(and_(*conditions)))
            ).scalar() or 0

            # 分页
            offset = (page - 1) * page_size
            rows = (
                (
                    await session.execute(
                        select(ReconciliationBatch)
                        .where(and_(*conditions))
                        .order_by(ReconciliationBatch.reconcile_date.desc())
                        .offset(offset)
                        .limit(page_size)
                    )
                )
                .scalars()
                .all()
            )

            batches = []
            for b in rows:
                batches.append(
                    {
                        "id": str(b.id),
                        "brand_id": b.brand_id,
                        "channel": b.channel,
                        "reconcile_date": b.reconcile_date.isoformat(),
                        "pos_total_count": b.pos_total_count,
                        "pos_total_fen": b.pos_total_fen,
                        "pos_total_yuan": round(b.pos_total_fen / 100, 2),
                        "channel_total_count": b.channel_total_count,
                        "channel_total_fen": b.channel_total_fen,
                        "channel_total_yuan": round(b.channel_total_fen / 100, 2),
                        "channel_fee_fen": b.channel_fee_fen,
                        "channel_fee_yuan": round(b.channel_fee_fen / 100, 2),
                        "matched_count": b.matched_count,
                        "unmatched_pos_count": b.unmatched_pos_count,
                        "unmatched_channel_count": b.unmatched_channel_count,
                        "diff_fen": b.diff_fen,
                        "diff_yuan": round(b.diff_fen / 100, 2),
                        "match_rate": b.match_rate,
                        "status": b.status,
                        "error_message": b.error_message,
                        "created_at": b.created_at.isoformat() if b.created_at else None,
                    }
                )

            return {
                "batches": batches,
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
            }

    async def get_batch_details(
        self,
        batch_id: str,
    ) -> Optional[Dict[str, Any]]:
        """获取对账批次详情（含差异记录）"""
        bid = uuid.UUID(batch_id)
        async with get_db_session() as session:
            batch = (
                await session.execute(select(ReconciliationBatch).where(ReconciliationBatch.id == bid))
            ).scalar_one_or_none()

            if not batch:
                return None

            diffs = (
                (
                    await session.execute(
                        select(ReconciliationDiff)
                        .where(ReconciliationDiff.batch_id == bid)
                        .order_by(ReconciliationDiff.created_at.asc())
                    )
                )
                .scalars()
                .all()
            )

            diff_list = []
            for d in diffs:
                diff_list.append(
                    {
                        "id": str(d.id),
                        "diff_type": d.diff_type,
                        "trade_no": d.trade_no,
                        "pos_amount_fen": d.pos_amount_fen,
                        "pos_amount_yuan": round(d.pos_amount_fen / 100, 2) if d.pos_amount_fen else None,
                        "channel_amount_fen": d.channel_amount_fen,
                        "channel_amount_yuan": round(d.channel_amount_fen / 100, 2) if d.channel_amount_fen else None,
                        "diff_amount_fen": d.diff_amount_fen,
                        "diff_amount_yuan": round(d.diff_amount_fen / 100, 2) if d.diff_amount_fen else None,
                        "order_id": d.order_id,
                        "description": d.description,
                        "resolved": d.resolved,
                        "resolved_by": d.resolved_by,
                        "resolved_at": d.resolved_at.isoformat() if d.resolved_at else None,
                    }
                )

            return {
                "batch": {
                    "id": str(batch.id),
                    "brand_id": batch.brand_id,
                    "channel": batch.channel,
                    "reconcile_date": batch.reconcile_date.isoformat(),
                    "pos_total_count": batch.pos_total_count,
                    "pos_total_fen": batch.pos_total_fen,
                    "pos_total_yuan": round(batch.pos_total_fen / 100, 2),
                    "channel_total_count": batch.channel_total_count,
                    "channel_total_fen": batch.channel_total_fen,
                    "channel_total_yuan": round(batch.channel_total_fen / 100, 2),
                    "channel_fee_yuan": round(batch.channel_fee_fen / 100, 2),
                    "matched_count": batch.matched_count,
                    "unmatched_pos_count": batch.unmatched_pos_count,
                    "unmatched_channel_count": batch.unmatched_channel_count,
                    "diff_fen": batch.diff_fen,
                    "diff_yuan": round(batch.diff_fen / 100, 2),
                    "match_rate": batch.match_rate,
                    "status": batch.status,
                    "error_message": batch.error_message,
                },
                "diffs": diff_list,
                "diff_count": len(diff_list),
            }

    async def get_summary(
        self,
        brand_id: str,
        days: int = 30,
    ) -> Dict[str, Any]:
        """获取汇总统计"""
        cutoff = date.today() - timedelta(days=days)

        async with get_db_session() as session:
            row = (
                await session.execute(
                    select(
                        func.count(ReconciliationBatch.id).label("total_batches"),
                        func.coalesce(func.sum(ReconciliationBatch.pos_total_fen), 0).label("total_pos_fen"),
                        func.coalesce(func.sum(ReconciliationBatch.channel_total_fen), 0).label("total_channel_fen"),
                        func.coalesce(func.sum(ReconciliationBatch.diff_fen), 0).label("total_diff_fen"),
                        func.coalesce(func.sum(ReconciliationBatch.matched_count), 0).label("total_matched"),
                        func.coalesce(func.sum(ReconciliationBatch.channel_fee_fen), 0).label("total_fee_fen"),
                        func.coalesce(func.avg(ReconciliationBatch.match_rate), 0).label("avg_match_rate"),
                        func.sum(case((ReconciliationBatch.status == "completed", 1), else_=0)).label("completed_count"),
                    ).where(
                        and_(
                            ReconciliationBatch.brand_id == brand_id,
                            ReconciliationBatch.reconcile_date >= cutoff,
                        )
                    )
                )
            ).one()

            # 未解决差异数
            unresolved = (
                await session.execute(
                    select(func.count())
                    .select_from(ReconciliationDiff)
                    .where(
                        and_(
                            ReconciliationDiff.resolved == False,  # noqa: E712
                            ReconciliationDiff.batch_id.in_(
                                select(ReconciliationBatch.id).where(
                                    and_(
                                        ReconciliationBatch.brand_id == brand_id,
                                        ReconciliationBatch.reconcile_date >= cutoff,
                                    )
                                )
                            ),
                        )
                    )
                )
            ).scalar() or 0

            total_pos_fen = int(row.total_pos_fen or 0)
            total_channel_fen = int(row.total_channel_fen or 0)
            total_diff_fen = int(row.total_diff_fen or 0)
            total_fee_fen = int(row.total_fee_fen or 0)

            return {
                "period_days": days,
                "total_batches": row.total_batches or 0,
                "completed_count": int(row.completed_count or 0),
                "total_pos_yuan": round(total_pos_fen / 100, 2),
                "total_channel_yuan": round(total_channel_fen / 100, 2),
                "total_diff_yuan": round(total_diff_fen / 100, 2),
                "total_fee_yuan": round(total_fee_fen / 100, 2),
                "total_matched": int(row.total_matched or 0),
                "avg_match_rate": round(float(row.avg_match_rate or 0), 4),
                "unresolved_diffs": unresolved,
            }

    # ── 标记差异已处理 ────────────────────────────────────────────────────────

    async def resolve_diff(
        self,
        diff_id: str,
        resolved_by: str,
    ) -> bool:
        """标记差异记录为已处理"""
        did = uuid.UUID(diff_id)
        async with get_db_session() as session:
            diff = (await session.execute(select(ReconciliationDiff).where(ReconciliationDiff.id == did))).scalar_one_or_none()

            if not diff:
                return False

            diff.resolved = True
            diff.resolved_by = resolved_by
            diff.resolved_at = datetime.utcnow()
            await session.commit()

            logger.info("差异已标记处理", diff_id=diff_id, resolved_by=resolved_by)
            return True


# 全局服务实例
payment_reconcile_service = PaymentReconcileService()
