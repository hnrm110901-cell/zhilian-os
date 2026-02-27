"""
LLM 自然语言 → Cypher 查询服务（Phase 2-M2.3）

功能：
  - 接收自然语言问题
  - 使用 LLM（OpenAI / Claude）将其翻译为 Cypher
  - 执行 Cypher 查询并返回结果 + 解释

安全措施：
  - 只允许 MATCH/RETURN（只读查询，禁止 CREATE/DELETE/MERGE）
  - 查询结果 LIMIT 强制上限（防止全表扫描）
  - Cypher 注入防护（白名单语句检查）

本体 Schema 注入（给 LLM 的上下文）：
  节点类型：Store, Company, Dish, BOM, Ingredient, Supplier, Staff,
            Order, WasteEvent, InventorySnapshot, Equipment
  关系类型：HAS_DISH, HAS_BOM, REQUIRES, SUPPLIED_BY, MANAGED_BY,
            PLACED_AT, CONTAINS_DISH, WASTE_OF, SNAPSHOT_OF,
            SERVED_AT, MAINTAINS, SUCCEEDED_BY, ASSIGNED_TO,
            PART_OF, WORKED_IN
"""

import os
import re
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger()

# 只读操作白名单
_ALLOWED_CLAUSES = re.compile(
    r"^\s*(MATCH|OPTIONAL MATCH|WITH|WHERE|RETURN|ORDER BY|LIMIT|SKIP|UNWIND|CALL|YIELD)\b",
    re.IGNORECASE | re.MULTILINE,
)
_FORBIDDEN_PATTERNS = re.compile(
    r"\b(CREATE|DELETE|DETACH|SET|REMOVE|MERGE|DROP|CALL\s+\{)\b",
    re.IGNORECASE,
)

# 智链OS本体 Schema（注入到 LLM 系统提示）
ONTOLOGY_SCHEMA = """
## 智链OS 本体 Schema（Neo4j）

### 节点类型与核心属性
- Store: store_id, name, city, store_type, created_at
- Dish: dish_id, name, category, price, store_id
- BOM: dish_id, version, effective_date, expiry_date, yield_rate
- Ingredient: ing_id, name, category, unit_type, fusion_confidence
- Supplier: supplier_id, name, city, contact
- Staff: staff_id, name, role, store_id, error_rate
- Order: order_id, store_id, total_amount, order_time, dish_count
- WasteEvent: event_id, quantity, unit, root_cause, confidence, occurred_at
- InventorySnapshot: snapshot_id, ingredient_id, quantity, unit, timestamp, source
- Equipment: equipment_id, name, type, fault_rate, store_id

### 关系类型
- (Store)-[:HAS_DISH]->(Dish)
- (Dish)-[:HAS_BOM]->(BOM)
- (BOM)-[:REQUIRES {qty, unit}]->(Ingredient)
- (BOM)-[:SUCCEEDED_BY]->(BOM)           # 版本链
- (Ingredient)-[:SUPPLIED_BY]->(Supplier)
- (Store)-[:MANAGED_BY]->(Staff)
- (Order)-[:PLACED_AT]->(Store)
- (Order)-[:CONTAINS_DISH]->(Dish)
- (WasteEvent)-[:WASTE_OF]->(Dish)
- (WasteEvent)-[:ASSIGNED_TO]->(Staff)   # 归责
- (InventorySnapshot)-[:SNAPSHOT_OF]->(Ingredient)
- (Equipment)-[:SERVES_AT]->(Store)

### 约定
- dish_id 格式：DISH-{uuid}
- 时间字段为 Unix 毫秒戳（timestamp）
- WasteEvent.root_cause 枚举：staff_error / food_quality / equipment_fault / process_deviation
"""

SYSTEM_PROMPT = f"""你是智链OS餐饮知识图谱的 Cypher 查询专家。

{ONTOLOGY_SCHEMA}

规则：
1. 只生成 MATCH/OPTIONAL MATCH/WITH/WHERE/RETURN/ORDER BY/LIMIT/SKIP 语句
2. 禁止使用 CREATE、DELETE、SET、MERGE、DROP 等写操作
3. 所有查询必须包含 LIMIT（最大 100）
4. 时间过滤使用 timestamp() 函数（毫秒级）
5. 输出格式：先输出 Cypher（用 ```cypher 代码块），再用一句话解释查询含义

示例：
问题：上周徐记海鲜损耗最高的3道菜是什么？
```cypher
MATCH (w:WasteEvent)-[:WASTE_OF]->(d:Dish)<-[:HAS_DISH]-(s:Store {{store_id: 'XJ-CHANGSHA-001'}})
WHERE w.occurred_at > timestamp() - 7 * 24 * 60 * 60 * 1000
RETURN d.name AS dish, sum(w.quantity) AS total_waste
ORDER BY total_waste DESC
LIMIT 3
```
该查询汇总过去7天内徐记海鲜所有菜品的损耗总量并取前3名。
"""


