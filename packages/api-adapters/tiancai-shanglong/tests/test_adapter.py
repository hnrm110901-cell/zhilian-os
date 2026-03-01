"""
天财商龙适配器单元测试 - 重点覆盖 to_order() 和 to_staff_action()
"""
import os
import sys

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

_here = os.path.dirname(__file__)
_repo_root = os.path.abspath(os.path.join(_here, "../../../.."))
_gateway_src = os.path.join(_repo_root, "apps", "api-gateway", "src")
if _gateway_src not in sys.path:
    sys.path.insert(0, _gateway_src)

import pytest
from decimal import Decimal
from datetime import datetime

_adapter_src = os.path.abspath(os.path.join(_here, "../src"))
if _adapter_src not in sys.path:
    sys.path.insert(0, _adapter_src)

from adapter import TiancaiShanglongAdapter


@pytest.fixture
def adapter():
    config = {
        "base_url": "https://api.tiancai.com",
        "app_id": "test_app_id",
        "app_secret": "test_app_secret",
        "store_id": "TC_STORE_001",
        "timeout": 30,
    }
    return TiancaiShanglongAdapter(config)


@pytest.fixture
def raw_order():
    return {
        "order_id": "TC_20240301_001",
        "order_no": "TC20240301001",
        "store_id": "TC_STORE_001",
        "table_no": "A03",
        "status": 2,                   # 已支付
        "pay_amount": 13600,           # 136.00 元
        "discount_amount": 1000,       # 10.00 元
        "create_time": "2024-03-01 12:30:00",
        "member_id": "MBR_001",
        "waiter_id": "STAFF_002",
        "remark": "加辣",
        "dishes": [
            {
                "item_id": "item_001",
                "dish_id": "DISH_001",
                "dish_name": "红烧肉",
                "quantity": 1,
                "price": 8800,
            },
            {
                "item_id": "item_002",
                "dish_id": "DISH_002",
                "dish_name": "白米饭",
                "quantity": 2,
                "price": 400,
            },
        ],
    }


@pytest.fixture
def raw_staff_action():
    return {
        "action_type": "discount_apply",
        "operator_id": "STAFF_001",
        "amount": 2000,            # 20.00 元
        "reason": "VIP 优惠",
        "approved_by": "MGR_001",
        "create_time": "2024-03-01 13:00:00",
    }


class TestTiancaiShanglongAdapterInit:
    def test_init_success(self, adapter):
        assert adapter.app_id == "test_app_id"
        assert adapter.app_secret == "test_app_secret"
        assert adapter.store_id == "TC_STORE_001"

    def test_init_missing_credentials(self):
        with pytest.raises(ValueError, match="app_id和app_secret不能为空"):
            TiancaiShanglongAdapter({"base_url": "https://api.tiancai.com"})


