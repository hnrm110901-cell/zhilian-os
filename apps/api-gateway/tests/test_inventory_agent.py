"""
Tests for InventoryAgent with RAG integration
"""
import pytest
from unittest.mock import AsyncMock

from src.agents.inventory_agent import InventoryAgent


@pytest.fixture
def inventory_agent():
    """Create InventoryAgent instance"""
    return InventoryAgent()


@pytest.fixture
def mock_rag_service():
    """Mock RAG service"""
    mock = AsyncMock()
    mock.analyze_with_rag.return_value = {
        "response": "预计未来3天销量120份，建议库存150份，明天上午10点补货。",
        "metadata": {
            "context_count": 12,
            "timestamp": "2026-02-21T10:00:00"
        }
    }
    return mock


@pytest.mark.asyncio
async def test_predict_inventory_needs_success(inventory_agent, mock_rag_service):
    """Test inventory needs prediction with RAG"""
    inventory_agent.rag_service = mock_rag_service

    result = await inventory_agent.predict_inventory_needs(
        store_id="STORE001",
        dish_id="DISH001",
        time_range="3d"
    )

    assert result["success"] is True
    assert "prediction" in result["data"]
    assert result["data"]["dish_id"] == "DISH001"
    assert result["data"]["time_range"] == "3d"
    assert result["data"]["context_used"] == 12

    # Verify RAG service was called with orders collection
    mock_rag_service.analyze_with_rag.assert_called_once()
    call_args = mock_rag_service.analyze_with_rag.call_args
    assert call_args.kwargs["store_id"] == "STORE001"
    assert call_args.kwargs["collection"] == "orders"
    assert call_args.kwargs["top_k"] == 12


@pytest.mark.asyncio
async def test_check_low_stock_alert_success(inventory_agent, mock_rag_service):
    """Test low stock alert check with RAG"""
    inventory_agent.rag_service = mock_rag_service
    mock_rag_service.analyze_with_rag.return_value = {
        "response": "高风险: 宫保鸡丁将在2小时内售罄，建议立即补货50份。",
        "metadata": {
            "context_count": 10,
            "timestamp": "2026-02-21T10:00:00"
        }
    }

    current_inventory = {
        "DISH001": 20,
        "DISH002": 50,
        "DISH003": 10
    }

    result = await inventory_agent.check_low_stock_alert(
        store_id="STORE001",
        current_inventory=current_inventory,
        threshold_hours=4
    )

    assert result["success"] is True
    assert "alert" in result["data"]
    assert result["data"]["inventory_count"] == 3
    assert result["data"]["threshold_hours"] == 4
    assert result["data"]["context_used"] == 10


@pytest.mark.asyncio
async def test_optimize_inventory_levels_success(inventory_agent, mock_rag_service):
    """Test inventory levels optimization with RAG"""
    inventory_agent.rag_service = mock_rag_service
    mock_rag_service.analyze_with_rag.return_value = {
        "response": "宫保鸡丁最优库存80份，安全库存50份，建议每日补货。",
        "metadata": {
            "context_count": 15,
            "timestamp": "2026-02-21T10:00:00"
        }
    }

    dish_ids = ["DISH001", "DISH002", "DISH003"]

    result = await inventory_agent.optimize_inventory_levels(
        store_id="STORE001",
        dish_ids=dish_ids
    )

    assert result["success"] is True
    assert "optimization" in result["data"]
    assert result["data"]["dish_count"] == 3
    assert result["data"]["context_used"] == 15

    # Verify RAG used more context for optimization
    call_args = mock_rag_service.analyze_with_rag.call_args
    assert call_args.kwargs["top_k"] == 15


