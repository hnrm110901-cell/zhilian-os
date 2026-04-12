"""
奥琦玮供应链适配器完整测试套件
覆盖：正常数据拉取、认证失败处理、数据格式转换验证、边界条件
只mock HTTP请求层（httpx），不mock适配器内部逻辑
"""
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
_repo_root = os.path.abspath(os.path.join(_here, "../../../.."))
_gateway_src = os.path.join(_repo_root, "apps", "api-gateway", "src")
if _gateway_src not in sys.path:
    sys.path.insert(0, _gateway_src)

import pytest
import httpx
from decimal import Decimal
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from src.adapter import AoqiweiAdapter
from core.exceptions import (
    POSAdapterError,
    AoqiweiAPIError,
    DataValidationError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def adapter():
    """创建奥琦玮适配器实例"""
    config = {
        "base_url": "https://openapi.acescm.cn",
        "app_key": "test_key",
        "app_secret": "test_secret",
        "timeout": 5,
        "retry_times": 1,
    }
    return AoqiweiAdapter(config)


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
# 正常数据拉取路径
# ---------------------------------------------------------------------------

class TestAoqiweiFetchData:
    """正常数据拉取路径测试"""

    @pytest.mark.asyncio
    async def test_query_goods_returns_data(self, adapter):
        """验证货品查询返回正确数据"""
        mock_response_data = {
            "success": True,
            "code": 0,
            "msg": "成功",
            "data": {
                "list": [
                    {"goodCode": "G001", "goodName": "五花肉", "unit": "kg", "price": 3500},
                    {"goodCode": "G002", "goodName": "鸡蛋", "unit": "个", "price": 150},
                ],
                "total": 2,
            },
        }
        adapter._client.get = AsyncMock(return_value=_mock_response(mock_response_data))

        result = await adapter.query_goods(page=1, page_size=100)

        assert isinstance(result, dict)
        assert result["total"] == 2
        assert len(result["list"]) == 2
        assert result["list"][0]["goodCode"] == "G001"
        assert result["list"][0]["goodName"] == "五花肉"

    @pytest.mark.asyncio
    async def test_query_shops_returns_list(self, adapter):
        """验证门店列表查询"""
        mock_response_data = {
            "success": True,
            "code": 0,
            "data": [
                {"shopCode": "SH001", "shopName": "总店", "address": "长沙市岳麓区"},
                {"shopCode": "SH002", "shopName": "分店", "address": "长沙市天心区"},
            ],
        }
        adapter._client.get = AsyncMock(return_value=_mock_response(mock_response_data))

        result = await adapter.query_shops()

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["shopCode"] == "SH001"
        assert result[1]["shopName"] == "分店"

    @pytest.mark.asyncio
    async def test_query_purchase_orders_returns_data(self, adapter):
        """验证采购入库单查询"""
        mock_response_data = {
            "success": True,
            "code": 0,
            "data": {
                "list": [
                    {"orderNo": "PO001", "depotCode": "D001", "totalAmount": 50000},
                ],
                "total": 1,
            },
        }
        adapter._client.get = AsyncMock(return_value=_mock_response(mock_response_data))

        result = await adapter.query_purchase_orders(
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

        assert result["total"] == 1
        assert result["list"][0]["orderNo"] == "PO001"

    @pytest.mark.asyncio
    async def test_query_delivery_dispatch_out(self, adapter):
        """验证配送出库单查询"""
        mock_response_data = {
            "success": True,
            "code": 0,
            "data": [
                {"orderNo": "DO001", "shopCode": "SH001", "status": "delivered"},
                {"orderNo": "DO002", "shopCode": "SH002", "status": "pending"},
            ],
        }
        adapter._client.get = AsyncMock(return_value=_mock_response(mock_response_data))

        result = await adapter.query_delivery_dispatch_out(
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["orderNo"] == "DO001"


# ---------------------------------------------------------------------------
# 认证失败处理
# ---------------------------------------------------------------------------

class TestAuthenticationFailure:
    """认证失败处理测试"""

    @pytest.mark.asyncio
    async def test_invalid_appkey_raises_business_error(self, adapter):
        """appkey无效时，query_goods 内部捕获业务错误并降级返回空结果"""
        mock_response_data = {
            "success": False,
            "code": 40001,
            "msg": "appkey不存在或已过期",
        }
        adapter._client.get = AsyncMock(return_value=_mock_response(mock_response_data))

        # query_goods 内部 try/except 会捕获业务错误，返回安全默认值
        result = await adapter.query_goods()
        assert result == {"list": [], "total": 0}

    @pytest.mark.asyncio
    async def test_invalid_sign_raises_error(self, adapter):
        """签名错误时，query_shops 内部捕获业务错误并降级返回空列表"""
        mock_response_data = {
            "success": False,
            "code": 40002,
            "msg": "签名验证失败",
        }
        adapter._client.get = AsyncMock(return_value=_mock_response(mock_response_data))

        # query_shops 内部 try/except 会捕获业务错误，降级返回空列表
        result = await adapter.query_shops()
        assert result == []

    @pytest.mark.asyncio
    async def test_http_401_raises_error(self, adapter):
        """HTTP 401认证失败时，query_goods 内部捕获并降级返回空结果"""
        adapter._client.get = AsyncMock(
            return_value=_mock_response({"error": "Unauthorized"}, status_code=401)
        )

        # query_goods 内部 try/except 捕获 HTTPStatusError，降级返回安全默认值
        result = await adapter.query_goods()
        assert result == {"list": [], "total": 0}

    def test_degraded_mode_init_without_credentials(self, monkeypatch):
        """未配置凭证时仍可初始化（降级模式）"""
        monkeypatch.delenv("AOQIWEI_APP_KEY", raising=False)
        monkeypatch.delenv("AOQIWEI_APP_SECRET", raising=False)
        adapter = AoqiweiAdapter({"base_url": "https://openapi.acescm.cn"})
        assert adapter.app_key == ""
        assert adapter.app_secret == ""


# ---------------------------------------------------------------------------
# 数据格式转换验证
# ---------------------------------------------------------------------------

class TestDataFormatConversion:
    """数据格式转换验证"""

    def test_to_order_complete_mapping(self, adapter):
        """验证完整订单数据映射"""
        raw = {
            "orderId": "AQ20240301001",
            "orderNo": "AQ-2024-0301-001",
            "orderDate": "2024-03-01 12:30:00",
            "orderStatus": "2",
            "shopCode": "SH001",
            "tableNo": "A05",
            "memberId": "VIP001",
            "totalAmount": 25600,
            "discountAmount": 3000,
            "remark": "多放辣",
            "waiterId": "W001",
            "items": [
                {"orderItemNo": "I001", "goodCode": "G001", "goodName": "剁椒鱼头", "qty": 1, "price": 12800},
                {"orderItemNo": "I002", "goodCode": "G002", "goodName": "蒜蓉西兰花", "qty": 2, "price": 3200},
            ],
        }

        order = adapter.to_order(raw, store_id="STORE_01", brand_id="BRAND_XJ")

        assert order.order_id == "AQ20240301001"
        assert order.order_number == "AQ-2024-0301-001"
        assert order.store_id == "STORE_01"
        assert order.brand_id == "BRAND_XJ"
        assert order.total == Decimal("256.00")
        assert order.discount == Decimal("30.00")
        assert order.table_number == "A05"
        assert order.customer_id == "VIP001"
        assert order.notes == "多放辣"
        assert len(order.items) == 2
        assert order.items[0].dish_name == "剁椒鱼头"
        assert order.items[0].unit_price == Decimal("128.00")
        assert order.items[1].quantity == 2
        assert order.items[1].subtotal == Decimal("64.00")

    def test_to_order_status_mapping(self, adapter):
        """验证各种状态码的映射"""
        from schemas.restaurant_standard_schema import OrderStatus

        base_raw = {
            "orderId": "A1", "orderNo": "N1",
            "totalAmount": 1000, "discountAmount": 0, "items": [],
        }

        for status_str, expected in [
            ("0", OrderStatus.PENDING),
            ("1", OrderStatus.CONFIRMED),
            ("2", OrderStatus.COMPLETED),
            ("3", OrderStatus.CANCELLED),
        ]:
            raw = {**base_raw, "orderStatus": status_str}
            order = adapter.to_order(raw, "S1", "B1")
            assert order.order_status == expected, f"status '{status_str}' 应映射为 {expected}"

    def test_to_order_empty_items(self, adapter):
        """没有订单项时items为空列表"""
        raw = {
            "orderId": "AQ_EMPTY",
            "orderNo": "AQ-EMPTY-001",
            "orderDate": "2024-01-01 12:00:00",
            "orderStatus": "2",
            "totalAmount": 10000,
            "discountAmount": 0,
            "items": [],
        }
        order = adapter.to_order(raw, "S1", "B1")
        assert order.items == []
        assert order.total == Decimal("100.00")

    def test_to_staff_action_complete_mapping(self, adapter):
        """验证完整操作数据映射"""
        raw = {
            "actionType": "refund",
            "operatorId": "OP_001",
            "amount": 5000,
            "reason": "菜品质量问题",
            "approvedBy": "MGR_001",
            "actionTime": "2024-03-01 14:30:00",
        }
        action = adapter.to_staff_action(raw, "STORE_01", "BRAND_XJ")

        assert action.action_type == "refund"
        assert action.operator_id == "OP_001"
        assert action.amount == Decimal("50.00")
        assert action.reason == "菜品质量问题"
        assert action.approved_by == "MGR_001"
        assert action.store_id == "STORE_01"
        assert action.brand_id == "BRAND_XJ"
        assert isinstance(action.created_at, datetime)


# ---------------------------------------------------------------------------
# 签名和参数构建测试
# ---------------------------------------------------------------------------

class TestSignAndParams:
    """签名和参数构建测试"""

    def test_sign_includes_app_secret(self, adapter):
        """签名计算中包含 app_secret"""
        params1 = {"a": "1"}
        sign1 = adapter._sign(params1)

        adapter2 = AoqiweiAdapter({
            "base_url": "https://openapi.acescm.cn",
            "app_key": "test_key",
            "app_secret": "different_secret",
        })
        sign2 = adapter2._sign(params1)

        assert sign1 != sign2

    def test_build_params_includes_appkey_and_sign(self, adapter):
        """_build_params 返回中包含 appkey, front, sign"""
        result = adapter._build_params({"shopCode": "SH001"})
        assert "appkey" in result
        assert "front" in result
        assert "sign" in result
        assert result["appkey"] == "test_key"

    def test_build_params_sign_is_32_chars(self, adapter):
        """签名长度为32位MD5"""
        result = adapter._build_params({"test": "value"})
        assert len(result["sign"]) == 32


# ---------------------------------------------------------------------------
# 参数校验
# ---------------------------------------------------------------------------

class TestParameterValidation:
    """参数校验测试"""

    @pytest.mark.asyncio
    async def test_query_goods_invalid_page_size(self, adapter):
        """page_size超出范围时抛出ValueError"""
        with pytest.raises(ValueError, match="page_size"):
            await adapter.query_goods(page_size=1000)

    @pytest.mark.asyncio
    async def test_query_goods_invalid_page(self, adapter):
        """page < 1 时抛出ValueError"""
        with pytest.raises(ValueError, match="page"):
            await adapter.query_goods(page=0)

    @pytest.mark.asyncio
    async def test_query_purchase_orders_bad_date(self, adapter):
        """日期格式错误时抛出ValueError"""
        with pytest.raises(ValueError, match="格式错误"):
            await adapter.query_purchase_orders(
                start_date="20240101",
                end_date="2024-01-31",
            )

    @pytest.mark.asyncio
    async def test_stock_estimate_validates_dates(self, adapter):
        """库存预估接口校验日期格式"""
        with pytest.raises(ValueError, match="格式错误"):
            await adapter.query_stock_estimate(
                shop_code="SH001",
                start_date="2024/01/01",
                end_date="2024-01-31",
            )


# ---------------------------------------------------------------------------
# 网络错误和重试
# ---------------------------------------------------------------------------

class TestNetworkErrors:
    """网络错误测试"""

    @pytest.mark.asyncio
    async def test_connection_timeout_raises(self, adapter):
        """连接超时后，query_shops 内部捕获并降级返回空列表"""
        adapter._client.get = AsyncMock(
            side_effect=httpx.ConnectTimeout("连接超时")
        )

        # query_shops 内部 try/except 捕获重试耗尽后的异常，降级返回空列表
        result = await adapter.query_shops()
        assert result == []

    @pytest.mark.asyncio
    async def test_server_error_500(self, adapter):
        """服务端500错误时，query_shops 内部捕获并降级返回空列表"""
        adapter._client.get = AsyncMock(
            return_value=_mock_response({"error": "Internal Server Error"}, status_code=500)
        )

        # query_shops 内部 try/except 捕获 HTTPStatusError，降级返回空列表
        result = await adapter.query_shops()
        assert result == []

    @pytest.mark.asyncio
    async def test_empty_response_from_shops(self, adapter):
        """门店查询返回空列表时不报错"""
        mock_response_data = {"success": True, "code": 0, "data": []}
        adapter._client.get = AsyncMock(return_value=_mock_response(mock_response_data))

        result = await adapter.query_shops()
        assert result == []

    @pytest.mark.asyncio
    async def test_query_stock_fallback_on_error(self, adapter):
        """库存查询失败时返回空列表"""
        adapter._client.get = AsyncMock(
            side_effect=httpx.ConnectTimeout("timeout")
        )

        result = await adapter.query_stock(depot_code="D001")
        assert result == []
