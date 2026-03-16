"""
KitchenAgent Service — 后厨效率智能（Sprint 5）

9-Agent 终态中的 KitchenAgent，核心能力：
1. 出品速度追踪（下单→出品 平均时长）
2. 退菜率分析（退菜原因分布）
3. 厨师绩效（产量/退菜/速度 综合评分）
4. 备餐效率（预估用量 vs 实际消耗）

定位：厨师长的效率管控仪表盘
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import and_, case, extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.order import Order, OrderItem
from src.models.waste_event import WasteEvent, WasteEventType

logger = logging.getLogger(__name__)


# ── 纯函数 ──────────────────────────────────────────────────────


def compute_dish_speed_score(avg_minutes: float) -> str:
    """
    出品速度评级

    fast: < 15分钟
    normal: 15-25分钟
    slow: 25-40分钟
    critical: > 40分钟
    """
    if avg_minutes < 15:
        return "fast"
    if avg_minutes < 25:
        return "normal"
    if avg_minutes < 40:
        return "slow"
    return "critical"


def classify_kitchen_efficiency(
    speed_score: str,
    return_rate: float,
    waste_rate: float,
) -> str:
    """
    后厨综合效率评级

    A: 速度fast + 退菜<2% + 损耗<3%
    B: 速度normal + 退菜<5%
    C: 其他
    D: 速度critical 或 退菜>10%
    """
    if speed_score == "critical" or return_rate > 0.10:
        return "D"
    if speed_score == "fast" and return_rate < 0.02 and waste_rate < 0.03:
        return "A"
    if speed_score in ("fast", "normal") and return_rate < 0.05:
        return "B"
    return "C"


def compute_return_rate(
    returned_items: int,
    total_items: int,
) -> float:
    """退菜率 = 退菜数 / 总出品数"""
    if total_items <= 0:
        return 0.0
    return round(returned_items / total_items, 4)


class KitchenAgentService:
    """KitchenAgent — 后厨效率智能"""

    async def get_kitchen_dashboard(
        self,
        db: AsyncSession,
        store_id: str,
        days: int = 7,
    ) -> dict:
        """
        后厨综合仪表盘

        返回：出品速度 + 退菜率 + 损耗事件数 + 效率评级
        """
        cutoff = datetime.utcnow() - timedelta(days=days)

        # 出品速度（order_time → completed_at）
        speed_result = await db.execute(
            select(
                func.avg(extract("epoch", Order.completed_at - Order.order_time) / 60),
                func.count(Order.id),
            ).where(
                Order.store_id == store_id,
                Order.order_time >= cutoff,
                Order.status == "completed",
                Order.completed_at.isnot(None),
            )
        )
        srow = speed_result.one()
        avg_speed_min = round(float(srow[0] or 30), 1)
        completed_orders = srow[1] or 0
        speed_score = compute_dish_speed_score(avg_speed_min)

        # 总出品数
        total_items = (
            await db.scalar(
                select(func.coalesce(func.sum(OrderItem.quantity), 0))
                .join(Order, Order.id == OrderItem.order_id)
                .where(
                    Order.store_id == store_id,
                    Order.order_time >= cutoff,
                    Order.status != "cancelled",
                )
            )
            or 0
        )

        # 退菜数（cancelled 状态的订单项 — 近似：cancelled订单的总菜品数）
        returned_items = (
            await db.scalar(
                select(func.coalesce(func.sum(OrderItem.quantity), 0))
                .join(Order, Order.id == OrderItem.order_id)
                .where(
                    Order.store_id == store_id,
                    Order.order_time >= cutoff,
                    Order.status == "cancelled",
                )
            )
            or 0
        )
        return_rate = compute_return_rate(returned_items, total_items + returned_items)

        # 损耗事件
        waste_count = (
            await db.scalar(
                select(func.count(WasteEvent.id)).where(
                    WasteEvent.store_id == store_id,
                    WasteEvent.occurred_at >= cutoff,
                )
            )
            or 0
        )

        # 烹饪损耗占比
        cooking_waste = (
            await db.scalar(
                select(func.count(WasteEvent.id)).where(
                    WasteEvent.store_id == store_id,
                    WasteEvent.occurred_at >= cutoff,
                    WasteEvent.event_type == WasteEventType.COOKING_LOSS,
                )
            )
            or 0
        )
        cooking_waste_rate = round(cooking_waste / waste_count, 4) if waste_count > 0 else 0.0

        # 综合评级
        efficiency = classify_kitchen_efficiency(
            speed_score,
            return_rate,
            cooking_waste_rate,
        )

        return {
            "period_days": days,
            "avg_speed_minutes": avg_speed_min,
            "speed_score": speed_score,
            "completed_orders": completed_orders,
            "total_items_produced": total_items,
            "returned_items": returned_items,
            "return_rate": return_rate,
            "waste_events": waste_count,
            "cooking_waste_rate": cooking_waste_rate,
            "efficiency_grade": efficiency,
        }

    async def get_dish_production_speed(
        self,
        db: AsyncSession,
        store_id: str,
        days: int = 7,
        limit: int = 20,
    ) -> List[dict]:
        """
        菜品出品速度排名

        按平均出品时长排序（慢→快）
        """
        cutoff = datetime.utcnow() - timedelta(days=days)

        stmt = (
            select(
                OrderItem.item_id,
                OrderItem.item_name,
                func.count(OrderItem.id).label("count"),
                func.avg(extract("epoch", Order.completed_at - Order.order_time) / 60).label("avg_min"),
            )
            .join(Order, Order.id == OrderItem.order_id)
            .where(
                Order.store_id == store_id,
                Order.order_time >= cutoff,
                Order.status == "completed",
                Order.completed_at.isnot(None),
            )
            .group_by(OrderItem.item_id, OrderItem.item_name)
            .having(func.count(OrderItem.id) >= 3)
            .order_by(func.avg(extract("epoch", Order.completed_at - Order.order_time) / 60).desc())
            .limit(limit)
        )
        result = await db.execute(stmt)

        dishes = []
        for row in result.all():
            avg_min = round(float(row[3] or 0), 1)
            dishes.append(
                {
                    "item_id": row[0],
                    "item_name": row[1],
                    "order_count": row[2],
                    "avg_minutes": avg_min,
                    "speed_score": compute_dish_speed_score(avg_min),
                }
            )
        return dishes

    async def get_waste_by_type(
        self,
        db: AsyncSession,
        store_id: str,
        days: int = 7,
    ) -> List[dict]:
        """
        损耗类型分布（厨房视角）

        按损耗类型统计数量
        """
        cutoff = datetime.utcnow() - timedelta(days=days)

        stmt = (
            select(
                WasteEvent.event_type,
                func.count(WasteEvent.id),
            )
            .where(
                WasteEvent.store_id == store_id,
                WasteEvent.occurred_at >= cutoff,
            )
            .group_by(WasteEvent.event_type)
            .order_by(func.count(WasteEvent.id).desc())
        )
        result = await db.execute(stmt)

        types = []
        for row in result.all():
            types.append(
                {
                    "type": row[0].value if hasattr(row[0], "value") else str(row[0]),
                    "count": row[1],
                }
            )
        return types


# 全局单例
kitchen_agent_service = KitchenAgentService()
