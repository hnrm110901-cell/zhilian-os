"""
供应商B2B采购单服务
创建/查询/提交/收货/取消采购单，统计概览
"""

import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.models.supplier_b2b import B2BPurchaseItem, B2BPurchaseOrder


class SupplierB2BService:
    """供应商B2B采购单业务逻辑"""

    # 合法状态转换
    _STATUS_TRANSITIONS = {
        "draft": ["submitted", "cancelled"],
        "submitted": ["confirmed", "cancelled"],
        "confirmed": ["shipping", "cancelled"],
        "shipping": ["received"],
        "received": ["completed"],
        "completed": [],
        "cancelled": [],
    }

    async def _generate_order_number(self, db: AsyncSession) -> str:
        """生成采购单号：PO-YYYYMMDD-XXXX"""
        today = datetime.utcnow().strftime("%Y%m%d")
        prefix = f"PO-{today}-"

        # 查询今天最大序号
        result = await db.execute(
            select(func.max(B2BPurchaseOrder.order_number)).where(B2BPurchaseOrder.order_number.like(f"{prefix}%"))
        )
        max_number = result.scalar_one_or_none()

        if max_number:
            seq = int(max_number.split("-")[-1]) + 1
        else:
            seq = 1

        return f"{prefix}{seq:04d}"

    async def create_order(self, db: AsyncSession, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建采购单（含明细）"""
        order_number = await self._generate_order_number(db)

        # 计算总金额
        items_data = data.get("items", [])
        total_amount_fen = 0
        order_items = []

        for item_data in items_data:
            qty = item_data.get("quantity", 0)
            unit_price = item_data.get("unit_price_fen", 0)
            amount = int(float(qty) * unit_price)
            total_amount_fen += amount

            order_items.append(
                B2BPurchaseItem(
                    id=uuid.uuid4(),
                    ingredient_name=item_data["ingredient_name"],
                    ingredient_id=item_data.get("ingredient_id"),
                    quantity=qty,
                    unit=item_data.get("unit", "kg"),
                    unit_price_fen=unit_price,
                    amount_fen=amount,
                )
            )

        # 解析预期交货日期
        expected_date = data.get("expected_delivery_date")
        if isinstance(expected_date, str):
            expected_date = date.fromisoformat(expected_date)

        order = B2BPurchaseOrder(
            id=uuid.uuid4(),
            brand_id=data["brand_id"],
            store_id=data.get("store_id", ""),
            supplier_id=data["supplier_id"],
            supplier_name=data["supplier_name"],
            order_number=order_number,
            status="draft",
            total_amount_fen=total_amount_fen,
            expected_delivery_date=expected_date,
            notes=data.get("notes"),
            items=order_items,
        )

        db.add(order)
        await db.flush()
        await db.refresh(order, attribute_names=["items"])

        return order.to_dict()

    async def list_orders(
        self,
        db: AsyncSession,
        brand_id: str,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
        supplier_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """分页查询采购单列表"""
        conditions = [B2BPurchaseOrder.brand_id == brand_id]
        if status:
            conditions.append(B2BPurchaseOrder.status == status)
        if supplier_id:
            conditions.append(B2BPurchaseOrder.supplier_id == supplier_id)

        where_clause = and_(*conditions)

        # 总数
        count_result = await db.execute(select(func.count(B2BPurchaseOrder.id)).where(where_clause))
        total = count_result.scalar_one()

        # 分页查询
        offset = (page - 1) * page_size
        result = await db.execute(
            select(B2BPurchaseOrder)
            .options(selectinload(B2BPurchaseOrder.items))
            .where(where_clause)
            .order_by(B2BPurchaseOrder.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        orders = result.scalars().all()

        return {
            "items": [o.to_dict() for o in orders],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def get_order(self, db: AsyncSession, order_id: str) -> Optional[Dict[str, Any]]:
        """获取采购单详情（含明细）"""
        result = await db.execute(
            select(B2BPurchaseOrder).options(selectinload(B2BPurchaseOrder.items)).where(B2BPurchaseOrder.id == order_id)
        )
        order = result.scalar_one_or_none()
        if not order:
            return None
        return order.to_dict()

    async def update_order_status(self, db: AsyncSession, order_id: str, new_status: str) -> Dict[str, Any]:
        """更新采购单状态（含状态机校验）"""
        result = await db.execute(
            select(B2BPurchaseOrder).options(selectinload(B2BPurchaseOrder.items)).where(B2BPurchaseOrder.id == order_id)
        )
        order = result.scalar_one_or_none()
        if not order:
            raise ValueError("采购单不存在")

        allowed = self._STATUS_TRANSITIONS.get(order.status, [])
        if new_status not in allowed:
            raise ValueError(f"无法从 {order.status} 转换到 {new_status}")

        order.status = new_status
        now = datetime.utcnow()

        if new_status == "submitted":
            order.submitted_at = now
        elif new_status == "confirmed":
            order.confirmed_at = now
        elif new_status == "received":
            order.received_at = now
            order.actual_delivery_date = now.date()

        await db.flush()
        await db.refresh(order, attribute_names=["items"])
        return order.to_dict()

    async def submit_order(self, db: AsyncSession, order_id: str) -> Dict[str, Any]:
        """提交采购单给供应商"""
        return await self.update_order_status(db, order_id, "submitted")

    async def receive_order(self, db: AsyncSession, order_id: str, received_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """收货：更新各明细的收货数量和质量状态"""
        result = await db.execute(
            select(B2BPurchaseOrder).options(selectinload(B2BPurchaseOrder.items)).where(B2BPurchaseOrder.id == order_id)
        )
        order = result.scalar_one_or_none()
        if not order:
            raise ValueError("采购单不存在")

        if order.status not in ("shipping", "confirmed"):
            raise ValueError(f"当前状态 {order.status} 不允许收货")

        # 按 item_id 建立索引
        items_map = {str(item.id): item for item in order.items}

        for ri in received_items:
            item = items_map.get(ri.get("item_id"))
            if item:
                item.received_quantity = ri.get("received_quantity", item.quantity)
                item.quality_status = ri.get("quality_status", "accepted")

        order.status = "received"
        order.received_at = datetime.utcnow()
        order.actual_delivery_date = datetime.utcnow().date()

        await db.flush()
        await db.refresh(order, attribute_names=["items"])
        return order.to_dict()

    async def cancel_order(self, db: AsyncSession, order_id: str, reason: Optional[str] = None) -> Dict[str, Any]:
        """取消采购单"""
        result = await db.execute(
            select(B2BPurchaseOrder).options(selectinload(B2BPurchaseOrder.items)).where(B2BPurchaseOrder.id == order_id)
        )
        order = result.scalar_one_or_none()
        if not order:
            raise ValueError("采购单不存在")

        allowed = self._STATUS_TRANSITIONS.get(order.status, [])
        if "cancelled" not in allowed:
            raise ValueError(f"当前状态 {order.status} 不允许取消")

        order.status = "cancelled"
        if reason:
            order.notes = f"{order.notes or ''}\n取消原因: {reason}".strip()

        await db.flush()
        await db.refresh(order, attribute_names=["items"])
        return order.to_dict()

    async def get_stats(self, db: AsyncSession, brand_id: str) -> Dict[str, Any]:
        """统计概览：各状态数量 + 本月采购额"""
        # 各状态数量
        status_result = await db.execute(
            select(
                B2BPurchaseOrder.status,
                func.count(B2BPurchaseOrder.id).label("count"),
            )
            .where(B2BPurchaseOrder.brand_id == brand_id)
            .group_by(B2BPurchaseOrder.status)
        )
        status_counts = {row.status: row.count for row in status_result}

        # 本月采购额（已完成/已收货）
        now = datetime.utcnow()
        month_result = await db.execute(
            select(
                func.coalesce(func.sum(B2BPurchaseOrder.total_amount_fen), 0),
                func.count(B2BPurchaseOrder.id),
            ).where(
                and_(
                    B2BPurchaseOrder.brand_id == brand_id,
                    B2BPurchaseOrder.status.in_(["received", "completed"]),
                    extract("year", B2BPurchaseOrder.created_at) == now.year,
                    extract("month", B2BPurchaseOrder.created_at) == now.month,
                )
            )
        )
        row = month_result.one()
        monthly_spend_fen = row[0]
        monthly_completed = row[1]

        return {
            "draft_count": status_counts.get("draft", 0),
            "submitted_count": status_counts.get("submitted", 0),
            "confirmed_count": status_counts.get("confirmed", 0),
            "shipping_count": status_counts.get("shipping", 0),
            "received_count": status_counts.get("received", 0),
            "completed_count": status_counts.get("completed", 0),
            "cancelled_count": status_counts.get("cancelled", 0),
            "pending_count": status_counts.get("submitted", 0)
            + status_counts.get("confirmed", 0)
            + status_counts.get("shipping", 0),
            "monthly_spend_fen": int(monthly_spend_fen),
            "monthly_completed": monthly_completed,
        }


# 单例
supplier_b2b_service = SupplierB2BService()
