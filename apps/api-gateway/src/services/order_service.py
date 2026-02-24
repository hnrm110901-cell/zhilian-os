"""
Order Service - 订单数据库服务
处理订单的数据库操作
"""
import os
import structlog
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload
import uuid

from src.core.database import get_db_session
from src.models.order import Order, OrderItem, OrderStatus

logger = structlog.get_logger()


class OrderService:
    """订单服务类"""

    def __init__(self, store_id: str = "STORE001"):
        """
        初始化订单服务

        Args:
            store_id: 门店ID
        """
        self.store_id = store_id
        logger.info("OrderService初始化", store_id=store_id)

    async def create_order(
        self,
        table_number: str,
        items: List[Dict[str, Any]],
        customer_name: Optional[str] = None,
        customer_phone: Optional[str] = None,
        notes: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        创建订单

        Args:
            table_number: 桌号
            items: 订单项列表 [{"item_id": "...", "item_name": "...", "quantity": 1, "unit_price": 100}]
            customer_name: 客户姓名
            customer_phone: 客户电话
            notes: 备注

        Returns:
            订单信息
        """
        async with get_db_session() as session:
            try:
                # 生成订单ID
                order_id = f"ORD_{datetime.now().strftime('%Y%m%d')}_{uuid.uuid4().hex[:6].upper()}"

                # 计算总金额
                total_amount = sum(item["quantity"] * item["unit_price"] for item in items)
                discount_amount = kwargs.get("discount_amount", 0)
                final_amount = total_amount - discount_amount

                # 创建订单
                order = Order(
                    id=order_id,
                    store_id=self.store_id,
                    table_number=table_number,
                    customer_name=customer_name,
                    customer_phone=customer_phone,
                    status=OrderStatus.PENDING,
                    total_amount=total_amount,
                    discount_amount=discount_amount,
                    final_amount=final_amount,
                    order_time=datetime.utcnow(),
                    notes=notes,
                    order_metadata=kwargs.get("metadata", {})
                )

                session.add(order)
                await session.flush()

                # 创建订单项
                for item in items:
                    order_item = OrderItem(
                        order_id=order_id,
                        item_id=item["item_id"],
                        item_name=item["item_name"],
                        quantity=item["quantity"],
                        unit_price=item["unit_price"],
                        subtotal=item["quantity"] * item["unit_price"],
                        notes=item.get("notes"),
                        customizations=item.get("customizations", {})
                    )
                    session.add(order_item)

                await session.commit()

                logger.info("订单创建成功", order_id=order_id, total_amount=total_amount)

                return self._order_to_dict(order, items)

            except Exception as e:
                await session.rollback()
                logger.error("创建订单失败", error=str(e))
                raise

    async def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        """
        获取订单详情

        Args:
            order_id: 订单ID

        Returns:
            订单信息
        """
        async with get_db_session() as session:
            stmt = (
                select(Order)
                .options(selectinload(Order.items))
                .where(Order.id == order_id)
            )
            result = await session.execute(stmt)
            order = result.scalar_one_or_none()

            if not order:
                return None

            return self._order_to_dict(order)

    async def list_orders(
        self,
        status: Optional[str] = None,
        table_number: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        查询订单列表

        Args:
            status: 订单状态
            table_number: 桌号
            start_date: 开始日期
            end_date: 结束日期
            limit: 返回数量限制

        Returns:
            订单列表
        """
        async with get_db_session() as session:
            stmt = (
                select(Order)
                .options(selectinload(Order.items))
                .where(Order.store_id == self.store_id)
            )

            if status:
                stmt = stmt.where(Order.status == status)

            if table_number:
                stmt = stmt.where(Order.table_number == table_number)

            if start_date:
                start_dt = datetime.fromisoformat(start_date)
                stmt = stmt.where(Order.order_time >= start_dt)

            if end_date:
                end_dt = datetime.fromisoformat(end_date)
                stmt = stmt.where(Order.order_time <= end_dt)

            stmt = stmt.order_by(Order.order_time.desc()).limit(limit)

            result = await session.execute(stmt)
            orders = result.scalars().all()

            return [self._order_to_dict(order) for order in orders]

    async def update_order_status(
        self,
        order_id: str,
        status: str,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        更新订单状态

        Args:
            order_id: 订单ID
            status: 新状态
            notes: 备注

        Returns:
            更新后的订单信息
        """
        async with get_db_session() as session:
            try:
                stmt = (
                    select(Order)
                    .options(selectinload(Order.items))
                    .where(Order.id == order_id)
                )
                result = await session.execute(stmt)
                order = result.scalar_one_or_none()

                if not order:
                    raise ValueError(f"订单不存在: {order_id}")

                order.status = OrderStatus(status)

                if status == OrderStatus.CONFIRMED.value:
                    order.confirmed_at = datetime.utcnow()
                elif status == OrderStatus.COMPLETED.value:
                    order.completed_at = datetime.utcnow()

                if notes:
                    order.notes = notes

                await session.commit()

                logger.info("订单状态更新成功", order_id=order_id, status=status)

                return self._order_to_dict(order)

            except Exception as e:
                await session.rollback()
                logger.error("更新订单状态失败", error=str(e))
                raise

    async def add_items(
        self,
        order_id: str,
        items: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        添加订单项

        Args:
            order_id: 订单ID
            items: 订单项列表

        Returns:
            更新后的订单信息
        """
        async with get_db_session() as session:
            try:
                stmt = (
                    select(Order)
                    .options(selectinload(Order.items))
                    .where(Order.id == order_id)
                )
                result = await session.execute(stmt)
                order = result.scalar_one_or_none()

                if not order:
                    raise ValueError(f"订单不存在: {order_id}")

                # 添加新订单项
                added_amount = 0
                for item in items:
                    order_item = OrderItem(
                        order_id=order_id,
                        item_id=item["item_id"],
                        item_name=item["item_name"],
                        quantity=item["quantity"],
                        unit_price=item["unit_price"],
                        subtotal=item["quantity"] * item["unit_price"],
                        notes=item.get("notes"),
                        customizations=item.get("customizations", {})
                    )
                    session.add(order_item)
                    added_amount += order_item.subtotal

                # 更新订单总金额
                order.total_amount += added_amount
                order.final_amount = order.total_amount - order.discount_amount

                await session.commit()
                await session.refresh(order, ["items"])

                logger.info("订单项添加成功", order_id=order_id, items_count=len(items))

                return self._order_to_dict(order)

            except Exception as e:
                await session.rollback()
                logger.error("添加订单项失败", error=str(e))
                raise

    async def cancel_order(
        self,
        order_id: str,
        reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        取消订单

        Args:
            order_id: 订单ID
            reason: 取消原因

        Returns:
            取消后的订单信息
        """
        async with get_db_session() as session:
            try:
                stmt = (
                    select(Order)
                    .options(selectinload(Order.items))
                    .where(Order.id == order_id)
                )
                result = await session.execute(stmt)
                order = result.scalar_one_or_none()

                if not order:
                    raise ValueError(f"订单不存在: {order_id}")

                order.status = OrderStatus.CANCELLED
                if reason:
                    order.notes = f"{order.notes or ''}\n取消原因: {reason}".strip()

                await session.commit()

                logger.info("订单取消成功", order_id=order_id)

                return self._order_to_dict(order)

            except Exception as e:
                await session.rollback()
                logger.error("取消订单失败", error=str(e))
                raise

    async def get_order_statistics(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取订单统计

        Args:
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            统计信息
        """
        async with get_db_session() as session:
            stmt = select(Order).options(selectinload(Order.items)).where(Order.store_id == self.store_id)

            if start_date:
                start_dt = datetime.fromisoformat(start_date)
                stmt = stmt.where(Order.order_time >= start_dt)

            if end_date:
                end_dt = datetime.fromisoformat(end_date)
                stmt = stmt.where(Order.order_time <= end_dt)

            result = await session.execute(stmt)
            orders = result.scalars().all()

            # 计算统计数据
            total_orders = len(orders)
            completed_orders = sum(1 for o in orders if o.status == OrderStatus.COMPLETED)
            cancelled_orders = sum(1 for o in orders if o.status == OrderStatus.CANCELLED)
            total_revenue = sum(o.final_amount for o in orders if o.status == OrderStatus.COMPLETED)
            average_order_value = total_revenue / completed_orders if completed_orders > 0 else 0

            # 按状态统计
            status_counts = {}
            for status in OrderStatus:
                status_counts[status.value] = sum(1 for o in orders if o.status == status)

            return {
                "total_orders": total_orders,
                "completed_orders": completed_orders,
                "cancelled_orders": cancelled_orders,
                "total_revenue": total_revenue / 100,  # Convert cents to yuan
                "average_order_value": average_order_value / 100,
                "status_breakdown": status_counts
            }

    def _order_to_dict(self, order: Order, items: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        将订单对象转换为字典

        Args:
            order: 订单对象
            items: 订单项列表（可选，如果不提供则从order.items获取）

        Returns:
            订单字典
        """
        order_dict = {
            "order_id": order.id,
            "store_id": order.store_id,
            "table_number": order.table_number,
            "customer_name": order.customer_name,
            "customer_phone": order.customer_phone,
            "status": order.status.value,
            "total_amount": order.total_amount / 100,  # Convert cents to yuan
            "discount_amount": order.discount_amount / 100,
            "final_amount": order.final_amount / 100,
            "order_time": order.order_time.isoformat() if order.order_time else None,
            "confirmed_at": order.confirmed_at.isoformat() if order.confirmed_at else None,
            "completed_at": order.completed_at.isoformat() if order.completed_at else None,
            "notes": order.notes,
            "metadata": order.order_metadata
        }

        # 添加订单项
        if items:
            order_dict["items"] = items
        elif hasattr(order, "items") and order.items:
            order_dict["items"] = [
                {
                    "item_id": item.item_id,
                    "item_name": item.item_name,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price / 100,
                    "subtotal": item.subtotal / 100,
                    "notes": item.notes,
                    "customizations": item.customizations
                }
                for item in order.items
            ]
        else:
            order_dict["items"] = []

        return order_dict


# 创建全局服务实例
order_service = OrderService()
