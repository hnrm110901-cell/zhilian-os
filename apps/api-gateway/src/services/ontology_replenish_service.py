"""
时序预测备货建议（P1）：结合 90 天历史预测、图谱 BOM、损耗缓冲，输出食材级备货建议。
与 L2 本体（BOM/Ingredient）、L3 损耗推理联动。
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.order import Order, OrderItem
from src.ontology import get_ontology_repository
from src.services.prophet_forecast_service import prophet_forecast_service


# 默认每单约几份菜（用于将订单量转为菜品份数）
DEFAULT_SERVINGS_PER_ORDER = float(__import__("os").getenv("REPLENISH_SERVINGS_PER_ORDER", "2.5"))
# 损耗缓冲系数（1.05 = 多备 5%）
DEFAULT_WASTE_BUFFER = float(__import__("os").getenv("REPLENISH_WASTE_BUFFER", "1.05"))


async def get_replenish_suggestion(
    session: AsyncSession,
    store_id: str,
    target_date: date,
    horizon_days: int = 1,
    waste_buffer: float = DEFAULT_WASTE_BUFFER,
    servings_per_order: float = DEFAULT_SERVINGS_PER_ORDER,
) -> Dict[str, Any]:
    """
    基于时序预测 + 图谱 BOM + 损耗缓冲，计算目标日（及可选未来几日）的食材备货建议。

    步骤：
    1. 用 Prophet 预测目标日订单量（基于近 90 天历史）。
    2. 从图谱取该门店菜品列表及每道菜的 BOM 用料。
    3. 用历史订单结构估算每道菜份数，汇总各食材需求量。
    4. 应用损耗缓冲系数，输出建议备货量。
    """
    repo = get_ontology_repository()
    if not repo:
        return {
            "store_id": store_id,
            "target_date": target_date.isoformat(),
            "suggestions": [],
            "message": "Neo4j 未启用，无法读取 BOM",
            "forecast_orders": None,
        }

    # 1) 预测订单量：从 PG 拉近 90 天订单量历史，预测目标日
    since = date.today() - timedelta(days=90)
    result = await session.execute(
        select(
            func.date(Order.order_time).label("dt"),
            func.count(Order.id).label("cnt"),
        )
        .where(
            Order.store_id == store_id,
            func.date(Order.order_time) >= since,
        )
        .group_by(func.date(Order.order_time))
        .order_by(func.date(Order.order_time))
    )
    history = [{"date": str(row.dt), "value": float(row.cnt)} for row in result.all()]

    if len(history) < 7:
        return {
            "store_id": store_id,
            "target_date": target_date.isoformat(),
            "suggestions": [],
            "message": "历史订单数据不足 7 天，无法预测",
            "forecast_orders": None,
        }

    forecast_result = await prophet_forecast_service.forecast(
        store_id=store_id,
        history=history,
        horizon_days=max(horizon_days, (target_date - date.today()).days + 1),
        metric="orders",
    )
    forecasts = forecast_result.get("forecasts") or []
    # 取目标日预测值
    pred_orders = None
    for f in forecasts:
        if f.get("date") == target_date.isoformat():
            pred_orders = f.get("predicted")
            break
    if pred_orders is None and forecasts:
        pred_orders = forecasts[0].get("predicted")
    if pred_orders is None:
        pred_orders = sum(h["value"] for h in history) / len(history)

    # 2) 图谱：门店菜品列表
    dish_ids = repo.get_store_dish_ids(store_id)
    if not dish_ids:
        return {
            "store_id": store_id,
            "target_date": target_date.isoformat(),
            "suggestions": [],
            "message": "图谱中无该门店菜品或 BOM，请先执行 /ontology/sync-from-pg 与 BOM 录入",
            "forecast_orders": round(pred_orders, 2),
        }

    # 3) 每道菜份数：简化按历史 OrderItem 占比，若无则均分
    total_servings = pred_orders * servings_per_order
    dish_servings: Dict[str, float] = {}
    result = await session.execute(
        select(OrderItem.item_id, func.sum(OrderItem.quantity).label("q"))
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            Order.store_id == store_id,
            func.date(Order.order_time) >= since,
        )
        .group_by(OrderItem.item_id)
    )
    rows = result.all()
    total_item_q = sum(r.q or 0 for r in rows)
    if total_item_q and total_item_q > 0:
        for r in rows:
            item_id = str(r.item_id)
            if item_id in dish_ids or not dish_servings:
                dish_servings[item_id] = (r.q or 0) / total_item_q * total_servings
    if not dish_servings:
        per_dish = total_servings / len(dish_ids) if dish_ids else 0
        dish_servings = {did: per_dish for did in dish_ids}

    # 4) 按 BOM 汇总食材需求量
    ing_need: Dict[str, Dict[str, Any]] = {}
    for dish_id in dish_ids:
        servings = dish_servings.get(dish_id, total_servings / len(dish_ids))
        for row in repo.get_dish_bom_ingredients(dish_id):
            ing_id = str(row.get("ing_id", ""))
            if not ing_id:
                continue
            qty = float(row.get("qty") or 0)
            unit = str(row.get("unit") or "")
            need = servings * qty
            if ing_id not in ing_need:
                ing_need[ing_id] = {"ing_id": ing_id, "unit": unit, "qty": 0.0}
            ing_need[ing_id]["qty"] += need

    # 5) 应用损耗缓冲
    suggestions: List[Dict[str, Any]] = []
    for ing_id, data in ing_need.items():
        qty = data["qty"] * waste_buffer
        suggestions.append({
            "ingredient_id": ing_id,
            "unit": data["unit"],
            "suggested_qty": round(qty, 2),
            "source": "forecast+bom+waste_buffer",
        })

    return {
        "store_id": store_id,
        "target_date": target_date.isoformat(),
        "forecast_orders": round(pred_orders, 2),
        "servings_per_order": servings_per_order,
        "waste_buffer": waste_buffer,
        "dishes_count": len(dish_ids),
        "suggestions": suggestions,
        "message": "ok",
    }
