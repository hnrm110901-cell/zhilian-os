"""
Supply Chain Integration Service
供应链整合服务 - 数据库持久化版本
"""

import os
import uuid
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
import structlog

from ..models.supply_chain import Supplier, PurchaseOrder

logger = structlog.get_logger()


class SupplyChainIntegration:
    """
    供应链整合服务（数据库持久化）

    功能：
    1. 供应商管理（CRUD）
    2. 询价与报价比较
    3. 采购订单管理
    4. 供应链金融选项
    5. 供应商绩效分析
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ==================== 供应商管理 ====================

    async def register_supplier(
        self,
        name: str,
        category: str,
        contact_person: str,
        phone: str,
        payment_terms: str = "net30",
        delivery_time: int = 3,
        email: Optional[str] = None,
        address: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Supplier:
        """注册新供应商"""
        code = f"SUP{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        supplier = Supplier(
            id=str(uuid.uuid4()),
            name=name,
            code=code,
            category=category,
            contact_person=contact_person,
            phone=phone,
            email=email,
            address=address,
            payment_terms=payment_terms,
            delivery_time=delivery_time,
            notes=notes,
            status="active",
            rating=5.0,
        )
        self.db.add(supplier)
        await self.db.commit()
        await self.db.refresh(supplier)
        logger.info("供应商注册成功", supplier_id=supplier.id, name=name)
        return supplier

    async def get_suppliers(self, category: Optional[str] = None, status: str = "active") -> List[Supplier]:
        """获取供应商列表"""
        conditions = [Supplier.status == status]
        if category:
            conditions.append(Supplier.category == category)
        result = await self.db.execute(select(Supplier).where(and_(*conditions)))
        return list(result.scalars().all())

    async def get_supplier(self, supplier_id: str) -> Optional[Supplier]:
        """获取单个供应商"""
        result = await self.db.execute(select(Supplier).where(Supplier.id == supplier_id))
        return result.scalar_one_or_none()

    # ==================== 询价与报价 ====================

    async def request_quotes(
        self,
        material_id: str,
        quantity: float,
        required_date: datetime,
        supplier_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """向供应商询价，返回模拟报价列表"""
        if supplier_ids:
            result = await self.db.execute(
                select(Supplier).where(Supplier.id.in_(supplier_ids), Supplier.status == "active")
            )
        else:
            result = await self.db.execute(
                select(Supplier).where(Supplier.status == "active")
            )
        suppliers = list(result.scalars().all())

        base_price = float(os.getenv(f"SUPPLY_PRICE_{material_id.upper()}", os.getenv("SUPPLY_CHAIN_MOCK_BASE_PRICE", "10.0")))
        quotes = []
        for supplier in suppliers:
            rating_factor = 0.9 + (supplier.rating / 5.0) * 0.2
            unit_price = round(base_price * rating_factor, 2)
            total_price = round(unit_price * quantity, 2)
            valid_days = int(os.getenv("SUPPLY_CHAIN_QUOTE_VALID_DAYS", "3"))
            quotes.append({
                "quote_id": f"quote_{supplier.id}_{material_id}_{int(datetime.utcnow().timestamp())}",
                "supplier_id": supplier.id,
                "supplier_name": supplier.name,
                "material_id": material_id,
                "quantity": quantity,
                "unit_price": unit_price,
                "total_price": total_price,
                "delivery_date": required_date.isoformat(),
                "valid_until": (datetime.utcnow() + timedelta(days=valid_days)).isoformat(),
                "delivery_time_days": supplier.delivery_time,
                "supplier_rating": supplier.rating,
            })
        return quotes

    def compare_quotes(self, quotes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """比较报价，返回最优方案"""
        if not quotes:
            return {"error": "No quotes provided"}
        sorted_quotes = sorted(quotes, key=lambda q: q["total_price"])
        best = sorted_quotes[0]
        for q in sorted_quotes:
            q["is_best"] = q["quote_id"] == best["quote_id"]
        savings = sorted_quotes[-1]["total_price"] - best["total_price"] if len(sorted_quotes) > 1 else 0
        return {
            "best_quote": {
                "quote_id": best["quote_id"],
                "supplier_name": best["supplier_name"],
                "total_price": best["total_price"],
                "savings": round(savings, 2),
            },
            "comparisons": sorted_quotes,
            "total_quotes": len(sorted_quotes),
        }

    # ==================== 采购订单 ====================

    async def create_purchase_order(
        self,
        store_id: str,
        supplier_id: str,
        items: List[Dict[str, Any]],
        expected_delivery: datetime,
        created_by: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> PurchaseOrder:
        """创建采购订单"""
        total_amount = int(sum(item.get("total_price", 0) * 100 for item in items))
        order_number = f"PO{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        order = PurchaseOrder(
            id=str(uuid.uuid4()),
            order_number=order_number,
            supplier_id=supplier_id,
            store_id=store_id,
            items=items,
            total_amount=total_amount,
            expected_delivery=expected_delivery,
            status="pending",
            created_by=created_by,
            notes=notes,
        )
        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)
        logger.info("采购订单创建成功", order_id=order.id, order_number=order_number)
        return order

    async def get_purchase_orders(
        self,
        store_id: Optional[str] = None,
        supplier_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[PurchaseOrder]:
        """查询采购订单"""
        conditions = []
        if store_id:
            conditions.append(PurchaseOrder.store_id == store_id)
        if supplier_id:
            conditions.append(PurchaseOrder.supplier_id == supplier_id)
        if status:
            conditions.append(PurchaseOrder.status == status)
        stmt = select(PurchaseOrder)
        if conditions:
            stmt = stmt.where(and_(*conditions))
        result = await self.db.execute(stmt.order_by(PurchaseOrder.created_at.desc()))
        return list(result.scalars().all())

    async def update_order_status(self, order_id: str, status: str, approved_by: Optional[str] = None) -> PurchaseOrder:
        """更新订单状态"""
        result = await self.db.execute(select(PurchaseOrder).where(PurchaseOrder.id == order_id))
        order = result.scalar_one_or_none()
        if not order:
            raise ValueError(f"采购订单不存在: {order_id}")
        order.status = status
        if approved_by:
            order.approved_by = approved_by
            order.approved_at = datetime.utcnow()
        if status == "delivered":
            order.actual_delivery = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(order)
        return order

    # ==================== 供应链金融 ====================

    async def get_finance_options(self, order_id: str) -> Dict[str, Any]:
        """获取供应链金融选项"""
        result = await self.db.execute(select(PurchaseOrder).where(PurchaseOrder.id == order_id))
        order = result.scalar_one_or_none()
        if not order:
            raise ValueError(f"采购订单不存在: {order_id}")

        sup_result = await self.db.execute(select(Supplier).where(Supplier.id == order.supplier_id))
        supplier = sup_result.scalar_one_or_none()

        amount = order.total_amount / 100  # 分转元
        early_discount = float(os.getenv("SUPPLY_CHAIN_EARLY_PAYMENT_DISCOUNT", "0.02"))
        extended_interest = float(os.getenv("SUPPLY_CHAIN_EXTENDED_INTEREST", "0.05"))

        return {
            "order_id": order_id,
            "order_amount": amount,
            "finance_options": [
                {
                    "type": "early_payment_discount",
                    "description": f"提前付款享受{int(early_discount*100)}%折扣",
                    "amount": round(amount * (1 - early_discount), 2),
                    "savings": round(amount * early_discount, 2),
                    "payment_terms": "立即付款",
                },
                {
                    "type": "standard_terms",
                    "description": f"标准付款条款: {supplier.payment_terms if supplier else 'net30'}",
                    "amount": amount,
                    "savings": 0,
                    "payment_terms": supplier.payment_terms if supplier else "net30",
                },
                {
                    "type": "extended_terms",
                    "description": f"延长付款期限至60天（需支付{int(extended_interest*100)}%利息）",
                    "amount": round(amount * (1 + extended_interest), 2),
                    "savings": round(-amount * extended_interest, 2),
                    "payment_terms": "Net 60",
                },
            ],
            "recommended": "early_payment_discount",
        }

    # ==================== 供应商绩效 ====================

    async def get_supplier_performance(
        self,
        supplier_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> Dict[str, Any]:
        """获取供应商绩效指标"""
        sup_result = await self.db.execute(select(Supplier).where(Supplier.id == supplier_id))
        supplier = sup_result.scalar_one_or_none()
        if not supplier:
            raise ValueError(f"供应商不存在: {supplier_id}")

        result = await self.db.execute(
            select(PurchaseOrder).where(
                and_(
                    PurchaseOrder.supplier_id == supplier_id,
                    PurchaseOrder.created_at >= start_date,
                    PurchaseOrder.created_at <= end_date,
                )
            )
        )
        orders = list(result.scalars().all())
        total_orders = len(orders)
        total_amount = sum(o.total_amount for o in orders) / 100
        delivered = [o for o in orders if o.status == "delivered"]
        on_time_rate = len(delivered) / total_orders if total_orders > 0 else 0

        return {
            "supplier_id": supplier_id,
            "supplier_name": supplier.name,
            "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "metrics": {
                "total_orders": total_orders,
                "total_amount": total_amount,
                "on_time_delivery_rate": round(on_time_rate, 3),
                "average_order_value": round(total_amount / total_orders, 2) if total_orders > 0 else 0,
                "supplier_rating": supplier.rating,
            },
        }

