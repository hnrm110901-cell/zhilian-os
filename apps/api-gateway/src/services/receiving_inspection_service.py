"""
收货验收服务
处理开始收货、记录条目、完成收货（触发入库）、提交争议等完整流程
质检 reject 的条目不入库，shortage / quality_issue 自动创建争议记录
"""

import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import structlog
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db_session
from src.models.receiving_inspection import (
    DisputeResolution,
    DisputeType,
    PurchaseReceiving,
    PurchaseReceivingItem,
    QualityStatus,
    ReceivingDispute,
    ReceivingStatus,
)
from src.models.inventory import InventoryItem, InventoryTransaction, TransactionType

logger = structlog.get_logger()


class ReceivingInspectionService:
    """收货验收服务"""

    async def start_receiving(
        self,
        store_id: str,
        receiver_id: str,
        supplier_id: Optional[str] = None,
        supplier_name: Optional[str] = None,
        purchase_order_id: Optional[str] = None,
        invoice_no: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        开始收货流程，返回 receiving_id
        创建一个 in_progress 的收货单，等待逐条录入
        """
        async with get_db_session() as session:
            receiving_no = await self._generate_receiving_no(session)

            receiving = PurchaseReceiving(
                id=uuid.uuid4(),
                receiving_no=receiving_no,
                store_id=uuid.UUID(str(store_id)),
                purchase_order_id=(
                    uuid.UUID(str(purchase_order_id)) if purchase_order_id else None
                ),
                supplier_id=uuid.UUID(str(supplier_id)) if supplier_id else None,
                supplier_name=supplier_name,
                status=ReceivingStatus.IN_PROGRESS,
                received_by=uuid.UUID(str(receiver_id)),
                received_at=datetime.utcnow(),
                invoice_no=invoice_no,
                total_amount_fen=0,
                created_at=datetime.utcnow(),
            )
            session.add(receiving)
            await session.commit()
            await session.refresh(receiving)

            logger.info(
                "开始收货",
                receiving_no=receiving_no,
                store_id=str(store_id),
                supplier_name=supplier_name,
            )

            return {
                "receiving_id": str(receiving.id),
                "receiving_no": receiving.receiving_no,
                "status": receiving.status.value,
            }

    async def record_item(
        self,
        receiving_id: str,
        ingredient_id: str,
        ingredient_name: str,
        unit: str,
        received_qty: float,
        quality_status: str,
        unit_price_fen: Optional[int] = None,
        rejected_qty: float = 0,
        temperature: Optional[float] = None,
        expiry_date: Optional[date] = None,
        batch_no: Optional[str] = None,
        ordered_qty: Optional[float] = None,
        quality_notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """记录单个食材收货情况"""
        async with get_db_session() as session:
            receiving = await self._get_receiving(session, receiving_id)

            if receiving.status != ReceivingStatus.IN_PROGRESS:
                raise ValueError(
                    f"收货单状态为 {receiving.status.value}，无法继续录入"
                )

            # 自动检测 shortage 和 quality_issue
            has_shortage, has_quality_issue = self._auto_detect_issues_inline(
                ordered_qty=ordered_qty,
                received_qty=received_qty,
                quality_status=quality_status,
                rejected_qty=rejected_qty,
            )

            item = PurchaseReceivingItem(
                id=uuid.uuid4(),
                receiving_id=uuid.UUID(str(receiving_id)),
                ingredient_id=uuid.UUID(str(ingredient_id)),
                ingredient_name=ingredient_name,
                unit=unit,
                ordered_qty=ordered_qty,
                received_qty=received_qty,
                rejected_qty=rejected_qty,
                unit_price_fen=unit_price_fen,
                quality_status=QualityStatus(quality_status),
                quality_notes=quality_notes,
                temperature=temperature,
                expiry_date=expiry_date,
                batch_no=batch_no,
                has_shortage=has_shortage,
                has_quality_issue=has_quality_issue,
            )
            session.add(item)
            await session.commit()
            await session.refresh(item)

            return {
                "item_id": str(item.id),
                "ingredient_name": ingredient_name,
                "received_qty": received_qty,
                "quality_status": quality_status,
                "has_shortage": has_shortage,
                "has_quality_issue": has_quality_issue,
            }

    async def complete_receiving(
        self,
        receiving_id: str,
        receiver_id: str,
    ) -> Dict[str, Any]:
        """
        完成收货 - 核心方法（原子事务）
        1. 验证 receiving 状态 = in_progress
        2. quality_status = pass/conditional 的条目：入库
        3. quality_status = reject 的条目：记录拒收，不入库
        4. has_shortage=True 或 has_quality_issue=True：自动创建 ReceivingDispute
        5. 计算 total_amount_fen
        6. 状态变 completed
        7. 所有库存变动在同一事务
        """
        async with get_db_session() as session:
            receiving = await self._get_receiving(session, receiving_id)

            if receiving.status != ReceivingStatus.IN_PROGRESS:
                raise ValueError(
                    f"收货单状态为 {receiving.status.value}，无法重复完成"
                )

            # 加载所有明细
            items_stmt = select(PurchaseReceivingItem).where(
                PurchaseReceivingItem.receiving_id == uuid.UUID(str(receiving_id))
            )
            items_result = await session.execute(items_stmt)
            items = items_result.scalars().all()

            if not items:
                raise ValueError("收货单没有录入任何条目，无法完成")

            items_received = 0
            items_rejected = 0
            disputes_created = 0
            total_amount_fen = 0

            for item in items:
                # 累计金额（只计入库部分）
                if item.unit_price_fen and item.quality_status != QualityStatus.REJECT:
                    total_amount_fen += int(item.unit_price_fen * item.received_qty)

                if item.quality_status == QualityStatus.REJECT:
                    # 拒收：不入库
                    items_rejected += 1
                    # 创建质量争议
                    dispute = ReceivingDispute(
                        id=uuid.uuid4(),
                        receiving_id=uuid.UUID(str(receiving_id)),
                        item_id=item.id,
                        dispute_type=DisputeType.QUALITY,
                        resolution=DisputeResolution.PENDING,
                        notes=item.quality_notes or "质检不合格，拒绝入库",
                        created_at=datetime.utcnow(),
                    )
                    session.add(dispute)
                    disputes_created += 1
                    continue

                # pass / conditional -> 入库
                items_received += 1

                # 增加库存
                inv_stmt = (
                    select(InventoryItem)
                    .where(
                        and_(
                            InventoryItem.store_id == str(receiving.store_id),
                            InventoryItem.name == item.ingredient_name,
                        )
                    )
                    .with_for_update()
                )
                inv_result = await session.execute(inv_stmt)
                inv = inv_result.scalar_one_or_none()

                if inv:
                    inv.current_quantity += item.received_qty
                    # 如果有单价，更新库存成本价（加权平均简化为直接覆盖）
                    if item.unit_price_fen:
                        inv.unit_cost = item.unit_price_fen

                    tx = InventoryTransaction(
                        id=uuid.uuid4(),
                        item_id=inv.id,
                        store_id=str(receiving.store_id),
                        transaction_type=TransactionType.PURCHASE.value,
                        quantity=item.received_qty,
                        notes=f"收货验收入库 {receiving.receiving_no}",
                        created_at=datetime.utcnow(),
                    )
                    session.add(tx)

                # 自动创建争议（shortage）
                if item.has_shortage:
                    dispute = ReceivingDispute(
                        id=uuid.uuid4(),
                        receiving_id=uuid.UUID(str(receiving_id)),
                        item_id=item.id,
                        dispute_type=DisputeType.SHORTAGE,
                        claimed_amount_fen=(
                            int(item.unit_price_fen * (item.ordered_qty - item.received_qty))
                            if item.unit_price_fen and item.ordered_qty
                            else None
                        ),
                        resolution=DisputeResolution.PENDING,
                        notes=f"收货数量 {item.received_qty} 少于订单数量 {item.ordered_qty}",
                        created_at=datetime.utcnow(),
                    )
                    session.add(dispute)
                    disputes_created += 1

                # 自动创建争议（quality_issue 但未拒收，如 conditional）
                elif item.has_quality_issue and item.quality_status == QualityStatus.CONDITIONAL:
                    dispute = ReceivingDispute(
                        id=uuid.uuid4(),
                        receiving_id=uuid.UUID(str(receiving_id)),
                        item_id=item.id,
                        dispute_type=DisputeType.QUALITY,
                        resolution=DisputeResolution.PENDING,
                        notes=item.quality_notes or "质量存在问题，条件接收",
                        created_at=datetime.utcnow(),
                    )
                    session.add(dispute)
                    disputes_created += 1

            receiving.total_amount_fen = total_amount_fen
            receiving.status = ReceivingStatus.COMPLETED
            receiving.received_by = uuid.UUID(str(receiver_id))

            await session.commit()

            logger.info(
                "收货完成",
                receiving_no=receiving.receiving_no,
                items_received=items_received,
                items_rejected=items_rejected,
                disputes_created=disputes_created,
            )

            return {
                "receiving_id": str(receiving.id),
                "receiving_no": receiving.receiving_no,
                "items_received": items_received,
                "items_rejected": items_rejected,
                "disputes_created": disputes_created,
                "total_amount_fen": total_amount_fen,
                "total_amount_yuan": round(total_amount_fen / 100, 2),
            }

    async def file_dispute(
        self,
        receiving_id: str,
        item_id: str,
        dispute_type: str,
        claimed_amount_fen: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """手动提交争议"""
        async with get_db_session() as session:
            receiving = await self._get_receiving(session, receiving_id)

            # 验证 item 属于该 receiving
            item_stmt = select(PurchaseReceivingItem).where(
                and_(
                    PurchaseReceivingItem.id == uuid.UUID(str(item_id)),
                    PurchaseReceivingItem.receiving_id == uuid.UUID(str(receiving_id)),
                )
            )
            item_result = await session.execute(item_stmt)
            item = item_result.scalar_one_or_none()
            if item is None:
                raise ValueError(f"收货条目不存在或不属于该收货单: {item_id}")

            dispute = ReceivingDispute(
                id=uuid.uuid4(),
                receiving_id=uuid.UUID(str(receiving_id)),
                item_id=uuid.UUID(str(item_id)),
                dispute_type=DisputeType(dispute_type),
                claimed_amount_fen=claimed_amount_fen,
                resolution=DisputeResolution.PENDING,
                notes=notes,
                created_at=datetime.utcnow(),
            )
            session.add(dispute)

            # 如果收货单已完成，更新为 disputed
            if receiving.status == ReceivingStatus.COMPLETED:
                receiving.status = ReceivingStatus.DISPUTED

            await session.commit()
            await session.refresh(dispute)

            return {
                "dispute_id": str(dispute.id),
                "dispute_type": dispute_type,
                "resolution": dispute.resolution.value,
            }

    async def get_receiving_stats(
        self,
        store_id: str,
        days: int = 30,
    ) -> Dict[str, Any]:
        """
        收货统计（用于衡量供应商质量）：
        - shortage_rate: 短缺率（received < ordered 的比例）
        - quality_pass_rate: 质检通过率
        - top_dispute_suppliers: 问题最多的供应商（按争议数排序）
        """
        async with get_db_session() as session:
            since = datetime.utcnow() - timedelta(days=days)
            store_uuid = uuid.UUID(str(store_id))

            # 该周期内已完成的收货单
            recv_stmt = select(PurchaseReceiving).where(
                and_(
                    PurchaseReceiving.store_id == store_uuid,
                    PurchaseReceiving.status.in_(
                        [ReceivingStatus.COMPLETED, ReceivingStatus.DISPUTED]
                    ),
                    PurchaseReceiving.created_at >= since,
                )
            )
            recv_result = await session.execute(recv_stmt)
            receivings = recv_result.scalars().all()

            total_receivings = len(receivings)
            if total_receivings == 0:
                return {
                    "period_days": days,
                    "total_receivings": 0,
                    "shortage_rate": 0.0,
                    "quality_pass_rate": 0.0,
                    "top_dispute_suppliers": [],
                }

            receiving_ids = [r.id for r in receivings]

            # 所有明细
            items_stmt = select(PurchaseReceivingItem).where(
                PurchaseReceivingItem.receiving_id.in_(receiving_ids)
            )
            items_result = await session.execute(items_stmt)
            all_items = items_result.scalars().all()

            total_items = len(all_items)
            shortage_count = sum(1 for i in all_items if i.has_shortage)
            quality_fail_count = sum(
                1 for i in all_items
                if i.quality_status in (QualityStatus.REJECT, QualityStatus.CONDITIONAL)
            )

            shortage_rate = shortage_count / total_items if total_items else 0.0
            quality_pass_rate = (
                1 - quality_fail_count / total_items
            ) if total_items else 1.0

            # 供应商争议 Top 排行
            disputes_stmt = (
                select(
                    PurchaseReceiving.supplier_name,
                    func.count(ReceivingDispute.id).label("dispute_count"),
                )
                .join(
                    ReceivingDispute,
                    ReceivingDispute.receiving_id == PurchaseReceiving.id,
                )
                .where(PurchaseReceiving.store_id == store_uuid)
                .where(PurchaseReceiving.created_at >= since)
                .group_by(PurchaseReceiving.supplier_name)
                .order_by(desc("dispute_count"))
                .limit(5)
            )
            disputes_result = await session.execute(disputes_stmt)
            top_dispute_suppliers = [
                {"supplier_name": row.supplier_name, "dispute_count": row.dispute_count}
                for row in disputes_result
            ]

            return {
                "period_days": days,
                "total_receivings": total_receivings,
                "total_items": total_items,
                "shortage_rate": round(shortage_rate, 4),
                "quality_pass_rate": round(quality_pass_rate, 4),
                "top_dispute_suppliers": top_dispute_suppliers,
            }

    # ------------------------------------------------------------------ #
    #  私有方法
    # ------------------------------------------------------------------ #

    async def _get_receiving(
        self,
        session: AsyncSession,
        receiving_id: str,
    ) -> PurchaseReceiving:
        """按 ID 获取收货单，不存在则抛出 ValueError"""
        stmt = select(PurchaseReceiving).where(
            PurchaseReceiving.id == uuid.UUID(str(receiving_id))
        )
        result = await session.execute(stmt)
        receiving = result.scalar_one_or_none()
        if receiving is None:
            raise ValueError(f"收货单不存在: {receiving_id}")
        return receiving

    async def _generate_receiving_no(self, session: AsyncSession) -> str:
        """生成唯一收货单号 REC-YYYYMMDD-NNNN"""
        today_str = date.today().strftime("%Y%m%d")
        prefix = f"REC-{today_str}-"

        stmt = (
            select(PurchaseReceiving.receiving_no)
            .where(PurchaseReceiving.receiving_no.like(f"{prefix}%"))
            .order_by(desc(PurchaseReceiving.receiving_no))
            .limit(1)
        )
        result = await session.execute(stmt)
        last_no = result.scalar_one_or_none()

        if last_no:
            seq = int(last_no[-4:]) + 1
        else:
            seq = 1

        return f"{prefix}{seq:04d}"

    @staticmethod
    def _auto_detect_issues_inline(
        ordered_qty: Optional[float],
        received_qty: float,
        quality_status: str,
        rejected_qty: float = 0,
    ) -> Tuple[bool, bool]:
        """
        自动检测 shortage 和 quality_issue 标记
        shortage: 实收 < 订单量（有订单量时）
        quality_issue: quality_status 为 conditional 或 reject，或有拒收数量
        """
        has_shortage = False
        has_quality_issue = False

        if ordered_qty is not None and received_qty < ordered_qty:
            has_shortage = True

        if quality_status in ("conditional", "reject") or rejected_qty > 0:
            has_quality_issue = True

        return has_shortage, has_quality_issue

    async def _auto_detect_issues(self, item: PurchaseReceivingItem) -> Tuple[bool, bool]:
        """对已存在的 item 对象执行自动检测（供外部调用）"""
        return self._auto_detect_issues_inline(
            ordered_qty=item.ordered_qty,
            received_qty=item.received_qty,
            quality_status=item.quality_status.value,
            rejected_qty=item.rejected_qty,
        )


# 模块级单例
receiving_inspection_service = ReceivingInspectionService()
