"""
Tests for ScheduleAgent with RAG integration
"""
import pytest
from unittest.mock import AsyncMock

from src.agents.schedule_agent import ScheduleAgent


@pytest.fixture
def schedule_agent():
    """Create ScheduleAgent instance"""
    return ScheduleAgent()


@pytest.fixture
def mock_rag_service():
    """Mock RAG service"""
    mock = AsyncMock()
    mock.analyze_with_rag.return_value = {
        "response": "建议排班12人，午高峰(11:00-13:00)需6人，晚高峰(17:00-19:00)需5人。",
        "metadata": {
            "context_count": 10,
            "timestamp": "2026-02-21T10:00:00"
        }
    }
    return mock


@pytest.mark.asyncio
async def test_optimize_schedule_success(schedule_agent, mock_rag_service):
    """Test schedule optimization with RAG"""
    schedule_agent.rag_service = mock_rag_service

    result = await schedule_agent.optimize_schedule(
        store_id="STORE001",
        date="2026-02-22",
        current_staff_count=10,
        expected_customer_flow=200
    )

    assert result["success"] is True
    assert "optimization" in result["data"]
    assert result["data"]["date"] == "2026-02-22"
    assert result["data"]["current_staff_count"] == 10
    assert result["data"]["expected_customer_flow"] == 200
    assert result["data"]["context_used"] == 10

    # Verify RAG service was called
    mock_rag_service.analyze_with_rag.assert_called_once()
    call_args = mock_rag_service.analyze_with_rag.call_args
    assert call_args.kwargs["store_id"] == "STORE001"
    assert call_args.kwargs["top_k"] == 10


@pytest.mark.asyncio
async def test_optimize_schedule_no_expected_flow(schedule_agent, mock_rag_service):
    """Test schedule optimization without expected customer flow"""
    schedule_agent.rag_service = mock_rag_service

    result = await schedule_agent.optimize_schedule(
        store_id="STORE001",
        date="2026-02-22",
        current_staff_count=10
    )

    assert result["success"] is True
    assert result["data"]["expected_customer_flow"] is None


@pytest.mark.asyncio
async def test_predict_staffing_needs_success(schedule_agent, mock_rag_service):
    """Test staffing needs prediction with RAG"""
    schedule_agent.rag_service = mock_rag_service
    mock_rag_service.analyze_with_rag.return_value = {
        "response": "未来7天建议人数: 周一10人, 周二11人, 周三12人...",
        "metadata": {
            "context_count": 15,
            "timestamp": "2026-02-21T10:00:00"
        }
    }

    result = await schedule_agent.predict_staffing_needs(
        store_id="STORE001",
        date_range="7d"
    )

    assert result["success"] is True
    assert "prediction" in result["data"]
    assert result["data"]["date_range"] == "7d"
    assert result["data"]["context_used"] == 15

    # Verify RAG used more context for prediction
    call_args = mock_rag_service.analyze_with_rag.call_args
    assert call_args.kwargs["top_k"] == 15


@pytest.mark.asyncio
async def test_analyze_shift_efficiency_success(schedule_agent, mock_rag_service):
    """Test shift efficiency analysis with RAG"""
    schedule_agent.rag_service = mock_rag_service
    mock_rag_service.analyze_with_rag.return_value = {
        "response": "班次效率良好，人均服务25位客户，建议优化点餐流程。",
        "metadata": {
            "context_count": 8,
            "timestamp": "2026-02-21T10:00:00"
        }
    }

    result = await schedule_agent.analyze_shift_efficiency(
        store_id="STORE001",
        shift_id="SHIFT001"
    )

    assert result["success"] is True
    assert "analysis" in result["data"]
    assert result["data"]["shift_id"] == "SHIFT001"
    assert result["data"]["context_used"] == 8


@pytest.mark.asyncio
async def test_balance_workload_success(schedule_agent, mock_rag_service):
    """Test workload balancing with RAG"""
    schedule_agent.rag_service = mock_rag_service
    mock_rag_service.analyze_with_rag.return_value = {
        "response": "员工A工作量偏高，建议调整班次分配，平衡工作时长。",
        "metadata": {
            "context_count": 10,
            "timestamp": "2026-02-21T10:00:00"
        }
    }

    staff_ids = ["STAFF001", "STAFF002", "STAFF003"]
    result = await schedule_agent.balance_workload(
        store_id="STORE001",
        staff_ids=staff_ids,
        time_period="week"
    )

    assert result["success"] is True
    assert "balance_plan" in result["data"]
    assert result["data"]["staff_count"] == 3
    assert result["data"]["time_period"] == "week"
    assert result["data"]["context_used"] == 10


@pytest.mark.asyncio
async def test_optimize_schedule_rag_failure(schedule_agent):
    """Test schedule optimization when RAG fails"""
    schedule_agent.rag_service = AsyncMock()
    schedule_agent.rag_service.analyze_with_rag.side_effect = Exception("RAG service unavailable")

    result = await schedule_agent.optimize_schedule(
        store_id="STORE001",
        date="2026-02-22",
        current_staff_count=10
    )

    assert result["success"] is False
    assert "优化失败" in result["message"]


@pytest.mark.asyncio
async def test_predict_staffing_needs_rag_failure(schedule_agent):
    """Test staffing needs prediction when RAG fails"""
    schedule_agent.rag_service = AsyncMock()
    schedule_agent.rag_service.analyze_with_rag.side_effect = Exception("Connection timeout")

    result = await schedule_agent.predict_staffing_needs(
        store_id="STORE001"
    )

    assert result["success"] is False
    assert "预测失败" in result["message"]


@pytest.mark.asyncio
async def test_analyze_shift_efficiency_rag_failure(schedule_agent):
    """Test shift efficiency analysis when RAG fails"""
    schedule_agent.rag_service = AsyncMock()
    schedule_agent.rag_service.analyze_with_rag.side_effect = Exception("Database error")

    result = await schedule_agent.analyze_shift_efficiency(
        store_id="STORE001",
        shift_id="SHIFT001"
    )

    assert result["success"] is False
    assert "分析失败" in result["message"]


@pytest.mark.asyncio
async def test_balance_workload_rag_failure(schedule_agent):
    """Test workload balancing when RAG fails"""
    schedule_agent.rag_service = AsyncMock()
    schedule_agent.rag_service.analyze_with_rag.side_effect = Exception("Service error")

    result = await schedule_agent.balance_workload(
        store_id="STORE001",
        staff_ids=["STAFF001", "STAFF002"],
        time_period="week"
    )

    assert result["success"] is False
    assert "平衡失败" in result["message"]
