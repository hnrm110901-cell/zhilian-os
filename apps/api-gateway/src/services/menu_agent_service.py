"""
MenuAgent Service — 菜品经营智能（Sprint 4）

9-Agent 终态中的 MenuAgent，核心能力：
1. 菜品星级分类（明星/金牛/问号/瘦狗 — BCG矩阵）
2. 菜品组合关联（经常一起点的菜 → 推荐套餐）
3. CDP增强洞察（哪些菜带来S1高价值客户）
4. 毛利优化建议（低毛利高销量菜品 → 调价/换料建议）

定位：老板和厨师长的菜品决策助手
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.consumer_identity import ConsumerIdentity
from src.models.order import Order, OrderItem
from src.models.private_domain import PrivateDomainMember

logger = logging.getLogger(__name__)


# ── 纯函数 ──────────────────────────────────────────────────────


def classify_dish_star(
    sales_rank_pct: float,
    margin_pct: float,
) -> str:
    """
    BCG菜品矩阵分类

    sales_rank_pct: 销量百分位（0-1，1=最高）
    margin_pct: 毛利率（0-1）

    返回：star(明星)/cash_cow(金牛)/question(问号)/dog(瘦狗)
    """
    high_sales = sales_rank_pct >= 0.5
    high_margin = margin_pct >= 0.6

    if high_sales and high_margin:
        return "star"  # 明星：高销量高毛利 → 保持
    if high_sales and not high_margin:
        return "cash_cow"  # 金牛：高销量低毛利 → 优化成本
    if not high_sales and high_margin:
        return "question"  # 问号：低销量高毛利 → 推广
    return "dog"  # 瘦狗：低销量低毛利 → 考虑下架


def compute_combo_affinity(
    co_occurrence: int,
    dish_a_total: int,
    dish_b_total: int,
) -> float:
    """
    菜品组合关联度（Jaccard-like）

    affinity = 共同出现次数 / (A总数 + B总数 - 共同次数)
    """
    denominator = dish_a_total + dish_b_total - co_occurrence
    if denominator <= 0:
        return 0.0
    return round(co_occurrence / denominator, 4)


def estimate_margin_impact(
    current_margin: float,
    target_margin: float,
    monthly_sales: int,
    avg_price_yuan: float,
) -> dict:
    """
    毛利优化¥影响估算

    返回：调整前后每月毛利差额
    """
    current_profit = monthly_sales * avg_price_yuan * current_margin
    target_profit = monthly_sales * avg_price_yuan * target_margin
    delta = target_profit - current_profit
    return {
        "current_monthly_profit_yuan": round(current_profit, 2),
        "target_monthly_profit_yuan": round(target_profit, 2),
        "monthly_delta_yuan": round(delta, 2),
        "annual_delta_yuan": round(delta * 12, 2),
    }


class MenuAgentService:
    """MenuAgent — 菜品经营智能"""

    async def get_menu_dashboard(
        self,
        db: AsyncSession,
        store_id: str,
        days: int = 30,
    ) -> dict:
        """
        菜品经营仪表盘

        返回：总菜品数 + 各星级分布 + Top10 明星菜 + 低毛利预警
        """
        cutoff = datetime.utcnow() - timedelta(days=days)

        # 按菜品聚合：销量 + 营收 + 平均毛利
        stmt = (
            select(
                OrderItem.item_id,
                OrderItem.item_name,
                func.sum(OrderItem.quantity).label("total_qty"),
                func.sum(OrderItem.subtotal).label("total_revenue"),
                func.avg(OrderItem.gross_margin).label("avg_margin"),
            )
            .join(Order, Order.id == OrderItem.order_id)
            .where(
                Order.store_id == store_id,
                Order.order_time >= cutoff,
                Order.status != "cancelled",
            )
            .group_by(OrderItem.item_id, OrderItem.item_name)
            .order_by(func.sum(OrderItem.quantity).desc())
        )
        result = await db.execute(stmt)
        rows = result.all()

        if not rows:
            return {
                "total_dishes": 0,
                "star_distribution": {"star": 0, "cash_cow": 0, "question": 0, "dog": 0},
                "top_dishes": [],
                "low_margin_alerts": [],
            }

        # 计算销量百分位
        total_dishes = len(rows)
        star_dist = {"star": 0, "cash_cow": 0, "question": 0, "dog": 0}
        dishes = []

        for rank, row in enumerate(rows):
            sales_pct = 1.0 - (rank / total_dishes)  # 排名越前百分位越高
            margin = float(row[4] or 0)
            star = classify_dish_star(sales_pct, margin)
            star_dist[star] += 1

            dishes.append(
                {
                    "item_id": row[0],
                    "item_name": row[1],
                    "total_qty": row[2],
                    "total_revenue_yuan": round(float(row[3] or 0), 2),
                    "avg_margin": round(margin, 4),
                    "star_class": star,
                    "sales_rank": rank + 1,
                }
            )

        # 低毛利预警（金牛菜：高销量低毛利）
        low_margin = [d for d in dishes if d["star_class"] == "cash_cow"][:5]

        return {
            "period_days": days,
            "total_dishes": total_dishes,
            "star_distribution": star_dist,
            "top_dishes": dishes[:10],
            "low_margin_alerts": low_margin,
        }

    async def get_dish_cdp_insights(
        self,
        db: AsyncSession,
        store_id: str,
        days: int = 30,
    ) -> List[dict]:
        """
        CDP增强菜品洞察：哪些菜品带来高价值客户（S1/S2）

        交叉分析：OrderItem × Order.consumer_id × PrivateDomainMember.rfm_level
        """
        cutoff = datetime.utcnow() - timedelta(days=days)

        stmt = (
            select(
                OrderItem.item_id,
                OrderItem.item_name,
                func.count(func.distinct(Order.consumer_id)).label("unique_consumers"),
                func.count(
                    func.distinct(
                        case(
                            (PrivateDomainMember.rfm_level.in_(["S1", "S2"]), Order.consumer_id),
                        )
                    )
                ).label("vip_consumers"),
                func.sum(OrderItem.quantity).label("total_qty"),
            )
            .join(Order, Order.id == OrderItem.order_id)
            .outerjoin(
                PrivateDomainMember,
                and_(
                    PrivateDomainMember.consumer_id == Order.consumer_id,
                    PrivateDomainMember.store_id == store_id,
                ),
            )
            .where(
                Order.store_id == store_id,
                Order.order_time >= cutoff,
                Order.status != "cancelled",
                Order.consumer_id.isnot(None),
            )
            .group_by(OrderItem.item_id, OrderItem.item_name)
            .order_by(
                func.count(
                    func.distinct(
                        case(
                            (PrivateDomainMember.rfm_level.in_(["S1", "S2"]), Order.consumer_id),
                        )
                    )
                ).desc()
            )
            .limit(20)
        )
        result = await db.execute(stmt)

        insights = []
        for row in result.all():
            unique = row[2] or 0
            vip = row[3] or 0
            vip_rate = round(vip / unique, 4) if unique > 0 else 0.0
            insights.append(
                {
                    "item_id": row[0],
                    "item_name": row[1],
                    "unique_consumers": unique,
                    "vip_consumers": vip,
                    "vip_rate": vip_rate,
                    "total_qty": row[4],
                    "is_vip_magnet": vip_rate >= 0.3,
                }
            )
        return insights

    async def get_combo_recommendations(
        self,
        db: AsyncSession,
        store_id: str,
        days: int = 30,
        limit: int = 10,
    ) -> List[dict]:
        """
        菜品组合推荐（经常一起点的菜对）

        基于同一订单中的菜品共现计算关联度
        """
        cutoff = datetime.utcnow() - timedelta(days=days)

        # 找同一订单中的菜品对
        a = OrderItem.__table__.alias("a")
        b = OrderItem.__table__.alias("b")

        stmt = (
            select(
                a.c.item_name.label("dish_a"),
                b.c.item_name.label("dish_b"),
                func.count().label("co_count"),
            )
            .join(Order, Order.id == a.c.order_id)
            .join(
                b,
                and_(
                    a.c.order_id == b.c.order_id,
                    a.c.item_id < b.c.item_id,
                ),
            )
            .where(
                Order.store_id == store_id,
                Order.order_time >= cutoff,
                Order.status != "cancelled",
            )
            .group_by(a.c.item_name, b.c.item_name)
            .having(func.count() >= 3)
            .order_by(func.count().desc())
            .limit(limit)
        )
        result = await db.execute(stmt)

        combos = []
        for row in result.all():
            combos.append(
                {
                    "dish_a": row[0],
                    "dish_b": row[1],
                    "co_occurrence": row[2],
                    "suggestion": f"推荐组合：{row[0]} + {row[1]}（{row[2]}次同点）",
                }
            )
        return combos


# 全局单例
menu_agent_service = MenuAgentService()
