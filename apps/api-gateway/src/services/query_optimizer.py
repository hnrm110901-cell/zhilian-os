"""
查询优化器（移植自 BettaFish keyword_optimizer，适配屯象OS餐饮运营域）

将自然语言查询改写为更贴近向量数据库存储格式的多变体查询，
通过多查询检索提升 RAG 召回率。

BettaFish原版用途：社交媒体舆情关键词优化（Weibo/小红书）
屯象OS改造要点：
  - 目标域：餐饮运营（菜品/食材/时段/成本/排班/损耗）
  - 输出：2-3个语义变体（非关键词列表），用于多查询检索
  - 复用 get_llm_client() 而非独立模型
  - 全程 async，失败时优雅降级返回原始查询

用法::

    result = await query_optimizer.optimize("上周末损耗最严重的是哪个食材？")
    # result.optimized_queries = [
    #     "食材损耗记录 过期浪费",
    #     "周末 损耗 食材成本",
    #     "库存报废 费用",
    # ]
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import List, Optional

import structlog

from ..core.llm import get_llm_client
from ..utils.retry_helper import HTTP_RETRY_CONFIG, async_graceful_retry

logger = structlog.get_logger()

# 禁用开关（环境变量 QUERY_OPTIMIZER_ENABLED=false 可运行时关闭）
import os

_ENABLED = os.getenv("QUERY_OPTIMIZER_ENABLED", "true").lower() != "false"

# 向量DB中各领域的存储描述（用于 system prompt 引导改写方向）
_DOMAIN_HINTS = {
    "events": "经营事件记录（营业额异常、设备故障、促销活动、特殊情况等）",
    "revenue": "营收订单数据（日销售额、时段客流、桌均消费、翻台率等）",
    "menu": "菜品信息（菜品名称、价格、食材用量、毛利率、销量排名等）",
    "staff": "员工排班记录（姓名、岗位、工时、绩效、排班冲突等）",
    "inventory": "库存食材记录（食材名称、进货量、损耗量、过期浪费、库存预警等）",
}

_SYSTEM_PROMPT = """\
你是一位餐饮门店经营数据检索专家。

我有一个向量数据库，存储了餐饮门店的运营记录，包括：
{domain_desc}

用户给出一个自然语言查询，你需要将其改写为 2-3 个简洁的检索变体，
让这些变体更贴近数据库中实际存储的文本格式，从而提高检索召回率。

改写原则：
1. 每个变体不超过 25 个汉字，简洁直接
2. 使用运营数据中常见的表达：菜品名、食材名、时段、金额、人员角色
3. 变体之间要有语义差异（换角度、换词），不要重复
4. 不要生造数据，保持与原始查询语义一致
5. 如果原始查询已经很精准，可以只生成 2 个变体（甚至 1 个）

输出格式（严格 JSON，不要有其他文字）：
{{"queries": ["变体1", "变体2", "变体3"], "reasoning": "一句话说明改写逻辑"}}

示例：
输入："上周末损耗最严重的是哪个食材？"
输出：
{{"queries": ["食材损耗记录 过期浪费 周末", "库存报废 食材成本 高损耗", "损耗量 食材 周六周日"], "reasoning": "将抽象问句转为描述性片段，覆盖损耗/报废/成本三个角度"}}
"""


@dataclass
class QueryOptimizationResult:
    """查询优化结果"""

    original_query: str
    optimized_queries: List[str]  # 始终 ≥1 条（降级时等于 [original_query]）
    reasoning: str = ""
    optimized: bool = True  # False 表示降级未优化


class QueryOptimizer:
    """
    RAG 查询优化器

    将用户原始查询改写为多个语义变体，供 RAGService 做多查询检索。
    失败时静默降级，不阻塞检索主流程。
    """

    def __init__(self) -> None:
        self._llm = None

    def _get_llm(self):
        if self._llm is None:
            self._llm = get_llm_client()
        return self._llm

    async def optimize(
        self,
        query: str,
        domain_hint: str = "events",
    ) -> QueryOptimizationResult:
        """
        优化查询，返回多变体结果。

        Args:
            query:       原始用户查询
            domain_hint: 目标向量域名称（events/revenue/menu/staff/inventory）

        Returns:
            QueryOptimizationResult，失败时 optimized=False 且 optimized_queries=[query]
        """
        if not _ENABLED or not query.strip():
            return QueryOptimizationResult(
                original_query=query,
                optimized_queries=[query],
                optimized=False,
            )

        return await self._call_llm_with_fallback(query, domain_hint)

    @async_graceful_retry(
        HTTP_RETRY_CONFIG,
        default_return=None,  # None 触发外层降级逻辑
    )
    async def _call_llm(self, query: str, domain_hint: str) -> Optional[QueryOptimizationResult]:
        """实际 LLM 调用（被 graceful retry 包裹）。"""
        llm = self._get_llm()
        domain_desc = _DOMAIN_HINTS.get(domain_hint, _DOMAIN_HINTS["events"])
        system_prompt = _SYSTEM_PROMPT.format(domain_desc=domain_desc)

        raw = await llm.generate(
            prompt=f"原始查询：{query}",
            system_prompt=system_prompt,
            temperature=0.3,
            max_tokens=256,
        )

        queries, reasoning = self._parse_response(raw, query)
        optimized = queries != [query]

        logger.info(
            "query_optimizer.done",
            original=query,
            variants=queries,
            domain=domain_hint,
            optimized=optimized,
        )
        return QueryOptimizationResult(
            original_query=query,
            optimized_queries=queries,
            reasoning=reasoning,
            optimized=optimized,
        )

    async def _call_llm_with_fallback(self, query: str, domain_hint: str) -> QueryOptimizationResult:
        """调用 LLM，任何失败都降级返回原始查询。"""
        result = await self._call_llm(query, domain_hint)
        if result is None:
            logger.warning("query_optimizer.fallback_to_original", query=query)
            return QueryOptimizationResult(
                original_query=query,
                optimized_queries=[query],
                optimized=False,
            )
        return result

    # ──────────────────────────────────────────────────────────────────────────
    # 解析辅助
    # ──────────────────────────────────────────────────────────────────────────

    def _parse_response(self, raw: str, original_query: str) -> tuple[List[str], str]:
        """
        解析 LLM 输出的 JSON，提取 queries 和 reasoning。
        任何解析失败都安全降级返回 [original_query]。
        """
        try:
            # 从输出中提取 JSON 块（LLM 有时会在 JSON 前后加说明文字）
            json_match = re.search(r"\{.*\}", raw, re.DOTALL)
            if not json_match:
                return [original_query], ""

            data = json.loads(json_match.group())
            raw_queries: List = data.get("queries", [])
            reasoning: str = data.get("reasoning", "")

            # 清洗：去空白、去重、长度限制
            seen: set[str] = set()
            clean: List[str] = []
            for q in raw_queries:
                q = str(q).strip()
                if q and len(q) <= 60 and q not in seen:
                    seen.add(q)
                    clean.append(q)
                if len(clean) >= 3:
                    break

            if not clean:
                return [original_query], reasoning

            return clean, reasoning

        except Exception as exc:
            logger.warning("query_optimizer.parse_failed", error=str(exc))
            return [original_query], ""


# ─────────────────────────────────────────────────────────────────────────────
# 全局单例
# ─────────────────────────────────────────────────────────────────────────────
query_optimizer = QueryOptimizer()
