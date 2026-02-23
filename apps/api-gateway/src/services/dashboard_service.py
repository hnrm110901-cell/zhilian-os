"""
Dashboard Service
数据可视化大屏服务层
"""
from typing import Dict, Any, List
from datetime import datetime, timedelta, date
import os
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..services.pos_service import pos_service
from ..services.member_service import member_service
from ..services.agent_service import agent_service
from ..core.database import get_db_session
from ..models.order import Order, OrderItem, OrderStatusfrom ..models.dish import Dish, DishCategory

logger = structlog.get_logger()


class DashboardService:
    """数据可视化大屏服务"""

    async def get_overview_stats(self) -> Dict[str, Any]:
        """
        获取概览统计数据

        Returns:
            概览统计数据
        """
        try:
            # 获取今日日期
            today = datetime.now().strftime("%Y-%m-%d")
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

            # 并发获取各系统数据
            stats = {
                "timestamp": datetime.now().isoformat(),
                "date": today,
                "stores": {
                    "total": 0,
                    "active": 0,
                },
                "orders": {
                    "today": 0,
                    "yesterday": 0,
                    "growth_rate": 0.0,
                },
                "members": {
                    "total": 0,
                    "new_today": 0,
                    "active_today": 0,
                },
                "revenue": {
                    "today": 0,
                    "yesterday": 0,
                    "growth_rate": 0.0,
                },
                "agents": {
                    "total": 7,
                    "active": 7,
                },
            }

            # 获取门店数据
            try:
                stores = await pos_service.get_stores()
                stats["stores"]["total"] = len(stores)
                stats["stores"]["active"] = len(stores)
            except Exception as e:
                logger.warning("获取门店数据失败", error=str(e))

            # 获取订单数据
            try:
                today_orders = await pos_service.query_orders(
                    begin_date=today,
                    end_date=today,
                    page_index=1,
                    page_size=int(os.getenv("POS_QUERY_PAGE_SIZE", "1000")),
                )
                yesterday_orders = await pos_service.query_orders(
                    begin_date=yesterday,
                    end_date=yesterday,
                    page_index=1,
                    page_size=int(os.getenv("POS_QUERY_PAGE_SIZE", "1000")),
                )

                stats["orders"]["today"] = len(today_orders.get("orders", []))
                stats["orders"]["yesterday"] = len(yesterday_orders.get("orders", []))

                if stats["orders"]["yesterday"] > 0:
                    stats["orders"]["growth_rate"] = (
                        (stats["orders"]["today"] - stats["orders"]["yesterday"])
                        / stats["orders"]["yesterday"]
                        * 100
                    )

                # 计算营收
                today_revenue = sum(
                    order.get("realPrice", 0) for order in today_orders.get("orders", [])
                )
                yesterday_revenue = sum(
                    order.get("realPrice", 0)
                    for order in yesterday_orders.get("orders", [])
                )

                stats["revenue"]["today"] = today_revenue
                stats["revenue"]["yesterday"] = yesterday_revenue

                if yesterday_revenue > 0:
                    stats["revenue"]["growth_rate"] = (
                        (today_revenue - yesterday_revenue) / yesterday_revenue * 100
                    )

            except Exception as e:
                logger.warning("获取订单数据失败", error=str(e))

            logger.info("获取概览统计数据成功")
            return stats

        except Exception as e:
            logger.error("获取概览统计数据失败", error=str(e))
            raise

    async def get_sales_trend(self, days: int = 7) -> Dict[str, Any]:
        """
        获取销售趋势数据

        Args:
            days: 天数

        Returns:
            销售趋势数据
        """
        try:
            dates = []
            orders_count = []
            revenue = []

            for i in range(days - 1, -1, -1):
                date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
                dates.append(date)

                try:
                    result = await pos_service.query_orders(
                        begin_date=date,
                        end_date=date,
                        page_index=1,
                        page_size=int(os.getenv("POS_QUERY_PAGE_SIZE", "1000")),
                    )

                    orders = result.get("orders", [])
                    orders_count.append(len(orders))
                    revenue.append(sum(order.get("realPrice", 0) for order in orders))

                except Exception as e:
                    logger.warning(f"获取{date}销售数据失败", error=str(e))
                    orders_count.append(0)
                    revenue.append(0)

            return {
                "dates": dates,
                "orders_count": orders_count,
                "revenue": revenue,
            }

        except Exception as e:
            logger.error("获取销售趋势数据失败", error=str(e))
            raise

    async def get_category_sales(self) -> Dict[str, Any]:
        """
        获取菜品类别销售数据

        Returns:
            菜品类别销售数据
        """
        try:
            # 从订单明细统计各分类销售额
            async with get_db_session() as session:
                result = await session.execute(
                    select(
                        DishCategory.name.label("category_name"),
                        func.sum(OrderItem.subtotal).label("total_sales"),
                    )
                    .join(Dish, OrderItem.item_id == func.cast(Dish.id, OrderItem.item_id.type))
                    .join(DishCategory, Dish.category_id == DishCategory.id)
                    .join(Order, OrderItem.order_id == Order.id)
                    .where(Order.status == OrderStatus.COMPLETED)
                    .group_by(DishCategory.name)
                    .order_by(func.sum(OrderItem.subtotal).desc())
                    .limit(5)
                )
                rows = result.all()

            if rows:
                category_sales = [
                    {"name": row.category_name, "value": int(row.total_sales or 0)}
                    for row in rows
                ]
            else:
                # fallback：从POS获取分类列表，销售额为0
                try:
                    categories = await pos_service.get_dish_categories()
                    category_sales = [
                        {"name": c.get("rcNAME", "未知"), "value": 0}
                        for c in categories[:5]
                    ]
                except Exception:
                    category_sales = []

            return {"categories": category_sales}

        except Exception as e:
            logger.error("获取菜品类别销售数据失败", error=str(e))
            return {"categories": []}

    async def get_payment_methods(self) -> Dict[str, Any]:
        """
        获取支付方式分布（从 order_metadata 统计，fallback 到 POS 分类列表）
        """
        try:
            async with get_db_session() as session:
                result = await session.execute(
                    select(Order.order_metadata, func.count(Order.id).label("cnt"))
                    .where(
                        Order.status == OrderStatus.COMPLETED,
                        Order.order_metadata.isnot(None),
                    )
                    .group_by(Order.order_metadata)
                    .limit(200)
                )
                rows = result.all()

            # 从 order_metadata JSON 中提取 payment_method
            payment_counts: Dict[str, int] = {}
            for row in rows:
                meta = row.order_metadata or {}
                pay = meta.get("payment_method") or meta.get("pay_type") or meta.get("payType")
                if pay:
                    payment_counts[pay] = payment_counts.get(pay, 0) + row.cnt

            if payment_counts:
                payment_distribution = [
                    {"name": name, "value": count}
                    for name, count in sorted(payment_counts.items(), key=lambda x: -x[1])
                ]
            else:
                # fallback：从 POS 获取分类列表，value 为 0
                try:
                    pay_types = await pos_service.get_pay_types()
                    payment_distribution = [
                        {"name": p.get("name", "未知"), "value": 0} for p in pay_types
                    ]
                except Exception:
                    payment_distribution = [
                        {"name": "微信支付", "value": 0},
                        {"name": "支付宝", "value": 0},
                        {"name": "现金", "value": 0},
                    ]

            return {"payment_methods": payment_distribution}

        except Exception as e:
            logger.error("获取支付方式分布失败", error=str(e))
            return {"payment_methods": []}

    async def get_member_stats(self) -> Dict[str, Any]:
        """
        获取会员统计数据

        Returns:
            会员统计数据
        """
        try:
            today = date.today()
            thirty_days_ago = today - timedelta(days=30)

            async with get_db_session() as session:
                # 总会员数（有手机号的唯一顾客）
                total_result = await session.execute(
                    select(func.count(func.distinct(Order.customer_phone))).where(
                        Order.customer_phone.isnot(None),
                        Order.customer_phone != "",
                    )
                )
                total_members = total_result.scalar() or 0

                # 今日新顾客（今天首次下单）
                new_today_result = await session.execute(
                    select(func.count(func.distinct(Order.customer_phone))).where(
                        Order.customer_phone.isnot(None),
                        func.date(Order.order_time) == today,
                    )
                )
                new_members_today = new_today_result.scalar() or 0

                # 近30天活跃顾客
                active_result = await session.execute(
                    select(func.count(func.distinct(Order.customer_phone))).where(
                        Order.customer_phone.isnot(None),
                        Order.customer_phone != "",
                        func.date(Order.order_time) >= thirty_days_ago,
                    )
                )
                active_members = active_result.scalar() or 0

            return {
                "total_members": total_members,
                "new_members_today": new_members_today,
                "active_members": active_members,
                "member_levels": [
                    {"level": "普通会员", "count": max(0, total_members - active_members)},
                    {"level": "活跃会员", "count": active_members},
                ],
            }

        except Exception as e:
            logger.error("获取会员统计数据失败", error=str(e))
            return {
                "total_members": 0,
                "new_members_today": 0,
                "active_members": 0,
                "member_levels": [],
            }

    async def get_agent_performance(self) -> Dict[str, Any]:
        """
        获取Agent性能数据（从 DecisionLog 统计）
        """
        try:
            from ..models.decision_log import DecisionLog, DecisionStatus

            agent_map = {
                "schedule": "排班Agent",
                "order": "订单Agent",
                "inventory": "库存Agent",
                "service": "服务Agent",
                "training": "培训Agent",
                "human_in_the_loop": "决策Agent",
                "reservation": "预定Agent",
            }

            async with get_db_session() as session:
                result = await session.execute(
                    select(
                        DecisionLog.agent_type,
                        func.count(DecisionLog.id).label("total"),
                        func.count(DecisionLog.id).filter(
                            DecisionLog.decision_status == DecisionStatus.EXECUTED
                        ).label("executed"),
                    ).group_by(DecisionLog.agent_type)
                )
                rows = result.all()

            db_agents = {
                row.agent_type: {
                    "tasks": row.total,
                    "success_rate": round(row.executed / row.total, 2) if row.total > 0 else 0.0,
                }
                for row in rows
            }

            agents = []
            for key, display_name in agent_map.items():
                data = db_agents.get(key, {"tasks": 0, "success_rate": 0.0})
                agents.append({"name": display_name, **data})

            return {"agents": agents}

        except Exception as e:
            logger.error("获取Agent性能数据失败", error=str(e))
            return {"agents": []}

    async def get_realtime_metrics(self) -> Dict[str, Any]:
        """
        获取实时指标（从 Order 和 Queue 表查询）
        """
        try:
            from ..models.queue import Queue, QueueStatus

            active_statuses = [
                OrderStatus.PENDING, OrderStatus.CONFIRMED,
                OrderStatus.PREPARING, OrderStatus.READY,
            ]

            async with get_db_session() as session:
                # 当前进行中订单
                orders_result = await session.execute(
                    select(func.count(Order.id)).where(Order.status.in_(active_statuses))
                )
                current_orders = orders_result.scalar() or 0

                # 厨房待制作
                kitchen_result = await session.execute(
                    select(func.count(Order.id)).where(
                        Order.status.in_([OrderStatus.CONFIRMED, OrderStatus.PREPARING])
                    )
                )
                kitchen_queue = kitchen_result.scalar() or 0

                # 当前排队人数
                queue_result = await session.execute(
                    select(func.sum(Queue.party_size)).where(Queue.status == QueueStatus.WAITING)
                )
                current_customers = queue_result.scalar() or 0

                # 平均等待时间（排队数 × 15分钟/桌）
                queue_count_result = await session.execute(
                    select(func.count(Queue.queue_id)).where(Queue.status == QueueStatus.WAITING)
                )
                queue_count = queue_count_result.scalar() or 0
                average_wait_time = queue_count * 15

                # 桌台占用率（用进行中订单数 / 50 估算）
                table_occupancy_rate = min(1.0, round(current_orders / 50, 2))

            return {
                "timestamp": datetime.now().isoformat(),
                "current_orders": current_orders,
                "current_customers": current_customers,
                "table_occupancy_rate": table_occupancy_rate,
                "average_wait_time": average_wait_time,
                "kitchen_queue": kitchen_queue,
            }

        except Exception as e:
            logger.error("获取实时指标失败", error=str(e))
            return {
                "timestamp": datetime.now().isoformat(),
                "current_orders": 0,
                "current_customers": 0,
                "table_occupancy_rate": 0.0,
                "average_wait_time": 0,
                "kitchen_queue": 0,
            }


# 创建全局服务实例
dashboard_service = DashboardService()
