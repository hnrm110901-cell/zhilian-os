"""
门店间调拨服务
处理调拨申请创建、审批、发货、收货等完整流程
所有库存变动在同一 asyncpg 事务内保证原子性
"""

import uuid
from datetime import datetime, date
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db_session
from src.models.inter_store_transfer import (
    InterStoreTransferItem,
    InterStoreTransferRequest,
    TransferStatus,
)
from src.models.inventory import InventoryItem, InventoryTransaction, TransactionType

logger = structlog.get_logger()


class InterStoreTransferService:
    """门店间调拨服务"""

    async def create_transfer_request(
        self,
        from_store_id: str,
        to_store_id: str,
        brand_id: str,
        items: List[Dict[str, Any]],
        requester_id: str,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        创建调拨申请
        1. 校验 from/to 是同品牌门店（brand_id 一致，此处信任调用方传入同一 brand_id）
        2. 检查 from_store 库存充足
        3. 生成 transfer_no（IST-{date}-{seq:04d} 格式）
        4. 创建主记录 + 明细，状态 = pending
        """
        async with get_db_session() as session:
            # 校验：from ≠ to
            if str(from_store_id) == str(to_store_id):
                raise ValueError("调出门店和调入门店不能相同")

            if not items:
                raise ValueError("调拨明细不能为空")

            # 检查每个食材在 from_store 的库存是否充足
            insufficient = []
            for item in items:
                ingredient_id = str(item.get("ingredient_id", ""))
                requested_qty = float(item.get("requested_qty", 0))
                if requested_qty <= 0:
                    raise ValueError(f"食材 {item.get('ingredient_name')} 调拨数量必须大于 0")

                stmt = select(InventoryItem).where(
                    and_(
                        InventoryItem.store_id == str(from_store_id),
                        # InventoryItem.id 是 String(50)，用 ingredient_id 做模糊匹配
                        # 实际项目中可能有专门的 ingredient_inventory 表
                        InventoryItem.name == item.get("ingredient_name"),
                    )
                )
                result = await session.execute(stmt)
                inv = result.scalar_one_or_none()
                if inv is None or inv.current_quantity < requested_qty:
                    available = inv.current_quantity if inv else 0
                    insufficient.append(
                        {
                            "ingredient_name": item.get("ingredient_name"),
                            "requested": requested_qty,
                            "available": available,
                        }
                    )

            if insufficient:
                raise ValueError(
                    f"以下食材库存不足: {insufficient}"
                )

            # 生成调拨单号
            transfer_no = await self._generate_transfer_no(session)

            # 创建主记录
            transfer = InterStoreTransferRequest(
                id=uuid.uuid4(),
                transfer_no=transfer_no,
                from_store_id=uuid.UUID(str(from_store_id)),
                to_store_id=uuid.UUID(str(to_store_id)),
                brand_id=uuid.UUID(str(brand_id)),
                status=TransferStatus.PENDING,
                requested_by=uuid.UUID(str(requester_id)),
                notes=notes,
                created_at=datetime.utcnow(),
            )
            session.add(transfer)

            # 创建明细
            for item in items:
                detail = InterStoreTransferItem(
                    id=uuid.uuid4(),
                    transfer_id=transfer.id,
                    ingredient_id=uuid.UUID(str(item["ingredient_id"])),
                    ingredient_name=item["ingredient_name"],
                    unit=item["unit"],
                    requested_qty=float(item["requested_qty"]),
                    unit_cost_fen=item.get("unit_cost_fen"),
                )
                session.add(detail)

            await session.commit()
            await session.refresh(transfer)

            logger.info(
                "调拨申请已创建",
                transfer_no=transfer_no,
                from_store_id=str(from_store_id),
                to_store_id=str(to_store_id),
            )

            return {
                "transfer_id": str(transfer.id),
                "transfer_no": transfer.transfer_no,
                "status": transfer.status.value,
                "items_count": len(items),
            }

    async def approve_transfer(
        self,
        transfer_id: str,
        approver_id: str,
    ) -> Dict[str, Any]:
        """审批通过 - 状态变 approved"""
        async with get_db_session() as session:
            transfer = await self._get_transfer(session, transfer_id)

            if transfer.status != TransferStatus.PENDING:
                raise ValueError(
                    f"调拨单状态为 {transfer.status.value}，只有 pending 状态可审批"
                )

            transfer.status = TransferStatus.APPROVED
            transfer.approved_by = uuid.UUID(str(approver_id))
            transfer.approved_at = datetime.utcnow()

            await session.commit()

            logger.info("调拨申请已审批", transfer_no=transfer.transfer_no)

            return {
                "transfer_id": str(transfer.id),
                "transfer_no": transfer.transfer_no,
                "status": transfer.status.value,
                "approved_at": transfer.approved_at.isoformat(),
            }

    async def dispatch_transfer(
        self,
        transfer_id: str,
        actual_items: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        确认发货（可能与申请量不同）
        1. 记录实际发出量（dispatched_qty）
        2. 从 from_store 扣减库存（SELECT FOR UPDATE）
        3. 状态变 dispatched + dispatched_at
        """
        async with get_db_session() as session:
            transfer = await self._get_transfer(session, transfer_id)

            if transfer.status != TransferStatus.APPROVED:
                raise ValueError(
                    f"调拨单状态为 {transfer.status.value}，只有 approved 状态可发货"
                )

            # 建立 ingredient_name -> dispatched_qty 映射
            dispatch_map = {
                item["ingredient_name"]: float(item["dispatched_qty"])
                for item in actual_items
            }

            # 加载明细
            stmt = select(InterStoreTransferItem).where(
                InterStoreTransferItem.transfer_id == transfer.id
            )
            result = await session.execute(stmt)
            details = result.scalars().all()

            for detail in details:
                dispatched_qty = dispatch_map.get(detail.ingredient_name, 0.0)
                detail.dispatched_qty = dispatched_qty

                if dispatched_qty <= 0:
                    continue

                # 从 from_store 扣减库存（FOR UPDATE 避免并发超扣）
                inv_stmt = (
                    select(InventoryItem)
                    .where(
                        and_(
                            InventoryItem.store_id == str(transfer.from_store_id),
                            InventoryItem.name == detail.ingredient_name,
                        )
                    )
                    .with_for_update()
                )
                inv_result = await session.execute(inv_stmt)
                inv = inv_result.scalar_one_or_none()

                if inv and inv.current_quantity >= dispatched_qty:
                    inv.current_quantity -= dispatched_qty
                    # 记录库存流水
                    tx = InventoryTransaction(
                        id=uuid.uuid4(),
                        item_id=inv.id,
                        store_id=str(transfer.from_store_id),
                        transaction_type=TransactionType.TRANSFER.value,
                        quantity=-dispatched_qty,
                        notes=f"调拨发货 {transfer.transfer_no}",
                        created_at=datetime.utcnow(),
                    )
                    session.add(tx)
                elif inv:
                    raise ValueError(
                        f"发货时食材 {detail.ingredient_name} 库存不足: "
                        f"现有 {inv.current_quantity}，需发 {dispatched_qty}"
                    )

            transfer.status = TransferStatus.DISPATCHED
            transfer.dispatched_at = datetime.utcnow()

            await session.commit()

            logger.info("调拨已发货", transfer_no=transfer.transfer_no)

            return {
                "transfer_id": str(transfer.id),
                "transfer_no": transfer.transfer_no,
                "status": transfer.status.value,
                "dispatched_at": transfer.dispatched_at.isoformat(),
            }

    async def receive_transfer(
        self,
        transfer_id: str,
        received_items: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        确认收货 - 最核心方法（原子事务）
        1. 记录实际收到量（received_qty）
        2. 计算差异（qty_variance = received - dispatched）
        3. 增加 to_store 库存（实际收到量）
        4. 差异为负时，在 from_store 创建损耗记录
        5. 状态变 received（全部）或 partial（部分）
        所有库存变动在同一 asyncpg 事务内
        """
        async with get_db_session() as session:
            transfer = await self._get_transfer(session, transfer_id)

            if transfer.status != TransferStatus.DISPATCHED:
                raise ValueError(
                    f"调拨单状态为 {transfer.status.value}，只有 dispatched 状态可收货"
                )

            # 建立收货映射
            receive_map = {
                item["ingredient_name"]: {
                    "received_qty": float(item["received_qty"]),
                    "variance_reason": item.get("variance_reason"),
                }
                for item in received_items
            }

            # 加载明细
            stmt = select(InterStoreTransferItem).where(
                InterStoreTransferItem.transfer_id == transfer.id
            )
            result = await session.execute(stmt)
            details = result.scalars().all()

            has_partial = False

            for detail in details:
                info = receive_map.get(detail.ingredient_name)
                if not info:
                    continue

                received_qty = info["received_qty"]
                detail.received_qty = received_qty
                detail.qty_variance = received_qty - (detail.dispatched_qty or 0)
                detail.variance_reason = info.get("variance_reason")

                if detail.qty_variance < 0:
                    has_partial = True

                if received_qty <= 0:
                    continue

                # 增加 to_store 库存
                to_inv_stmt = (
                    select(InventoryItem)
                    .where(
                        and_(
                            InventoryItem.store_id == str(transfer.to_store_id),
                            InventoryItem.name == detail.ingredient_name,
                        )
                    )
                    .with_for_update()
                )
                to_inv_result = await session.execute(to_inv_stmt)
                to_inv = to_inv_result.scalar_one_or_none()

                if to_inv:
                    to_inv.current_quantity += received_qty
                    # 入库流水
                    tx_in = InventoryTransaction(
                        id=uuid.uuid4(),
                        item_id=to_inv.id,
                        store_id=str(transfer.to_store_id),
                        transaction_type=TransactionType.TRANSFER.value,
                        quantity=received_qty,
                        notes=f"调拨收货 {transfer.transfer_no}",
                        created_at=datetime.utcnow(),
                    )
                    session.add(tx_in)

                # 差异为负时在 from_store 创建损耗记录
                if detail.qty_variance < 0:
                    loss_qty = abs(detail.qty_variance)
                    from_inv_stmt = (
                        select(InventoryItem)
                        .where(
                            and_(
                                InventoryItem.store_id == str(transfer.from_store_id),
                                InventoryItem.name == detail.ingredient_name,
                            )
                        )
                        .with_for_update()
                    )
                    from_inv_result = await session.execute(from_inv_stmt)
                    from_inv = from_inv_result.scalar_one_or_none()

                    if from_inv:
                        # 损耗流水（来源：调拨运输差异）
                        tx_loss = InventoryTransaction(
                            id=uuid.uuid4(),
                            item_id=from_inv.id,
                            store_id=str(transfer.from_store_id),
                            transaction_type=TransactionType.WASTE.value,
                            quantity=-loss_qty,
                            notes=(
                                f"调拨运输损耗 {transfer.transfer_no}: "
                                f"{detail.variance_reason or '数量差异'}"
                            ),
                            created_at=datetime.utcnow(),
                        )
                        session.add(tx_loss)

            # 判断是全收还是部分收货
            transfer.status = (
                TransferStatus.PARTIAL if has_partial else TransferStatus.RECEIVED
            )
            transfer.received_at = datetime.utcnow()

            await session.commit()

            logger.info(
                "调拨已收货",
                transfer_no=transfer.transfer_no,
                status=transfer.status.value,
            )

            return {
                "transfer_id": str(transfer.id),
                "transfer_no": transfer.transfer_no,
                "status": transfer.status.value,
                "received_at": transfer.received_at.isoformat(),
                "has_partial": has_partial,
            }

    async def get_pending_transfers(
        self,
        store_id: str,
        direction: str = "inbound",
    ) -> List[Dict[str, Any]]:
        """
        获取待处理调拨单
        inbound  = 我是调入方，需要收货的
        outbound = 我是调出方，需要发货的
        """
        async with get_db_session() as session:
            if direction == "inbound":
                stmt = select(InterStoreTransferRequest).where(
                    and_(
                        InterStoreTransferRequest.to_store_id == uuid.UUID(str(store_id)),
                        InterStoreTransferRequest.status == TransferStatus.DISPATCHED,
                    )
                )
            else:
                stmt = select(InterStoreTransferRequest).where(
                    and_(
                        InterStoreTransferRequest.from_store_id == uuid.UUID(str(store_id)),
                        InterStoreTransferRequest.status == TransferStatus.APPROVED,
                    )
                )

            stmt = stmt.order_by(desc(InterStoreTransferRequest.created_at))
            result = await session.execute(stmt)
            transfers = result.scalars().all()

            return [self._format_transfer(t) for t in transfers]

    async def get_transfer_history(
        self,
        store_id: str,
        days: int = 30,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """调拨历史（分页）"""
        async with get_db_session() as session:
            from datetime import timedelta

            since = datetime.utcnow() - timedelta(days=days)
            store_uuid = uuid.UUID(str(store_id))

            base_where = and_(
                or_(
                    InterStoreTransferRequest.from_store_id == store_uuid,
                    InterStoreTransferRequest.to_store_id == store_uuid,
                ),
                InterStoreTransferRequest.created_at >= since,
            )

            # 总数
            count_stmt = select(func.count()).select_from(
                InterStoreTransferRequest
            ).where(base_where)
            total = (await session.execute(count_stmt)).scalar_one()

            # 分页数据
            offset = (page - 1) * page_size
            stmt = (
                select(InterStoreTransferRequest)
                .where(base_where)
                .order_by(desc(InterStoreTransferRequest.created_at))
                .limit(page_size)
                .offset(offset)
            )
            result = await session.execute(stmt)
            transfers = result.scalars().all()

            return {
                "total": total,
                "page": page,
                "page_size": page_size,
                "items": [self._format_transfer(t) for t in transfers],
            }

    # ------------------------------------------------------------------ #
    #  私有方法
    # ------------------------------------------------------------------ #

    async def _get_transfer(
        self,
        session: AsyncSession,
        transfer_id: str,
    ) -> InterStoreTransferRequest:
        """按 ID 获取调拨单，不存在则抛出 ValueError"""
        stmt = select(InterStoreTransferRequest).where(
            InterStoreTransferRequest.id == uuid.UUID(str(transfer_id))
        )
        result = await session.execute(stmt)
        transfer = result.scalar_one_or_none()
        if transfer is None:
            raise ValueError(f"调拨单不存在: {transfer_id}")
        return transfer

    async def _generate_transfer_no(self, session: AsyncSession) -> str:
        """生成唯一调拨单号 IST-YYYYMMDD-NNNN"""
        today_str = date.today().strftime("%Y%m%d")
        prefix = f"IST-{today_str}-"

        stmt = (
            select(InterStoreTransferRequest.transfer_no)
            .where(InterStoreTransferRequest.transfer_no.like(f"{prefix}%"))
            .order_by(desc(InterStoreTransferRequest.transfer_no))
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
    def _format_transfer(t: InterStoreTransferRequest) -> Dict[str, Any]:
        """格式化调拨单为字典"""
        return {
            "transfer_id": str(t.id),
            "transfer_no": t.transfer_no,
            "from_store_id": str(t.from_store_id),
            "to_store_id": str(t.to_store_id),
            "brand_id": str(t.brand_id),
            "status": t.status.value,
            "requested_by": str(t.requested_by),
            "approved_by": str(t.approved_by) if t.approved_by else None,
            "approved_at": t.approved_at.isoformat() if t.approved_at else None,
            "dispatched_at": t.dispatched_at.isoformat() if t.dispatched_at else None,
            "received_at": t.received_at.isoformat() if t.received_at else None,
            "notes": t.notes,
            "created_at": t.created_at.isoformat(),
        }


# 模块级单例（无状态，可共享）
inter_store_transfer_service = InterStoreTransferService()
