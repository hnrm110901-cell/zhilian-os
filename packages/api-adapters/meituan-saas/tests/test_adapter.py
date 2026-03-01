"""
美团SAAS适配器单元测试 - 重点覆盖 to_order() 和 to_staff_action()
"""
import os
import sys

# 必须在 import src 前设置环境变量（避免 pydantic-settings 校验失败）
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

# 确保 repo root 在 sys.path（用于 schema 导入）
_here = os.path.dirname(__file__)
_repo_root = os.path.abspath(os.path.join(_here, "../../../.."))
_gateway_src = os.path.join(_repo_root, "apps", "api-gateway", "src")
if _gateway_src not in sys.path:
    sys.path.insert(0, _gateway_src)

import pytest
from decimal import Decimal
from datetime import datetime

# 将 meituan-saas/src 加入 path
_adapter_src = os.path.abspath(os.path.join(_here, "../src"))
if _adapter_src not in sys.path:
    sys.path.insert(0, _adapter_src)

from adapter import MeituanSaasAdapter


@pytest.fixture
def adapter():
    config = {
        "base_url": "https://waimaiopen.meituan.com",
        "app_key": "test_app_key",
        "app_secret": "test_app_secret",
        "poi_id": "12345678",
        "timeout": 30,
    }
    return MeituanSaasAdapter(config)


@pytest.fixture
def raw_order():
    return {
        "order_id": "MT_20240301_001",
        "day_seq": "20240301001",
        "status": 4,
        "total_price": 8800,          # 88.00 元
        "discount_price": 500,         # 5.00 元
        "create_time": 1709280000,     # unix timestamp
        "caution": "不要辣",
        "user_id": "user_123",
        "food_list": [
            {
                "cart_id": "cart_001",
                "food_id": "FOOD_001",
                "food_name": "宫保鸡丁",
                "count": 2,
                "price": 3800,
            },
            {
                "cart_id": "cart_002",
                "food_id": "FOOD_002",
                "food_name": "米饭",
                "count": 2,
                "price": 600,
            },
        ],
    }


@pytest.fixture
def raw_staff_action():
    return {
        "action_type": "refund_apply",
        "operator_id": "OP_001",
        "amount": 1000,            # 10.00 元
        "reason": "顾客投诉",
        "approved_by": "MANAGER_001",
        "action_time": 1709280300,
    }


class TestMeituanSaasAdapterInit:
    def test_init_success(self, adapter):
        assert adapter.app_key == "test_app_key"
        assert adapter.app_secret == "test_app_secret"
        assert adapter.poi_id == "12345678"

    def test_init_missing_credentials(self):
        with pytest.raises(ValueError, match="app_key和app_secret不能为空"):
            MeituanSaasAdapter({"base_url": "https://waimaiopen.meituan.com"})


class TestToOrder:
    def test_maps_order_id(self, adapter, raw_order):
        result = adapter.to_order(raw_order, "STORE_MT1", "BRAND_001")
        assert result.order_id == "MT_20240301_001"

    def test_maps_order_number_from_day_seq(self, adapter, raw_order):
        result = adapter.to_order(raw_order, "STORE_MT1", "BRAND_001")
        assert result.order_number == "20240301001"

    def test_maps_store_and_brand(self, adapter, raw_order):
        result = adapter.to_order(raw_order, "STORE_MT1", "BRAND_001")
        assert result.store_id == "STORE_MT1"
        assert result.brand_id == "BRAND_001"

    def test_maps_status_completed(self, adapter, raw_order):
        from schemas.restaurant_standard_schema import OrderStatus
        result = adapter.to_order(raw_order, "STORE_MT1", "BRAND_001")
        assert result.order_status == OrderStatus.COMPLETED

    def test_maps_status_cancelled(self, adapter, raw_order):
        from schemas.restaurant_standard_schema import OrderStatus
        raw_order["status"] = 5
        result = adapter.to_order(raw_order, "STORE_MT1", "BRAND_001")
        assert result.order_status == OrderStatus.CANCELLED

    def test_converts_fen_to_yuan(self, adapter, raw_order):
        result = adapter.to_order(raw_order, "STORE_MT1", "BRAND_001")
        assert result.total == Decimal("88.00")
        assert result.discount == Decimal("5.00")

    def test_maps_items(self, adapter, raw_order):
        result = adapter.to_order(raw_order, "STORE_MT1", "BRAND_001")
        assert len(result.items) == 2
        assert result.items[0].dish_id == "FOOD_001"
        assert result.items[0].dish_name == "宫保鸡丁"
        assert result.items[0].quantity == 2
        assert result.items[0].unit_price == Decimal("38.00")

    def test_maps_notes(self, adapter, raw_order):
        result = adapter.to_order(raw_order, "STORE_MT1", "BRAND_001")
        assert result.notes == "不要辣"

    def test_unix_timestamp_parsed(self, adapter, raw_order):
        result = adapter.to_order(raw_order, "STORE_MT1", "BRAND_001")
        assert isinstance(result.created_at, datetime)

    def test_empty_food_list(self, adapter, raw_order):
        raw_order["food_list"] = []
        result = adapter.to_order(raw_order, "STORE_MT1", "BRAND_001")
        assert result.items == []

    def test_order_type_is_takeout(self, adapter, raw_order):
        from schemas.restaurant_standard_schema import OrderType
        result = adapter.to_order(raw_order, "STORE_MT1", "BRAND_001")
        assert result.order_type == OrderType.TAKEOUT


class TestToStaffAction:
    def test_maps_action_type(self, adapter, raw_staff_action):
        result = adapter.to_staff_action(raw_staff_action, "STORE_MT1", "BRAND_001")
        assert result.action_type == "refund_apply"

    def test_maps_store_and_brand(self, adapter, raw_staff_action):
        result = adapter.to_staff_action(raw_staff_action, "STORE_MT1", "BRAND_001")
        assert result.store_id == "STORE_MT1"
        assert result.brand_id == "BRAND_001"

    def test_maps_operator(self, adapter, raw_staff_action):
        result = adapter.to_staff_action(raw_staff_action, "STORE_MT1", "BRAND_001")
        assert result.operator_id == "OP_001"

    def test_converts_amount_fen_to_yuan(self, adapter, raw_staff_action):
        result = adapter.to_staff_action(raw_staff_action, "STORE_MT1", "BRAND_001")
        assert result.amount == Decimal("10.00")

    def test_maps_reason_and_approver(self, adapter, raw_staff_action):
        result = adapter.to_staff_action(raw_staff_action, "STORE_MT1", "BRAND_001")
        assert result.reason == "顾客投诉"
        assert result.approved_by == "MANAGER_001"

    def test_unix_timestamp_parsed(self, adapter, raw_staff_action):
        result = adapter.to_staff_action(raw_staff_action, "STORE_MT1", "BRAND_001")
        assert isinstance(result.created_at, datetime)

    def test_no_amount_is_none(self, adapter, raw_staff_action):
        del raw_staff_action["amount"]
        result = adapter.to_staff_action(raw_staff_action, "STORE_MT1", "BRAND_001")
        assert result.amount is None
