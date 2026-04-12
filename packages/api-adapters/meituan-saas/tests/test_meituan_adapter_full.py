"""
美团SAAS适配器完整测试套件
覆盖：Webhook接收验证、等位数据处理、订单管理、商品管理、错误处理
只mock HTTP请求层（httpx），不mock适配器内部逻辑
"""
import os
import sys

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

_here = os.path.dirname(os.path.abspath(__file__))
_repo_root = os.path.abspath(os.path.join(_here, "../../../.."))
_gateway_src = os.path.join(_repo_root, "apps", "api-gateway", "src")
if _gateway_src not in sys.path:
    sys.path.insert(0, _gateway_src)

_adapter_src = os.path.abspath(os.path.join(_here, "../src"))
if _adapter_src not in sys.path:
    sys.path.insert(0, _adapter_src)

import pytest
import httpx
from decimal import Decimal
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from adapter import MeituanSaasAdapter
from core.exceptions import (
    POSAdapterError,
    MeituanAPIError,
    DataValidationError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def adapter():
    """创建美团SAAS适配器实例"""
    config = {
        "base_url": "https://waimaiopen.meituan.com",
        "app_key": "test_app_key",
        "app_secret": "test_app_secret",
        "poi_id": "12345678",
        "timeout": 5,
        "retry_times": 1,
    }
    return MeituanSaasAdapter(config)


def _mock_response(json_data, status_code=200):
    """构造模拟的 httpx.Response"""
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.json.return_value = json_data
    response.raise_for_status = MagicMock()
    if status_code >= 400:
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            message=f"HTTP {status_code}",
            request=MagicMock(),
            response=response,
        )
    return response


# ---------------------------------------------------------------------------
# Webhook 签名验证
# ---------------------------------------------------------------------------

class TestWebhookSignatureVerification:
    """Webhook接收签名验证测试"""

    def test_generate_sign_deterministic(self, adapter):
        """签名生成是确定性的"""
        params = {"order_id": "MT001", "status": "4"}
        sign1 = adapter._generate_sign(params)
        sign2 = adapter._generate_sign(params)
        assert sign1 == sign2

    def test_generate_sign_format(self, adapter):
        """签名格式为32位小写MD5"""
        params = {"order_id": "MT001"}
        sign = adapter._generate_sign(params)
        assert len(sign) == 32
        assert sign == sign.lower()
        assert all(c in "0123456789abcdef" for c in sign)

    def test_generate_sign_includes_secret(self, adapter):
        """不同app_secret生成不同签名"""
        params = {"order_id": "MT001"}
        sign1 = adapter._generate_sign(params)

        adapter2 = MeituanSaasAdapter({
            "base_url": "https://waimaiopen.meituan.com",
            "app_key": "test_app_key",
            "app_secret": "different_secret",
            "poi_id": "12345678",
        })
        sign2 = adapter2._generate_sign(params)
        assert sign1 != sign2

    def test_authenticate_adds_sign_and_app_key(self, adapter):
        """authenticate 方法添加 app_key, timestamp, sign"""
        result = adapter.authenticate({"order_id": "MT001"})
        assert "app_key" in result
        assert "timestamp" in result
        assert "sign" in result
        assert result["app_key"] == "test_app_key"
        assert result["order_id"] == "MT001"


# ---------------------------------------------------------------------------
# 等位/预订数据处理（reservation.py）
# ---------------------------------------------------------------------------

class TestReservationMixin:
    """等位/预订数据处理测试（MeituanReservationMixin）"""

    @pytest.mark.asyncio
    async def test_query_reservation_detail(self, adapter):
        """验证预订详情查询"""
        # MeituanReservationMixin 使用 _request 方法
        # 先导入 mixin
        from reservation import MeituanReservationMixin

        # 创建同时继承两者的测试类
        class TestableAdapter(MeituanReservationMixin, MeituanSaasAdapter):
            pass

        mixed = TestableAdapter({
            "base_url": "https://waimaiopen.meituan.com",
            "app_key": "test_key",
            "app_secret": "test_secret",
            "poi_id": "P001",
        })

        mock_data = {
            "code": "ok",
            "data": {
                "reservation_id": "RSV001",
                "guest_name": "张先生",
                "guest_count": 4,
                "arrival_time": "2024-03-01 18:00:00",
                "status": "confirmed",
                "table_type": "大桌",
            },
        }
        mixed.client.get = AsyncMock(return_value=_mock_response(mock_data))

        result = await mixed.query_reservation(external_reservation_id="RSV001")

        assert result["data"]["reservation_id"] == "RSV001"
        assert result["data"]["guest_count"] == 4
        assert result["data"]["status"] == "confirmed"

    @pytest.mark.asyncio
    async def test_confirm_reservation(self, adapter):
        """验证预订确认操作"""
        from reservation import MeituanReservationMixin

        class TestableAdapter(MeituanReservationMixin, MeituanSaasAdapter):
            pass

        mixed = TestableAdapter({
            "base_url": "https://waimaiopen.meituan.com",
            "app_key": "test_key",
            "app_secret": "test_secret",
            "poi_id": "P001",
        })

        mock_data = {"code": "ok", "data": {"reservation_id": "RSV001", "status": "confirmed"}}
        mixed.client.post = AsyncMock(return_value=_mock_response(mock_data))

        result = await mixed.confirm_reservation(external_reservation_id="RSV001")

        assert result["data"]["status"] == "confirmed"

    @pytest.mark.asyncio
    async def test_cancel_reservation_with_reason(self, adapter):
        """验证带原因的预订取消"""
        from reservation import MeituanReservationMixin

        class TestableAdapter(MeituanReservationMixin, MeituanSaasAdapter):
            pass

        mixed = TestableAdapter({
            "base_url": "https://waimaiopen.meituan.com",
            "app_key": "test_key",
            "app_secret": "test_secret",
            "poi_id": "P001",
        })

        mock_data = {"code": "ok", "data": {"reservation_id": "RSV001", "status": "cancelled"}}
        mixed.client.post = AsyncMock(return_value=_mock_response(mock_data))

        result = await mixed.cancel_reservation(
            external_reservation_id="RSV001",
            reason="顾客临时有事",
        )

        assert result["data"]["status"] == "cancelled"
        # 验证请求中包含 reason
        call_kwargs = mixed.client.post.call_args
        sent_data = call_kwargs.kwargs.get("data", call_kwargs[1].get("data", {}))
        assert sent_data["reason"] == "顾客临时有事"


