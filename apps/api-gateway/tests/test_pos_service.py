"""
POS服务测试
Tests for POS Service
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.services.pos_service import POSService, pos_service


class TestPOSService:
    """POSService测试类"""

    def test_init(self):
        """测试服务初始化"""
        service = POSService()
        assert service._adapter is None

    @pytest.mark.asyncio
    @patch('src.services.pos_service.PINZHI_AVAILABLE', True)
    @patch('src.services.pos_service.PinzhiAdapter')
    async def test_get_adapter(self, mock_adapter_class):
        """测试获取适配器"""
        mock_adapter = AsyncMock()
        mock_adapter_class.return_value = mock_adapter

        service = POSService()
        adapter = service._get_adapter()

        assert adapter == mock_adapter
        assert service._adapter == mock_adapter
        mock_adapter_class.assert_called_once()

    @pytest.mark.asyncio
    @patch('src.services.pos_service.PINZHI_AVAILABLE', False)
    async def test_get_adapter_not_available(self):
        """测试适配器不可用"""
        service = POSService()

        with pytest.raises(RuntimeError, match="PinzhiAdapter is not available"):
            service._get_adapter()

    @pytest.mark.asyncio
    @patch('src.services.pos_service.PINZHI_AVAILABLE', True)
    @patch('src.services.pos_service.PinzhiAdapter')
    async def test_get_stores(self, mock_adapter_class):
        """测试获取门店信息"""
        mock_adapter = AsyncMock()
        mock_stores = [
            {"ognid": "STORE001", "name": "测试门店1"},
            {"ognid": "STORE002", "name": "测试门店2"}
        ]
        mock_adapter.get_store_info.return_value = mock_stores
        mock_adapter_class.return_value = mock_adapter

        service = POSService()
        result = await service.get_stores()

        assert len(result) == 2
        assert result[0]["ognid"] == "STORE001"
        mock_adapter.get_store_info.assert_called_once_with(None)

    @pytest.mark.asyncio
    @patch('src.services.pos_service.PINZHI_AVAILABLE', True)
    @patch('src.services.pos_service.PinzhiAdapter')
    async def test_get_stores_with_ognid(self, mock_adapter_class):
        """测试获取指定门店信息"""
        mock_adapter = AsyncMock()
        mock_stores = [{"ognid": "STORE001", "name": "测试门店1"}]
        mock_adapter.get_store_info.return_value = mock_stores
        mock_adapter_class.return_value = mock_adapter

        service = POSService()
        result = await service.get_stores(ognid="STORE001")

        assert len(result) == 1
        mock_adapter.get_store_info.assert_called_once_with("STORE001")

    @pytest.mark.asyncio
    @patch('src.services.pos_service.PINZHI_AVAILABLE', True)
    @patch('src.services.pos_service.PinzhiAdapter')
    async def test_get_dish_categories(self, mock_adapter_class):
        """测试获取菜品类别"""
        mock_adapter = AsyncMock()
        mock_categories = [
            {"id": "CAT001", "name": "主食"},
            {"id": "CAT002", "name": "饮料"}
        ]
        mock_adapter.get_dish_categories.return_value = mock_categories
        mock_adapter_class.return_value = mock_adapter

        service = POSService()
        result = await service.get_dish_categories()

        assert len(result) == 2
        assert result[0]["name"] == "主食"
        mock_adapter.get_dish_categories.assert_called_once()

    @pytest.mark.asyncio
    @patch('src.services.pos_service.PINZHI_AVAILABLE', True)
    @patch('src.services.pos_service.PinzhiAdapter')
    async def test_get_dishes(self, mock_adapter_class):
        """测试获取菜品信息"""
        mock_adapter = AsyncMock()
        mock_dishes = [
            {"id": "DISH001", "name": "汉堡", "price": 25.0},
            {"id": "DISH002", "name": "可乐", "price": 8.0}
        ]
        mock_adapter.get_dishes.return_value = mock_dishes
        mock_adapter_class.return_value = mock_adapter

        service = POSService()
        result = await service.get_dishes(updatetime=0)

        assert len(result) == 2
        assert result[0]["name"] == "汉堡"
        mock_adapter.get_dishes.assert_called_once_with(0)

    @pytest.mark.asyncio
    @patch('src.services.pos_service.PINZHI_AVAILABLE', True)
    @patch('src.services.pos_service.PinzhiAdapter')
    async def test_get_tables(self, mock_adapter_class):
        """测试获取桌台信息"""
        mock_adapter = AsyncMock()
        mock_tables = [
            {"id": "TABLE001", "name": "1号桌", "capacity": 4},
            {"id": "TABLE002", "name": "2号桌", "capacity": 6}
        ]
        mock_adapter.get_tables.return_value = mock_tables
        mock_adapter_class.return_value = mock_adapter

        service = POSService()
        result = await service.get_tables()

        assert len(result) == 2
        assert result[0]["name"] == "1号桌"
        mock_adapter.get_tables.assert_called_once()

    @pytest.mark.asyncio
    @patch('src.services.pos_service.PINZHI_AVAILABLE', True)
    @patch('src.services.pos_service.PinzhiAdapter')
    async def test_get_employees(self, mock_adapter_class):
        """测试获取员工信息"""
        mock_adapter = AsyncMock()
        mock_employees = [
            {"id": "EMP001", "name": "张三", "role": "服务员"},
            {"id": "EMP002", "name": "李四", "role": "厨师"}
        ]
        mock_adapter.get_employees.return_value = mock_employees
        mock_adapter_class.return_value = mock_adapter

        service = POSService()
        result = await service.get_employees()

        assert len(result) == 2
        assert result[0]["name"] == "张三"
        mock_adapter.get_employees.assert_called_once()

    @pytest.mark.asyncio
    @patch('src.services.pos_service.PINZHI_AVAILABLE', True)
    @patch('src.services.pos_service.PinzhiAdapter')
    async def test_query_orders(self, mock_adapter_class):
        """测试查询订单"""
        mock_adapter = AsyncMock()
        mock_orders = [
            {"order_id": "ORD001", "amount": 100.0},
            {"order_id": "ORD002", "amount": 150.0}
        ]
        mock_adapter.query_orders.return_value = mock_orders
        mock_adapter_class.return_value = mock_adapter

        service = POSService()
        result = await service.query_orders(
            ognid="STORE001",
            begin_date="2026-03-01",
            end_date="2026-03-31",
            page_index=1,
            page_size=20
        )

        assert result["orders"] == mock_orders
        assert result["page"] == 1
        assert result["page_size"] == 20
        assert result["total"] == 2
        mock_adapter.query_orders.assert_called_once()

    @pytest.mark.asyncio
    @patch('src.services.pos_service.PINZHI_AVAILABLE', True)
    @patch('src.services.pos_service.PinzhiAdapter')
    async def test_query_order_summary(self, mock_adapter_class):
        """测试查询收入汇总"""
        mock_adapter = AsyncMock()
        mock_summary = {
            "total_amount": 5000.0,
            "order_count": 50,
            "avg_amount": 100.0
        }
        mock_adapter.query_order_summary.return_value = mock_summary
        mock_adapter_class.return_value = mock_adapter

        service = POSService()
        result = await service.query_order_summary("STORE001", "2026-03-01")

        assert result["total_amount"] == 5000.0
        assert result["order_count"] == 50
        mock_adapter.query_order_summary.assert_called_once_with("STORE001", "2026-03-01")

    @pytest.mark.asyncio
    @patch('src.services.pos_service.PINZHI_AVAILABLE', True)
    @patch('src.services.pos_service.PinzhiAdapter')
    async def test_get_pay_types(self, mock_adapter_class):
        """测试获取支付方式"""
        mock_adapter = AsyncMock()
        mock_pay_types = [
            {"id": "PAY001", "name": "现金"},
            {"id": "PAY002", "name": "微信支付"}
        ]
        mock_adapter.get_pay_types.return_value = mock_pay_types
        mock_adapter_class.return_value = mock_adapter

        service = POSService()
        result = await service.get_pay_types()

        assert len(result) == 2
        assert result[0]["name"] == "现金"
        mock_adapter.get_pay_types.assert_called_once()

    @pytest.mark.asyncio
    @patch('src.services.pos_service.PINZHI_AVAILABLE', True)
    @patch('src.services.pos_service.PinzhiAdapter')
    async def test_test_connection_success(self, mock_adapter_class):
        """测试连接成功"""
        mock_adapter = AsyncMock()
        mock_stores = [{"ognid": "STORE001"}]
        mock_adapter.get_store_info.return_value = mock_stores
        mock_adapter_class.return_value = mock_adapter

        service = POSService()
        result = await service.test_connection()

        assert result["success"] is True
        assert result["message"] == "连接成功"
        assert result["stores_count"] == 1

    @pytest.mark.asyncio
    @patch('src.services.pos_service.PINZHI_AVAILABLE', True)
    @patch('src.services.pos_service.PinzhiAdapter')
    async def test_test_connection_failure(self, mock_adapter_class):
        """测试连接失败"""
        mock_adapter = AsyncMock()
        mock_adapter.get_store_info.side_effect = Exception("连接超时")
        mock_adapter_class.return_value = mock_adapter

        service = POSService()
        result = await service.test_connection()

        assert result["success"] is False
        assert "连接超时" in result["error"]

    @pytest.mark.asyncio
    @patch('src.services.pos_service.PINZHI_AVAILABLE', True)
    @patch('src.services.pos_service.PinzhiAdapter')
    async def test_close(self, mock_adapter_class):
        """测试关闭服务"""
        mock_adapter = AsyncMock()
        mock_adapter_class.return_value = mock_adapter

        service = POSService()
        # 先获取适配器
        service._get_adapter()
        assert service._adapter is not None

        # 关闭服务
        await service.close()

        assert service._adapter is None
        mock_adapter.close.assert_called_once()


class TestGlobalInstance:
    """测试全局实例"""

    def test_pos_service_instance(self):
        """测试pos_service全局实例"""
        assert pos_service is not None
        assert isinstance(pos_service, POSService)
