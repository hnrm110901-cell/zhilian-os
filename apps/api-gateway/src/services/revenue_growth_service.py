"""
RevenueGrowth Service — 增收月报（Sprint 4）

聚合各 Agent 贡献的月度增收效果：
1. 唤醒回店营收（MemberAgent → dormant_wakeup → 回店订单）
2. 裂变新客营收（ReferralEngine → 大桌推荐 → 新客消费）
3. 菜品优化毛利（MenuAgent → 明星菜推广/瘦狗菜下架 → 毛利提升）
4. 楼面效率改善（FloorAgent → 翻台率提升 → 营收增长）
5. 各 Agent ¥影响汇总

Sprint 4 KPI: 增收月报可量化 ¥ 影响
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.consumer_identity import ConsumerIdentity
from src.models.order import Order, OrderItem
from src.models.private_domain import PrivateDomainMember
from src.models.reservation import Reservation

logger = logging.getLogger(__name__)


# ── 纯函数 ──────────────────────────────────────────────────────


def compute_revenue_growth(
    current_yuan: float,
    previous_yuan: float,
) -> dict:
    """月环比增长"""
    if previous_yuan <= 0:
        growth_rate = 1.0 if current_yuan > 0 else 0.0
    else:
        growth_rate = round((current_yuan - previous_yuan) / previous_yuan, 4)
    return {
        "current_yuan": round(current_yuan, 2),
        "previous_yuan": round(previous_yuan, 2),
        "delta_yuan": round(current_yuan - previous_yuan, 2),
        "growth_rate": growth_rate,
    }


def compute_agent_contribution(
    wakeup_revenue: float,
    referral_revenue: float,
    margin_improvement: float,
    total_revenue: float,
) -> dict:
    """各Agent贡献占比"""
    agent_total = wakeup_revenue + referral_revenue + margin_improvement
    return {
        "wakeup_revenue_yuan": round(wakeup_revenue, 2),
        "referral_revenue_yuan": round(referral_revenue, 2),
        "margin_improvement_yuan": round(margin_improvement, 2),
        "agent_total_yuan": round(agent_total, 2),
        "agent_contribution_rate": round(agent_total / total_revenue, 4) if total_revenue > 0 else 0.0,
    }


class RevenueGrowthService:
    """增收月报 — 各Agent贡献的¥影响追踪"""

    async def generate_monthly_report(
        self,
        db: AsyncSession,
        store_id: str,
        month_offset: int = 0,
    ) -> dict:
        """
        生成增收月报

        month_offset: 0=本月, -1=上月
        """
        now = datetime.utcnow()
        # 计算目标月份的起止
        target_month = now.month + month_offset
        target_year = now.year
        while target_month <= 0:
            target_month += 12
            target_year -= 1
        while target_month > 12:
            target_month -= 12
            target_year += 1

        month_start = datetime(target_year, target_month, 1)
        if target_month == 12:
            month_end = datetime(target_year + 1, 1, 1)
        else:
            month_end = datetime(target_year, target_month + 1, 1)

        # 上月同期
        prev_year = target_year
        prev_month = target_month - 1
        if prev_month <= 0:
            prev_month += 12
            prev_year -= 1
        prev_start = datetime(prev_year, prev_month, 1)

        # 1. 本月总营收
        current_revenue = await self._get_revenue(db, store_id, month_start, month_end)
        previous_revenue = await self._get_revenue(db, store_id, prev_start, month_start)
        growth = compute_revenue_growth(current_revenue, previous_revenue)

        # 2. 本月订单统计
        order_stats = await db.execute(
            select(
                func.count(Order.id),
                func.count(func.distinct(Order.consumer_id)),
            ).where(
                Order.store_id == store_id,
                Order.order_time >= month_start,
                Order.order_time < month_end,
                Order.status != "cancelled",
            )
        )
        orow = order_stats.one()
        total_orders = orow[0] or 0
        unique_consumers = orow[1] or 0

        # 3. 唤醒回店营收（consumer_id 在唤醒名单中 + 本月有订单）
        wakeup_revenue = await self._estimate_wakeup_revenue(
            db,
            store_id,
            month_start,
            month_end,
        )

        # 4. 新客营收（本月新建 consumer_id 的消费）
        referral_revenue = await self._estimate_new_customer_revenue(
            db,
            store_id,
            month_start,
            month_end,
        )

        # 5. 毛利改善（本月 vs 上月的平均毛利率差 × 营收）
        margin_improvement = await self._estimate_margin_improvement(
            db,
            store_id,
            month_start,
            month_end,
            prev_start,
        )

        # 6. Agent 贡献汇总
        contribution = compute_agent_contribution(
            wakeup_revenue,
            referral_revenue,
            margin_improvement,
            current_revenue,
        )

        return {
            "store_id": store_id,
            "month": f"{target_year}-{target_month:02d}",
            "revenue": growth,
            "total_orders": total_orders,
            "unique_consumers": unique_consumers,
            "avg_ticket_yuan": round(current_revenue / total_orders, 2) if total_orders > 0 else 0.0,
            "agent_contribution": contribution,
            "generated_at": datetime.utcnow().isoformat(),
        }

    async def _get_revenue(
        self,
        db: AsyncSession,
        store_id: str,
        start: datetime,
        end: datetime,
    ) -> float:
        """获取时间段内营收"""
        result = await db.scalar(
            select(func.coalesce(func.sum(Order.total_amount), 0)).where(
                Order.store_id == store_id,
                Order.order_time >= start,
                Order.order_time < end,
                Order.status != "cancelled",
            )
        )
        return float(result or 0)

    async def _estimate_wakeup_revenue(
        self,
        db: AsyncSession,
        store_id: str,
        start: datetime,
        end: datetime,
    ) -> float:
        """
        估算唤醒带来的回店营收

        逻辑：S4/S5 会员在本月有新订单 → 归因为唤醒效果
        """
        stmt = (
            select(func.coalesce(func.sum(Order.total_amount), 0))
            .join(
                PrivateDomainMember,
                and_(
                    PrivateDomainMember.consumer_id == Order.consumer_id,
                    PrivateDomainMember.store_id == store_id,
                ),
            )
            .where(
                Order.store_id == store_id,
                Order.order_time >= start,
                Order.order_time < end,
                Order.status != "cancelled",
                Order.consumer_id.isnot(None),
                PrivateDomainMember.rfm_level.in_(["S4", "S5"]),
            )
        )
        result = await db.scalar(stmt)
        return float(result or 0)

    async def _estimate_new_customer_revenue(
        self,
        db: AsyncSession,
        store_id: str,
        start: datetime,
        end: datetime,
    ) -> float:
        """
        估算新客营收

        逻辑：consumer 创建时间在本月 + 本月有订单
        """
        stmt = (
            select(func.coalesce(func.sum(Order.total_amount), 0))
            .join(
                ConsumerIdentity,
                ConsumerIdentity.id == Order.consumer_id,
            )
            .where(
                Order.store_id == store_id,
                Order.order_time >= start,
                Order.order_time < end,
                Order.status != "cancelled",
                ConsumerIdentity.created_at >= start,
                ConsumerIdentity.created_at < end,
                ConsumerIdentity.is_merged.is_(False),
            )
        )
        result = await db.scalar(stmt)
        return float(result or 0)

    async def _estimate_margin_improvement(
        self,
        db: AsyncSession,
        store_id: str,
        current_start: datetime,
        current_end: datetime,
        prev_start: datetime,
    ) -> float:
        """
        估算毛利改善¥影响

        公式：(本月均毛利率 - 上月均毛利率) × 本月营收
        """

        async def _avg_margin(start, end):
            result = await db.scalar(
                select(func.avg(OrderItem.gross_margin))
                .join(Order, Order.id == OrderItem.order_id)
                .where(
                    Order.store_id == store_id,
                    Order.order_time >= start,
                    Order.order_time < end,
                    Order.status != "cancelled",
                    OrderItem.gross_margin.isnot(None),
                )
            )
            return float(result or 0)

        current_margin = await _avg_margin(current_start, current_end)
        prev_margin = await _avg_margin(prev_start, current_start)

        if current_margin <= prev_margin:
            return 0.0  # 没有改善则不计入

        current_revenue = await self._get_revenue(db, store_id, current_start, current_end)
        return round((current_margin - prev_margin) * current_revenue, 2)


# 全局单例
revenue_growth_service = RevenueGrowthService()
