"""
KnowledgeAwareAgent — 本体感知 Agent 基类（Palantir 本体适配层）

设计：
  - 继承 LLMEnhancedAgent，在其基础上增加 Neo4j 本体查询能力
  - 双轨查询：PostgreSQL（事务数据）+ Neo4j（知识图谱/推理）
  - 提供标准化方法：
      query_ontology()     : Cypher 查询
      get_dish_bom()       : 获取菜品当前 BOM
      get_waste_events()   : 获取损耗事件链
      explain_reasoning()  : 从 WasteEvent 节点读取推理证据链

所有继承此基类的 Agent 自动获得以下 Neo4j 工具：
  - fetch_dish_bom_from_ontology
  - query_waste_events
  - get_ontology_reasoning_chain
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import structlog

from ..agents.llm_agent import LLMEnhancedAgent, AgentResult

logger = structlog.get_logger()


class KnowledgeAwareAgent(LLMEnhancedAgent):
    """
    本体感知 Agent 基类

    子类示例::

        class WasteAnalysisAgent(KnowledgeAwareAgent):
            def __init__(self):
                super().__init__(agent_type="waste_analysis")

            async def analyze(self, store_id: str, dish_code: str) -> AgentResult:
                bom = await self.get_dish_bom(dish_code, store_id)
                waste = await self.get_waste_events(dish_code, limit=10)
                ...
    """

    def __init__(self, agent_type: str):
        super().__init__(agent_type=agent_type)
        self._neo4j_driver = None

    def _get_driver(self):
        """懒加载 Neo4j 驱动（连接失败不影响 Agent 初始化）"""
        if self._neo4j_driver is not None:
            return self._neo4j_driver
        try:
            import os
            from neo4j import GraphDatabase
            uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
            user = os.getenv("NEO4J_USER", "neo4j")
            pw = os.getenv("NEO4J_PASSWORD", "")
            if not pw:
                raise EnvironmentError("NEO4J_PASSWORD 未设置")
            self._neo4j_driver = GraphDatabase.driver(uri, auth=(user, pw))
            return self._neo4j_driver
        except Exception as e:
            logger.warning("Neo4j 驱动初始化失败", error=str(e))
            return None

    def query_ontology(self, cypher: str, params: Optional[Dict] = None) -> List[Dict]:
        """
        执行 Cypher 查询，返回记录列表。
        Neo4j 不可用时返回空列表（降级策略）。
        """
        driver = self._get_driver()
        if driver is None:
            logger.warning("Neo4j 不可用，跳过本体查询", cypher=cypher[:80])
            return []
        try:
            with driver.session() as session:
                result = session.run(cypher, **(params or {}))
                return [dict(record) for record in result]
        except Exception as e:
            logger.warning("Cypher 查询失败", error=str(e), cypher=cypher[:80])
            return []

    def get_dish_bom(
        self,
        dish_id: str,
        store_id: Optional[str] = None,
    ) -> Optional[Dict]:
        """
        获取菜品当前激活 BOM 节点及食材明细（从 Neo4j 本体层）

        返回结构::

            {
              "dish_id": "DISH-xxx",
              "dish_name": "海鲜粥",
              "bom_version": "v1",
              "yield_rate": 0.92,
              "items": [
                {"ingredient_name": "大米", "qty": 150.0, "unit": "克"},
                ...
              ]
            }
        """
        cypher = """
        MATCH (d:Dish {dish_id: $dish_id})-[:HAS_BOM]->(b:BOM)
        WHERE b.expiry_date IS NULL
        MATCH (b)-[r:REQUIRES]->(i:Ingredient)
        RETURN
          d.dish_id   AS dish_id,
          d.name      AS dish_name,
          b.version   AS bom_version,
          b.yield_rate AS yield_rate,
          collect({
            ingredient_id:   i.ing_id,
            ingredient_name: i.name,
            qty:             r.qty,
            unit:            r.unit
          }) AS items
        LIMIT 1
        """
        rows = self.query_ontology(cypher, {"dish_id": dish_id})
        if not rows:
            return None
        row = rows[0]
        return {
            "dish_id": row.get("dish_id"),
            "dish_name": row.get("dish_name"),
            "bom_version": row.get("bom_version"),
            "yield_rate": row.get("yield_rate"),
            "items": row.get("items", []),
        }

    def get_waste_events(
        self,
        dish_id: str,
        limit: int = 20,
    ) -> List[Dict]:
        """
        获取指定菜品的损耗事件历史（从 Neo4j）

        返回每个事件的 root_cause / confidence / evidence_chain。
        """
        cypher = """
        MATCH (w:WasteEvent)-[:WASTE_OF]->(d:Dish {dish_id: $dish_id})
        RETURN
          w.event_id        AS event_id,
          w.quantity        AS quantity,
          w.unit            AS unit,
          w.root_cause      AS root_cause,
          w.confidence      AS confidence,
          w.evidence_chain  AS evidence_chain,
          w.occurred_at     AS occurred_at
        ORDER BY w.occurred_at DESC
        LIMIT $limit
        """
        return self.query_ontology(cypher, {"dish_id": dish_id, "limit": limit})

    def explain_reasoning(self, event_id: str) -> Optional[Dict]:
        """
        读取损耗事件的完整推理证据链（XAI 可解释性）

        返回::

            {
              "event_id": "WE-xxxx",
              "root_cause": "staff_error",
              "confidence": 0.82,
              "evidence": { step1: ..., step2: ..., ... },
              "scores": { staff_error: 0.82, food_quality: 0.1, ... }
            }
        """
        cypher = """
        MATCH (w:WasteEvent {event_id: $event_id})
        RETURN
          w.event_id       AS event_id,
          w.root_cause     AS root_cause,
          w.confidence     AS confidence,
          w.evidence_chain AS evidence_chain,
          w.scores         AS scores
        """
        rows = self.query_ontology(cypher, {"event_id": event_id})
        if not rows:
            return None
        row = rows[0]
        import json
        evidence = row.get("evidence_chain")
        scores = row.get("scores")
        try:
            evidence = json.loads(evidence) if isinstance(evidence, str) else evidence
        except Exception:
            pass
        try:
            scores = json.loads(scores) if isinstance(scores, str) else scores
        except Exception:
            pass
        return {
            "event_id": row.get("event_id"),
            "root_cause": row.get("root_cause"),
            "confidence": row.get("confidence"),
            "evidence": evidence,
            "scores": scores,
        }

    def get_store_knowledge_summary(self, store_id: str) -> Dict:
        """
        获取门店知识图谱摘要（节点数量统计）

        用于仪表盘展示本体健康度。
        """
        cypher = """
        MATCH (s:Store {store_id: $store_id})
        OPTIONAL MATCH (s)-[:HAS_DISH]->(d:Dish)
        OPTIONAL MATCH (d)-[:HAS_BOM]->(b:BOM)
        OPTIONAL MATCH (b)-[:REQUIRES]->(i:Ingredient)
        OPTIONAL MATCH (w:WasteEvent)-[:WASTE_OF]->(d)
        RETURN
          count(DISTINCT d) AS dish_count,
          count(DISTINCT b) AS bom_count,
          count(DISTINCT i) AS ingredient_count,
          count(DISTINCT w) AS waste_event_count
        """
        rows = self.query_ontology(cypher, {"store_id": store_id})
        if not rows:
            return {"dish_count": 0, "bom_count": 0, "ingredient_count": 0, "waste_event_count": 0}
        return rows[0]

    def close(self):
        """关闭 Neo4j 驱动连接"""
        if self._neo4j_driver:
            self._neo4j_driver.close()
            self._neo4j_driver = None
