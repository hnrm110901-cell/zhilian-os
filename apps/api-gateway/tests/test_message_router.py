"""
消息路由服务测试
Tests for Message Router Service
"""
import pytest
from src.services.message_router import MessageRouter


class TestMessageRouter:
    """MessageRouter测试类"""

    def test_init(self):
        """测试初始化"""
        router = MessageRouter()
        assert router.agent_keywords is not None
        assert router.action_keywords is not None
        assert "schedule" in router.agent_keywords
        assert "order" in router.agent_keywords

    def test_identify_agent_schedule(self):
        """测试识别排班Agent"""
        router = MessageRouter()
        agent_type = router._identify_agent("查询今天的排班")
        assert agent_type == "schedule"

    def test_identify_agent_order(self):
        """测试识别订单Agent"""
        router = MessageRouter()
        agent_type = router._identify_agent("查询订单状态")
        assert agent_type == "order"

    def test_identify_agent_inventory(self):
        """测试识别库存Agent"""
        router = MessageRouter()
        agent_type = router._identify_agent("查询库存情况")
        assert agent_type == "inventory"

    def test_identify_agent_no_match(self):
        """测试无法识别Agent"""
        router = MessageRouter()
        agent_type = router._identify_agent("你好")
        assert agent_type is None

    def test_identify_action_schedule(self):
        """测试识别排班动作"""
        router = MessageRouter()
        action = router._identify_action("schedule", "查询今天的排班")
        assert action == "query_schedule"

    def test_identify_action_order_create(self):
        """测试识别创建订单动作"""
        router = MessageRouter()
        action = router._identify_action("order", "创建新订单")
        assert action == "create_order"

    def test_identify_action_no_match(self):
        """测试无法识别动作"""
        router = MessageRouter()
        action = router._identify_action("schedule", "随便说说")
        assert action is None

    def test_get_default_action_schedule(self):
        """测试获取排班默认动作"""
        router = MessageRouter()
        action = router._get_default_action("schedule")
        assert action == "query_schedule"

    def test_get_default_action_order(self):
        """测试获取订单默认动作"""
        router = MessageRouter()
        action = router._get_default_action("order")
        assert action == "query_order"

    def test_get_default_action_unknown(self):
        """测试获取未知Agent默认动作"""
        router = MessageRouter()
        action = router._get_default_action("unknown")
        assert action == "query"

    def test_extract_params_basic(self):
        """测试提取基本参数"""
        router = MessageRouter()
        params = router._extract_params("schedule", "query_schedule", "查询排班", "USER001")
        assert params["user_id"] == "USER001"
        assert params["message"] == "查询排班"

    def test_extract_params_with_date(self):
        """测试提取日期参数"""
        router = MessageRouter()
        params = router._extract_params("schedule", "query_schedule", "查询2024-01-15的排班", "USER001")
        assert "date" in params
        assert "2024-01-15" in params["date"]

    def test_extract_params_with_today(self):
        """测试提取今天参数"""
        router = MessageRouter()
        params = router._extract_params("schedule", "query_schedule", "查询今天的排班", "USER001")
        assert params.get("date") == "today"

    def test_extract_params_with_tomorrow(self):
        """测试提取明天参数"""
        router = MessageRouter()
        params = router._extract_params("schedule", "query_schedule", "查询明天的排班", "USER001")
        assert params.get("date") == "tomorrow"

    def test_extract_params_with_quantity(self):
        """测试提取数量参数"""
        router = MessageRouter()
        params = router._extract_params("inventory", "request_restock", "补货100个", "USER001")
        assert params.get("quantity") == 100

    def test_extract_params_order_id(self):
        """测试提取订单号"""
        router = MessageRouter()
        params = router._extract_params("order", "query_order", "查询订单号ABC1234567", "USER001")
        assert "order_id" in params
        assert params["order_id"] == "ABC1234567"

    def test_route_message_schedule(self):
        """测试路由排班消息"""
        router = MessageRouter()
        agent_type, action, params = router.route_message("查询今天的排班", "USER001")
        assert agent_type == "schedule"
        assert action == "query_schedule"
        assert params["user_id"] == "USER001"
        assert params.get("date") == "today"

    def test_route_message_order(self):
        """测试路由订单消息"""
        router = MessageRouter()
        agent_type, action, params = router.route_message("创建新订单", "USER001")
        assert agent_type == "order"
        assert action == "create_order"
        assert params["user_id"] == "USER001"

    def test_route_message_no_agent(self):
        """测试路由无法识别的消息"""
        router = MessageRouter()
        agent_type, action, params = router.route_message("你好", "USER001")
        assert agent_type is None
        assert action is None
        assert params == {}

    def test_route_message_no_action(self):
        """测试路由无动作的消息"""
        router = MessageRouter()
        agent_type, action, params = router.route_message("排班", "USER001")
        assert agent_type == "schedule"
        assert action == "query_schedule"  # 默认动作

    def test_format_agent_response_error(self):
        """测试格式化错误响应"""
        router = MessageRouter()
        result = {"success": False, "error": "系统错误"}
        response = router.format_agent_response("schedule", "query_schedule", result)
        assert "❌" in response
        assert "系统错误" in response

    def test_format_agent_response_success(self):
        """测试格式化成功响应"""
        router = MessageRouter()
        result = {"success": True, "data": {"schedule": "test"}}
        response = router.format_agent_response("schedule", "query_schedule", result)
        assert response is not None
        assert isinstance(response, str)
