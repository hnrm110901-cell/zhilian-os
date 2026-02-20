"""
仪表板服务测试
Tests for Dashboard Service
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.dashboard_service import DashboardService, dashboard_service


class TestDashboardService:
    """DashboardService测试类"""

    @pytest.mark.asyncio
    @patch('src.services.dashboard_service.pos_service')
    async def test_get_overview_stats_success(self, mock_pos_service):
        """测试获取概览统计数据成功"""
        # Mock stores - need to return awaitable
        async def mock_get_stores():
            return [
                {"ognid": "STORE001", "name": "门店1"},
                {"ognid": "STORE002", "name": "门店2"}
            ]
        mock_pos_service.get_stores = mock_get_stores

        # Mock orders - need to return awaitable
        async def mock_query_orders_today(*args, **kwargs):
            return {
                "orders": [
                    {"order_id": "ORD001", "realPrice": 100},
                    {"order_id": "ORD002", "realPrice": 150}
                ]
            }

        async def mock_query_orders_yesterday(*args, **kwargs):
            return {
                "orders": [
                    {"order_id": "ORD003", "realPrice": 120}
                ]
            }

        # Use side_effect to return different values for each call
        call_count = [0]
        async def mock_query_orders(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return await mock_query_orders_today()
            else:
                return await mock_query_orders_yesterday()

        mock_pos_service.query_orders = mock_query_orders

        service = DashboardService()
        result = await service.get_overview_stats()

        assert "timestamp" in result
        assert result["stores"]["total"] == 2
        assert result["stores"]["active"] == 2
        assert result["orders"]["today"] == 2
        assert result["orders"]["yesterday"] == 1
        assert result["revenue"]["today"] == 250
        assert result["revenue"]["yesterday"] == 120

    @pytest.mark.asyncio
    @patch('src.services.dashboard_service.pos_service')
    async def test_get_overview_stats_with_errors(self, mock_pos_service):
        """测试获取概览统计数据（部分失败）"""
        # Mock stores to raise exception
        async def mock_get_stores():
            raise Exception("连接失败")
        mock_pos_service.get_stores = mock_get_stores

        async def mock_query_orders(*args, **kwargs):
            raise Exception("查询失败")
        mock_pos_service.query_orders = mock_query_orders

        service = DashboardService()
        result = await service.get_overview_stats()

        # Should return default values when errors occur
        assert result["stores"]["total"] == 0
        assert result["orders"]["today"] == 0

    @pytest.mark.asyncio
    @patch('src.services.dashboard_service.pos_service')
    async def test_get_sales_trend(self, mock_pos_service):
        """测试获取销售趋势数据"""
        # Mock orders for each day
        async def mock_query_orders(*args, **kwargs):
            return {
                "orders": [
                    {"order_id": "ORD001", "realPrice": 100},
                    {"order_id": "ORD002", "realPrice": 150}
                ]
            }
        mock_pos_service.query_orders = mock_query_orders

        service = DashboardService()
        result = await service.get_sales_trend(days=3)

        assert "dates" in result
        assert "orders_count" in result
        assert "revenue" in result
        assert len(result["dates"]) == 3
        assert len(result["orders_count"]) == 3
        assert len(result["revenue"]) == 3

    @pytest.mark.asyncio
    @patch('src.services.dashboard_service.pos_service')
    async def test_get_sales_trend_with_errors(self, mock_pos_service):
        """测试获取销售趋势数据（有错误）"""
        # Mock to raise exception
        async def mock_query_orders(*args, **kwargs):
            raise Exception("查询失败")
        mock_pos_service.query_orders = mock_query_orders

        service = DashboardService()
        result = await service.get_sales_trend(days=2)

        # Should return zeros when errors occur
        assert len(result["dates"]) == 2
        assert all(count == 0 for count in result["orders_count"])
        assert all(rev == 0 for rev in result["revenue"])

    @pytest.mark.asyncio
    @patch('src.services.dashboard_service.pos_service')
    async def test_get_category_sales_success(self, mock_pos_service):
        """测试获取菜品类别销售数据成功"""
        async def mock_get_dish_categories():
            return [
                {"rcNAME": "主食", "id": "CAT001"},
                {"rcNAME": "饮料", "id": "CAT002"},
                {"rcNAME": "小吃", "id": "CAT003"}
            ]
        mock_pos_service.get_dish_categories = mock_get_dish_categories

        service = DashboardService()
        result = await service.get_category_sales()

        assert "categories" in result
        assert len(result["categories"]) == 3
        assert result["categories"][0]["name"] == "主食"

    @pytest.mark.asyncio
    @patch('src.services.dashboard_service.pos_service')
    async def test_get_category_sales_error(self, mock_pos_service):
        """测试获取菜品类别销售数据失败"""
        async def mock_get_dish_categories():
            raise Exception("获取失败")
        mock_pos_service.get_dish_categories = mock_get_dish_categories

        service = DashboardService()
        result = await service.get_category_sales()

        assert result["categories"] == []

    @pytest.mark.asyncio
    @patch('src.services.dashboard_service.pos_service')
    async def test_get_payment_methods_success(self, mock_pos_service):
        """测试获取支付方式分布成功"""
        async def mock_get_pay_types():
            return [
                {"name": "现金", "id": "PAY001"},
                {"name": "微信支付", "id": "PAY002"},
                {"name": "支付宝", "id": "PAY003"}
            ]
        mock_pos_service.get_pay_types = mock_get_pay_types

        service = DashboardService()
        result = await service.get_payment_methods()

        assert "payment_methods" in result
        assert len(result["payment_methods"]) == 3
        assert result["payment_methods"][0]["name"] == "现金"

    @pytest.mark.asyncio
    @patch('src.services.dashboard_service.pos_service')
    async def test_get_payment_methods_error(self, mock_pos_service):
        """测试获取支付方式分布失败"""
        async def mock_get_pay_types():
            raise Exception("获取失败")
        mock_pos_service.get_pay_types = mock_get_pay_types

        service = DashboardService()
        result = await service.get_payment_methods()

        assert result["payment_methods"] == []

    @pytest.mark.asyncio
    async def test_get_member_stats(self):
        """测试获取会员统计数据"""
        service = DashboardService()
        result = await service.get_member_stats()

        assert "total_members" in result
        assert "new_members_today" in result
        assert "active_members" in result
        assert "member_levels" in result
        assert len(result["member_levels"]) == 4

    @pytest.mark.asyncio
    async def test_get_agent_performance(self):
        """测试获取Agent性能数据"""
        service = DashboardService()
        result = await service.get_agent_performance()

        assert "agents" in result
        assert len(result["agents"]) == 7
        assert result["agents"][0]["name"] == "排班Agent"

    @pytest.mark.asyncio
    async def test_get_realtime_metrics(self):
        """测试获取实时指标"""
        service = DashboardService()
        result = await service.get_realtime_metrics()

        assert "timestamp" in result
        assert "current_orders" in result
        assert "current_customers" in result
        assert "table_occupancy_rate" in result
        assert "average_wait_time" in result
        assert "kitchen_queue" in result


class TestGlobalInstance:
    """测试全局实例"""

    def test_dashboard_service_instance(self):
        """测试dashboard_service全局实例"""
        assert dashboard_service is not None
        assert isinstance(dashboard_service, DashboardService)
