"""
StoreAgent Service — 门店经营综合智能（Sprint 5）

9-Agent 终态中的 StoreAgent，核心能力：
1. 门店健康评分（5维度：营收/成本/会员/楼面/菜品）
2. 跨门店排名（哪家店最需要关注）
3. 趋势分析（本周 vs 上周，本月 vs 上月）
4. 综合经营建议（Top3 最该做的事）

定位：老板的全局经营驾驶舱
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.consumer_identity import ConsumerIdentity
from src.models.inventory import InventoryItem
from src.models.order import Order, OrderItem
from src.models.private_domain import PrivateDomainMember
from src.models.waste_event import WasteEvent

logger = logging.getLogger(__name__)


# ── 纯函数 ──────────────────────────────────────────────────────


def compute_store_health_score(
    revenue_score: float,
    cost_score: float,
    member_score: float,
    floor_score: float,
    menu_score: float,
) -> float:
    """
    门店健康评分（0-100，加权平均）

    权重：营收30% + 成本25% + 会员20% + 楼面15% + 菜品10%
    """
    score = revenue_score * 0.30 + cost_score * 0.25 + member_score * 0.20 + floor_score * 0.15 + menu_score * 0.10
    return round(min(max(score, 0), 100), 1)


def classify_store_status(health_score: float) -> str:
    """
    门店状态分级

    excellent: ≥ 80
    good: 60-80
    warning: 40-60
    critical: < 40
    """
    if health_score >= 80:
        return "excellent"
    if health_score >= 60:
        return "good"
    if health_score >= 40:
        return "warning"
    return "critical"


def _revenue_score(growth_rate: float) -> float:
    """营收维度评分：增长>10%=100, 0%=60, 下降>10%=20"""
    if growth_rate >= 0.10:
        return 100.0
    if growth_rate >= 0:
        return 60 + growth_rate * 400  # 0%→60, 10%→100
    if growth_rate >= -0.10:
        return 60 + growth_rate * 400  # -10%→20
    return 20.0


def _cost_score(cost_rate: float) -> float:
    """成本维度评分：<30%=100, 35%=60, >40%=20"""
    if cost_rate <= 0.30:
        return 100.0
    if cost_rate <= 0.35:
        return 100 - (cost_rate - 0.30) / 0.05 * 40  # 30%→100, 35%→60
    if cost_rate <= 0.40:
        return 60 - (cost_rate - 0.35) / 0.05 * 40  # 35%→60, 40%→20
    return 20.0


def _member_score(s1_s2_rate: float) -> float:
    """会员维度评分：S1+S2占比>40%=100, 20%=60, <10%=20"""
    if s1_s2_rate >= 0.40:
        return 100.0
    if s1_s2_rate >= 0.20:
        return 60 + (s1_s2_rate - 0.20) / 0.20 * 40
    if s1_s2_rate >= 0.10:
        return 20 + (s1_s2_rate - 0.10) / 0.10 * 40
    return 20.0


class StoreAgentService:
    """StoreAgent — 门店经营综合智能"""

    async def get_store_scorecard(
        self,
        db: AsyncSession,
        store_id: str,
        days: int = 7,
    ) -> dict:
        """
        门店经营记分卡

        5维度评分 + 综合健康分 + Top3建议
        """
        cutoff = datetime.utcnow() - timedelta(days=days)
        prev_cutoff = cutoff - timedelta(days=days)

        # 1. 营收维度
        current_rev = await self._get_revenue(db, store_id, cutoff)
        prev_rev = await self._get_revenue(db, store_id, prev_cutoff, cutoff)
        growth_rate = (current_rev - prev_rev) / prev_rev if prev_rev > 0 else 0.0
        rev_score = _revenue_score(growth_rate)

        # 2. 成本维度
        food_cost_fen = (
            await db.scalar(
                select(func.coalesce(func.sum(OrderItem.food_cost_actual), 0))
                .join(Order, Order.id == OrderItem.order_id)
                .where(
                    Order.store_id == store_id,
                    Order.order_time >= cutoff,
                    Order.status != "cancelled",
                    OrderItem.food_cost_actual.isnot(None),
                )
            )
            or 0
        )
        cost_rate = (float(food_cost_fen) / 100) / current_rev if current_rev > 0 else 0.0
        c_score = _cost_score(cost_rate)

        # 3. 会员维度
        member_stats = await db.execute(
            select(
                func.count(PrivateDomainMember.id),
                func.count(
                    case(
                        (PrivateDomainMember.rfm_level.in_(["S1", "S2"]), 1),
                    )
                ),
            ).where(
                PrivateDomainMember.store_id == store_id,
                PrivateDomainMember.is_active.is_(True),
            )
        )
        mrow = member_stats.one()
        total_members = mrow[0] or 0
        s1_s2 = mrow[1] or 0
        s1_s2_rate = s1_s2 / total_members if total_members > 0 else 0.0
        m_score = _member_score(s1_s2_rate)

        # 4. 楼面维度（翻台率 → 评分）
        order_count = (
            await db.scalar(
                select(func.count(Order.id)).where(
                    Order.store_id == store_id,
                    Order.order_time >= cutoff,
                    Order.status != "cancelled",
                    Order.table_number.isnot(None),
                )
            )
            or 0
        )
        tables = (
            await db.scalar(
                select(func.count(func.distinct(Order.table_number))).where(
                    Order.store_id == store_id,
                    Order.order_time >= cutoff,
                    Order.table_number.isnot(None),
                )
            )
            or 1
        )
        turnover = order_count / (tables * max(days, 1))
        f_score = min(turnover / 2.5 * 100, 100)  # 2.5翻台=满分

        # 5. 菜品维度（平均毛利率 → 评分）
        avg_margin = await db.scalar(
            select(func.avg(OrderItem.gross_margin))
            .join(Order, Order.id == OrderItem.order_id)
            .where(
                Order.store_id == store_id,
                Order.order_time >= cutoff,
                Order.status != "cancelled",
                OrderItem.gross_margin.isnot(None),
            )
        )
        margin = float(avg_margin or 0.5)
        menu_score = min(margin / 0.65 * 100, 100)  # 65%毛利=满分

        # 综合评分
        health = compute_store_health_score(rev_score, c_score, m_score, f_score, menu_score)
        status = classify_store_status(health)

        # Top3 建议
        suggestions = self._generate_suggestions(
            growth_rate,
            cost_rate,
            s1_s2_rate,
            turnover,
            margin,
        )

        return {
            "store_id": store_id,
            "period_days": days,
            "health_score": health,
            "status": status,
            "dimensions": {
                "revenue": {
                    "score": round(rev_score, 1),
                    "growth_rate": round(growth_rate, 4),
                    "current_yuan": round(current_rev, 2),
                },
                "cost": {"score": round(c_score, 1), "cost_rate": round(cost_rate, 4)},
                "member": {"score": round(m_score, 1), "s1_s2_rate": round(s1_s2_rate, 4), "total_members": total_members},
                "floor": {"score": round(f_score, 1), "turnover_rate": round(turnover, 2)},
                "menu": {"score": round(menu_score, 1), "avg_margin": round(margin, 4)},
            },
            "top3_suggestions": suggestions,
        }

    async def get_cross_store_ranking(
        self,
        db: AsyncSession,
        store_ids: Optional[List[str]] = None,
        days: int = 7,
    ) -> List[dict]:
        """
        跨门店排名（按营收排序）

        返回各门店的营收 + 订单数 + 客单价
        """
        cutoff = datetime.utcnow() - timedelta(days=days)

        where = [
            Order.order_time >= cutoff,
            Order.status != "cancelled",
        ]
        if store_ids:
            where.append(Order.store_id.in_(store_ids))

        stmt = (
            select(
                Order.store_id,
                func.count(Order.id),
                func.coalesce(func.sum(Order.total_amount), 0),
                func.count(func.distinct(Order.consumer_id)),
            )
            .where(and_(*where))
            .group_by(Order.store_id)
            .order_by(func.sum(Order.total_amount).desc())
        )
        result = await db.execute(stmt)

        stores = []
        for row in result.all():
            orders = row[1] or 0
            revenue = float(row[2] or 0)
            stores.append(
                {
                    "store_id": row[0],
                    "order_count": orders,
                    "revenue_yuan": round(revenue, 2),
                    "avg_ticket_yuan": round(revenue / orders, 2) if orders > 0 else 0.0,
                    "unique_consumers": row[3] or 0,
                }
            )
        return stores

    async def _get_revenue(
        self,
        db: AsyncSession,
        store_id: str,
        start: datetime,
        end: Optional[datetime] = None,
    ) -> float:
        where = [
            Order.store_id == store_id,
            Order.order_time >= start,
            Order.status != "cancelled",
        ]
        if end:
            where.append(Order.order_time < end)
        result = await db.scalar(select(func.coalesce(func.sum(Order.total_amount), 0)).where(and_(*where)))
        return float(result or 0)

    def _generate_suggestions(
        self,
        growth_rate: float,
        cost_rate: float,
        s1_s2_rate: float,
        turnover: float,
        margin: float,
    ) -> List[str]:
        """生成 Top3 经营建议"""
        issues = []
        if growth_rate < 0:
            issues.append((-growth_rate, f"营收下滑{abs(growth_rate)*100:.1f}%，建议加大会员唤醒和裂变推广"))
        if cost_rate > 0.35:
            issues.append((cost_rate, f"食材成本率{cost_rate*100:.1f}%偏高，建议检查高销量低毛利菜品"))
        if s1_s2_rate < 0.20:
            issues.append((1 - s1_s2_rate, f"高价值会员占比仅{s1_s2_rate*100:.1f}%，建议加强S3→S2转化"))
        if turnover < 1.5:
            issues.append((1 / max(turnover, 0.1), f"翻台率{turnover:.1f}偏低，建议优化用餐时长管理"))
        if margin < 0.55:
            issues.append((1 - margin, f"菜品平均毛利{margin*100:.1f}%，建议推广明星高毛利菜品"))

        issues.sort(key=lambda x: x[0], reverse=True)
        return [s[1] for s in issues[:3]]


# 全局单例
store_agent_service = StoreAgentService()