# ---------------------------------------------------------------------------
# 订单管理（核心路径）
# ---------------------------------------------------------------------------

class TestOrderManagement:
    """订单管理接口测试"""

    @pytest.mark.asyncio
    async def test_query_order_by_id(self, adapter):
        """通过订单ID查询订单详情"""
        mock_data = {
            "code": "ok",
            "data": {
                "order_id": "MT001",
                "status": 4,
                "total_price": 8800,
                "food_list": [
                    {"food_id": "F001", "food_name": "宫保鸡丁", "count": 1, "price": 3800},
                ],
            },
        }
        adapter.client.get = AsyncMock(return_value=_mock_response(mock_data))

        result = await adapter.query_order(order_id="MT001")

        assert result["order_id"] == "MT001"
        assert result["status"] == 4
        assert result["total_price"] == 8800
        assert len(result["food_list"]) == 1

    @pytest.mark.asyncio
    async def test_query_order_requires_id_or_seq(self, adapter):
        """未提供order_id和day_seq时抛出ValueError"""
        with pytest.raises(ValueError, match="order_id和day_seq至少提供一个"):
            await adapter.query_order()

    @pytest.mark.asyncio
    async def test_confirm_order(self, adapter):
        """确认订单"""
        mock_data = {"code": "ok", "data": {"order_id": "MT001", "status": "confirmed"}}
        adapter.client.post = AsyncMock(return_value=_mock_response(mock_data))

        result = await adapter.confirm_order(order_id="MT001")

        assert result["status"] == "confirmed"

    @pytest.mark.asyncio
    async def test_cancel_order(self, adapter):
        """取消订单"""
        mock_data = {"code": "ok", "data": {"order_id": "MT001", "status": "cancelled"}}
        adapter.client.post = AsyncMock(return_value=_mock_response(mock_data))

        result = await adapter.cancel_order(
            order_id="MT001",
            reason_code=1,
            reason="商家缺货",
        )

        assert result["status"] == "cancelled"


# ---------------------------------------------------------------------------
# 商品管理
# ---------------------------------------------------------------------------

class TestFoodManagement:
    """商品管理接口测试"""

    @pytest.mark.asyncio
    async def test_query_food_list(self, adapter):
        """查询商品列表"""
        mock_data = {
            "code": "ok",
            "data": [
                {"food_id": "F001", "food_name": "宫保鸡丁", "price": 3800, "stock": 50},
                {"food_id": "F002", "food_name": "米饭", "price": 300, "stock": 200},
            ],
        }
        adapter.client.get = AsyncMock(return_value=_mock_response(mock_data))

        result = await adapter.query_food()

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["food_name"] == "宫保鸡丁"

    @pytest.mark.asyncio
    async def test_update_food_stock(self, adapter):
        """更新商品库存"""
        mock_data = {"code": "ok", "data": {"food_id": "F001", "stock": 30}}
        adapter.client.post = AsyncMock(return_value=_mock_response(mock_data))

        result = await adapter.update_food_stock(food_id="F001", stock=30)

        assert result["stock"] == 30

    @pytest.mark.asyncio
    async def test_sold_out_food(self, adapter):
        """商品售罄"""
        mock_data = {"code": "ok", "data": {"food_id": "F001", "status": "sold_out"}}
        adapter.client.post = AsyncMock(return_value=_mock_response(mock_data))

        result = await adapter.sold_out_food(food_id="F001")

        assert result["status"] == "sold_out"


# ---------------------------------------------------------------------------
# 错误处理
# ---------------------------------------------------------------------------

