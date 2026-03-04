"""
Tests for PerformanceAgent._nl_query keyword dispatch (no-LLM path)
"""
import os

for _k, _v in {
    "DATABASE_URL":          "postgresql+asyncpg://test:test@localhost/test",
    "REDIS_URL":             "redis://localhost:6379/0",
    "CELERY_BROKER_URL":     "redis://localhost:6379/0",
    "CELERY_RESULT_BACKEND": "redis://localhost:6379/0",
    "SECRET_KEY":            "test-secret-key",
    "JWT_SECRET":            "test-jwt-secret",
}.items():
    os.environ.setdefault(_k, _v)

import pytest
from unittest.mock import AsyncMock, patch

from src.agents.performance_agent import (
    PerformanceAgent, _detect_nl_role, _detect_nl_rule,
    _NL_INTENT_REPORT, _NL_INTENT_COMMISSION, _NL_INTENT_RULE,
)


@pytest.fixture
def agent():
    return PerformanceAgent()


# ── _detect_nl_role ───────────────────────────────────────────────────────────

class TestDetectNlRole:
    def test_store_manager_from_店长(self):
        assert _detect_nl_role("店长本月绩效") == "store_manager"

    def test_waiter_from_服务员(self):
        assert _detect_nl_role("服务员加单提成") == "waiter"

    def test_kitchen_from_后厨(self):
        assert _detect_nl_role("后厨出餐效率") == "kitchen"

    def test_delivery_from_外卖(self):
        assert _detect_nl_role("外卖单量提成") == "delivery"

    def test_cashier_from_收银(self):
        assert _detect_nl_role("收银准确率") == "cashier"

    def test_shift_manager_from_值班经理(self):
        assert _detect_nl_role("值班经理业绩") == "shift_manager"

    def test_no_role_keyword_returns_none(self):
        assert _detect_nl_role("本月提成汇总") is None

    def test_empty_string_returns_none(self):
        assert _detect_nl_role("") is None


# ── _detect_nl_rule ───────────────────────────────────────────────────────────

class TestDetectNlRule:
    def test_exact_rule_name_found(self):
        assert _detect_nl_rule("好评奖规则") == "好评奖"

    def test_partial_name_found(self):
        # "单量提成" is prefix of "单量提成(元/单或阶梯)"
        result = _detect_nl_rule("外卖单量提成怎么算")
        assert result is not None and "单量提成" in result

    def test_no_rule_name_returns_none(self):
        assert _detect_nl_rule("本月总收入") is None


# ── _nl_query: missing question → error ──────────────────────────────────────

class TestNlQueryValidation:
    @pytest.mark.asyncio
    async def test_empty_question_returns_error(self, agent):
        r = await agent._nl_query({"query": "", "store_id": "S1"})
        assert not r["success"]
        assert "query" in r["error"] or "question" in r["error"]

    @pytest.mark.asyncio
    async def test_whitespace_only_returns_error(self, agent):
        r = await agent._nl_query({"query": "   "})
        assert not r["success"]


# ── _nl_query: keyword dispatch (no LLM) ─────────────────────────────────────

class TestNlQueryKeywordDispatch:

    # ── rule intent ──────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_rule_query_dispatches_to_explain_rule(self, agent):
        r = await agent._nl_query({"query": "好评奖怎么计算", "store_id": "S1"})
        assert r["success"]
        assert r["metadata"]["source"] == "keyword_dispatch"
        assert r["data"]["tool"] == "explain_rule"
        assert "calculation_steps" in r["data"]["detail"]

    @pytest.mark.asyncio
    async def test_rule_query_answer_contains_rule_name(self, agent):
        r = await agent._nl_query({"query": "好评奖的规则说明"})
        assert r["success"]
        assert "好评奖" in r["data"]["answer"]

    @pytest.mark.asyncio
    async def test_rule_query_no_matching_rule_falls_through(self, agent):
        """Question mentions rule intent but no rule name matched — falls through to role-config or fallback."""
        r = await agent._nl_query({"query": "这个规则是什么", "store_id": "S1"})
        assert r["success"]
        # Should not crash; may route to fallback
        assert r["metadata"]["source"] == "keyword_dispatch"

    # ── commission intent ────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_commission_query_dispatches(self, agent):
        with patch.object(agent, "_calculate_commission", new=AsyncMock(return_value={
            "success": True,
            "data": {
                "role_id": "store_manager",
                "total_commission_yuan": 3200.0,
                "rules": [{"name": "月度目标达成奖", "amount_yuan": 2000.0}],
            },
        })):
            r = await agent._nl_query({"query": "店长本月提成是多少", "store_id": "S1"})
        assert r["success"]
        assert r["data"]["tool"] == "calculate_commission"
        assert "3200" in r["data"]["answer"]
        assert "月度目标达成奖" in r["data"]["answer"]

    @pytest.mark.asyncio
    async def test_commission_query_source_is_keyword_dispatch(self, agent):
        with patch.object(agent, "_calculate_commission", new=AsyncMock(return_value={
            "success": True,
            "data": {"role_id": "delivery", "total_commission_yuan": 800.0, "rules": []},
        })):
            r = await agent._nl_query({"query": "外卖员奖金", "store_id": "S1"})
        assert r["metadata"]["source"] == "keyword_dispatch"

    # ── report intent ────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_report_query_dispatches(self, agent):
        mock_report = {
            "success": True,
            "data": {
                "roles": [
                    {"role_name": "店长", "avg_score": 1.25, "total_commission_yuan": 3000.0},
                    {"role_name": "服务员", "avg_score": 0.95, "total_commission_yuan": 500.0},
                ],
            },
        }
        with patch.object(agent, "_get_performance_report", new=AsyncMock(return_value=mock_report)):
            r = await agent._nl_query({"query": "门店绩效报告汇总", "store_id": "S1"})
        assert r["success"]
        assert r["data"]["tool"] == "get_performance_report"
        assert "店长" in r["data"]["answer"]
        assert "1.25" in r["data"]["answer"]

    @pytest.mark.asyncio
    async def test_report_answer_contains_store_and_period(self, agent):
        with patch.object(agent, "_get_performance_report", new=AsyncMock(return_value={
            "success": True, "data": {"roles": []},
        })):
            r = await agent._nl_query({
                "query": "本月绩效评分", "store_id": "XJ001", "period": "2026-03",
            })
        assert "XJ001" in r["data"]["answer"]
        assert "2026-03" in r["data"]["answer"]

    # ── config intent ────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_config_query_dispatches(self, agent):
        r = await agent._nl_query({"query": "服务员考核指标有哪些", "store_id": "S1"})
        assert r["success"]
        assert r["data"]["tool"] == "get_role_config"
        answer = r["data"]["answer"]
        assert "桌均消费" in answer
        assert "好评奖" in answer

    # ── complete fallback ─────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_unrecognised_query_returns_helpful_fallback(self, agent):
        r = await agent._nl_query({"query": "帮我看看情况", "store_id": "S1"})
        assert r["success"]
        assert r["metadata"]["source"] == "keyword_dispatch"
        answer = r["data"]["answer"]
        assert "店长" in answer  # lists role names
        assert "示例" in answer

    # ── no placeholder source ever returned ──────────────────────────────────

    @pytest.mark.asyncio
    async def test_source_never_placeholder(self, agent):
        queries = [
            "好评奖怎么算", "提成", "绩效报告", "指标配置", "随便问问",
        ]
        for q in queries:
            r = await agent._nl_query({"query": q, "store_id": "S1"})
            src = (r.get("metadata") or {}).get("source", "")
            assert src != "placeholder", f"Query '{q}' still returned placeholder source"
