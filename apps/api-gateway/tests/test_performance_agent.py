"""
PerformanceAgent 功能测试
覆盖：get_role_config, calculate_performance, calculate_commission,
      get_performance_report, explain_rule, nl_query, unsupported_action
"""
import os
import pytest
from unittest.mock import patch, AsyncMock

# Provide required env vars before any src imports
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

from src.agents.performance_agent import PerformanceAgent, DEFAULT_ROLE_CONFIG


@pytest.fixture
def agent():
    with patch("src.agents.performance_agent.LLMEnhancedAgent.__init__", return_value=None):
        a = PerformanceAgent.__new__(PerformanceAgent)
        a.agent_type = "performance"
        a.llm_enabled = False
        a._rag = None
        return a


# ─────────────────────────── get_role_config ───────────────────────────

class TestGetRoleConfig:
    @pytest.mark.asyncio
    async def test_get_all_roles(self, agent):
        result = await agent._get_role_config({})
        assert result["success"] is True
        assert len(result["data"]["roles"]) == len(DEFAULT_ROLE_CONFIG)

    @pytest.mark.asyncio
    async def test_get_specific_role(self, agent):
        result = await agent._get_role_config({"role_id": "waiter"})
        assert result["success"] is True
        assert result["data"]["roles"][0]["id"] == "waiter"
        assert result["data"]["roles"][0]["name"] == "服务员"

    @pytest.mark.asyncio
    async def test_get_unknown_role_returns_error(self, agent):
        result = await agent._get_role_config({"role_id": "nonexistent"})
        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_all_roles_have_metrics_and_commission_rules(self, agent):
        result = await agent._get_role_config({})
        for role in result["data"]["roles"]:
            assert len(role["metrics"]) > 0
            assert len(role["commission_rules"]) > 0

    @pytest.mark.asyncio
    async def test_store_id_passed_through(self, agent):
        result = await agent._get_role_config({"store_id": "S001", "role_id": "cashier"})
        assert result["data"]["store_id"] == "S001"


# ─────────────────────────── calculate_performance ───────────────────────────

class TestCalculatePerformance:
    @pytest.mark.asyncio
    async def test_valid_role_returns_metrics_structure(self, agent):
        result = await agent._calculate_performance({
            "store_id": "S001",
            "role_id": "store_manager",
            "period": "month",
        })
        assert result["success"] is True
        data = result["data"]
        assert data["role_id"] == "store_manager"
        assert data["period"] == "month"
        assert len(data["metrics"]) == len(DEFAULT_ROLE_CONFIG["store_manager"]["metrics"])

    @pytest.mark.asyncio
    async def test_metrics_have_required_fields(self, agent):
        result = await agent._calculate_performance({"role_id": "waiter"})
        for m in result["data"]["metrics"]:
            assert "metric_id" in m
            assert "metric_name" in m
            assert "weight" in m

    @pytest.mark.asyncio
    async def test_missing_role_id_returns_error(self, agent):
        result = await agent._calculate_performance({"store_id": "S001"})
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_invalid_role_id_returns_error(self, agent):
        result = await agent._calculate_performance({"role_id": "ghost"})
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_staff_ids_passed_through(self, agent):
        result = await agent._calculate_performance({
            "role_id": "kitchen",
            "staff_ids": ["E001", "E002"],
        })
        assert result["data"]["staff_ids"] == ["E001", "E002"]

    @pytest.mark.asyncio
    async def test_weights_sum_to_one(self, agent):
        result = await agent._calculate_performance({"role_id": "cashier"})
        total_weight = sum(m["weight"] for m in result["data"]["metrics"])
        assert abs(total_weight - 1.0) < 0.001


# ─────────────────────────── calculate_commission ───────────────────────────

class TestCalculateCommission:
    @pytest.mark.asyncio
    async def test_valid_role_returns_commission_structure(self, agent):
        result = await agent._calculate_commission({
            "store_id": "S001",
            "role_id": "waiter",
            "period": "month",
        })
        assert result["success"] is True
        data = result["data"]
        assert data["role_id"] == "waiter"
        assert len(data["details"]) == len(DEFAULT_ROLE_CONFIG["waiter"]["commission_rules"])

    @pytest.mark.asyncio
    async def test_commission_details_have_rule_name(self, agent):
        result = await agent._calculate_commission({"role_id": "cashier"})
        for d in result["data"]["details"]:
            assert "rule_name" in d

    @pytest.mark.asyncio
    async def test_missing_role_id_returns_error(self, agent):
        result = await agent._calculate_commission({})
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_invalid_role_returns_error(self, agent):
        result = await agent._calculate_commission({"role_id": "unknown"})
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_all_roles_commission_structure(self, agent):
        for role_id in DEFAULT_ROLE_CONFIG:
            result = await agent._calculate_commission({"role_id": role_id})
            assert result["success"] is True


