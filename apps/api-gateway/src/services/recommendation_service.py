"""
经营推荐服务 — 门店级别推荐
基于销售速度 + 库存状态，推荐：
  - 推广菜品（高需求 + 有库存）
  - 下架/减产菜品（低销量 + 高库存占压）
  - 今日特推（将到期库存的菜品）

设计准则（CLAUDE.md 规则6）：
  每条建议必须包含 建议动作 + 预期¥影响 + 置信度
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

import structlog

logger = structlog.get_logger()


class RecommendAction(str, Enum):
    PROMOTE = "promote"  # 重点推广
    BUNDLE = "bundle"  # 搭配套餐
    DISCOUNT = "discount"  # 限时折扣（库存即将到期）
    REDUCE = "reduce"  # 减少产量
    RETIRE = "retire"  # 建议下架


@dataclass
class DishRecommendation:
    dish_id: str
    dish_name: str
    action: RecommendAction
    reason: str  # 简短理由
    expected_revenue_impact: float  # 预期¥影响（正=增收，负=减损）
    confidence: float  # 0-1 置信度
    priority: int  # 1=最高优先级
    tags: List[str] = field(default_factory=list)


def generate_store_recommendations(
    store_id: str,
    sales_data: Optional[List[dict]] = None,
    inventory_data: Optional[List[dict]] = None,
) -> List[DishRecommendation]:
    """
    基于门店销售数据和库存数据生成推荐列表。

    sales_data 期望字段: dish_id, dish_name, qty_sold_7d, revenue_7d, avg_daily_qty
    inventory_data 期望字段: dish_id, dish_name, stock_qty, days_until_expiry, cost_per_unit
    """
    recs: List[DishRecommendation] = []

    # ── 1. 推广高销量菜品 ──
    if sales_data:
        top_dishes = sorted(sales_data, key=lambda d: d.get("revenue_7d", 0), reverse=True)[:3]
        for rank, dish in enumerate(top_dishes):
            revenue = float(dish.get("revenue_7d", 0))
            if revenue > 0:
                recs.append(
                    DishRecommendation(
                        dish_id=dish.get("dish_id", ""),
                        dish_name=dish.get("dish_name", "未知菜品"),
                        action=RecommendAction.PROMOTE,
                        reason=f"近7天营收 ¥{revenue:.0f}，为门店TOP{rank+1}菜品",
                        expected_revenue_impact=revenue * 0.15,  # 推广预计提升15%
                        confidence=0.82 - rank * 0.05,
                        priority=rank + 1,
                        tags=["高销量", "主推"],
                    )
                )

    # ── 2. 低销量高库存→减产或下架 ──
    if sales_data and inventory_data:
        inv_map = {d["dish_id"]: d for d in inventory_data if "dish_id" in d}
        slow_movers = [d for d in sales_data if d.get("avg_daily_qty", 999) < 2 and d.get("dish_id") in inv_map]
        for dish in slow_movers[:2]:
            inv = inv_map[dish["dish_id"]]
            stock = float(inv.get("stock_qty", 0))
            cost = float(inv.get("cost_per_unit", 0))
            waste_cost = stock * cost * 0.3  # 假设30%会浪费
            recs.append(
                DishRecommendation(
                    dish_id=dish.get("dish_id", ""),
                    dish_name=dish.get("dish_name", "未知菜品"),
                    action=RecommendAction.REDUCE,
                    reason=f"日均销量 {dish.get('avg_daily_qty', 0):.1f} 份，库存 {stock:.0f} 件，存在积压风险",
                    expected_revenue_impact=-waste_cost,  # 减少损耗即减少成本
                    confidence=0.75,
                    priority=4,
                    tags=["低销量", "库存积压"],
                )
            )

    # ── 3. 即将到期库存→限时折扣促销 ──
    if inventory_data:
        expiring = [d for d in inventory_data if 0 < d.get("days_until_expiry", 99) <= 2]
        for dish in expiring[:2]:
            stock = float(dish.get("stock_qty", 0))
            cost = float(dish.get("cost_per_unit", 0))
            potential_save = stock * cost * 0.8  # 打折后挽回80%成本
            recs.append(
                DishRecommendation(
                    dish_id=dish.get("dish_id", ""),
                    dish_name=dish.get("dish_name", "未知菜品"),
                    action=RecommendAction.DISCOUNT,
                    reason=f"库存 {stock:.0f} 件将在 {dish.get('days_until_expiry')} 天内到期",
                    expected_revenue_impact=potential_save,
                    confidence=0.90,
                    priority=2,
                    tags=["即将到期", "限时折扣"],
                )
            )

    # 按优先级排序
    recs.sort(key=lambda r: (r.priority, -r.confidence))
    logger.info("生成推荐完成", store_id=store_id, count=len(recs))
    return recs