@pytest.mark.asyncio
async def test_analyze_waste_success(inventory_agent, mock_rag_service):
    """Test waste analysis with RAG"""
    inventory_agent.rag_service = mock_rag_service
    mock_rag_service.analyze_with_rag.return_value = {
        "response": "损耗率最高的是海鲜类菜品(15%)，主要原因是过量采购。",
        "metadata": {
            "context_count": 10,
            "timestamp": "2026-02-21T10:00:00"
        }
    }

    result = await inventory_agent.analyze_waste(
        store_id="STORE001",
        time_period="7d"
    )

    assert result["success"] is True
    assert "analysis" in result["data"]
    assert result["data"]["time_period"] == "7d"
    assert result["data"]["context_used"] == 10

    # Verify RAG used events collection for waste analysis
    call_args = mock_rag_service.analyze_with_rag.call_args
    assert call_args.kwargs["collection"] == "events"


@pytest.mark.asyncio
async def test_generate_restock_plan_success(inventory_agent, mock_rag_service):
    """Test restock plan generation with RAG"""
    inventory_agent.rag_service = mock_rag_service
    mock_rag_service.analyze_with_rag.return_value = {
        "response": "补货清单: 宫保鸡丁100份, 鱼香肉丝80份, 明天8AM补货。",
        "metadata": {
            "context_count": 12,
            "timestamp": "2026-02-21T10:00:00"
        }
    }

    result = await inventory_agent.generate_restock_plan(
        store_id="STORE001",
        target_date="2026-02-22"
    )

    assert result["success"] is True
    assert "plan" in result["data"]
    assert result["data"]["target_date"] == "2026-02-22"
    assert result["data"]["context_used"] == 12


@pytest.mark.asyncio
async def test_predict_inventory_needs_rag_failure(inventory_agent):
    """Test inventory needs prediction when RAG fails"""
    inventory_agent.rag_service = AsyncMock()
    inventory_agent.rag_service.analyze_with_rag.side_effect = Exception("RAG service unavailable")

    result = await inventory_agent.predict_inventory_needs(
        store_id="STORE001",
        dish_id="DISH001"
    )

    assert result["success"] is False
    assert "预测失败" in result["message"]


@pytest.mark.asyncio
async def test_check_low_stock_alert_rag_failure(inventory_agent):
    """Test low stock alert when RAG fails"""
    inventory_agent.rag_service = AsyncMock()
    inventory_agent.rag_service.analyze_with_rag.side_effect = Exception("Connection timeout")

    result = await inventory_agent.check_low_stock_alert(
        store_id="STORE001",
        current_inventory={"DISH001": 10}
    )

    assert result["success"] is False
    assert "检查失败" in result["message"]


@pytest.mark.asyncio
async def test_optimize_inventory_levels_rag_failure(inventory_agent):
    """Test inventory optimization when RAG fails"""
    inventory_agent.rag_service = AsyncMock()
    inventory_agent.rag_service.analyze_with_rag.side_effect = Exception("Database error")

    result = await inventory_agent.optimize_inventory_levels(
        store_id="STORE001",
        dish_ids=["DISH001", "DISH002"]
    )

    assert result["success"] is False
    assert "优化失败" in result["message"]


@pytest.mark.asyncio
async def test_analyze_waste_rag_failure(inventory_agent):
    """Test waste analysis when RAG fails"""
    inventory_agent.rag_service = AsyncMock()
    inventory_agent.rag_service.analyze_with_rag.side_effect = Exception("Service error")

    result = await inventory_agent.analyze_waste(
        store_id="STORE001"
    )

    assert result["success"] is False
    assert "分析失败" in result["message"]


@pytest.mark.asyncio
async def test_generate_restock_plan_rag_failure(inventory_agent):
    """Test restock plan generation when RAG fails"""
    inventory_agent.rag_service = AsyncMock()
    inventory_agent.rag_service.analyze_with_rag.side_effect = Exception("Network error")

    result = await inventory_agent.generate_restock_plan(
        store_id="STORE001",
        target_date="2026-02-22"
    )

    assert result["success"] is False
    assert "生成失败" in result["message"]
