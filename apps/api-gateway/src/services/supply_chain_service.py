"""
供应链服务
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.exceptions import NotFoundError
from src.models.supply_chain import PurchaseOrder, Supplier

logger = structlog.get_logger()


class SupplyChainService:
    """供应商与采购订单管理服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Suppliers ──────────────────────────────────────────────────────────────

    async def get_suppliers(
        self,
        status: Optional[str] = None,
        category: Optional[str] = None,
    ) -> Dict[str, Any]:
        """获取供应商列表。"""
        stmt = select(Supplier)
        if status:
            stmt = stmt.where(Supplier.status == status)
        if category:
            stmt = stmt.where(Supplier.category == category)

        result = await self.db.execute(stmt)
        suppliers = result.scalars().all()

        # 获取总数（复用同一查询结果）
        from sqlalchemy import func
        from sqlalchemy import select as sa_select

        count_stmt = sa_select(func.count()).select_from(Supplier)
        if status:
            count_stmt = count_stmt.where(Supplier.status == status)
        if category:
            count_stmt = count_stmt.where(Supplier.category == category)
        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar() or 0

        return {
            "suppliers": [self._supplier_to_dict(s) for s in suppliers],
            "total": total,
        }

    async def create_supplier(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建供应商。"""
        supplier = Supplier(
            name=data.get("name", ""),
            code=data.get("code"),
            category=data.get("category", "food"),
            contact_person=data.get("contact_person"),
            phone=data.get("phone"),
            email=data.get("email"),
            address=data.get("address"),
            status=data.get("status", "active"),
            rating=data.get("rating", 5.0),
            payment_terms=data.get("payment_terms", "net30"),
            delivery_time=data.get("delivery_time", 3),
        )
        self.db.add(supplier)
        await self.db.commit()
        await self.db.refresh(supplier)
        return self._supplier_to_dict(supplier)

    # ── Purchase Orders ────────────────────────────────────────────────────────

    async def get_purchase_orders(
        self,
        status: Optional[str] = None,
        supplier_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """获取采购订单列表。"""
        stmt = select(PurchaseOrder)
        if status:
            stmt = stmt.where(PurchaseOrder.status == status)
        if supplier_id:
            stmt = stmt.where(PurchaseOrder.supplier_id == supplier_id)

        result = await self.db.execute(stmt)
        orders = result.scalars().all()

        return {"orders": [self._order_to_dict(o) for o in orders]}

    async def create_purchase_order(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建采购订单。"""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        order = PurchaseOrder(
            order_number=f"PO-{timestamp}",
            supplier_id=data.get("supplier_id", ""),
            store_id=data.get("store_id", ""),
            total_amount=data.get("total_amount", 0),
            items=data.get("items", []),
            expected_delivery=data.get("expected_delivery"),
            notes=data.get("notes"),
            status="pending",
        )
        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)
        return self._order_to_dict(order)

    async def update_order_status(
        self,
        order_id: str,
        status: str,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """更新采购订单状态。

        Raises:
            NotFoundError: 订单不存在
        """
        stmt = select(PurchaseOrder).where(PurchaseOrder.id == order_id)
        result = await self.db.execute(stmt)
        order = result.scalar_one_or_none()

        if order is None:
            raise NotFoundError(f"PurchaseOrder not found: {order_id}")

        order.status = status
        if notes is not None:
            order.notes = notes
        order.updated_at = datetime.utcnow()

        await self.db.commit()
        return self._order_to_dict(order)

    async def get_supplier_performance(
        self,
        supplier_id: str,
        days: int = 30,
    ) -> Dict[str, Any]:
        """获取供应商绩效统计。"""
        stmt = select(PurchaseOrder).where(PurchaseOrder.supplier_id == supplier_id)
        result = await self.db.execute(stmt)
        orders = result.scalars().all()

        if not orders:
            return {
                "supplier_id": supplier_id,
                "total_orders": 0,
                "on_time_delivery_rate": 0,
                "total_amount": 0,
            }

        total = len(orders)
        on_time = sum(
            1 for o in orders if o.actual_delivery and o.expected_delivery and o.actual_delivery <= o.expected_delivery
        )
        total_amount = sum(o.total_amount or 0 for o in orders)

        return {
            "supplier_id": supplier_id,
            "total_orders": total,
            "on_time_delivery_rate": round(on_time / total, 2) if total else 0,
            "total_amount": total_amount,
        }

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _supplier_to_dict(self, s: Supplier) -> Dict[str, Any]:
        return {
            "id": str(s.id),
            "name": s.name,
            "code": s.code,
            "category": s.category,
            "contact_person": s.contact_person,
            "phone": s.phone,
            "email": s.email,
            "address": s.address,
            "status": s.status,
            "rating": s.rating,
            "payment_terms": s.payment_terms,
            "delivery_time": s.delivery_time,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }

    def _order_to_dict(self, o: PurchaseOrder) -> Dict[str, Any]:
        return {
            "id": str(o.id),
            "order_number": o.order_number,
            "supplier_id": str(o.supplier_id),
            "store_id": o.store_id,
            "status": o.status,
            "total_amount": o.total_amount,
            "items": o.items or [],
            "expected_delivery": o.expected_delivery.isoformat() if o.expected_delivery else None,
            "created_at": o.created_at.isoformat() if o.created_at else None,
        }


def get_supply_chain_service(db: AsyncSession) -> SupplyChainService:
    return SupplyChainService(db)
