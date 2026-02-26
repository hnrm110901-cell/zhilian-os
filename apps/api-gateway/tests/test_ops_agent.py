"""
OpsAgent 功能测试
覆盖：health_check, diagnose_fault, runbook_suggestion, predict_maintenance,
      security_advice, link_switch_advice, asset_overview, nl_query, unsupported_action
"""
import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

from src.agents.ops_agent import OpsAgent


_EMPTY_RAG = {"response": "", "metadata": {"context_count": 0, "timestamp": ""}}


@pytest.fixture
def agent():
    """OpsAgent with LLM and RAG disabled for unit tests."""
    with patch("src.agents.ops_agent.LLMEnhancedAgent.__init__", return_value=None):
        a = OpsAgent.__new__(OpsAgent)
        a.agent_type = "ops"
        a.llm_enabled = False
        a._rag = None
        return a


# ─────────────────────────── supported actions ───────────────────────────

class TestSupportedActions:
    def test_all_actions_declared(self, agent):
        actions = agent.get_supported_actions()
        expected = {
            "health_check", "diagnose_fault", "runbook_suggestion",
            "predict_maintenance", "security_advice", "link_switch_advice",
            "asset_overview", "nl_query",
        }
        assert expected.issubset(set(actions))

    @pytest.mark.asyncio
    async def test_unsupported_action_returns_error(self, agent):
        resp = await agent.execute("nonexistent", {})
        assert resp.success is False
        assert "不支持" in (resp.error or "")


# ─────────────────────────── health_check ───────────────────────────

class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_health_check_store_scope(self, agent):
        resp = await agent.execute("health_check", {"store_id": "S001", "scope": "store"})
        assert resp.success is True
        assert resp.data is not None

    @pytest.mark.asyncio
    async def test_health_check_all_scope(self, agent):
        resp = await agent.execute("health_check", {"scope": "all"})
        assert resp.success is True

    @pytest.mark.asyncio
    async def test_health_check_no_store_id(self, agent):
        resp = await agent.execute("health_check", {})
        assert resp.success is True

    @pytest.mark.asyncio
    async def test_health_check_with_rag(self, agent):
        mock_rag = AsyncMock()
        mock_rag.analyze_with_rag.return_value = {
            "response": "POS正常，打印机纸张不足",
            "metadata": {"context_count": 3, "timestamp": ""},
        }
        agent._rag = mock_rag
        resp = await agent.execute("health_check", {"store_id": "S002"})
        assert resp.success is True
        agent._rag = None


# ─────────────────────────── diagnose_fault ───────────────────────────

class TestDiagnoseFault:
    @pytest.mark.asyncio
    async def test_diagnose_with_symptom(self, agent):
        resp = await agent.execute("diagnose_fault", {
            "store_id": "S001",
            "symptom": "POS机无法连接网络",
        })
        assert resp.success is True

    @pytest.mark.asyncio
    async def test_diagnose_empty_symptom(self, agent):
        resp = await agent.execute("diagnose_fault", {"store_id": "S001", "symptom": ""})
        assert resp.success is True

    @pytest.mark.asyncio
    async def test_diagnose_no_store_id(self, agent):
        resp = await agent.execute("diagnose_fault", {"symptom": "数据库连接超时"})
        assert resp.success is True

    @pytest.mark.asyncio
    async def test_diagnose_data_contains_symptom(self, agent):
        resp = await agent.execute("diagnose_fault", {
            "store_id": "S003",
            "symptom": "收银系统崩溃",
        })
        assert resp.success is True
        assert resp.data is not None


# ─────────────────────────── runbook_suggestion ───────────────────────────

class TestRunbookSuggestion:
    @pytest.mark.asyncio
    async def test_runbook_with_fault_type(self, agent):
        resp = await agent.execute("runbook_suggestion", {
            "fault_type": "pos_offline",
            "store_id": "S001",
        })
        assert resp.success is True

    @pytest.mark.asyncio
    async def test_runbook_empty_fault_type(self, agent):
        resp = await agent.execute("runbook_suggestion", {})
        assert resp.success is True

    @pytest.mark.asyncio
    async def test_runbook_data_has_fault_type(self, agent):
        resp = await agent.execute("runbook_suggestion", {"fault_type": "network_down"})
        assert resp.success is True
        assert resp.data is not None


# ─────────────────────────── predict_maintenance ───────────────────────────

