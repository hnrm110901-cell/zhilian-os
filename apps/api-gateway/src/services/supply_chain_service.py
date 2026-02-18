"""
供应链服务
管理供应商、采购订单、库存补货
"""
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func

from src.models import Supplier, PurchaseOrder, InventoryItem
from src.core.exceptions import NotFoundError, ValidationError

logger = structlog.get_logger()


class SupplyChainService:
    """供应链服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_suppliers(
        self,
        skip: int = 0,
        limit: int = 100,
        status: Optional[str] = None,
        category: Optional[str] = None,
    ) -> Dict[str, Any]:
        """获取供应商列表"""
        query = select(Supplier)

        if status:
            query = query.where(Supplier.status == status)
        if category:
            query = query.where(Supplier.category == category)

        query = query.offset(skip).limit(limit)
        result = await self.db.execute(query)
        suppliers = result.scalars().all()

        # 获取总数
        count_query = select(func.count(Supplier.id))
        if status:
            count_query = count_query.where(Supplier.status == status)
        if category:
            count_query = count_query.where(Supplier.category == category)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar()

        return {
            "suppliers": [
                {
                    "id": s.id,
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
                for s in suppliers
            ],
            "total": total,
            "skip": skip,
            "limit": limit,
        }

    async def create_supplier(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建供应商"""
        supplier = Supplier(
            name=data["name"],
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

        logger.info("supplier_created", supplier_id=supplier.id, name=supplier.name)

        return {
            "id": supplier.id,
            "name": supplier.name,
            "code": supplier.code,
            "status": supplier.status,
        }

    async def get_purchase_orders(
        self,
        skip: int = 0,
        limit: int = 100,
        status: Optional[str] = None,
        supplier_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """获取采购订单列表"""
        query = select(PurchaseOrder)

        if status:
            query = query.where(PurchaseOrder.status == status)
        if supplier_id:
            query = query.where(PurchaseOrder.supplier_id == supplier_id)

        query = query.order_by(PurchaseOrder.created_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        orders = result.scalars().all()

        return {
            "orders": [
                {
                    "id": o.id,
                    "order_number": o.order_number,
                    "supplier_id": o.supplier_id,
                    "store_id": o.store_id,
                    "status": o.status,
                    "total_amount": o.total_amount,
                    "items_count": len(o.items) if o.items else 0,
                    "expected_delivery": o.expected_delivery.isoformat() if o.expected_delivery else None,
                    "created_at": o.created_at.isoformat() if o.created_at else None,
                }
                for o in orders
            ],
            "total": len(orders),
        }

    async def create_purchase_order(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建采购订单"""
        order = PurchaseOrder(
            order_number=data.get("order_number", f"PO-{datetime.now().strftime('%Y%m%d%H%M%S')}"),
            supplier_id=data["supplier_id"],
            store_id=data["store_id"],
            status=data.get("status", "pending"),
            total_amount=data.get("total_amount", 0),
            expected_delivery=data.get("expected_delivery"),
            notes=data.get("notes"),
        )

        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)

        logger.info("purchase_order_created", order_id=order.id, order_number=order.order_number)

        return {
            "id": order.id,
            "order_number": order.order_number,
            "status": order.status,
        }

    async def update_order_status(
        self, order_id: str, status: str, notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """更新采购订单状态"""
        query = select(PurchaseOrder).where(PurchaseOrder.id == order_id)
        result = await self.db.execute(query)
        order = result.scalar_one_or_none()

        if not order:
            raise NotFoundError(f"Purchase order {order_id} not found")

        order.status = status
        if notes:
            order.notes = notes
        order.updated_at = datetime.utcnow()

        await self.db.commit()

        logger.info("order_status_updated", order_id=order_id, status=status)

        return {
            "id": order.id,
            "order_number": order.order_number,
            "status": order.status,
        }

    async def get_replenishment_suggestions(
        self, store_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """获取补货建议"""
        # 查询库存低于安全库存的商品
        query = select(InventoryItem).where(
            InventoryItem.quantity <= InventoryItem.reorder_point
        )

        if store_id:
            query = query.where(InventoryItem.store_id == store_id)

        result = await self.db.execute(query)
        items = result.scalars().all()

        suggestions = []
        for item in items:
            # 计算建议采购量
            suggested_quantity = item.reorder_quantity or (item.reorder_point * 2 - item.quantity)

            suggestions.append({
                "item_id": item.id,
                "item_name": item.name,
                "current_quantity": item.quantity,
                "reorder_point": item.reorder_point,
                "suggested_quantity": suggested_quantity,
                "unit": item.unit,
                "supplier_id": item.supplier_id,
                "estimated_cost": item.unit_cost * suggested_quantity if item.unit_cost else 0,
                "urgency": "high" if item.quantity < item.reorder_point * 0.5 else "medium",
            })

        # 按紧急程度排序
        suggestions.sort(key=lambda x: (x["urgency"] == "high", -x["current_quantity"]), reverse=True)

        return suggestions

    async def get_supplier_performance(
        self, supplier_id: str, days: int = 30
    ) -> Dict[str, Any]:
        """获取供应商绩效"""
        start_date = datetime.utcnow() - timedelta(days=days)

        # 查询该供应商的订单
        query = select(PurchaseOrder).where(
            and_(
                PurchaseOrder.supplier_id == supplier_id,
                PurchaseOrder.created_at >= start_date,
            )
        )
        result = await self.db.execute(query)
        orders = result.scalars().all()

        if not orders:
            return {
                "supplier_id": supplier_id,
                "period_days": days,
                "total_orders": 0,
                "on_time_delivery_rate": 0,
                "average_delivery_time": 0,
                "total_amount": 0,
            }

        # 计算指标
        total_orders = len(orders)
        completed_orders = [o for o in orders if o.status == "completed"]
        on_time_orders = [
            o for o in completed_orders
            if o.actual_delivery and o.expected_delivery and o.actual_delivery <= o.expected_delivery
        ]

        on_time_rate = (len(on_time_orders) / len(completed_orders) * 100) if completed_orders else 0

        # 计算平均交货时间
        delivery_times = [
            (o.actual_delivery - o.created_at).days
            for o in completed_orders
            if o.actual_delivery
        ]
        avg_delivery_time = sum(delivery_times) / len(delivery_times) if delivery_times else 0

        total_amount = sum(o.total_amount for o in orders if o.total_amount)

        return {
            "supplier_id": supplier_id,
            "period_days": days,
            "total_orders": total_orders,
            "completed_orders": len(completed_orders),
            "on_time_delivery_rate": round(on_time_rate, 2),
            "average_delivery_time": round(avg_delivery_time, 1),
            "total_amount": total_amount,
        }


# 全局服务实例
supply_chain_service: Optional[SupplyChainService] = None


def get_supply_chain_service(db: AsyncSession) -> SupplyChainService:
    """获取供应链服务实例"""
    return SupplyChainService(db)