class TestToOrder:
    def test_maps_order_id(self, adapter, raw_order):
        result = adapter.to_order(raw_order, "STORE_TC1", "BRAND_001")
        assert result.order_id == "TC_20240301_001"

    def test_maps_order_number(self, adapter, raw_order):
        result = adapter.to_order(raw_order, "STORE_TC1", "BRAND_001")
        assert result.order_number == "TC20240301001"

    def test_maps_store_and_brand(self, adapter, raw_order):
        result = adapter.to_order(raw_order, "STORE_TC1", "BRAND_001")
        assert result.store_id == "STORE_TC1"
        assert result.brand_id == "BRAND_001"

    def test_maps_status_completed(self, adapter, raw_order):
        from schemas.restaurant_standard_schema import OrderStatus
        result = adapter.to_order(raw_order, "STORE_TC1", "BRAND_001")
        assert result.order_status == OrderStatus.COMPLETED

    def test_maps_status_pending(self, adapter, raw_order):
        from schemas.restaurant_standard_schema import OrderStatus
        raw_order["status"] = 1
        result = adapter.to_order(raw_order, "STORE_TC1", "BRAND_001")
        assert result.order_status == OrderStatus.PENDING

    def test_maps_status_cancelled(self, adapter, raw_order):
        from schemas.restaurant_standard_schema import OrderStatus
        raw_order["status"] = 3
        result = adapter.to_order(raw_order, "STORE_TC1", "BRAND_001")
        assert result.order_status == OrderStatus.CANCELLED

    def test_converts_fen_to_yuan(self, adapter, raw_order):
        result = adapter.to_order(raw_order, "STORE_TC1", "BRAND_001")
        assert result.total == Decimal("136.00")
        assert result.discount == Decimal("10.00")

    def test_maps_table_number(self, adapter, raw_order):
        result = adapter.to_order(raw_order, "STORE_TC1", "BRAND_001")
        assert result.table_number == "A03"

    def test_maps_customer_id(self, adapter, raw_order):
        result = adapter.to_order(raw_order, "STORE_TC1", "BRAND_001")
        assert result.customer_id == "MBR_001"

    def test_maps_waiter_id(self, adapter, raw_order):
        result = adapter.to_order(raw_order, "STORE_TC1", "BRAND_001")
        assert result.waiter_id == "STAFF_002"

    def test_maps_items(self, adapter, raw_order):
        result = adapter.to_order(raw_order, "STORE_TC1", "BRAND_001")
        assert len(result.items) == 2
        assert result.items[0].dish_id == "DISH_001"
        assert result.items[0].dish_name == "红烧肉"
        assert result.items[0].quantity == 1
        assert result.items[0].unit_price == Decimal("88.00")
        assert result.items[1].quantity == 2
        assert result.items[1].unit_price == Decimal("4.00")

    def test_maps_notes(self, adapter, raw_order):
        result = adapter.to_order(raw_order, "STORE_TC1", "BRAND_001")
        assert result.notes == "加辣"

    def test_datetime_string_parsed(self, adapter, raw_order):
        result = adapter.to_order(raw_order, "STORE_TC1", "BRAND_001")
        assert isinstance(result.created_at, datetime)
        assert result.created_at.year == 2024

    def test_order_type_is_dine_in(self, adapter, raw_order):
        from schemas.restaurant_standard_schema import OrderType
        result = adapter.to_order(raw_order, "STORE_TC1", "BRAND_001")
        assert result.order_type == OrderType.DINE_IN

    def test_empty_dishes(self, adapter, raw_order):
        raw_order["dishes"] = []
        result = adapter.to_order(raw_order, "STORE_TC1", "BRAND_001")
        assert result.items == []


class TestToStaffAction:
    def test_maps_action_type(self, adapter, raw_staff_action):
        result = adapter.to_staff_action(raw_staff_action, "STORE_TC1", "BRAND_001")
        assert result.action_type == "discount_apply"

    def test_maps_store_and_brand(self, adapter, raw_staff_action):
        result = adapter.to_staff_action(raw_staff_action, "STORE_TC1", "BRAND_001")
        assert result.store_id == "STORE_TC1"
        assert result.brand_id == "BRAND_001"

    def test_maps_operator(self, adapter, raw_staff_action):
        result = adapter.to_staff_action(raw_staff_action, "STORE_TC1", "BRAND_001")
        assert result.operator_id == "STAFF_001"

    def test_converts_amount_fen_to_yuan(self, adapter, raw_staff_action):
        result = adapter.to_staff_action(raw_staff_action, "STORE_TC1", "BRAND_001")
        assert result.amount == Decimal("20.00")

    def test_maps_reason_and_approver(self, adapter, raw_staff_action):
        result = adapter.to_staff_action(raw_staff_action, "STORE_TC1", "BRAND_001")
        assert result.reason == "VIP 优惠"
        assert result.approved_by == "MGR_001"

    def test_datetime_string_parsed(self, adapter, raw_staff_action):
        result = adapter.to_staff_action(raw_staff_action, "STORE_TC1", "BRAND_001")
        assert isinstance(result.created_at, datetime)

    def test_no_amount_is_none(self, adapter, raw_staff_action):
        del raw_staff_action["amount"]
        result = adapter.to_staff_action(raw_staff_action, "STORE_TC1", "BRAND_001")
        assert result.amount is None
