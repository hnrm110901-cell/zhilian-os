"""
Dashboard Service
数据可视化大屏服务层
"""
from typing import Dict, Any, List
from datetime import datetime, timedelta
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from ..services.pos_service import pos_service
from ..services.member_service import member_service
from ..services.agent_service import agent_service

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
                    page_size=1000,
                )
                yesterday_orders = await pos_service.query_orders(
                    begin_date=yesterday,
                    end_date=yesterday,
                    page_index=1,
                    page_size=1000,
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
                        page_size=1000,
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
            categories = await pos_service.get_dish_categories()

            # 模拟销售数据（实际应该从订单明细中统计）
            category_sales = []
            for category in categories[:5]:  # 取前5个类别
                category_sales.append({
                    "name": category.get("rcNAME", "未知"),
                    "value": 0,  # 实际应该统计销售额
                })

            return {"categories": category_sales}

        except Exception as e:
            logger.error("获取菜品类别销售数据失败", error=str(e))
            return {"categories": []}

    async def get_payment_methods(self) -> Dict[str, Any]:
        """
        获取支付方式分布

        Returns:
            支付方式分布数据
        """
        try:
            pay_types = await pos_service.get_pay_types()

            # 模拟支付方式分布（实际应该从订单中统计）
            payment_distribution = []
            for pay_type in pay_types:
                payment_distribution.append({
                    "name": pay_type.get("name", "未知"),
                    "value": 0,  # 实际应该统计使用次数
                })

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
            # 模拟会员数据（实际应该从会员系统获取）
            return {
                "total_members": 0,
                "new_members_today": 0,
                "active_members": 0,
                "member_levels": [
                    {"level": "普通会员", "count": 0},
                    {"level": "银卡会员", "count": 0},
                    {"level": "金卡会员", "count": 0},
                    {"level": "钻石会员", "count": 0},
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
        获取Agent性能数据

        Returns:
            Agent性能数据
        """
        try:
            agents = [
                {"name": "排班Agent", "tasks": 0, "success_rate": 0.0},
                {"name": "订单Agent", "tasks": 0, "success_rate": 0.0},
                {"name": "库存Agent", "tasks": 0, "success_rate": 0.0},
                {"name": "服务Agent", "tasks": 0, "success_rate": 0.0},
                {"name": "培训Agent", "tasks": 0, "success_rate": 0.0},
                {"name": "决策Agent", "tasks": 0, "success_rate": 0.0},
                {"name": "预定Agent", "tasks": 0, "success_rate": 0.0},
            ]

            return {"agents": agents}

        except Exception as e:
            logger.error("获取Agent性能数据失败", error=str(e))
            return {"agents": []}

    async def get_realtime_metrics(self) -> Dict[str, Any]:
        """
        获取实时指标

        Returns:
            实时指标数据
        """
        try:
            return {
                "timestamp": datetime.now().isoformat(),
                "current_orders": 0,  # 当前进行中的订单
                "current_customers": 0,  # 当前在店顾客
                "table_occupancy_rate": 0.0,  # 桌台占用率
                "average_wait_time": 0,  # 平均等待时间（分钟）
                "kitchen_queue": 0,  # 厨房待制作订单
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
