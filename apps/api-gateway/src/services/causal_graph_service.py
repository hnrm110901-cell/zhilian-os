"""
L4 因果图谱查询服务（Causal Graph Query Service）

职责：从 Neo4j 知识图谱中提取因果链、供应链溯源、设备故障关联、
     跨店学习线索，返回可直接插入 ReasoningEngine 证据链的文本列表。

Cypher 查询遵循 Hassabis 推理仿真原则：
  - 多跳关系遍历（1-3 跳因果路径）
  - 时间窗口过滤（7/14/30 天滑动窗口）
  - 置信度加权排序
  - 跨店模式泛化

与 WasteReasoningEngine 的关系：
  WasteReasoningEngine._fetch_event_context  → 针对单一损耗事件的同步查询
  CausalGraphService                         → 面向门店维度的批量异步分析
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger()

DEFAULT_WINDOW_DAYS = 14


class CausalGraphService:
    """
    Neo4j 因果图谱查询服务

    使用方式（上下文管理器）::

        with CausalGraphService() as svc:
            hints = await svc.get_full_causal_summary("STORE001")

    直接调用（推荐在 DiagnosisService 中使用）::

        svc = CausalGraphService()
        try:
            hints = await svc.get_full_causal_summary(store_id)
        finally:
            svc.close()
    """

    def __init__(self):
        self._driver = None

    # ── 驱动管理 ──────────────────────────────────────────────────────────────

    def _get_driver(self):
        """惰性初始化 Neo4j 驱动（连接失败时返回 None，不抛异常）"""
        if self._driver is None:
            try:
                from neo4j import GraphDatabase
                uri  = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
                user = os.getenv("NEO4J_USER",     "neo4j")
                pwd  = os.getenv("NEO4J_PASSWORD",  "")
                if not pwd:
                    logger.warning("NEO4J_PASSWORD 未设置，跳过因果图谱查询")
                    return None
                self._driver = GraphDatabase.driver(uri, auth=(user, pwd))
            except Exception as e:
                logger.warning("Neo4j 驱动初始化失败", error=str(e))
        return self._driver

    def close(self):
        if self._driver:
            self._driver.close()
            self._driver = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _run(self, cypher: str, params: Dict) -> List[Dict]:
        """执行只读 Cypher，返回记录列表（失败返回 []）"""
        driver = self._get_driver()
        if driver is None:
            return []
        try:
            with driver.session() as session:
                result = session.run(cypher, **params)
                return [dict(r) for r in result]
        except Exception as e:
            logger.warning("Cypher 执行失败", error=str(e), cypher=cypher[:100])
            return []

    # ── 损耗根因分布 ──────────────────────────────────────────────────────────

    async def get_waste_root_cause_summary(
        self,
        store_id:    str,
        window_days: int = DEFAULT_WINDOW_DAYS,
    ) -> List[str]:
        """
        近 N 天损耗事件根因分布统计。

        Cypher 路径: Store ← OCCURRED_IN ← WasteEvent
        Returns: List[str] 可读证据文本
        """
        rows = self._run(
            """
            MATCH (s:Store {store_id: $store_id})<-[:OCCURRED_IN]-(w:WasteEvent)
            WHERE w.occurred_at > datetime() - duration({days: $days})
              AND w.root_cause_type IS NOT NULL
            WITH w.root_cause_type  AS cause,
                 count(w)           AS freq,
                 avg(toFloat(w.root_cause_confidence)) AS avg_conf
            RETURN cause, freq, round(avg_conf * 100) / 100 AS avg_conf
            ORDER BY freq * avg_conf DESC
            LIMIT 5
            """,
            {"store_id": store_id, "days": window_days},
        )
        return [
            f"近{window_days}天根因「{r['cause']}」出现 {r['freq']} 次，"
            f"平均置信度 {r['avg_conf']:.0%}"
            for r in rows
        ]

    # ── 供应链溯源 ────────────────────────────────────────────────────────────

    async def get_ingredient_supply_chain(
        self,
        store_id:    str,
        window_days: int = DEFAULT_WINDOW_DAYS,
    ) -> List[str]:
        """
        追溯高损耗食材的供应商，识别品质风险。

        Cypher 路径:
          WasteEvent → INVOLVES → Ingredient ← SUPPLIED_BY ← Supplier
        """
        rows = self._run(
            """
            MATCH (s:Store {store_id: $store_id})<-[:OCCURRED_IN]-(w:WasteEvent)
            WHERE w.occurred_at > datetime() - duration({days: $days})
            MATCH (w)-[:INVOLVES]->(ing:Ingredient)
            OPTIONAL MATCH (ing)<-[:SUPPLIED_BY]-(sup:Supplier)
            WITH ing.name        AS ingredient,
                 sup.name        AS supplier,
                 sup.quality_score AS q_score,
                 count(w)        AS waste_cnt,
                 sum(toFloat(w.amount)) AS total_loss
            WHERE waste_cnt >= 2
            RETURN ingredient, supplier, q_score, waste_cnt, total_loss
            ORDER BY total_loss DESC
            LIMIT 5
            """,
            {"store_id": store_id, "days": window_days},
        )
        hints = []
        for r in rows:
            hint = f"食材「{r['ingredient']}」损耗 {r['waste_cnt']} 次（累计 {r['total_loss']:.1f}）"
            if r.get("supplier"):
                hint += f"，供应商「{r['supplier']}」品质评分 {r.get('q_score', 'N/A')}"
                if r.get("q_score") and float(r["q_score"]) < 3.0:
                    hint += "（偏低，建议评估更换）"
            hints.append(hint)
        return hints

    # ── BOM 合规因果分析 ──────────────────────────────────────────────────────

    async def get_bom_compliance_issues(
        self,
        store_id:    str,
        window_days: int = 30,
    ) -> List[str]:
        """
        识别哪些菜品食材损耗集中超出 BOM 理论量。

        Cypher 路径:
          Store → HAS_DISH → Dish → HAS_BOM → BOM → REQUIRES → Ingredient
                  + Store ← OCCURRED_IN ← WasteEvent → INVOLVES → Ingredient
        """
        rows = self._run(
            """
            MATCH (s:Store {store_id: $store_id})-[:HAS_DISH]->(d:Dish)
            MATCH (d)-[:HAS_BOM]->(b:BOM)
            MATCH (b)-[:REQUIRES]->(ing:Ingredient)
            OPTIONAL MATCH (s)<-[:OCCURRED_IN]-(w:WasteEvent)-[:INVOLVES]->(ing)
            WHERE w.occurred_at > datetime() - duration({days: $days})
            WITH d.name  AS dish_name,
                 ing.name AS ing_name,
                 count(w) AS waste_events
            WHERE waste_events >= 3
            RETURN dish_name, ing_name, waste_events
            ORDER BY waste_events DESC
            LIMIT 5
            """,
            {"store_id": store_id, "days": window_days},
        )
        return [
            f"菜品「{r['dish_name']}」食材「{r['ing_name']}」"
            f"近{window_days}天损耗 {r['waste_events']} 次，建议复核 BOM 配方用量"
            for r in rows
        ]

    # ── 设备故障因果链 ────────────────────────────────────────────────────────

    async def get_equipment_fault_chain(
        self,
        store_id: str,
    ) -> List[str]:
        """
        故障/维护设备与相关食材损耗的因果关联。

        Cypher 路径:
          Store → HAS_EQUIPMENT → Equipment → STORES → Ingredient
                + Store ← OCCURRED_IN ← WasteEvent → INVOLVES → Ingredient
        """
        rows = self._run(
            """
            MATCH (s:Store {store_id: $store_id})-[:HAS_EQUIPMENT]->(eq:Equipment)
            WHERE eq.status IN ['fault', 'maintenance']
            MATCH (eq)-[:STORES]->(ing:Ingredient)
            OPTIONAL MATCH (s)<-[:OCCURRED_IN]-(w:WasteEvent)-[:INVOLVES]->(ing)
            WHERE w.occurred_at > datetime() - duration({days: 14})
            RETURN eq.name              AS equip,
                   eq.status            AS eq_status,
                   eq.malfunction_rate  AS m_rate,
                   ing.name             AS ingredient,
                   count(w)             AS related_waste
            ORDER BY related_waste DESC
            LIMIT 5
            """,
            {"store_id": store_id},
        )
        hints = []
        for r in rows:
            hint = f"设备「{r['equip']}」状态「{r['eq_status']}」"
            if r.get("m_rate"):
                hint += f"（故障率 {float(r['m_rate']):.0%}）"
            hint += f"，相关食材「{r['ingredient']}」近14天损耗 {r['related_waste']} 次"
            hints.append(hint)
        return hints

    # ── 员工操作误差时段模式 ──────────────────────────────────────────────────

    async def get_staff_error_patterns(
        self,
        store_id:    str,
        window_days: int = 30,
    ) -> List[str]:
        """
        分析员工操作失误的小时分布，识别换班高危时段。

        Cypher 路径: Store ← OCCURRED_IN ← WasteEvent (root_cause_type=staff_error)
        """
        rows = self._run(
            """
            MATCH (s:Store {store_id: $store_id})<-[:OCCURRED_IN]-(w:WasteEvent)
            WHERE w.root_cause_type = 'staff_error'
              AND w.occurred_at > datetime() - duration({days: $days})
            WITH w.occurred_at.hour AS hour_of_day,
                 count(w) AS cnt
            RETURN hour_of_day, cnt
            ORDER BY cnt DESC
            LIMIT 3
            """,
            {"store_id": store_id, "days": window_days},
        )
        hints = []
        SHIFT_LABELS = {
            range(7, 10):  "早晚班交接（07-09时）",
            range(14, 17): "午晚班交接（14-16时）",
            range(21, 24): "晚班收尾（21-23时）",
        }
        for r in rows:
            hour = r.get("hour_of_day")
            cnt  = r.get("cnt", 0)
            label = f"{hour}:00 附近"
            if hour is not None:
                for rng, lbl in SHIFT_LABELS.items():
                    if int(hour) in rng:
                        label = lbl
                        break
            hints.append(
                f"员工操作失误集中在 {label}（{cnt} 次），"
                f"建议强化该时段操作规范检查"
            )
        return hints

    # ── 跨店学习线索 ──────────────────────────────────────────────────────────

    async def get_cross_store_learning_hints(
        self,
        store_id:    str,
        metric_name: str = "waste_rate_p30d",
    ) -> List[str]:
        """
        找到相似门店中表现更好的，提取学习线索（CROSS-045~050 规则的图谱支撑）。

        Cypher 路径: Store ← SIMILAR_TO → Store (better performers)
        """
        rows = self._run(
            """
            MATCH (s:Store {store_id: $store_id})-[sim:SIMILAR_TO]-(peer:Store)
            WHERE peer[$metric] IS NOT NULL
              AND s[$metric] IS NOT NULL
              AND peer[$metric] < s[$metric] * 0.85
            RETURN peer.store_id          AS peer_id,
                   peer[$metric]          AS peer_value,
                   s[$metric]             AS self_value,
                   sim.similarity_score   AS sim_score
            ORDER BY sim.similarity_score DESC
            LIMIT 3
            """,
            {"store_id": store_id, "metric": metric_name},
        )
        hints = []
        for r in rows:
            self_val   = r.get("self_value") or 0
            peer_val   = r.get("peer_value") or 0
            gap        = (self_val - peer_val) / self_val if self_val else 0
            sim_score  = r.get("sim_score", 0)
            hints.append(
                f"相似门店「{r['peer_id']}」{metric_name}={peer_val:.3f}，"
                f"优于本店 {gap:.0%}（相似度 {sim_score:.2f}），"
                f"建议重点学习其运营经验"
            )
        return hints

    # ── 综合因果摘要（主入口） ────────────────────────────────────────────────

    async def get_full_causal_summary(
        self,
        store_id:    str,
        window_days: int = DEFAULT_WINDOW_DAYS,
    ) -> List[str]:
        """
        聚合所有因果查询，返回综合证据列表（最多 12 条，每类 ≤2 条）。

        供 DiagnosisService._fetch_causal_hints() 调用。
        """
        all_hints: List[str] = []

        _queries = [
            (self.get_waste_root_cause_summary,    (store_id, window_days)),
            (self.get_ingredient_supply_chain,     (store_id, window_days)),
            (self.get_bom_compliance_issues,       (store_id, window_days)),
            (self.get_equipment_fault_chain,       (store_id,)),
            (self.get_staff_error_patterns,        (store_id, window_days)),
            (self.get_cross_store_learning_hints,  (store_id,)),
        ]

        for fn, args in _queries:
            try:
                hints = await fn(*args)
                all_hints.extend(hints[:2])
            except Exception as e:
                logger.warning("因果子查询失败", fn=fn.__name__, error=str(e))

        return all_hints[:12]
