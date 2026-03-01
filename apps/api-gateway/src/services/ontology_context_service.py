"""
图谱上下文服务：为决策校验与 Agent 提供从图谱拉取的上下文（BOM、库存快照、损耗摘要）
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from src.ontology import get_ontology_repository


async def get_ontology_facts_for_decision(
    store_id: str,
    decision_type: str,
    tenant_id: str = "",
) -> Dict[str, Any]:
    """
    为决策校验拉取图谱事实：BOM 用料、近期库存快照摘要、近期损耗 TOP3。
    供 decision_validator 的 context 使用。
    """
    repo = get_ontology_repository()
    if not repo:
        return {"enabled": False, "reason": "Neo4j 未启用"}

    out: Dict[str, Any] = {"enabled": True, "store_id": store_id}

    # 近期库存快照摘要（最近 7 天）
    end = datetime.now()
    start = end - timedelta(days=7)
    ts_start = start.strftime("%Y-%m-%dT00:00:00")
    ts_end = end.strftime("%Y-%m-%dT23:59:59")
    snapshots = repo.get_inventory_snapshots(store_id, ts_start, ts_end)
    by_ing: Dict[str, List[float]] = {}
    for s in snapshots:
        ing = s.get("ing_id", "")
        qty = float(s.get("qty", 0))
        if ing not in by_ing:
            by_ing[ing] = []
        by_ing[ing].append(qty)
    out["inventory_snapshot_summary"] = {
        "period": f"{ts_start[:10]} ~ {ts_end[:10]}",
        "ingredient_count": len(by_ing),
        "total_records": len(snapshots),
        "by_ingredient": {k: {"count": len(v), "last_qty": v[-1] if v else 0} for k, v in list(by_ing.items())[:30]},
    }

    # 门店下菜品 BOM 用料（前 20 个菜品）
    dishes = repo.run_read_only_query(
        "MATCH (d:Dish) WHERE d.store_id = $store_id RETURN d.dish_id AS dish_id, d.name AS name LIMIT 20",
        {"store_id": store_id},
    )
    bom_summary = []
    for d in dishes:
        dish_id = d.get("dish_id", "")
        rows = repo.get_dish_bom_ingredients(dish_id)
        if rows:
            bom_summary.append({"dish_id": dish_id, "name": d.get("name"), "ingredients": [r.get("ing_id") for r in rows], "qty_per_portion": [r.get("qty") for r in rows]})
    out["bom_summary"] = bom_summary[:20]

    # 近期损耗推理 TOP3（需同步调用 waste_reasoning；此处仅占位，由调用方可选注入）
    out["waste_top3"] = []  # 调用方可在 validate 前先调 reasoning/waste 并传入
    return out


async def get_ontology_context_for_agent(
    store_id: str,
    tenant_id: str = "",
    types: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    为 Agent 拉取图谱上下文。types 可选: bom, inventory_snapshot, waste_summary。
    未指定则全部拉取。
    """
    want = set(types or ["bom", "inventory_snapshot", "waste_summary"])
    repo = get_ontology_repository()
    if not repo:
        return {"enabled": False, "store_id": store_id}

    out: Dict[str, Any] = {"enabled": True, "store_id": store_id, "tenant_id": tenant_id}

    if "bom" in want:
        dishes = repo.run_read_only_query(
            "MATCH (d:Dish) WHERE d.store_id = $store_id RETURN d.dish_id AS dish_id, d.name AS name LIMIT 50",
            {"store_id": store_id},
        )
        boms = []
        for d in dishes:
            rows = repo.get_dish_bom_ingredients(d.get("dish_id", ""))
            if rows:
                boms.append({"dish_id": d.get("dish_id"), "dish_name": d.get("name"), "requirements": rows})
        out["bom"] = boms

    if "inventory_snapshot" in want:
        end = datetime.now()
        start = end - timedelta(days=3)
        ts_start = start.strftime("%Y-%m-%dT00:00:00")
        ts_end = end.strftime("%Y-%m-%dT23:59:59")
        snapshots = repo.get_inventory_snapshots(store_id, ts_start, ts_end)
        out["inventory_snapshot"] = {"period_days": 3, "records": snapshots[-100:]}

    if "waste_summary" in want:
        out["waste_summary"] = "请调用 POST /api/v1/ontology/reasoning/waste 获取近期损耗根因"

    return out
