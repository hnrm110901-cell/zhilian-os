"""
本体/图谱数据导出（Phase 3 数据主权：一键导出）
将 Neo4j 图谱当前快照导出为 JSON，供客户留存或迁移。
Phase 3+: 全图模式，包含 Staff/WasteEvent/TrainingModule 节点与培训/损耗关系。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.ontology import get_ontology_repository


def export_graph_snapshot(
    tenant_id: str = "",
    store_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    导出图谱快照：Store、Dish、Ingredient、BOM、InventorySnapshot。
    仅只读查询，不包含 Order/Staff/Action 等（可按需扩展）。
    """
    repo = get_ontology_repository()
    if not repo:
        return {"error": "Neo4j 未启用", "stores": [], "dishes": [], "ingredients": [], "boms": [], "inventory_snapshots": []}

    def run(q: str, params: Optional[Dict] = None) -> List[Dict]:
        return repo.run_read_only_query(q, params or {})

    where_store = " WHERE n.store_id = $store_id" if store_id else ""
    params: Dict[str, Any] = {"store_id": store_id} if store_id else {}

    stores = run("MATCH (n:Store) RETURN n.store_id AS store_id, n.name AS name, n.tenant_id AS tenant_id" + where_store, params if store_id else None)
    dishes = run("MATCH (n:Dish) RETURN n.dish_id AS dish_id, n.name AS name, n.store_id AS store_id" + where_store, params if store_id else None)
    ingredients = run("MATCH (n:Ingredient) RETURN n.ing_id AS ing_id, n.name AS name, n.unit AS unit, n.store_id AS store_id" + where_store, params if store_id else None)
    boms = run("MATCH (n:BOM) RETURN n.bom_id AS bom_id, n.dish_id AS dish_id, n.store_id AS store_id, n.version AS version, n.effective_date AS effective_date" + where_store, params if store_id else None)
    snapshots = run("MATCH (n:InventorySnapshot) RETURN n.snapshot_id AS snapshot_id, n.store_id AS store_id, n.ing_id AS ing_id, n.qty AS qty, n.ts AS ts, n.source AS source" + where_store, params if store_id else None)

    return {
        "tenant_id": tenant_id,
        "store_id_filter": store_id,
        "export_type": "ontology_snapshot",
        "stores": stores,
        "dishes": dishes,
        "ingredients": ingredients,
        "boms": boms,
        "inventory_snapshots": snapshots,
    }


def export_full_graph(
    tenant_id: str = "",
    store_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    全图模式导出：包含 Staff、WasteEvent、TrainingModule 节点及其所有关系。
    用于 OntologyGraphPage 全图可视化，呈现完整知识飞轮：
    Store -SIMILAR_TO-> Store
    Staff -BELONGS_TO-> Store
    WasteEvent -TRIGGERED_BY-> Staff
    Staff -NEEDS_TRAINING-> TrainingModule
    Staff -COMPLETED_TRAINING-> TrainingModule
    """
    snapshot = export_graph_snapshot(tenant_id=tenant_id, store_id=store_id)
    if "error" in snapshot:
        return snapshot

    repo = get_ontology_repository()
    assert repo is not None  # checked in export_graph_snapshot

    def run(q: str, params: Optional[Dict] = None) -> List[Dict]:
        return repo.run_read_only_query(q, params or {})

    store_filter = " WHERE s.store_id = $store_id" if store_id else ""
    p: Dict[str, Any] = {"store_id": store_id} if store_id else {}

    # 节点
    staff = run(
        "MATCH (n:Staff)" + (f" WHERE n.store_id = $store_id" if store_id else "")
        + " RETURN n.staff_id AS staff_id, n.name AS name, n.role AS role, n.store_id AS store_id",
        p if store_id else None,
    )
    waste_events = run(
        "MATCH (n:WasteEvent)" + (f" WHERE n.store_id = $store_id" if store_id else "")
        + " RETURN n.event_id AS event_id, n.store_id AS store_id, n.event_type AS event_type,"
          " n.root_cause AS root_cause, n.amount AS amount",
        p if store_id else None,
    )
    training_modules = run(
        "MATCH (n:TrainingModule) RETURN n.module_id AS module_id, n.name AS name,"
        " n.skill_gap AS skill_gap, n.course_ids AS course_ids",
    )

    # 关系（边）
    similar_to = run(
        "MATCH (a:Store)-[r:SIMILAR_TO]->(b:Store)"
        + (f" WHERE a.store_id = $store_id OR b.store_id = $store_id" if store_id else "")
        + " RETURN a.store_id AS from_id, b.store_id AS to_id, r.score AS score, r.reason AS reason",
        p if store_id else None,
    )
    belongs_to = run(
        "MATCH (s:Staff)-[:BELONGS_TO]->(st:Store)"
        + (f" WHERE st.store_id = $store_id" if store_id else "")
        + " RETURN s.staff_id AS from_id, st.store_id AS to_id",
        p if store_id else None,
    )
    triggered_by = run(
        "MATCH (w:WasteEvent)-[:TRIGGERED_BY]->(s:Staff)"
        + (f" WHERE w.store_id = $store_id" if store_id else "")
        + " RETURN w.event_id AS from_id, s.staff_id AS to_id",
        p if store_id else None,
    )
    needs_training = run(
        "MATCH (s:Staff)-[r:NEEDS_TRAINING]->(m:TrainingModule)"
        + (f" WHERE s.store_id = $store_id" if store_id else "")
        + " RETURN s.staff_id AS from_id, m.module_id AS to_id,"
          " r.urgency AS urgency, r.waste_event_id AS waste_event_id",
        p if store_id else None,
    )
    completed_training = run(
        "MATCH (s:Staff)-[r:COMPLETED_TRAINING]->(m:TrainingModule)"
        + (f" WHERE s.store_id = $store_id" if store_id else "")
        + " RETURN s.staff_id AS from_id, m.module_id AS to_id,"
          " r.score AS score, r.completed_at AS completed_at",
        p if store_id else None,
    )

    return {
        **snapshot,
        "export_type": "full_graph",
        # 运营层节点
        "staff": staff,
        "waste_events": waste_events,
        "training_modules": training_modules,
        # 关系
        "relations": {
            "similar_to": similar_to,
            "belongs_to": belongs_to,
            "triggered_by": triggered_by,
            "needs_training": needs_training,
            "completed_training": completed_training,
        },
    }
