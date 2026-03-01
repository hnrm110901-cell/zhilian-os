"""
Tests for InventoryAgent with RAG integration
"""
import pytest
from unittest.mock import AsyncMock, patch

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
    """Test inventory needs prediction with Tool Use"""
    from src.agents.llm_agent import AgentResult
    inventory_agent.rag_service = mock_rag_service

    mock_result = AgentResult(success=True, data="预计未来3天销量120份，建议库存150份。", confidence=0.85)
    with patch.object(inventory_agent, 'execute_with_tools', new=AsyncMock(return_value=mock_result)):
        result = await inventory_agent.predict_inventory_needs(
            store_id="STORE001",
            dish_id="DISH001",
            time_range="3d"
        )

    assert result["success"] is True
    assert "prediction" in result["data"]
    assert result["data"]["dish_id"] == "DISH001"
    assert result["data"]["time_range"] == "3d"


@pytest.mark.asyncio
async def test_check_low_stock_alert_success(inventory_agent, mock_rag_service):
    """Test low stock alert check with Tool Use"""
    from src.agents.llm_agent import AgentResult
    inventory_agent.rag_service = mock_rag_service

    current_inventory = {
        "DISH001": 20,
        "DISH002": 50,
        "DISH003": 10
    }

    mock_result = AgentResult(success=True, data="高风险: 宫保鸡丁将在2小时内售罄，建议立即补货50份。", confidence=0.85)
    with patch.object(inventory_agent, 'execute_with_tools', new=AsyncMock(return_value=mock_result)):
        result = await inventory_agent.check_low_stock_alert(
            store_id="STORE001",
            current_inventory=current_inventory,
            threshold_hours=4
        )

    assert result["success"] is True
    assert "alert" in result["data"]
    assert result["data"]["inventory_count"] == 3
    assert result["data"]["threshold_hours"] == 4


@pytest.mark.asyncio
async def test_optimize_inventory_levels_success(inventory_agent, mock_rag_service):
    """Test inventory levels optimization with Tool Use"""
    from src.agents.llm_agent import AgentResult
    inventory_agent.rag_service = mock_rag_service

    dish_ids = ["DISH001", "DISH002", "DISH003"]

    mock_result = AgentResult(success=True, data="宫保鸡丁最优库存80份，安全库存50份，建议每日补货。", confidence=0.85)
    with patch.object(inventory_agent, 'execute_with_tools', new=AsyncMock(return_value=mock_result)):
        result = await inventory_agent.optimize_inventory_levels(
            store_id="STORE001",
            dish_ids=dish_ids
        )

    assert result["success"] is True
    assert "optimization" in result["data"]
    assert result["data"]["dish_count"] == 3


@pytest.mark.asyncio
async def test_analyze_waste_success(inventory_agent, mock_rag_service):
    """Test waste analysis with Tool Use"""
    from src.agents.llm_agent import AgentResult
    inventory_agent.rag_service = mock_rag_service

    mock_result = AgentResult(success=True, data="损耗率最高的是海鲜类菜品(15%)，主要原因是过量采购。", confidence=0.85)
    with patch.object(inventory_agent, 'execute_with_tools', new=AsyncMock(return_value=mock_result)):
        result = await inventory_agent.analyze_waste(
            store_id="STORE001",
            time_period="7d"
        )

    assert result["success"] is True
    assert "analysis" in result["data"]
    assert result["data"]["time_period"] == "7d"


@pytest.mark.asyncio
async def test_generate_restock_plan_success(inventory_agent, mock_rag_service):
    """Test restock plan generation with Tool Use"""
    from src.agents.llm_agent import AgentResult
    inventory_agent.rag_service = mock_rag_service

    mock_result = AgentResult(success=True, data="补货清单: 宫保鸡丁100份, 鱼香肉丝80份, 明天8AM补货。", confidence=0.85)
    with patch.object(inventory_agent, 'execute_with_tools', new=AsyncMock(return_value=mock_result)):
        result = await inventory_agent.generate_restock_plan(
            store_id="STORE001",
            target_date="2026-02-22"
        )

    assert result["success"] is True
    assert "plan" in result["data"]
    assert result["data"]["target_date"] == "2026-02-22"


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
