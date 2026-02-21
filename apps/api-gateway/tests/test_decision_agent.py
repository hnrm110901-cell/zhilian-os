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
    """Test revenue anomaly analysis with RAG"""
    # Mock RAG service
    decision_agent.rag_service = mock_rag_service

    # Test data
    store_id = "STORE001"
    current_revenue = 8000.0
    expected_revenue = 10000.0

    # Execute
    result = await decision_agent.analyze_revenue_anomaly(
        store_id=store_id,
        current_revenue=current_revenue,
        expected_revenue=expected_revenue,
        time_period="today"
    )

    # Verify
    assert result["success"] is True
    assert "analysis" in result["data"]
    assert result["data"]["deviation"] == -20.0
    assert result["data"]["current_revenue"] == current_revenue
    assert result["data"]["expected_revenue"] == expected_revenue
    assert result["data"]["context_used"] == 5

    # Verify RAG service was called
    mock_rag_service.analyze_with_rag.assert_called_once()
    call_args = mock_rag_service.analyze_with_rag.call_args
    assert call_args.kwargs["store_id"] == store_id
    assert call_args.kwargs["collection"] == "events"
    assert call_args.kwargs["top_k"] == 5


@pytest.mark.asyncio
async def test_analyze_revenue_anomaly_positive_deviation(decision_agent, mock_rag_service):
    """Test revenue anomaly with positive deviation"""
    decision_agent.rag_service = mock_rag_service

    result = await decision_agent.analyze_revenue_anomaly(
        store_id="STORE001",
        current_revenue=12000.0,
        expected_revenue=10000.0
    )

    assert result["success"] is True
    assert result["data"]["deviation"] == 20.0


@pytest.mark.asyncio
async def test_analyze_order_trend_success(decision_agent, mock_rag_service):
    """Test order trend analysis with RAG"""
    decision_agent.rag_service = mock_rag_service
    mock_rag_service.analyze_with_rag.return_value = {
        "response": "订单量呈上升趋势，客单价稳定，热门菜品为宫保鸡丁。",
        "metadata": {
            "context_count": 10,
            "timestamp": "2026-02-21T10:00:00"
        }
    }

    result = await decision_agent.analyze_order_trend(
        store_id="STORE001",
        time_range="7d"
    )

    assert result["success"] is True
    assert "analysis" in result["data"]
    assert result["data"]["time_range"] == "7d"
    assert result["data"]["context_used"] == 10

    # Verify RAG used orders collection
    call_args = mock_rag_service.analyze_with_rag.call_args
    assert call_args.kwargs["collection"] == "orders"
    assert call_args.kwargs["top_k"] == 10


@pytest.mark.asyncio
async def test_generate_business_recommendations_success(decision_agent, mock_rag_service):
    """Test business recommendations generation"""
    decision_agent.rag_service = mock_rag_service
    mock_rag_service.analyze_with_rag.return_value = {
        "response": "建议: 1. 优化菜单结构 2. 加强员工培训 3. 改善客户体验",
        "metadata": {
            "context_count": 8,
            "timestamp": "2026-02-21T10:00:00"
        }
    }

    result = await decision_agent.generate_business_recommendations(
        store_id="STORE001",
        focus_area="revenue"
    )

    assert result["success"] is True
    assert "recommendations" in result["data"]
    assert result["data"]["focus_area"] == "revenue"
    assert result["data"]["context_used"] == 8


@pytest.mark.asyncio
async def test_generate_business_recommendations_no_focus(decision_agent, mock_rag_service):
    """Test business recommendations without focus area"""
    decision_agent.rag_service = mock_rag_service

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