class TestMeituanErrorHandling:
    """错误处理测试"""

    def test_handle_error_code_ok(self, adapter):
        """code='ok' 不应抛异常"""
        adapter.handle_error({"code": "ok", "data": {}})

    def test_handle_error_code_zero(self, adapter):
        """code=0 不应抛异常"""
        adapter.handle_error({"code": 0, "data": {}})

    def test_handle_error_business_error(self, adapter):
        """业务错误码抛出异常"""
        with pytest.raises(Exception, match="美团API错误"):
            adapter.handle_error({"code": "invalid_param", "message": "参数错误"})

    def test_handle_error_with_numeric_code(self, adapter):
        """数字错误码"""
        with pytest.raises(Exception, match="美团API错误"):
            adapter.handle_error({"code": 40001, "message": "签名验证失败"})

    @pytest.mark.asyncio
    async def test_network_timeout(self, adapter):
        """网络超时"""
        adapter.client.get = AsyncMock(
            side_effect=httpx.ConnectTimeout("连接超时")
        )

        with pytest.raises(Exception):
            await adapter.query_order(order_id="MT001")

    @pytest.mark.asyncio
    async def test_http_500_error(self, adapter):
        """服务端500错误"""
        adapter.client.post = AsyncMock(
            return_value=_mock_response({"error": "Internal Server Error"}, status_code=500)
        )

        with pytest.raises(Exception):
            await adapter.confirm_order(order_id="MT001")

    @pytest.mark.asyncio
    async def test_malformed_json_response(self, adapter):
        """响应非JSON格式"""
        response = MagicMock(spec=httpx.Response)
        response.status_code = 200
        response.raise_for_status = MagicMock()
        response.json.side_effect = ValueError("Invalid JSON")
        adapter.client.get = AsyncMock(return_value=response)

        with pytest.raises(Exception):
            await adapter.query_order(order_id="MT001")


# ---------------------------------------------------------------------------
# 初始化校验
# ---------------------------------------------------------------------------

class TestMeituanAdapterInit:
    """适配器初始化测试"""

    def test_init_missing_app_key(self):
        """缺少app_key时抛出ValueError"""
        with pytest.raises(ValueError, match="app_key和app_secret不能为空"):
            MeituanSaasAdapter({
                "base_url": "https://waimaiopen.meituan.com",
                "app_secret": "secret",
            })

    def test_init_missing_app_secret(self):
        """缺少app_secret时抛出ValueError"""
        with pytest.raises(ValueError, match="app_key和app_secret不能为空"):
            MeituanSaasAdapter({
                "base_url": "https://waimaiopen.meituan.com",
                "app_key": "key",
            })

    def test_init_default_base_url(self):
        """未指定base_url时使用默认美团地址"""
        adapter = MeituanSaasAdapter({
            "app_key": "k",
            "app_secret": "s",
        })
        assert adapter.base_url == "https://waimaiopen.meituan.com"

    def test_init_custom_poi_id(self):
        """自定义门店ID"""
        adapter = MeituanSaasAdapter({
            "app_key": "k",
            "app_secret": "s",
            "poi_id": "CUSTOM_POI",
        })
        assert adapter.poi_id == "CUSTOM_POI"


# ---------------------------------------------------------------------------
# to_order 补充测试
# ---------------------------------------------------------------------------

class TestToOrderEdgeCases:
    """to_order 边界场景"""

    def test_order_with_iso_string_time(self, adapter):
        """ISO格式时间字符串正确解析"""
        raw = {
            "order_id": "MT_ISO",
            "day_seq": "001",
            "status": 2,
            "total_price": 5000,
            "discount_price": 0,
            "create_time": "2024-03-01T12:00:00",
            "food_list": [],
        }
        order = adapter.to_order(raw, "S1", "B1")
        assert order.created_at.year == 2024
        assert order.created_at.month == 3

    def test_order_with_invalid_time_fallback(self, adapter):
        """无效时间降级为当前时间"""
        raw = {
            "order_id": "MT_BAD",
            "day_seq": "002",
            "status": 1,
            "total_price": 3000,
            "discount_price": 0,
            "create_time": "not-a-time",
            "food_list": [],
        }
        order = adapter.to_order(raw, "S1", "B1")
        assert isinstance(order.created_at, datetime)

    def test_order_status_refund_maps_cancelled(self, adapter):
        """美团status=8（退款）映射为CANCELLED"""
        from schemas.restaurant_standard_schema import OrderStatus
        raw = {
            "order_id": "MT_REFUND",
            "day_seq": "003",
            "status": 8,
            "total_price": 5000,
            "discount_price": 0,
            "food_list": [],
        }
        order = adapter.to_order(raw, "S1", "B1")
        assert order.order_status == OrderStatus.CANCELLED


# ---------------------------------------------------------------------------
# 异步资源管理
# ---------------------------------------------------------------------------

class TestAsyncResourceManagement:
    """异步资源管理测试"""

    @pytest.mark.asyncio
    async def test_close_releases_client(self, adapter):
        """close() 正确释放资源"""
        adapter.client.aclose = AsyncMock()
        await adapter.close()
        adapter.client.aclose.assert_called_once()