# ─────────────────────────── get_performance_report ───────────────────────────

class TestGetPerformanceReport:
    @pytest.mark.asyncio
    async def test_report_all_roles(self, agent):
        result = await agent._get_performance_report({"store_id": "S001", "period": "month"})
        assert result["success"] is True
        assert len(result["data"]["summary"]) == len(DEFAULT_ROLE_CONFIG)

    @pytest.mark.asyncio
    async def test_report_specific_role(self, agent):
        result = await agent._get_performance_report({"role_id": "kitchen", "period": "week"})
        assert result["success"] is True
        assert result["data"]["summary"][0]["role_id"] == "kitchen"

    @pytest.mark.asyncio
    async def test_report_unknown_role_returns_error(self, agent):
        result = await agent._get_performance_report({"role_id": "ghost"})
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_report_summary_has_required_fields(self, agent):
        result = await agent._get_performance_report({})
        for item in result["data"]["summary"]:
            assert "role_id" in item
            assert "role_name" in item
            assert "period" in item

    @pytest.mark.asyncio
    async def test_report_format_passed_through(self, agent):
        result = await agent._get_performance_report({"format": "detail"})
        assert result["data"]["format"] == "detail"


# ─────────────────────────── explain_rule ───────────────────────────

class TestExplainRule:
    @pytest.mark.asyncio
    async def test_explain_by_rule_id(self, agent):
        result = await agent._explain_rule({"rule_id": "月度目标达成奖", "role_id": "store_manager"})
        assert result["success"] is True
        assert result["data"]["rule_id"] == "月度目标达成奖"

    @pytest.mark.asyncio
    async def test_explain_by_commission_id(self, agent):
        result = await agent._explain_rule({"commission_id": "COMM_001"})
        assert result["success"] is True
        assert result["data"]["commission_id"] == "COMM_001"

    @pytest.mark.asyncio
    async def test_missing_both_ids_returns_error(self, agent):
        result = await agent._explain_rule({})
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_explain_returns_rule_text(self, agent):
        result = await agent._explain_rule({"rule_id": "桌均提成", "role_id": "waiter"})
        assert "rule_text" in result["data"]
        assert result["data"]["rule_text"] != ""


# ─────────────────────────── nl_query ───────────────────────────

class TestNLQuery:
    @pytest.mark.asyncio
    async def test_empty_query_returns_error(self, agent):
        result = await agent._nl_query({"query": ""})
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_whitespace_query_returns_error(self, agent):
        result = await agent._nl_query({"query": "   "})
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_valid_query_returns_answer(self, agent):
        result = await agent._nl_query({"query": "本月服务员绩效怎么样", "store_id": "S001"})
        assert result["success"] is True
        assert "answer" in result["data"]

    @pytest.mark.asyncio
    async def test_question_field_alias(self, agent):
        result = await agent._nl_query({"question": "店长提成规则是什么"})
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_query_echoed_in_response(self, agent):
        result = await agent._nl_query({"query": "收银员开卡提成"})
        assert "收银员开卡提成" in result["data"]["answer"]


# ─────────────────────────── execute 分发 ───────────────────────────

class TestExecuteDispatch:
    @pytest.mark.asyncio
    async def test_execute_unsupported_action(self, agent):
        resp = await agent.execute("nonexistent", {})
        assert resp.success is False
        assert "不支持" in (resp.error or "")

    @pytest.mark.asyncio
    async def test_execute_get_role_config(self, agent):
        resp = await agent.execute("get_role_config", {"role_id": "delivery"})
        assert resp.success is True
        assert resp.data is not None

    @pytest.mark.asyncio
    async def test_execute_calculate_performance(self, agent):
        resp = await agent.execute("calculate_performance", {"role_id": "shift_manager"})
        assert resp.success is True

    @pytest.mark.asyncio
    async def test_execute_calculate_commission(self, agent):
        resp = await agent.execute("calculate_commission", {"role_id": "kitchen"})
        assert resp.success is True

    @pytest.mark.asyncio
    async def test_execute_get_performance_report(self, agent):
        resp = await agent.execute("get_performance_report", {"period": "month"})
        assert resp.success is True

    @pytest.mark.asyncio
    async def test_execute_explain_rule(self, agent):
        resp = await agent.execute("explain_rule", {"rule_id": "单量提成(元/单或阶梯)", "role_id": "delivery"})
        assert resp.success is True

    @pytest.mark.asyncio
    async def test_execute_nl_query(self, agent):
        resp = await agent.execute("nl_query", {"query": "外卖专员本月提成多少"})
        assert resp.success is True

    @pytest.mark.asyncio
    async def test_supported_actions_list(self, agent):
        actions = agent.get_supported_actions()
        expected = {"get_role_config", "calculate_performance", "calculate_commission",
                    "get_performance_report", "explain_rule", "nl_query"}
        assert expected.issubset(set(actions))
