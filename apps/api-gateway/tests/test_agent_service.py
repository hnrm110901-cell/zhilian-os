"""
测试Agent服务
"""
import pytest
from src.services.agent_service import AgentService


class TestAgentService:
    """测试AgentService类"""

    @pytest.fixture
    def agent_service(self):
        """创建AgentService实例"""
        return AgentService()

    @pytest.mark.unit
    async def test_execute_schedule_agent(self, agent_service, sample_schedule_data):
        """测试执行排班Agent"""
        input_data = {
            "action": "run",
            **sample_schedule_data,
        }

        result = await agent_service.execute_agent("schedule", input_data)

        assert result is not None
        assert "execution_time" in result
        assert isinstance(result["execution_time"], (int, float))

    @pytest.mark.unit
    async def test_execute_order_agent(self, agent_service, sample_order_data):
        """测试执行订单Agent"""
        input_data = {
            "action": "process",
            "order_id": "ORD_001",
            "order_data": sample_order_data,
        }

        result = await agent_service.execute_agent("order", input_data)

        assert result is not None
        assert "execution_time" in result

    @pytest.mark.unit
    async def test_execute_inventory_agent(self, agent_service, sample_inventory_data):
        """测试执行库存Agent"""
        input_data = {
            "action": "check",
            "store_id": "store_001",
            "items": ["大米", "食用油"],
        }

        result = await agent_service.execute_agent("inventory", input_data)

        assert result is not None
        assert "execution_time" in result

    @pytest.mark.unit
    async def test_execute_invalid_agent(self, agent_service):
        """测试执行不存在的Agent"""
        result = await agent_service.execute_agent("invalid_agent", {"action": "test"})

        assert result is not None
        assert result["success"] is False
        assert "未知的Agent类型" in result["error"]

    @pytest.mark.unit
    async def test_execute_agent_with_empty_data(self, agent_service):
        """测试使用空数据执行Agent"""
        result = await agent_service.execute_agent("schedule", {"action": "run"})

        assert result is not None
        # Agent应该能处理空数据或返回错误

    @pytest.mark.unit
    async def test_agent_execution_time(self, agent_service, sample_schedule_data):
        """测试Agent执行时间记录"""
        input_data = {
            "action": "run",
            **sample_schedule_data,
        }

        result = await agent_service.execute_agent("schedule", input_data)

        assert "execution_time" in result
        assert result["execution_time"] >= 0
        assert result["execution_time"] < 10  # 应该在10秒内完成

    @pytest.mark.unit
    async def test_multiple_agent_executions(self, agent_service, sample_schedule_data):
        """测试多次执行Agent"""
        input_data = {
            "action": "run",
            **sample_schedule_data,
        }

        # 执行多次
        results = []
        for _ in range(3):
            result = await agent_service.execute_agent("schedule", input_data)
            results.append(result)

        # 所有执行都应该成功
        assert len(results) == 3
        for result in results:
            assert result is not None
            assert "execution_time" in result

    @pytest.mark.unit
    async def test_service_agent(self, agent_service):
        """测试服务质量Agent"""
        input_data = {
            "action": "analyze",
            "store_id": "store_001",
            "feedback_data": {
                "rating": 4.5,
                "comments": ["服务很好", "菜品美味"],
            },
        }

        result = await agent_service.execute_agent("service", input_data)

        assert result is not None
        assert "execution_time" in result

    @pytest.mark.unit
    async def test_training_agent(self, agent_service):
        """测试培训Agent"""
        input_data = {
            "action": "assess",
            "store_id": "store_001",
            "employee_id": "emp_001",
        }

        result = await agent_service.execute_agent("training", input_data)

        assert result is not None
        assert "execution_time" in result

    @pytest.mark.unit
    async def test_decision_agent(self, agent_service):
        """测试决策Agent"""
        input_data = {
            "action": "analyze",
            "store_id": "store_001",
            "date_range": {
                "start": "2024-02-01",
                "end": "2024-02-28",
            },
        }

        result = await agent_service.execute_agent("decision", input_data)

        assert result is not None
        assert "execution_time" in result

    @pytest.mark.unit
    async def test_reservation_agent(self, agent_service):
        """测试预订Agent"""
        input_data = {
            "action": "create",
            "store_id": "store_001",
            "reservation_data": {
                "customer_name": "张三",
                "phone": "13800138000",
                "date": "2024-02-25",
                "time": "18:00",
                "party_size": 4,
            },
        }

        result = await agent_service.execute_agent("reservation", input_data)

        assert result is not None
        assert "execution_time" in result
