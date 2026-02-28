"""
智链OS 数据融合引擎（Palantir Fusion Layer）

职责：将 POS / 企微 / Excel 等多源数据标准化，写入 Neo4j 本体节点。

融合策略：
  - 置信度加权（confidence score）
  - 相似度匹配（食材名称模糊匹配）
  - 多源映射表（external_ids 字段记录原始 ID）

目前实现：
  - POS → 菜品节点同步
  - PostgreSQL BOM → Neo4j BOM 节点（含版本链）
  - 库存快照写入
"""

import os
import hashlib
import structlog
from datetime import datetime
from typing import Optional

from neo4j import GraphDatabase

logger = structlog.get_logger()

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")


class OntologyDataSync:
    """
    PostgreSQL / POS → Neo4j 本体同步器

    使用方式：
        sync = OntologyDataSync()
        await sync.upsert_dish(dish_id="DISH-海鲜粥-001", name="海鲜粥",
                               category="粥品", price=68.0, store_id="XJ-CHANGSHA-001")
    """

    def __init__(
        self,
        uri: str = NEO4J_URI,
        user: str = NEO4J_USER,
        password: str = NEO4J_PASSWORD,
    ):
        if not password:
            raise EnvironmentError("NEO4J_PASSWORD 未设置")
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self) -> None:
        self.driver.close()

    # ── 菜品 ────────────────────────────────────────────────────────────────

    def upsert_dish(
        self,
        dish_id: str,
        name: str,
        category: str,
        price: float,
        store_id: str,
    ) -> None:
        """MERGE 菜品节点，并建立 (Store)-[:HAS_DISH]->(Dish) 关系"""
        with self.driver.session() as session:
            session.run(
                """
                MERGE (d:Dish {dish_id: $dish_id})
                ON CREATE SET
                    d.name       = $name,
                    d.category   = $category,
                    d.price      = $price,
                    d.store_id   = $store_id,
                    d.created_at = timestamp()
                ON MATCH SET
                    d.name     = $name,
                    d.category = $category,
                    d.price    = $price
                WITH d
                MATCH (s:Store {store_id: $store_id})
                MERGE (s)-[:HAS_DISH]->(d)
                """,
                dish_id=dish_id,
                name=name,
                category=category,
                price=price,
                store_id=store_id,
            )
            logger.debug("菜品节点同步", dish_id=dish_id, store_id=store_id)

    # ── BOM 配方 ─────────────────────────────────────────────────────────────

    def upsert_bom(
        self,
        dish_id: str,
        version: str,
        effective_date: datetime,
        yield_rate: float = 1.0,
        expiry_date: Optional[datetime] = None,
        notes: Optional[str] = None,
    ) -> None:
        """
        MERGE BOM 节点，建立 (Dish)-[:HAS_BOM]->(BOM) 关系
        同时维护版本链 (old_bom)-[:SUCCEEDED_BY]->(new_bom)
        """
        eff_ts = int(effective_date.timestamp() * 1000)
        exp_ts = int(expiry_date.timestamp() * 1000) if expiry_date else None

        with self.driver.session() as session:
            session.run(
                """
                MATCH (d:Dish {dish_id: $dish_id})
                MERGE (b:BOM {dish_id: $dish_id, version: $version})
                ON CREATE SET
                    b.effective_date = $eff_ts,
                    b.expiry_date    = $exp_ts,
                    b.yield_rate     = $yield_rate,
                    b.notes          = $notes,
                    b.created_at     = timestamp()
                ON MATCH SET
                    b.effective_date = $eff_ts,
                    b.expiry_date    = $exp_ts,
                    b.yield_rate     = $yield_rate
                MERGE (d)-[:HAS_BOM]->(b)
                """,
                dish_id=dish_id,
                version=version,
                eff_ts=eff_ts,
                exp_ts=exp_ts,
                yield_rate=yield_rate,
                notes=notes,
            )
            logger.debug("BOM 节点同步", dish_id=dish_id, version=version)

    def upsert_bom_item(
        self,
        dish_id: str,
        bom_version: str,
        ingredient_id: str,
        quantity: float,
        unit: str,
    ) -> None:
        """MERGE BOM → Ingredient 的 REQUIRES 关系"""
        with self.driver.session() as session:
            session.run(
                """
                MATCH (b:BOM {dish_id: $dish_id, version: $bom_version})
                MATCH (i:Ingredient {ing_id: $ingredient_id})
                MERGE (b)-[r:REQUIRES {ingredient_id: $ingredient_id}]->(i)
                ON CREATE SET r.qty = $qty, r.unit = $unit
                ON MATCH SET  r.qty = $qty, r.unit = $unit
                """,
                dish_id=dish_id,
                bom_version=bom_version,
                ingredient_id=ingredient_id,
                qty=quantity,
                unit=unit,
            )

    # ── 食材 ────────────────────────────────────────────────────────────────

    def upsert_ingredient(
        self,
        ing_id: str,
        name: str,
        category: str,
        unit_type: str,
        external_ids: Optional[dict] = None,
        fusion_confidence: float = 1.0,
    ) -> None:
        """
        MERGE 食材节点，记录多源 external_ids（POS ID / 供应商 ID / 企微名称）
        """
        with self.driver.session() as session:
            session.run(
                """
                MERGE (i:Ingredient {ing_id: $ing_id})
                ON CREATE SET
                    i.name               = $name,
                    i.category           = $category,
                    i.unit_type          = $unit_type,
                    i.external_ids       = $external_ids,
                    i.fusion_confidence  = $fusion_confidence,
                    i.created_at         = timestamp()
                ON MATCH SET
                    i.name              = $name,
                    i.category          = $category,
                    i.unit_type         = $unit_type,
                    i.external_ids      = $external_ids,
                    i.fusion_confidence = $fusion_confidence
                """,
                ing_id=ing_id,
                name=name,
                category=category,
                unit_type=unit_type,
                external_ids=str(external_ids or {}),
                fusion_confidence=fusion_confidence,
            )

    # ── 库存快照（追加写入，不覆盖） ────────────────────────────────────────────

    def append_inventory_snapshot(
        self,
        ingredient_id: str,
        quantity: float,
        unit: str,
        source: str = "manual_input",
        timestamp_ms: Optional[int] = None,
    ) -> str:
        """
        追加写入库存快照节点，返回 snapshot_id
        """
        import time
        ts = timestamp_ms or int(time.time() * 1000)
        # 用时间戳+食材ID生成确定性 snapshot_id
        raw = f"{ingredient_id}:{ts}"
        snapshot_id = "SNAP-" + hashlib.sha1(raw.encode()).hexdigest()[:12].upper()

        with self.driver.session() as session:
            session.run(
                """
                CREATE (n:InventorySnapshot {
                    snapshot_id:   $snapshot_id,
                    ingredient_id: $ingredient_id,
                    quantity:      $quantity,
                    unit:          $unit,
                    timestamp:     $ts,
                    source:        $source
                })
                WITH n
                MATCH (i:Ingredient {ing_id: $ingredient_id})
                CREATE (n)-[:SNAPSHOT_OF]->(i)
                """,
                snapshot_id=snapshot_id,
                ingredient_id=ingredient_id,
                quantity=quantity,
                unit=unit,
                ts=ts,
                source=source,
            )
            logger.debug("库存快照写入", snapshot_id=snapshot_id, ingredient_id=ingredient_id, qty=quantity)

        return snapshot_id

    # ── L2 融合层节点 ────────────────────────────────────────────────────────

    def upsert_ingredient_mapping(
        self,
        canonical_id:     str,
        canonical_name:   str,
        category:         str,
        unit:             str,
        external_ids:     dict,
        fusion_confidence: float,
        fusion_method:    str,
        conflict_flag:    bool = False,
        canonical_cost_fen: int = 0,
    ) -> None:
        """
        MERGE IngredientMapping 节点（规范ID注册中心）并与 Ingredient 节点关联。

        Cypher 本体：
          (IngredientMapping)-[:RESOLVES_TO]->(Ingredient)
          每个 ExternalSource 代表一个原始系统食材条目
        """
        with self.driver.session() as session:
            session.run(
                """
                MERGE (m:IngredientMapping {canonical_id: $canonical_id})
                ON CREATE SET
                    m.canonical_name    = $canonical_name,
                    m.category          = $category,
                    m.unit              = $unit,
                    m.fusion_confidence = $fusion_confidence,
                    m.fusion_method     = $fusion_method,
                    m.conflict_flag     = $conflict_flag,
                    m.canonical_cost_fen= $canonical_cost_fen,
                    m.external_ids      = $external_ids_str,
                    m.created_at        = timestamp()
                ON MATCH SET
                    m.canonical_name    = $canonical_name,
                    m.fusion_confidence = $fusion_confidence,
                    m.fusion_method     = $fusion_method,
                    m.conflict_flag     = $conflict_flag,
                    m.canonical_cost_fen= $canonical_cost_fen,
                    m.external_ids      = $external_ids_str,
                    m.updated_at        = timestamp()
                WITH m
                MERGE (i:Ingredient {ing_id: $canonical_id})
                ON CREATE SET
                    i.name     = $canonical_name,
                    i.category = $category,
                    i.unit_type= $unit
                MERGE (m)-[:RESOLVES_TO]->(i)
                """,
                canonical_id=canonical_id,
                canonical_name=canonical_name,
                category=category or "",
                unit=unit or "",
                fusion_confidence=fusion_confidence,
                fusion_method=fusion_method or "",
                conflict_flag=conflict_flag,
                canonical_cost_fen=canonical_cost_fen or 0,
                external_ids_str=str(external_ids),
            )
            logger.debug(
                "IngredientMapping 节点同步",
                canonical_id=canonical_id,
                method=fusion_method,
                confidence=fusion_confidence,
            )

    def link_external_source(
        self,
        canonical_id:  str,
        source_system: str,
        external_id:   str,
        confidence:    float,
        method:        str,
    ) -> None:
        """
        将外部系统食材节点链接到规范 IngredientMapping：
          (ExternalSource {source_key: "pinzhi::12345"})-[:MAPPED_TO {confidence}]->(IngredientMapping)

        source_key 格式："{source_system}::{external_id}"
        """
        source_key = f"{source_system}::{external_id}"
        with self.driver.session() as session:
            session.run(
                """
                MERGE (s:ExternalSource {source_key: $source_key})
                ON CREATE SET
                    s.source_system = $source_system,
                    s.external_id   = $external_id,
                    s.created_at    = timestamp()
                WITH s
                MATCH (m:IngredientMapping {canonical_id: $canonical_id})
                MERGE (s)-[r:MAPPED_TO]->(m)
                ON CREATE SET
                    r.confidence = $confidence,
                    r.method     = $method,
                    r.created_at = timestamp()
                ON MATCH SET
                    r.confidence = $confidence,
                    r.method     = $method
                """,
                source_key=source_key,
                source_system=source_system,
                external_id=external_id,
                canonical_id=canonical_id,
                confidence=confidence,
                method=method or "",
            )
            logger.debug(
                "ExternalSource 链接",
                source_key=source_key,
                canonical_id=canonical_id,
                confidence=confidence,
            )

    def mark_source_conflict(
        self,
        canonical_id_a: str,
        canonical_id_b: str,
        reason:         str,
        confidence:     float,
    ) -> None:
        """
        在两个 IngredientMapping 间建立 SOURCE_CONFLICT 关系
        （供 L4 推理层检测跨源成本异常）

        (IngredientMapping_A)-[:SOURCE_CONFLICT {reason, confidence}]->(IngredientMapping_B)
        """
        with self.driver.session() as session:
            session.run(
                """
                MATCH (a:IngredientMapping {canonical_id: $id_a})
                MATCH (b:IngredientMapping {canonical_id: $id_b})
                MERGE (a)-[r:SOURCE_CONFLICT]->(b)
                ON CREATE SET
                    r.reason     = $reason,
                    r.confidence = $confidence,
                    r.created_at = timestamp()
                ON MATCH SET
                    r.reason     = $reason,
                    r.confidence = $confidence
                """,
                id_a=canonical_id_a,
                id_b=canonical_id_b,
                reason=reason,
                confidence=confidence,
            )
            logger.warning(
                "来源冲突关系建立",
                id_a=canonical_id_a,
                id_b=canonical_id_b,
                reason=reason,
            )

    def upsert_store_external_ids(
        self, store_id: str, external_ids: dict
    ) -> None:
        """
        将门店的多源外部 ID 写入 Store 节点属性。
        external_ids = {"meituan_poi": "12345678", "tiancai": "TC-BJ-001",
                        "pinzhi_ognid": "XJ-01", "yiding": "YD-888"}
        """
        with self.driver.session() as session:
            session.run(
                """
                MERGE (s:Store {store_id: $store_id})
                ON MATCH SET s.external_ids = $external_ids_str
                ON CREATE SET
                    s.external_ids = $external_ids_str,
                    s.created_at   = timestamp()
                """,
                store_id=store_id,
                external_ids_str=str(external_ids),
            )

    # ── 约束 & 索引建议（在 Neo4j Browser 中手动执行一次）────────────────────
    # CREATE CONSTRAINT ON (m:IngredientMapping) ASSERT m.canonical_id IS UNIQUE;
    # CREATE CONSTRAINT ON (s:ExternalSource)    ASSERT s.source_key   IS UNIQUE;
    # CREATE INDEX ON :IngredientMapping(category);
    # CREATE INDEX ON :IngredientMapping(fusion_confidence);
    # CREATE INDEX ON :IngredientMapping(conflict_flag);

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
