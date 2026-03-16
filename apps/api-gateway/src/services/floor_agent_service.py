"""
FloorAgent Service — 楼面经营智能（Sprint 4）

9-Agent 终态中的 FloorAgent，核心能力：
1. 翻台率分析（桌均翻台次数 + 趋势）
2. 座位利用率（实际就座人数 / 总座位容量）
3. 等位转化率（等位→入座 / 总等位）
4. 时段效率热力图（哪个时段最赚钱）
5. 桌台效率排名（哪张桌翻台最快）

定位：楼面经理的经营仪表盘
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import and_, case, extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.order import Order
from src.models.queue import Queue, QueueStatus
from src.models.reservation import Reservation

logger = logging.getLogger(__name__)


# ── 纯函数 ──────────────────────────────────────────────────────


def compute_turnover_rate(
    total_orders: int,
    total_tables: int,
    days: int,
) -> float:
    """
    翻台率 = 总订单数 / (桌数 × 天数)

    行业基准：午市 1.5-2.0，晚市 2.0-3.0
    """
    if total_tables <= 0 or days <= 0:
        return 0.0
    return round(total_orders / (total_tables * days), 2)


def compute_seat_utilization(
    actual_guests: int,
    total_capacity: int,
) -> float:
    """
    座位利用率 = 实际就餐人数 / 总座位容量

    行业基准：60%-80%
    """
    if total_capacity <= 0:
        return 0.0
    return round(min(actual_guests / total_capacity, 1.0), 4)


def classify_table_efficiency(
    turnover: float,
    avg_duration_min: float,
) -> str:
    """
    桌台效率分级

    高效：翻台≥2.5 且 平均用餐≤70分钟
    正常：翻台≥1.5
    低效：翻台<1.5 或 用餐>120分钟
    """
    if turnover >= 2.5 and avg_duration_min <= 70:
        return "high"
    if turnover >= 1.5:
        return "normal"
    return "low"


def compute_wait_conversion(
    total_waiting: int,
    seated: int,
) -> float:
    """
    等位转化率 = 入座数 / 总等位数

    行业基准：≥70%
    """
    if total_waiting <= 0:
        return 0.0
    return round(seated / total_waiting, 4)


class FloorAgentService:
    """FloorAgent — 楼面经营智能"""

    async def get_floor_dashboard(
        self,
        db: AsyncSession,
        store_id: str,
        days: int = 7,
    ) -> dict:
        """
        楼面综合仪表盘

        聚合：翻台率 + 等位转化 + 时段分布 + 预订到店率
        """
        cutoff = datetime.utcnow() - timedelta(days=days)

        # 订单总数（有桌号的）
        order_stats = await db.execute(
            select(
                func.count(Order.id),
                func.count(func.distinct(Order.table_number)),
                func.sum(Order.total_amount),
            ).where(
                Order.store_id == store_id,
                Order.order_time >= cutoff,
                Order.status != "cancelled",
                Order.table_number.isnot(None),
            )
        )
        row = order_stats.one()
        total_orders = row[0] or 0
        distinct_tables = row[1] or 0
        total_revenue = float(row[2] or 0)

        # 翻台率
        turnover = compute_turnover_rate(total_orders, max(distinct_tables, 1), days)

        # 等位统计
        wait_stats = await db.execute(
            select(
                func.count(Queue.queue_id),
                func.count(
                    case(
                        (Queue.status == QueueStatus.SEATED.value, 1),
                    )
                ),
                func.count(
                    case(
                        (Queue.status.in_([QueueStatus.CANCELLED.value, QueueStatus.NO_SHOW.value]), 1),
                    )
                ),
                func.avg(Queue.actual_wait_time),
            ).where(
                Queue.store_id == store_id,
                Queue.created_at >= cutoff,
            )
        )
        wrow = wait_stats.one()
        total_waiting = wrow[0] or 0
        seated_count = wrow[1] or 0
        lost_count = wrow[2] or 0
        avg_wait_min = round(float(wrow[3] or 0), 1)

        wait_conversion = compute_wait_conversion(total_waiting, seated_count)

        # 预订到店率
        reservation_stats = await db.execute(
            select(
                func.count(Reservation.id),
                func.count(
                    case(
                        (Reservation.status.in_(["arrived", "seated", "completed"]), 1),
                    )
                ),
                func.count(
                    case(
                        (Reservation.status == "no_show", 1),
                    )
                ),
            ).where(
                Reservation.store_id == store_id,
                Reservation.created_at >= cutoff,
            )
        )
        rrow = reservation_stats.one()
        total_reservations = rrow[0] or 0
        arrived_reservations = rrow[1] or 0
        no_show_count = rrow[2] or 0
        arrival_rate = round(arrived_reservations / total_reservations, 4) if total_reservations > 0 else 0.0

        return {
            "period_days": days,
            "turnover_rate": turnover,
            "total_orders": total_orders,
            "distinct_tables": distinct_tables,
            "total_revenue_yuan": round(total_revenue, 2),
            "avg_revenue_per_table_yuan": round(total_revenue / total_orders, 2) if total_orders > 0 else 0.0,
            "wait_queue": {
                "total": total_waiting,
                "seated": seated_count,
                "lost": lost_count,
                "conversion_rate": wait_conversion,
                "avg_wait_minutes": avg_wait_min,
            },
            "reservations": {
                "total": total_reservations,
                "arrived": arrived_reservations,
                "no_show": no_show_count,
                "arrival_rate": arrival_rate,
            },
        }

    async def get_hourly_heatmap(
        self,
        db: AsyncSession,
        store_id: str,
        days: int = 7,
    ) -> List[dict]:
        """
        时段效率热力图（每小时订单数 + 营收）

        返回 24 小时 × (订单数, 营收, 客单价)
        """
        cutoff = datetime.utcnow() - timedelta(days=days)

        stmt = (
            select(
                extract("hour", Order.order_time).label("hour"),
                func.count(Order.id),
                func.coalesce(func.sum(Order.total_amount), 0),
            )
            .where(
                Order.store_id == store_id,
                Order.order_time >= cutoff,
                Order.status != "cancelled",
            )
            .group_by(extract("hour", Order.order_time))
            .order_by(extract("hour", Order.order_time))
        )
        result = await db.execute(stmt)

        # 填充完整 24 小时
        hour_data = {i: {"orders": 0, "revenue_yuan": 0.0} for i in range(24)}
        for hour, count, revenue in result.all():
            h = int(hour)
            hour_data[h] = {
                "orders": count,
                "revenue_yuan": round(float(revenue or 0), 2),
            }

        heatmap = []
        for h in range(24):
            d = hour_data[h]
            avg_ticket = round(d["revenue_yuan"] / d["orders"], 2) if d["orders"] > 0 else 0.0
            heatmap.append(
                {
                    "hour": h,
                    "orders": d["orders"],
                    "revenue_yuan": d["revenue_yuan"],
                    "avg_ticket_yuan": avg_ticket,
                }
            )
        return heatmap

    async def get_table_efficiency(
        self,
        db: AsyncSession,
        store_id: str,
        days: int = 7,
        limit: int = 30,
    ) -> List[dict]:
        """
        桌台效率排名

        按翻台次数排序，标注效率等级
        """
        cutoff = datetime.utcnow() - timedelta(days=days)

        stmt = (
            select(
                Order.table_number,
                func.count(Order.id).label("order_count"),
                func.coalesce(func.sum(Order.total_amount), 0).label("revenue"),
                func.avg(extract("epoch", Order.completed_at - Order.order_time) / 60).label("avg_duration_min"),
            )
            .where(
                Order.store_id == store_id,
                Order.order_time >= cutoff,
                Order.status != "cancelled",
                Order.table_number.isnot(None),
                Order.table_number != "",
            )
            .group_by(Order.table_number)
            .order_by(func.count(Order.id).desc())
            .limit(limit)
        )
        result = await db.execute(stmt)

        tables = []
        for row in result.all():
            turnover = round((row[1] or 0) / max(days, 1), 2)
            duration = float(row[3] or 60)
            efficiency = classify_table_efficiency(turnover, duration)
            tables.append(
                {
                    "table_number": row[0],
                    "order_count": row[1],
                    "revenue_yuan": round(float(row[2] or 0), 2),
                    "turnover_rate": turnover,
                    "avg_duration_min": round(duration, 1),
                    "efficiency": efficiency,
                }
            )
        return tables


# 全局单例
floor_agent_service = FloorAgentService()