class TestPredictMaintenance:
    @pytest.mark.asyncio
    async def test_predict_pos_printer(self, agent):
        resp = await agent.execute("predict_maintenance", {
            "store_id": "S001",
            "device_type": "pos_printer",
        })
        assert resp.success is True

    @pytest.mark.asyncio
    async def test_predict_router(self, agent):
        resp = await agent.execute("predict_maintenance", {
            "store_id": "S001",
            "device_type": "router",
        })
        assert resp.success is True

    @pytest.mark.asyncio
    async def test_predict_kds(self, agent):
        resp = await agent.execute("predict_maintenance", {"device_type": "kds"})
        assert resp.success is True

    @pytest.mark.asyncio
    async def test_predict_no_device_type(self, agent):
        resp = await agent.execute("predict_maintenance", {"store_id": "S001"})
        assert resp.success is True


# ─────────────────────────── security_advice ───────────────────────────

class TestSecurityAdvice:
    @pytest.mark.asyncio
    async def test_security_password_focus(self, agent):
        resp = await agent.execute("security_advice", {
            "store_id": "S001",
            "focus": "password",
        })
        assert resp.success is True

    @pytest.mark.asyncio
    async def test_security_firmware_focus(self, agent):
        resp = await agent.execute("security_advice", {
            "store_id": "S001",
            "focus": "firmware",
        })
        assert resp.success is True

    @pytest.mark.asyncio
    async def test_security_vpn_focus(self, agent):
        resp = await agent.execute("security_advice", {"focus": "vpn"})
        assert resp.success is True

    @pytest.mark.asyncio
    async def test_security_no_focus_full_check(self, agent):
        resp = await agent.execute("security_advice", {"store_id": "S001"})
        assert resp.success is True


# ─────────────────────────── link_switch_advice ───────────────────────────

class TestLinkSwitchAdvice:
    @pytest.mark.asyncio
    async def test_link_switch_low_quality(self, agent):
        resp = await agent.execute("link_switch_advice", {
            "store_id": "S001",
            "quality_score": 55,
        })
        assert resp.success is True

    @pytest.mark.asyncio
    async def test_link_switch_high_quality(self, agent):
        resp = await agent.execute("link_switch_advice", {
            "store_id": "S001",
            "quality_score": 95,
        })
        assert resp.success is True

    @pytest.mark.asyncio
    async def test_link_switch_no_score(self, agent):
        resp = await agent.execute("link_switch_advice", {"store_id": "S001"})
        assert resp.success is True


# ─────────────────────────── asset_overview ───────────────────────────

class TestAssetOverview:
    @pytest.mark.asyncio
    async def test_asset_overview_with_store(self, agent):
        resp = await agent.execute("asset_overview", {"store_id": "S001"})
        assert resp.success is True

    @pytest.mark.asyncio
    async def test_asset_overview_no_store(self, agent):
        resp = await agent.execute("asset_overview", {})
        assert resp.success is True

    @pytest.mark.asyncio
    async def test_asset_overview_data_not_none(self, agent):
        resp = await agent.execute("asset_overview", {"store_id": "S002"})
        assert resp.data is not None


# ─────────────────────────── nl_query ───────────────────────────

class TestNLQuery:
    @pytest.mark.asyncio
    async def test_nl_query_network_question(self, agent):
        resp = await agent.execute("nl_query", {
            "question": "3号店今天网络为什么慢",
            "store_id": "S003",
        })
        assert resp.success is True

    @pytest.mark.asyncio
    async def test_nl_query_empty_question(self, agent):
        resp = await agent.execute("nl_query", {"question": ""})
        assert resp.success is True  # ops agent doesn't validate empty question

    @pytest.mark.asyncio
    async def test_nl_query_no_store_id(self, agent):
        resp = await agent.execute("nl_query", {"question": "全域健康状态如何"})
        assert resp.success is True

    @pytest.mark.asyncio
    async def test_nl_query_with_rag(self, agent):
        mock_rag = AsyncMock()
        mock_rag.analyze_with_rag.return_value = {
            "response": "网络带宽占用过高，建议限速非业务流量",
            "metadata": {"context_count": 5, "timestamp": ""},
        }
        agent._rag = mock_rag
        resp = await agent.execute("nl_query", {"question": "网络慢的原因"})
        assert resp.success is True
        agent._rag = None


# ─────────────────────────── _with_rag fallback ───────────────────────────

class TestWithRAGFallback:
    @pytest.mark.asyncio
    async def test_no_rag_returns_empty_context(self, agent):
        result = await agent._with_rag("test query", "S001")
        assert result["response"] == ""
        assert result["metadata"]["context_count"] == 0

    @pytest.mark.asyncio
    async def test_rag_called_with_correct_params(self, agent):
        mock_rag = AsyncMock()
        mock_rag.analyze_with_rag.return_value = _EMPTY_RAG
        agent._rag = mock_rag
        await agent._with_rag("test query", "S001", top_k=3)
        mock_rag.analyze_with_rag.assert_called_once_with(
            query="test query", store_id="S001", collection="events", top_k=3
        )
        agent._rag = None
