"""
连锁门店本体复制器（多店扩展 — Phase 3-M3.2）

功能：
  1. 将源门店（已运营）的本体结构克隆到新门店
     - 克隆 Dish 节点列表（不含订单/损耗数据）
     - 克隆 BOM 配方（当前激活版本）
     - 克隆 Ingredient 节点（共享供应商）
     - 在 Neo4j 建立 (newStore)-[:PART_OF]->(brand) 品牌关系
  2. 跨店对比分析（Cypher）
     - 各门店损耗率对比
     - BOM 配方差异分析（同一道菜不同门店用料对比）
     - 人效基准对比

扩展逻辑：
  - PostgreSQL：复制 Dish / BOMTemplate / BOMItem / InventoryItem 主档
  - Neo4j：复制 Dish / BOM / Ingredient 节点及其关系
  - 保持 store_id 独立（各店数据主权隔离）
"""

import uuid
from datetime import datetime
from typing import Dict, List, Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.bom import BOMTemplate, BOMItem
from src.models.dish import Dish, DishCategory
from src.models.inventory import InventoryItem, InventoryStatus
from src.services.bom_service import BOMService

logger = structlog.get_logger()


class StoreOntologyReplicator:
    """
    门店本体克隆器

    用法::

        async with get_db() as db:
            repl = StoreOntologyReplicator(db)
            report = await repl.replicate(
                source_store_id="XJ-CHANGSHA-001",
                target_store_id="XJ-SHENZHEN-001",
                target_store_name="徐记海鲜深圳店",
            )
    """

    def __init__(self, db: AsyncSession, created_by: str = "system"):
        self.db = db
        self.created_by = created_by

    async def replicate(
        self,
        source_store_id: str,
        target_store_id: str,
        target_store_name: str,
        include_bom: bool = True,
        include_inventory: bool = True,
        dish_filter: Optional[List[str]] = None,  # 限定菜品编码列表
    ) -> Dict:
        """
        将源门店本体克隆到目标门店

        Returns 导入报告::

            {
              "source_store_id": "XJ-CHANGSHA-001",
              "target_store_id": "XJ-SHENZHEN-001",
              "dishes_cloned": 102,
              "boms_cloned": 98,
              "ingredients_cloned": 245,
              "neo4j_synced": True,
              "errors": []
            }
        """
        report = {
            "source_store_id": source_store_id,
            "target_store_id": target_store_id,
            "dishes_cloned": 0,
            "boms_cloned": 0,
            "ingredients_cloned": 0,
            "neo4j_synced": False,
            "errors": [],
        }

        # 1. 克隆食材主档（InventoryItem）
        if include_inventory:
            cloned_ings = await self._clone_ingredients(
                source_store_id, target_store_id
            )
            report["ingredients_cloned"] = cloned_ings

        # 2. 克隆菜品主档（Dish）
        cloned_dishes = await self._clone_dishes(
            source_store_id, target_store_id, dish_filter
        )
        report["dishes_cloned"] = len(cloned_dishes)

        # 3. 克隆 BOM（激活版本）
        if include_bom:
            bom_count = await self._clone_boms(
                source_store_id, target_store_id, cloned_dishes
            )
            report["boms_cloned"] = bom_count

        await self.db.commit()

        # 4. Neo4j 本体同步
        try:
            await self._sync_to_neo4j(
                source_store_id, target_store_id, target_store_name
            )
            report["neo4j_synced"] = True
        except Exception as e:
            report["errors"].append(f"Neo4j 同步失败（非致命）: {e}")
            logger.warning("Neo4j 同步失败", error=str(e))

        logger.info(
            "门店本体克隆完成",
            source=source_store_id,
            target=target_store_id,
            dishes=report["dishes_cloned"],
            boms=report["boms_cloned"],
        )
        return report

    async def get_cross_store_comparison(
        self,
        store_ids: List[str],
        metric: str = "waste_rate",
    ) -> List[Dict]:
        """
        跨店对比分析（Neo4j Cypher）

        metric 选项：
          waste_rate     - 各店损耗率对比
          bom_diff       - 同菜品 BOM 差异
          top_dishes     - 各店热销菜品对比
        """
        from src.agents.ontology_adapter import KnowledgeAwareAgent

        agent = KnowledgeAwareAgent("cross_store")
        store_list = str(store_ids)

        if metric == "waste_rate":
            cypher = """
            UNWIND $store_ids AS sid
            MATCH (s:Store {store_id: sid})
            OPTIONAL MATCH (w:WasteEvent)-[:WASTE_OF]->(d:Dish)<-[:HAS_DISH]-(s)
            RETURN
              s.store_id     AS store_id,
              s.name         AS store_name,
              count(w)       AS waste_events,
              sum(w.quantity) AS total_waste
            ORDER BY total_waste DESC
            """
            results = agent.query_ontology(cypher, {"store_ids": store_ids})

        elif metric == "bom_diff":
            cypher = """
            UNWIND $store_ids AS sid
            MATCH (s:Store {store_id: sid})-[:HAS_DISH]->(d:Dish)-[:HAS_BOM]->(b:BOM)
            WHERE b.expiry_date IS NULL
            MATCH (b)-[r:REQUIRES]->(i:Ingredient)
            RETURN
              s.store_id AS store_id,
              d.name     AS dish_name,
              i.name     AS ingredient,
              r.qty      AS qty,
              r.unit     AS unit
            ORDER BY d.name, s.store_id
            LIMIT 200
            """
            results = agent.query_ontology(cypher, {"store_ids": store_ids})

        elif metric == "top_dishes":
            cypher = """
            UNWIND $store_ids AS sid
            MATCH (s:Store {store_id: sid})-[:HAS_DISH]->(d:Dish)
            OPTIONAL MATCH (o:Order)-[:CONTAINS_DISH]->(d)
            RETURN
              s.store_id AS store_id,
              d.name     AS dish_name,
              count(o)   AS order_count
            ORDER BY s.store_id, order_count DESC
            LIMIT 100
            """
            results = agent.query_ontology(cypher, {"store_ids": store_ids})

        else:
            results = []

        agent.close()
        return results

    async def get_brand_benchmark(self, brand_store_ids: List[str]) -> Dict:
        """
        品牌级基准对比报告（所有连锁店汇总）

        指标：平均损耗率、头部菜品、各店本体健康度
        """
        from src.agents.ontology_adapter import KnowledgeAwareAgent

        agent = KnowledgeAwareAgent("benchmark")
        summaries = []
        for sid in brand_store_ids:
            summary = agent.get_store_knowledge_summary(sid)
            summary["store_id"] = sid
            summaries.append(summary)
        agent.close()

        total_dishes = sum(s.get("dish_count", 0) for s in summaries)
        total_boms = sum(s.get("bom_count", 0) for s in summaries)
        total_waste_events = sum(s.get("waste_event_count", 0) for s in summaries)

        return {
            "store_count": len(brand_store_ids),
            "total_dishes": total_dishes,
            "total_boms": total_boms,
            "total_waste_events": total_waste_events,
            "avg_bom_per_store": round(total_boms / max(len(brand_store_ids), 1), 1),
            "stores": summaries,
        }

    # ── 内部克隆方法 ──────────────────────────────────────────────────────────

    async def _clone_ingredients(
        self,
        source_store_id: str,
        target_store_id: str,
    ) -> int:
        """克隆食材主档（InventoryItem）"""
        stmt = select(InventoryItem).where(InventoryItem.store_id == source_store_id)
        result = await self.db.execute(stmt)
        source_ings = list(result.scalars().all())

        count = 0
        for src in source_ings:
            # 检查目标门店是否已有相同 ID 的食材
            existing_stmt = select(InventoryItem).where(
                InventoryItem.id == src.id
            )
            existing = await self.db.execute(existing_stmt)
            if existing.scalar_one_or_none():
                continue  # 食材 ID 共享（供应商食材通用）

            new_ing = InventoryItem(
                id=src.id,  # 保持同 ID（食材在品牌层共享）
                store_id=target_store_id,
                name=src.name,
                category=src.category,
                unit=src.unit,
                current_quantity=0.0,  # 新店库存归零
                min_quantity=src.min_quantity,
                max_quantity=src.max_quantity,
                unit_cost=src.unit_cost,
                status=InventoryStatus.NORMAL,
                supplier_name=src.supplier_name,
                supplier_contact=src.supplier_contact,
            )
            self.db.add(new_ing)
            count += 1

        await self.db.flush()
        return count

    async def _clone_dishes(
        self,
        source_store_id: str,
        target_store_id: str,
        dish_filter: Optional[List[str]],
    ) -> Dict[str, str]:
        """
        克隆菜品主档，返回 {源 dish_id: 新 dish_id}
        """
        stmt = select(Dish).where(Dish.store_id == source_store_id)
        if dish_filter:
            stmt = stmt.where(Dish.code.in_(dish_filter))
        result = await self.db.execute(stmt)
        source_dishes = list(result.scalars().all())

        id_mapping: Dict[str, str] = {}
        for src in source_dishes:
            new_id = uuid.uuid4()
            new_dish = Dish(
                id=new_id,
                store_id=target_store_id,
                name=src.name,
                code=src.code,
                category_id=src.category_id,
                description=src.description,
                price=src.price,
                original_price=src.original_price,
                cost=src.cost,
                unit=src.unit,
                is_available=src.is_available,
                cooking_method=src.cooking_method,
                kitchen_station=src.kitchen_station,
                preparation_time=src.preparation_time,
                tags=src.tags,
                allergens=src.allergens,
                notes=src.notes,
            )
            self.db.add(new_dish)
            id_mapping[str(src.id)] = str(new_id)

        await self.db.flush()
        return id_mapping

    async def _clone_boms(
        self,
        source_store_id: str,
        target_store_id: str,
        dish_id_mapping: Dict[str, str],
    ) -> int:
        """克隆 BOM（仅激活版本）"""
        bom_svc = BOMService(self.db)
        count = 0

        for src_dish_id, tgt_dish_id in dish_id_mapping.items():
            src_bom = await bom_svc.get_active_bom(src_dish_id)
            if not src_bom:
                continue

            new_bom = await bom_svc.create_bom(
                store_id=target_store_id,
                dish_id=tgt_dish_id,
                version=src_bom.version,
                effective_date=datetime.utcnow(),
                yield_rate=float(src_bom.yield_rate),
                standard_portion=float(src_bom.standard_portion) if src_bom.standard_portion else None,
                prep_time_minutes=src_bom.prep_time_minutes,
                notes=f"[克隆自 {source_store_id}] {src_bom.notes or ''}",
                created_by=self.created_by,
                activate=True,
            )

            for item in src_bom.items:
                await bom_svc.add_bom_item(
                    bom_id=str(new_bom.id),
                    ingredient_id=item.ingredient_id,
                    standard_qty=float(item.standard_qty),
                    unit=item.unit,
                    raw_qty=float(item.raw_qty) if item.raw_qty else None,
                    unit_cost=item.unit_cost,
                    waste_factor=float(item.waste_factor) if item.waste_factor else 0.0,
                    is_key_ingredient=item.is_key_ingredient,
                    is_optional=item.is_optional,
                    prep_notes=item.prep_notes,
                )

            count += 1

        await self.db.flush()
        return count

    async def _sync_to_neo4j(
        self,
        source_store_id: str,
        target_store_id: str,
        target_store_name: str,
    ) -> None:
        """将目标门店结构同步到 Neo4j，建立品牌本体关系"""
        from src.ontology.data_sync import OntologyDataSync

        with OntologyDataSync() as sync:
            # 创建目标门店节点
            sync.driver.session().run(
                """
                MERGE (s:Store {store_id: $store_id})
                ON CREATE SET s.name = $name, s.created_at = timestamp()
                ON MATCH SET  s.name = $name
                WITH s
                MATCH (src:Store {store_id: $source_id})
                MERGE (s)-[:PART_OF]->(src)
                """,
                store_id=target_store_id,
                name=target_store_name,
                source_id=source_store_id,
            )

            # 从源门店复制 Dish 节点到目标门店（共享名称/BOM 结构）
            sync.driver.session().run(
                """
                MATCH (src:Store {store_id: $source_id})-[:HAS_DISH]->(d:Dish)
                MATCH (tgt:Store {store_id: $target_id})
                MERGE (tgt)-[:HAS_DISH]->(d)
                """,
                source_id=source_store_id,
                target_id=target_store_id,
            )

        logger.info(
            "Neo4j 多店本体同步完成",
            source=source_store_id,
            target=target_store_id,
        )
