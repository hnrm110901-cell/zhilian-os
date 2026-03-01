"""
OntologyRepository：封装 Neo4j Cypher 访问，提供本体 CRUD 与图遍历
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

import structlog
from neo4j import GraphDatabase

from .schema import NodeLabel, RelType, NODE_ID_PROP, ExtensionNodeLabel, EXTENSION_ID_PROP

logger = structlog.get_logger()


class OntologyRepository:
    """L2 本体层图数据库访问封装。"""

    def __init__(self, uri: str, user: str, password: str):
        self._uri = uri
        self._user = user
        self._password = password
        self._driver = None

    def close(self) -> None:
        if self._driver:
            self._driver.close()
            self._driver = None

    @property
    def driver(self):
        if self._driver is None:
            self._driver = GraphDatabase.driver(
                self._uri, auth=(self._user, self._password)
            )
        return self._driver

    @contextmanager
    def session(self):
        s = self.driver.session()
        try:
            yield s
        finally:
            s.close()

    def init_schema(self, tenant_id: str) -> None:
        """创建约束与索引（幂等）。tenant_id 用于多租户命名空间（可选）。含徐记扩展约束。"""
        from .cypher_schema import constraints_cypher, indexes_cypher, extension_constraints_cypher
        with self.session() as session:
            for cypher in constraints_cypher():
                try:
                    session.run(cypher)
                except Exception as e:
                    logger.warning("ontology_constraint_skip", cypher=cypher, error=str(e))
            for cypher in extension_constraints_cypher():
                try:
                    session.run(cypher)
                except Exception as e:
                    logger.warning("ontology_extension_constraint_skip", cypher=cypher, error=str(e))
            for cypher in indexes_cypher():
                try:
                    session.run(cypher)
                except Exception as e:
                    logger.warning("ontology_index_skip", cypher=cypher, error=str(e))
        logger.info("ontology_schema_inited", tenant_id=tenant_id)

    # ---------- 节点 MERGE ----------
    def merge_node(
        self,
        label: str,
        id_prop: str,
        id_value: str,
        props: Optional[Dict[str, Any]] = None,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """创建或更新节点。id_prop 为唯一键（如 store_id, dish_id）。"""
        props = dict(props or {})
        props[id_prop] = id_value
        if tenant_id is not None:
            props["tenant_id"] = tenant_id
        with self.session() as session:
            cypher = (
                f"MERGE (n:{label} {{ {id_prop}: $id_value }}) "
                "SET n += $props RETURN n"
            )
            result = session.run(
                cypher,
                id_value=id_value,
                props=props,
            )
            record = result.single()
            if not record or not record.get("n"):
                return {}
            node = record["n"]
            return dict(node)

    def get_node(self, label: str, id_prop: str, id_value: str) -> Optional[Dict[str, Any]]:
        """按标签与唯一键查询节点。"""
        with self.session() as session:
            result = session.run(
                f"MATCH (n:{label} {{ {id_prop}: $id_value }}) RETURN n",
                id_value=id_value,
            )
            record = result.single()
            if not record or not record.get("n"):
                return None
            return dict(record["n"])

    # ---------- 关系 ----------
    def merge_relation(
        self,
        from_label: str,
        from_id_prop: str,
        from_id_value: str,
        rel_type: str,
        to_label: str,
        to_id_prop: str,
        to_id_value: str,
        rel_props: Optional[Dict[str, Any]] = None,
    ) -> None:
        """创建或更新一条关系（基于两端节点存在）。"""
        rel_props = dict(rel_props or {})
        with self.session() as session:
            set_clause = ", ".join(f"r.{k} = ${k}" for k in rel_props) if rel_props else ""
            set_part = f" SET {set_clause}" if set_clause else ""
            cypher = (
                f"MATCH (a:{from_label} {{ {from_id_prop}: $from_id }}) "
                f"MATCH (b:{to_label} {{ {to_id_prop}: $to_id }}) "
                f"MERGE (a)-[r:{rel_type}]->(b){set_part}"
            )
            params = {"from_id": from_id_value, "to_id": to_id_value, **rel_props}
            session.run(cypher, params)

    # ---------- BOM 本体化 ----------
    def upsert_bom(
        self,
        tenant_id: str,
        store_id: str,
        dish_id: str,
        version: int,
        effective_date: str,
        expiry_date: Optional[str] = None,
        yield_portions: float = 1.0,
    ) -> str:
        """创建或更新 BOM 节点，并关联到 Dish。返回 bom_id。"""
        bom_id = f"{store_id}_{dish_id}_v{version}"
        self.merge_node(
            NodeLabel.BOM.value,
            "bom_id",
            bom_id,
            {
                "tenant_id": tenant_id,
                "store_id": store_id,
                "dish_id": dish_id,
                "version": version,
                "effective_date": effective_date,
                "expiry_date": expiry_date or "",
                "yield_portions": yield_portions,
            },
            tenant_id=tenant_id,
        )
        self.merge_relation(
            NodeLabel.Dish.value, "dish_id", dish_id,
            RelType.HAS_BOM.value,
            NodeLabel.BOM.value, "bom_id", bom_id,
            {"version": version},
        )
        return bom_id

    def upsert_bom_requires(
        self,
        bom_id: str,
        ing_id: str,
        qty: float,
        unit: str,
        waste_factor: float = 1.0,
    ) -> None:
        """建立 BOM-[:REQUIRES {qty, unit, waste_factor}]->Ingredient。
        waste_factor: 损耗系数（默认 1.0；1.05 = 额外备 5%）。
        """
        self.merge_relation(
            NodeLabel.BOM.value, "bom_id", bom_id,
            RelType.REQUIRES.value,
            NodeLabel.Ingredient.value, "ing_id", ing_id,
            {"qty": qty, "unit": unit, "waste_factor": waste_factor},
        )

    def get_ingredient_waste_factor(self, ing_id: str, store_id: str) -> float:
        """查询某食材在该门店 BOM 中的最大 waste_factor（取所有关联 BOM 的最高值）。
        无 BOM 关联时返回环境变量 INVENTORY_DEFAULT_WASTE_FACTOR（默认 1.05）。
        """
        import os
        try:
            with self.session() as session:
                result = session.run(
                    """
                    MATCH (b:BOM { store_id: $store_id })-[r:REQUIRES]->(i:Ingredient { ing_id: $ing_id })
                    RETURN max(coalesce(r.waste_factor, 1.0)) AS max_wf
                    """,
                    store_id=store_id,
                    ing_id=ing_id,
                )
                record = result.single()
                if record and record.get("max_wf") is not None:
                    return float(record["max_wf"])
        except Exception as e:
            logger.debug("get_ingredient_waste_factor_failed", ing_id=ing_id, error=str(e))
        return float(os.getenv("INVENTORY_DEFAULT_WASTE_FACTOR", "1.05"))

    # ---------- 感知层：库存快照（L1 标准化输出写入 L2）----------
    def merge_inventory_snapshot(
        self,
        tenant_id: str,
        store_id: str,
        ing_id: str,
        qty: float,
        ts: str,
        source: str = "manual",
        unit: str = "",
    ) -> str:
        """写入库存快照节点，并建立 LOCATED_AT 指向 Ingredient。snapshot_id 唯一。"""
        snapshot_id = f"{store_id}_{ing_id}_{ts}"
        self.merge_node(
            NodeLabel.InventorySnapshot.value,
            "snapshot_id",
            snapshot_id,
            {
                "tenant_id": tenant_id,
                "store_id": store_id,
                "ing_id": ing_id,
                "qty": qty,
                "ts": ts,
                "source": source,
                "unit": unit or "",
            },
            tenant_id=tenant_id,
        )
        self.merge_relation(
            NodeLabel.InventorySnapshot.value, "snapshot_id", snapshot_id,
            RelType.LOCATED_AT.value,
            NodeLabel.Ingredient.value, "ing_id", ing_id,
            {},
        )
        return snapshot_id

    # ---------- 徐记 POC 扩展节点 ----------
    def merge_live_seafood(
        self,
        live_seafood_id: str,
        store_id: str,
        species: str = "",
        weight_kg: float = 0,
        price_cents: int = 0,
        pool_time: str = "",
        mortality_rate: float = 0,
        tenant_id: Optional[str] = None,
    ) -> None:
        """活海鲜节点：用于死亡损耗 vs 正常损耗的异常识别。"""
        self.merge_node(
            ExtensionNodeLabel.LiveSeafood.value,
            EXTENSION_ID_PROP[ExtensionNodeLabel.LiveSeafood.value],
            live_seafood_id,
            {"store_id": store_id, "species": species, "weight_kg": weight_kg, "price_cents": price_cents, "pool_time": pool_time, "mortality_rate": mortality_rate},
            tenant_id=tenant_id,
        )
        self.merge_relation(ExtensionNodeLabel.LiveSeafood.value, "live_seafood_id", live_seafood_id, RelType.BELONGS_TO.value, NodeLabel.Store.value, "store_id", store_id, {})

    def merge_seafood_pool(
        self,
        pool_id: str,
        store_id: str,
        capacity: str = "",
        temperature: float = 0,
        salinity: float = 0,
        equipment_status: str = "",
        tenant_id: Optional[str] = None,
    ) -> None:
        """海鲜池节点：设备异常→死亡率上升的推理链。"""
        self.merge_node(
            ExtensionNodeLabel.SeafoodPool.value,
            EXTENSION_ID_PROP[ExtensionNodeLabel.SeafoodPool.value],
            pool_id,
            {"store_id": store_id, "capacity": capacity, "temperature": temperature, "salinity": salinity, "equipment_status": equipment_status},
            tenant_id=tenant_id,
        )
        self.merge_relation(ExtensionNodeLabel.SeafoodPool.value, "pool_id", pool_id, RelType.BELONGS_TO.value, NodeLabel.Store.value, "store_id", store_id, {})

    def merge_portion_weight(
        self,
        portion_id: str,
        store_id: str,
        dish_id: str = "",
        actual_g: float = 0,
        standard_g: float = 0,
        staff_id: str = "",
        ts: str = "",
        tenant_id: Optional[str] = None,
    ) -> None:
        """份量记录：出成率偏差→厨师责任定位。"""
        self.merge_node(
            ExtensionNodeLabel.PortionWeight.value,
            EXTENSION_ID_PROP[ExtensionNodeLabel.PortionWeight.value],
            portion_id,
            {"store_id": store_id, "dish_id": dish_id, "actual_g": actual_g, "standard_g": standard_g, "staff_id": staff_id, "ts": ts},
            tenant_id=tenant_id,
        )
        if dish_id:
            self.merge_relation(ExtensionNodeLabel.PortionWeight.value, "portion_id", portion_id, RelType.LOCATED_AT.value, NodeLabel.Dish.value, "dish_id", dish_id, {})
        if staff_id:
            self.merge_relation(ExtensionNodeLabel.PortionWeight.value, "portion_id", portion_id, RelType.TRIGGERED_BY.value, NodeLabel.Staff.value, "staff_id", staff_id, {})

    def merge_purchase_invoice(
        self,
        invoice_id: str,
        store_id: str,
        supplier_id: str = "",
        batch: str = "",
        price_cents: int = 0,
        receiver_staff_id: str = "",
        ts: str = "",
        tenant_id: Optional[str] = None,
    ) -> None:
        """采购凭证：价格虚高→采购异常检测。"""
        self.merge_node(
            ExtensionNodeLabel.PurchaseInvoice.value,
            EXTENSION_ID_PROP[ExtensionNodeLabel.PurchaseInvoice.value],
            invoice_id,
            {"store_id": store_id, "supplier_id": supplier_id, "batch": batch, "price_cents": price_cents, "receiver_staff_id": receiver_staff_id, "ts": ts},
            tenant_id=tenant_id,
        )
        self.merge_relation(ExtensionNodeLabel.PurchaseInvoice.value, "invoice_id", invoice_id, RelType.BELONGS_TO.value, NodeLabel.Store.value, "store_id", store_id, {})

    def merge_waste_event(
        self,
        event_id: str,
        store_id: str,
        event_type: str = "inventory_variance",
        amount: float = 0,
        root_cause: str = "",
        staff_id: Optional[str] = None,
        ing_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> None:
        """损耗事件节点：关联 TRIGGERED_BY->Staff、可关联 Ingredient。"""
        self.merge_node(
            NodeLabel.WasteEvent.value,
            "event_id",
            event_id,
            {"store_id": store_id, "type": event_type, "amount": amount, "root_cause": root_cause or "", "tenant_id": tenant_id or ""},
            tenant_id=tenant_id,
        )
        if staff_id:
            self.merge_relation(NodeLabel.WasteEvent.value, "event_id", event_id, RelType.TRIGGERED_BY.value, NodeLabel.Staff.value, "staff_id", staff_id, {})

    def merge_equipment(
        self,
        equip_id: str,
        store_id: str,
        equip_type: str = "",
        status: str = "",
        location: str = "",
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """设备节点：属于门店，可触发维护 Action。"""
        out = self.merge_node(
            NodeLabel.Equipment.value,
            "equip_id",
            equip_id,
            {
                "store_id": store_id,
                "equip_type": equip_type,
                "status": status,
                "location": location,
            },
            tenant_id=tenant_id,
        )
        self.merge_relation(
            NodeLabel.Equipment.value, "equip_id", equip_id,
            RelType.BELONGS_TO.value,
            NodeLabel.Store.value, "store_id", store_id,
        )
        return out

    # ---------- 推理层查询：库存快照 ----------
    def get_inventory_snapshots(
        self,
        store_id: str,
        ts_start: str,
        ts_end: str,
        ing_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """按门店、时间范围查询库存快照，可选按食材过滤。"""
        with self.session() as session:
            if ing_id:
                result = session.run(
                    """
                    MATCH (s:InventorySnapshot { store_id: $store_id })
                    WHERE s.ts >= $ts_start AND s.ts <= $ts_end AND s.ing_id = $ing_id
                    RETURN s.snapshot_id AS snapshot_id, s.ing_id AS ing_id, s.qty AS qty, s.ts AS ts, s.source AS source
                    ORDER BY s.ts
                    """,
                    store_id=store_id,
                    ts_start=ts_start,
                    ts_end=ts_end,
                    ing_id=ing_id,
                )
            else:
                result = session.run(
                    """
                    MATCH (s:InventorySnapshot { store_id: $store_id })
                    WHERE s.ts >= $ts_start AND s.ts <= $ts_end
                    RETURN s.snapshot_id AS snapshot_id, s.ing_id AS ing_id, s.qty AS qty, s.ts AS ts, s.source AS source
                    ORDER BY s.ing_id, s.ts
                    """,
                    store_id=store_id,
                    ts_start=ts_start,
                    ts_end=ts_end,
                )
            return [dict(record) for record in result]

    def get_store_dish_ids(self, store_id: str) -> List[str]:
        """按门店查询图谱中的菜品 id 列表（用于备货建议等）。"""
        with self.session() as session:
            result = session.run(
                "MATCH (d:Dish) WHERE d.store_id = $store_id RETURN d.dish_id AS dish_id",
                store_id=store_id,
            )
            return [r["dish_id"] for r in result if r.get("dish_id")]

    # ---------- 查询示例（图谱遍历）----------
    def get_dish_bom_ingredients(self, dish_id: str) -> List[Dict[str, Any]]:
        """查询某菜品的 BOM 及所需食材（含用量与损耗系数），取最新版本。"""
        with self.session() as session:
            result = session.run(
                """
                MATCH (d:Dish { dish_id: $dish_id })-[:HAS_BOM]->(b:BOM)
                MATCH (b)-[r:REQUIRES]->(i:Ingredient)
                RETURN b.bom_id AS bom_id, b.version AS version,
                       i.ing_id AS ing_id, i.name AS ing_name, r.qty AS qty,
                       r.unit AS unit, r.waste_factor AS waste_factor
                ORDER BY b.version DESC
                LIMIT 1
                """,
                dish_id=dish_id,
            )
            return [dict(record) for record in result]

    def get_dish_bom_ingredients_as_of(
        self, dish_id: str, as_of_date: str
    ) -> List[Dict[str, Any]]:
        """时间旅行：按 as_of 日期查询当时生效的 BOM 及用料。as_of_date 格式 YYYY-MM-DD。"""
        with self.session() as session:
            result = session.run(
                """
                MATCH (d:Dish { dish_id: $dish_id })-[:HAS_BOM]->(b:BOM)
                WHERE b.effective_date <= $as_of
                  AND (b.expiry_date IS NULL OR b.expiry_date = '' OR b.expiry_date >= $as_of)
                MATCH (b)-[r:REQUIRES]->(i:Ingredient)
                RETURN b.bom_id AS bom_id, b.version AS version,
                       i.ing_id AS ing_id, r.qty AS qty, r.unit AS unit
                ORDER BY b.version DESC
                LIMIT 1
                """,
                dish_id=dish_id,
                as_of=as_of_date,
            )
            return [dict(record) for record in result]

    def get_dish_bom_full(self, dish_id: str) -> Optional[Dict[str, Any]]:
        """取某菜品当前 BOM 完整信息（版本、生效日、用料列表），用于模板复制。"""
        with self.session() as session:
            result = session.run(
                """
                MATCH (d:Dish { dish_id: $dish_id })-[:HAS_BOM]->(b:BOM)
                WITH b ORDER BY b.version DESC LIMIT 1
                OPTIONAL MATCH (b)-[r:REQUIRES]->(i:Ingredient)
                RETURN b.bom_id AS bom_id, b.version AS version,
                       b.effective_date AS effective_date, b.expiry_date AS expiry_date,
                       collect({ing_id: i.ing_id, qty: r.qty, unit: r.unit}) AS items
                """,
                dish_id=dish_id,
            )
            record = result.single()
            if not record or not record.get("bom_id"):
                return None
            items = [x for x in (record.get("items") or []) if x and x.get("ing_id")]
            return {
                "bom_id": record["bom_id"],
                "version": record["version"],
                "effective_date": record["effective_date"] or "",
                "expiry_date": record["expiry_date"] or "",
                "items": items,
            }

    def clone_template_to_store(
        self,
        source_store_id: str,
        target_store_id: str,
        tenant_id: str,
    ) -> Dict[str, int]:
        """
        将源门店的本体模板（Dish + BOM + REQUIRES）复制到目标门店。
        目标门店若已有同 dish_id 则覆盖 BOM；Ingredient 节点不复制（沿用全局）。
        返回复制的 dish 数、bom 数。
        """
        dish_ids = self.get_store_dish_ids(source_store_id)
        dishes_ok, boms_ok = 0, 0
        for dish_id in dish_ids:
            full = self.get_dish_bom_full(dish_id)
            if not full:
                continue
            self.merge_node(
                NodeLabel.Dish.value,
                "dish_id",
                dish_id,
                {"store_id": target_store_id, "tenant_id": tenant_id},
                tenant_id=tenant_id,
            )
            dishes_ok += 1
            version = full.get("version") or 1
            effective = full.get("effective_date") or "2000-01-01"
            self.upsert_bom(
                tenant_id=tenant_id,
                store_id=target_store_id,
                dish_id=dish_id,
                version=version,
                effective_date=effective,
                expiry_date=full.get("expiry_date"),
            )
            bom_id = f"{target_store_id}_{dish_id}_v{version}"
            for it in full.get("items") or []:
                ing_id = it.get("ing_id")
                if not ing_id:
                    continue
                qty = float(it.get("qty") or 0)
                unit = str(it.get("unit") or "")
                self.upsert_bom_requires(bom_id, ing_id, qty, unit)
            boms_ok += 1
        return {"dishes": dishes_ok, "boms": boms_ok}

    def run_read_only_query(self, cypher: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """执行只读 Cypher（仅允许 MATCH/RETURN/WITH/ORDER BY/LIMIT），返回记录列表。用于 NL 查询。"""
        cypher_upper = cypher.strip().upper()
        if any(c in cypher_upper for c in ("CREATE", "MERGE", "DELETE", "SET", "REMOVE", "DROP", "CALL")):
            logger.warning("ontology_query_rejected_write", cypher_preview=cypher[:200])
            return []
        params = params or {}
        with self.session() as session:
            result = session.run(cypher, params)
            return [dict(record) for record in result]

    def delete_tenant_data(self, tenant_id: str, store_ids: Optional[List[str]] = None) -> Dict[str, int]:
        """
        数据主权断开权：删除指定租户/门店在图谱中的数据（DETACH DELETE）。
        仅用于 data_sovereignty 流程，需 DATA_SOVEREIGNTY_ENABLED。
        返回各类型删除的节点数。
        """
        counts: Dict[str, int] = {}
        with self.session() as session:
            if store_ids:
                for label, id_prop in [("InventorySnapshot", "snapshot_id"), ("BOM", "bom_id"), ("Dish", "dish_id"), ("Ingredient", "ing_id"), ("Store", "store_id")]:
                    q = f"MATCH (n:{label}) WHERE n.{id_prop} IS NOT NULL AND n.store_id IN $store_ids DETACH DELETE n"
                    try:
                        r = session.run(q, store_ids=store_ids)
                        summary = r.consume()
                        counts[label] = summary.counters.nodes_deleted
                    except Exception as e:
                        logger.warning("ontology_delete_batch_failed", label=label, error=str(e))
                        counts[label] = 0
            if tenant_id:
                for label in ["InventorySnapshot", "BOM"]:
                    q = f"MATCH (n:{label}) WHERE n.tenant_id = $tenant_id DETACH DELETE n"
                    try:
                        r = session.run(q, tenant_id=tenant_id)
                        summary = r.consume()
                        counts[f"{label}_by_tenant"] = summary.counters.nodes_deleted
                    except Exception as e:
                        logger.warning("ontology_delete_tenant_failed", label=label, error=str(e))
                        counts[f"{label}_by_tenant"] = 0
        return counts

    def health(self) -> bool:
        """检查 Neo4j 连接。"""
        try:
            self.driver.verify_connectivity()
            return True
        except Exception as e:
            logger.warning("neo4j_health_failed", error=str(e))
            return False

    # ---------- Phase 1.3: Staff-Training 关系 ----------

    def merge_training_module(
        self,
        module_id: str,
        name: str,
        skill_gap: str,
        course_ids: Optional[List[str]] = None,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """创建或更新 TrainingModule 节点。"""
        return self.merge_node(
            NodeLabel.TrainingModule.value,
            "module_id",
            module_id,
            {
                "name": name,
                "skill_gap": skill_gap,
                "course_ids": ",".join(course_ids or []),
            },
            tenant_id=tenant_id,
        )

    def staff_completed_training(
        self,
        staff_id: str,
        module_id: str,
        completed_at: str,
        score: float = 0.0,
    ) -> None:
        """建立 (Staff)-[:COMPLETED_TRAINING {score, completed_at}]->(TrainingModule)。"""
        self.merge_relation(
            NodeLabel.Staff.value, "staff_id", staff_id,
            RelType.COMPLETED_TRAINING.value,
            NodeLabel.TrainingModule.value, "module_id", module_id,
            {"score": score, "completed_at": completed_at},
        )

    def staff_needs_training(
        self,
        staff_id: str,
        module_id: str,
        waste_event_id: str,
        urgency: str = "medium",
        deadline: Optional[str] = None,
    ) -> None:
        """建立 (Staff)-[:NEEDS_TRAINING {waste_event_id, urgency, deadline}]->(TrainingModule)。"""
        self.merge_relation(
            NodeLabel.Staff.value, "staff_id", staff_id,
            RelType.NEEDS_TRAINING.value,
            NodeLabel.TrainingModule.value, "module_id", module_id,
            {
                "waste_event_id": waste_event_id,
                "urgency": urgency,
                "deadline": deadline or "",
            },
        )

    def get_staff_training_status(
        self,
        staff_id: str,
        store_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """查询员工的培训状态：已完成与待完成的 TrainingModule。"""
        with self.session() as session:
            completed = session.run(
                """
                MATCH (s:Staff { staff_id: $staff_id })-[r:COMPLETED_TRAINING]->(m:TrainingModule)
                RETURN m.module_id AS module_id, m.name AS name, m.skill_gap AS skill_gap,
                       r.score AS score, r.completed_at AS completed_at
                ORDER BY r.completed_at DESC
                """,
                staff_id=staff_id,
            )
            needs = session.run(
                """
                MATCH (s:Staff { staff_id: $staff_id })-[r:NEEDS_TRAINING]->(m:TrainingModule)
                RETURN m.module_id AS module_id, m.name AS name, m.skill_gap AS skill_gap,
                       r.waste_event_id AS waste_event_id, r.urgency AS urgency, r.deadline AS deadline
                ORDER BY r.urgency
                """,
                staff_id=staff_id,
            )
            return {
                "staff_id": staff_id,
                "completed": [dict(r) for r in completed],
                "needs": [dict(r) for r in needs],
            }

    # ------------------------------------------------------------------
    # Phase 3: Store SIMILAR_TO 跨门店知识路由
    # ------------------------------------------------------------------

    def merge_store_similarity(
        self,
        store_id_a: str,
        store_id_b: str,
        similarity_score: float = 0.8,
        reason: str = "region",
    ) -> None:
        """建立 (Store)-[:SIMILAR_TO {score, reason}]->(Store) 双向关系（幂等）。"""
        from datetime import datetime as _dt
        now = _dt.utcnow().isoformat()
        with self.session() as session:
            session.run(
                """
                MERGE (a:Store {store_id: $a})
                MERGE (b:Store {store_id: $b})
                MERGE (a)-[r:SIMILAR_TO]->(b)
                SET r.score = $score, r.reason = $reason, r.updated_at = $now
                MERGE (b)-[r2:SIMILAR_TO]->(a)
                SET r2.score = $score, r2.reason = $reason, r2.updated_at = $now
                """,
                a=store_id_a,
                b=store_id_b,
                score=similarity_score,
                reason=reason,
                now=now,
            )

    def get_similar_stores(
        self,
        store_id: str,
        min_score: float = 0.5,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """查询与指定门店相似的门店列表（按 SIMILAR_TO 关系排序）。"""
        with self.session() as session:
            result = session.run(
                """
                MATCH (a:Store {store_id: $store_id})-[r:SIMILAR_TO]->(b:Store)
                WHERE r.score >= $min_score
                RETURN b.store_id AS store_id, r.score AS score, r.reason AS reason
                ORDER BY r.score DESC
                LIMIT $limit
                """,
                store_id=store_id,
                min_score=min_score,
                limit=limit,
            )
            return [dict(row) for row in result]
