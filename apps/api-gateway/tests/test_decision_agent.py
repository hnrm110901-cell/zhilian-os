"""
Tests for DecisionAgent with RAG integration
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.decision_agent import DecisionAgent


@pytest.fixture
def decision_agent():
    """Create DecisionAgent instance"""
    return DecisionAgent()


@pytest.fixture
def mock_rag_service():
    """Mock RAG service"""
    mock = AsyncMock()
    mock.analyze_with_rag.return_value = {
        "response": "营收下降可能由于天气原因导致客流减少，建议加强线上营销。",
        "metadata": {
            "context_count": 5,
            "timestamp": "2026-02-21T10:00:00"
        }
    }
    return mock


@pytest.mark.asyncio
async def test_analyze_revenue_anomaly_success(decision_agent, mock_rag_service):
    """Test revenue anomaly analysis with Tool Use"""
    from src.agents.llm_agent import AgentResult
    decision_agent.rag_service = mock_rag_service

    store_id = "STORE001"
    current_revenue = 8000.0
    expected_revenue = 10000.0

    mock_result = AgentResult(success=True, data="营收下降可能由于天气原因导致客流减少，建议加强线上营销。", confidence=0.85)
    with patch.object(decision_agent, 'execute_with_tools', new=AsyncMock(return_value=mock_result)):
        result = await decision_agent.analyze_revenue_anomaly(
            store_id=store_id,
            current_revenue=current_revenue,
            expected_revenue=expected_revenue,
            time_period="today"
        )

    assert result["success"] is True
    assert "analysis" in result["data"]
    assert result["data"]["deviation"] == -20.0
    assert result["data"]["current_revenue"] == str(current_revenue)
    assert result["data"]["expected_revenue"] == str(expected_revenue)


@pytest.mark.asyncio
async def test_analyze_revenue_anomaly_positive_deviation(decision_agent, mock_rag_service):
    """Test revenue anomaly with positive deviation"""
    from src.agents.llm_agent import AgentResult
    decision_agent.rag_service = mock_rag_service

    mock_result = AgentResult(success=True, data="营收超预期", confidence=0.9)
    with patch.object(decision_agent, 'execute_with_tools', new=AsyncMock(return_value=mock_result)):
        result = await decision_agent.analyze_revenue_anomaly(
            store_id="STORE001",
            current_revenue=12000.0,
            expected_revenue=10000.0
        )

    assert result["success"] is True
    assert result["data"]["deviation"] == 20.0


@pytest.mark.asyncio
async def test_analyze_order_trend_success(decision_agent, mock_rag_service):
    """Test order trend analysis with Tool Use"""
    from src.agents.llm_agent import AgentResult
    decision_agent.rag_service = mock_rag_service
    mock_rag_service.analyze_with_rag.return_value = {
        "response": "订单量呈上升趋势，客单价稳定，热门菜品为宫保鸡丁。",
        "metadata": {"context_count": 10, "timestamp": "2026-02-21T10:00:00"}
    }

    mock_result = AgentResult(success=True, data="订单量上升趋势", confidence=0.8)
    with patch.object(decision_agent, 'execute_with_tools', new=AsyncMock(return_value=mock_result)):
        result = await decision_agent.analyze_order_trend(
            store_id="STORE001",
            time_range="7d"
        )

    assert result["success"] is True
    assert "analysis" in result["data"]
    assert result["data"]["time_range"] == "7d"


@pytest.mark.asyncio
async def test_generate_business_recommendations_success(decision_agent, mock_rag_service):
    """Test business recommendations generation with Tool Use"""
    from src.agents.llm_agent import AgentResult
    decision_agent.rag_service = mock_rag_service
    mock_rag_service.analyze_with_rag.return_value = {
        "response": "建议: 1. 优化菜单结构 2. 加强员工培训 3. 改善客户体验",
        "metadata": {"context_count": 8, "timestamp": "2026-02-21T10:00:00"}
    }

    mock_result = AgentResult(success=True, data="业务建议内容", confidence=0.85)
    with patch.object(decision_agent, 'execute_with_tools', new=AsyncMock(return_value=mock_result)):
        result = await decision_agent.generate_business_recommendations(
            store_id="STORE001",
            focus_area="revenue"
        )

    assert result["success"] is True
    assert "recommendations" in result["data"]
    assert result["data"]["focus_area"] == "revenue"


@pytest.mark.asyncio
async def test_generate_business_recommendations_no_focus(decision_agent, mock_rag_service):
    """Test business recommendations without focus area"""
    from src.agents.llm_agent import AgentResult
    decision_agent.rag_service = mock_rag_service

    mock_result = AgentResult(success=True, data="通用业务建议", confidence=0.8)
    with patch.object(decision_agent, 'execute_with_tools', new=AsyncMock(return_value=mock_result)):
        result = await decision_agent.generate_business_recommendations(
            store_id="STORE001"
        )

    assert result["success"] is True
    assert result["data"]["focus_area"] is None


@pytest.mark.asyncio
async def test_analyze_revenue_anomaly_rag_failure(decision_agent):
    """Test revenue anomaly analysis when RAG fails"""
    # Mock RAG service to raise exception
    decision_agent.rag_service = AsyncMock()
    decision_agent.rag_service.analyze_with_rag.side_effect = Exception("RAG service unavailable")

    result = await decision_agent.analyze_revenue_anomaly(
        store_id="STORE001",
        current_revenue=8000.0,
        expected_revenue=10000.0
    )

    assert result["success"] is False
    assert "分析失败" in result["message"]


@pytest.mark.asyncio
async def test_analyze_order_trend_rag_failure(decision_agent):
    """Test order trend analysis when RAG fails"""
    decision_agent.rag_service = AsyncMock()
    decision_agent.rag_service.analyze_with_rag.side_effect = Exception("Connection timeout")

    result = await decision_agent.analyze_order_trend(
        store_id="STORE001"
    )

    assert result["success"] is False
    assert "分析失败" in result["message"]
