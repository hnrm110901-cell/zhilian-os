"""
CostAgent Service — 成本经营智能（Sprint 5）

9-Agent 终态中的 CostAgent，核心能力：
1. 食材成本率追踪（日/周/月维度）
2. 损耗率分析（按类型归因）
3. 品类成本结构（肉类/蔬菜/海鲜/调料占比）
4. CDP增强：高价值客户的成本投入 ROI

定位：老板和厨师长的成本管控仪表盘
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.inventory import InventoryItem, InventoryTransaction, TransactionType
from src.models.order import Order, OrderItem
from src.models.private_domain import PrivateDomainMember
from src.models.waste_event import WasteEvent

logger = logging.getLogger(__name__)


# ── 纯函数 ──────────────────────────────────────────────────────


def compute_food_cost_rate(
    food_cost_yuan: float,
    revenue_yuan: float,
) -> float:
    """
    食材成本率 = 食材成本 / 营收

    行业基准：30%-38%（正餐），<30%优秀，>40%预警
    """
    if revenue_yuan <= 0:
        return 0.0
    return round(food_cost_yuan / revenue_yuan, 4)


def classify_cost_health(cost_rate: float) -> str:
    """
    成本健康度分级

    excellent: < 30%
    good: 30%-35%
    warning: 35%-40%
    critical: > 40%
    """
    if cost_rate < 0.30:
        return "excellent"
    if cost_rate < 0.35:
        return "good"
    if cost_rate < 0.40:
        return "warning"
    return "critical"


def compute_waste_rate(
    waste_cost_yuan: float,
    total_usage_yuan: float,
) -> float:
    """
    损耗率 = 损耗成本 / 总用料成本

    行业基准：2%-5%，>5%需要干预
    """
    if total_usage_yuan <= 0:
        return 0.0
    return round(waste_cost_yuan / total_usage_yuan, 4)


def estimate_cost_saving(
    current_rate: float,
    target_rate: float,
    monthly_revenue_yuan: float,
) -> dict:
    """
    估算成本优化¥影响

    每降低1%成本率 = 月营收 × 1% 直接利润提升
    """
    if current_rate <= target_rate:
        return {"monthly_saving_yuan": 0.0, "annual_saving_yuan": 0.0, "gap_pct": 0.0}
    gap = current_rate - target_rate
    monthly = round(gap * monthly_revenue_yuan, 2)
    return {
        "monthly_saving_yuan": monthly,
        "annual_saving_yuan": round(monthly * 12, 2),
        "gap_pct": round(gap * 100, 2),
    }


class CostAgentService:
    """CostAgent — 成本经营智能"""

    async def get_cost_dashboard(
        self,
        db: AsyncSession,
        store_id: str,
        days: int = 30,
    ) -> dict:
        """
        成本综合仪表盘

        返回：食材成本率 + 健康度 + 损耗率 + 优化空间¥
        """
        cutoff = datetime.utcnow() - timedelta(days=days)

        # 营收
        revenue = await db.scalar(
            select(func.coalesce(func.sum(Order.total_amount), 0)).where(
                Order.store_id == store_id,
                Order.order_time >= cutoff,
                Order.status != "cancelled",
            )
        )
        revenue_yuan = float(revenue or 0)

        # 食材成本（从 OrderItem.food_cost_actual 聚合，单位：分）
        food_cost_fen = await db.scalar(
            select(func.coalesce(func.sum(OrderItem.food_cost_actual), 0))
            .join(Order, Order.id == OrderItem.order_id)
            .where(
                Order.store_id == store_id,
                Order.order_time >= cutoff,
                Order.status != "cancelled",
                OrderItem.food_cost_actual.isnot(None),
            )
        )
        food_cost_yuan = float(food_cost_fen or 0) / 100

        # 成本率
        cost_rate = compute_food_cost_rate(food_cost_yuan, revenue_yuan)
        health = classify_cost_health(cost_rate)

        # 损耗统计（quantity × ingredient.unit_cost）
        waste_cost_fen = await db.scalar(
            select(func.coalesce(func.sum(WasteEvent.quantity * InventoryItem.unit_cost), 0))
            .join(InventoryItem, InventoryItem.id == WasteEvent.ingredient_id)
            .where(
                WasteEvent.store_id == store_id,
                WasteEvent.occurred_at >= cutoff,
            )
        )
        waste_cost_yuan = float(waste_cost_fen or 0) / 100
        waste_rate = compute_waste_rate(waste_cost_yuan, food_cost_yuan)

        # 优化空间
        monthly_revenue = revenue_yuan / max(days, 1) * 30
        saving = estimate_cost_saving(cost_rate, 0.32, monthly_revenue)

        return {
            "period_days": days,
            "revenue_yuan": round(revenue_yuan, 2),
            "food_cost_yuan": round(food_cost_yuan, 2),
            "cost_rate": cost_rate,
            "cost_health": health,
            "waste_cost_yuan": round(waste_cost_yuan, 2),
            "waste_rate": waste_rate,
            "optimization": saving,
        }

    async def get_cost_by_category(
        self,
        db: AsyncSession,
        store_id: str,
        days: int = 30,
    ) -> List[dict]:
        """
        按品类的成本结构

        返回：各食材品类的成本占比
        """
        cutoff = datetime.utcnow() - timedelta(days=days)

        stmt = (
            select(
                InventoryItem.category,
                func.count(InventoryTransaction.id),
                func.coalesce(func.sum(InventoryTransaction.quantity * InventoryItem.unit_cost), 0),
            )
            .join(InventoryItem, InventoryItem.id == InventoryTransaction.item_id)
            .where(
                InventoryTransaction.store_id == store_id,
                InventoryTransaction.transaction_type == TransactionType.USAGE.value,
                InventoryTransaction.created_at >= cutoff,
            )
            .group_by(InventoryItem.category)
            .order_by(func.sum(InventoryTransaction.quantity * InventoryItem.unit_cost).desc())
        )
        result = await db.execute(stmt)
        rows = result.all()

        total_cost = sum(float(r[2] or 0) for r in rows)
        categories = []
        for row in rows:
            cost = float(row[2] or 0)
            categories.append(
                {
                    "category": row[0] or "未分类",
                    "transaction_count": row[1],
                    "cost_yuan": round(cost / 100, 2),
                    "percentage": round(cost / total_cost, 4) if total_cost > 0 else 0.0,
                }
            )
        return categories

    async def get_waste_analysis(
        self,
        db: AsyncSession,
        store_id: str,
        days: int = 30,
    ) -> dict:
        """
        损耗类型分析

        按 WasteEventType 归因
        """
        cutoff = datetime.utcnow() - timedelta(days=days)

        stmt = (
            select(
                WasteEvent.event_type,
                func.count(WasteEvent.id),
                func.coalesce(func.sum(WasteEvent.quantity * InventoryItem.unit_cost), 0),
            )
            .join(InventoryItem, InventoryItem.id == WasteEvent.ingredient_id)
            .where(
                WasteEvent.store_id == store_id,
                WasteEvent.occurred_at >= cutoff,
            )
            .group_by(WasteEvent.event_type)
            .order_by(func.sum(WasteEvent.quantity * InventoryItem.unit_cost).desc())
        )
        result = await db.execute(stmt)

        breakdown = []
        total_events = 0
        total_cost = 0
        for row in result.all():
            cost = float(row[2] or 0)
            breakdown.append(
                {
                    "type": row[0],
                    "count": row[1],
                    "cost_yuan": round(cost / 100, 2),
                }
            )
            total_events += row[1]
            total_cost += cost

        return {
            "total_events": total_events,
            "total_cost_yuan": round(total_cost / 100, 2),
            "breakdown": breakdown,
            "top_action": breakdown[0]["type"] if breakdown else None,
        }


# 全局单例
cost_agent_service = CostAgentService()