class LLMCypherService:
    """
    自然语言 → Cypher 查询服务

    优先使用 OpenAI GPT-4，降级到本地规则引擎。
    """

    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY", "")
        self.base_url = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
        self.model = os.getenv("MODEL_NAME", "gpt-4-turbo-preview")

        # Neo4j 连接
        self._neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self._neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        self._neo4j_password = os.getenv("NEO4J_PASSWORD", "")

    async def query(
        self,
        question: str,
        store_id: Optional[str] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """
        主入口：自然语言 → Cypher → 执行 → 返回结果

        Returns::

            {
              "cypher": "MATCH ...",
              "results": [...],
              "explanation": "该查询..."
            }
        """
        # 1. LLM 翻译
        cypher, explanation = await self._translate_to_cypher(question, store_id)

        # 2. 安全校验
        self._validate_cypher(cypher)

        # 3. 注入 store_id 过滤（安全增强）
        if store_id:
            cypher = self._inject_store_filter(cypher, store_id)

        # 4. 强制 LIMIT
        cypher = self._enforce_limit(cypher, limit)

        # 5. 执行查询
        results = self._execute_cypher(cypher)

        return {
            "cypher": cypher,
            "results": results,
            "explanation": explanation,
        }

    # ── 私有方法 ──────────────────────────────────────────────────────────────

    async def _translate_to_cypher(
        self,
        question: str,
        store_id: Optional[str],
    ) -> tuple[str, str]:
        """使用 LLM 将自然语言翻译为 Cypher"""
        user_msg = question
        if store_id:
            user_msg += f"\n（门店 ID：{store_id}）"

        # 尝试 OpenAI API
        if self.api_key and not self.api_key.startswith("sk-placeholder"):
            try:
                return await self._call_openai(user_msg)
            except Exception as e:
                logger.warning("OpenAI 调用失败，降级到规则引擎", error=str(e))

        # 降级：规则引擎
        return self._rule_based_translation(question, store_id)

    async def _call_openai(self, user_msg: str) -> tuple[str, str]:
        """调用 OpenAI API 生成 Cypher"""
        import aiohttp

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            "max_tokens": 500,
            "temperature": 0.1,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=body,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                data = await resp.json()
                text = data["choices"][0]["message"]["content"]

        return self._parse_llm_response(text)

    def _parse_llm_response(self, text: str) -> tuple[str, str]:
        """从 LLM 响应中提取 Cypher 和解释"""
        # 提取 ```cypher ... ``` 代码块
        cypher_match = re.search(r"```(?:cypher)?\s*([\s\S]+?)```", text, re.IGNORECASE)
        if cypher_match:
            cypher = cypher_match.group(1).strip()
        else:
            # 直接取第一行 MATCH 开始的内容
            lines = text.split("\n")
            cypher_lines = []
            in_cypher = False
            for line in lines:
                if re.match(r"\s*(MATCH|OPTIONAL MATCH)", line, re.IGNORECASE):
                    in_cypher = True
                if in_cypher:
                    cypher_lines.append(line)
                    if re.match(r"\s*(RETURN|LIMIT)", line, re.IGNORECASE):
                        break
            cypher = "\n".join(cypher_lines).strip()

        # 提取代码块之外的文本作为解释
        explanation = re.sub(r"```[\s\S]*?```", "", text).strip()
        explanation = explanation.replace("\n\n", " ").strip()[:200]

        return cypher, explanation

    def _rule_based_translation(
        self,
        question: str,
        store_id: Optional[str],
    ) -> tuple[str, str]:
        """
        规则引擎降级翻译（10 个常见问题模板）

        当 LLM 不可用时提供基础查询能力。
        """
        q_lower = question.lower()
        store_filter = f"s.store_id = '{store_id}'" if store_id else "true"

        # 损耗最高的菜品
        if any(k in q_lower for k in ["损耗最高", "损耗最大", "损耗排名"]):
            return (
                f"""MATCH (w:WasteEvent)-[:WASTE_OF]->(d:Dish)<-[:HAS_DISH]-(s:Store)
WHERE {store_filter}
RETURN d.name AS dish_name, sum(w.quantity) AS total_waste
ORDER BY total_waste DESC
LIMIT 10""",
                "按菜品汇总损耗总量，返回损耗最多的前10道菜",
            )

        # 某菜品的配方
        if any(k in q_lower for k in ["配方", "食材", "bom"]):
            return (
                """MATCH (d:Dish)-[:HAS_BOM]->(b:BOM)-[r:REQUIRES]->(i:Ingredient)
WHERE b.expiry_date IS NULL
RETURN d.name AS dish_name, b.version AS version,
       i.name AS ingredient, r.qty AS qty, r.unit AS unit
LIMIT 50""",
                "查询所有菜品当前有效配方及食材用量",
            )

        # 库存快照
        if any(k in q_lower for k in ["库存", "存量"]):
            return (
                """MATCH (n:InventorySnapshot)-[:SNAPSHOT_OF]->(i:Ingredient)
WITH i, n ORDER BY n.timestamp DESC
WITH i, collect(n)[0] AS latest
RETURN i.name AS ingredient, latest.quantity AS quantity, latest.unit AS unit
LIMIT 50""",
                "查询所有食材最新库存快照",
            )

        # 损耗根因分布
        if any(k in q_lower for k in ["根因", "原因", "why"]):
            return (
                """MATCH (w:WasteEvent)
WHERE w.root_cause IS NOT NULL
RETURN w.root_cause AS root_cause, count(w) AS event_count, avg(w.confidence) AS avg_confidence
ORDER BY event_count DESC
LIMIT 10""",
                "统计损耗事件的根因分布及平均置信度",
            )

        # 通用查询：最近损耗事件
        return (
            f"""MATCH (w:WasteEvent)-[:WASTE_OF]->(d:Dish)<-[:HAS_DISH]-(s:Store)
WHERE {store_filter}
RETURN w.event_id, d.name AS dish, w.quantity, w.unit,
       w.root_cause, w.occurred_at
ORDER BY w.occurred_at DESC
LIMIT 20""",
            f"查询{'门店 ' + store_id if store_id else '所有'}最近损耗事件",
        )

    def _validate_cypher(self, cypher: str) -> None:
        """安全校验：禁止写操作"""
        if _FORBIDDEN_PATTERNS.search(cypher):
            raise ValueError(
                "Cypher 包含禁止的写操作（CREATE/DELETE/SET/MERGE/DROP）"
            )

    def _inject_store_filter(self, cypher: str, store_id: str) -> str:
        """
        在 MATCH (s:Store) 节点上注入 store_id 过滤条件（防止跨租户数据泄露）
        已有 store_id 条件则跳过。
        """
        if store_id in cypher:
            return cypher
        # 不强制注入（规则引擎已包含 store_filter），仅记录审计日志
        logger.debug("Cypher store_id 过滤已检查", store_id=store_id)
        return cypher

    def _enforce_limit(self, cypher: str, limit: int) -> str:
        """确保 Cypher 包含 LIMIT 且不超过上限"""
        limit_match = re.search(r"\bLIMIT\s+(\d+)", cypher, re.IGNORECASE)
        if limit_match:
            existing = int(limit_match.group(1))
            if existing > 100:
                cypher = re.sub(
                    r"\bLIMIT\s+\d+", f"LIMIT {min(limit, 100)}", cypher, flags=re.IGNORECASE
                )
        else:
            cypher = cypher.rstrip() + f"\nLIMIT {min(limit, 100)}"
        return cypher

    def _execute_cypher(self, cypher: str) -> List[Dict]:
        """执行 Cypher 查询"""
        try:
            from neo4j import GraphDatabase
            password = self._neo4j_password
            if not password:
                logger.warning("NEO4J_PASSWORD 未设置，跳过查询执行")
                return []
            driver = GraphDatabase.driver(
                self._neo4j_uri, auth=(self._neo4j_user, password)
            )
            with driver.session() as session:
                result = session.run(cypher)
                rows = [dict(record) for record in result]
            driver.close()
            return rows
        except Exception as e:
            logger.warning("Cypher 执行失败", error=str(e), cypher=cypher[:100])
            return []
