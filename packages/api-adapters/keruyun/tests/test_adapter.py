"""
客如云适配器单元测试 - 重点覆盖 to_order() 和 to_staff_action()
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

from adapter import KeruyunAdapter


@pytest.fixture
def adapter():
    config = {
        "base_url": "https://api.keruyun.com",
        "client_id": "test_client_id",
        "client_secret": "test_client_secret",
        "store_id": "KR_STORE_001",
        "timeout": 30,
    }
    return KeruyunAdapter(config)


@pytest.fixture
def raw_order():
    return {
        "order_id": "KR_20240301_001",
        "order_sn": "KR20240301001",
        "store_id": "KR_STORE_001",
        "table_id": "T05",
        "table_name": "5号桌",
        "status": 3,                    # 已结账
        "total_amount": 24600,          # 246.00 元
        "discount_amount": 2400,        # 24.00 元
        "create_time": "2024-03-01 18:00:00",
        "member_id": "MBR_KR_001",
        "waiter_id": "WAITER_KR_002",
        "note": "少辣",
        "items": [
            {
                "item_id": "item_001",
                "sku_id": "SKU_001",
                "sku_name": "夫妻肺片",
                "qty": 1,
                "unit_price": 15800,
            },
            {
                "item_id": "item_002",
                "sku_id": "SKU_002",
                "sku_name": "米饭",
                "qty": 2,
                "unit_price": 300,
            },
        ],
    }


@pytest.fixture
def raw_staff_action():
    return {
        "action_type": "void_item",
        "staff_id": "STAFF_KR_001",
        "amount": 3000,             # 30.00 元
        "reason": "顾客不满意",
        "approved_by": "MGR_KR_001",
        "operate_time": "2024-03-01 18:30:00",
    }


class TestKeruyunAdapterInit:
    def test_init_success(self, adapter):
        assert adapter.client_id == "test_client_id"
        assert adapter.client_secret == "test_client_secret"
        assert adapter.store_id == "KR_STORE_001"

    def test_init_missing_credentials(self):
        with pytest.raises(ValueError, match="client_id和client_secret不能为空"):
            KeruyunAdapter({"base_url": "https://api.keruyun.com"})


class TestToOrder:
    def test_maps_order_id(self, adapter, raw_order):
        result = adapter.to_order(raw_order, "STORE_KR1", "BRAND_001")
        assert result.order_id == "KR_20240301_001"

    def test_maps_order_number(self, adapter, raw_order):
        result = adapter.to_order(raw_order, "STORE_KR1", "BRAND_001")
        assert result.order_number == "KR20240301001"

    def test_maps_store_and_brand(self, adapter, raw_order):
        result = adapter.to_order(raw_order, "STORE_KR1", "BRAND_001")
        assert result.store_id == "STORE_KR1"
        assert result.brand_id == "BRAND_001"

    def test_maps_status_completed(self, adapter, raw_order):
        from schemas.restaurant_standard_schema import OrderStatus
        result = adapter.to_order(raw_order, "STORE_KR1", "BRAND_001")
        assert result.order_status == OrderStatus.COMPLETED

    def test_maps_status_pending(self, adapter, raw_order):
        from schemas.restaurant_standard_schema import OrderStatus
        raw_order["status"] = 1
        result = adapter.to_order(raw_order, "STORE_KR1", "BRAND_001")
        assert result.order_status == OrderStatus.PENDING

    def test_maps_status_confirmed(self, adapter, raw_order):
        from schemas.restaurant_standard_schema import OrderStatus
        raw_order["status"] = 2
        result = adapter.to_order(raw_order, "STORE_KR1", "BRAND_001")
        assert result.order_status == OrderStatus.CONFIRMED

    def test_maps_status_cancelled(self, adapter, raw_order):
        from schemas.restaurant_standard_schema import OrderStatus
        raw_order["status"] = 4
        result = adapter.to_order(raw_order, "STORE_KR1", "BRAND_001")
        assert result.order_status == OrderStatus.CANCELLED

    def test_converts_fen_to_yuan(self, adapter, raw_order):
        result = adapter.to_order(raw_order, "STORE_KR1", "BRAND_001")
        assert result.total == Decimal("246.00")
        assert result.discount == Decimal("24.00")

    def test_maps_table_name(self, adapter, raw_order):
        result = adapter.to_order(raw_order, "STORE_KR1", "BRAND_001")
        assert result.table_number == "5号桌"

    def test_maps_table_id_as_fallback(self, adapter, raw_order):
        del raw_order["table_name"]
        result = adapter.to_order(raw_order, "STORE_KR1", "BRAND_001")
        assert result.table_number == "T05"

    def test_maps_customer_id(self, adapter, raw_order):
        result = adapter.to_order(raw_order, "STORE_KR1", "BRAND_001")
        assert result.customer_id == "MBR_KR_001"

    def test_maps_waiter_id(self, adapter, raw_order):
        result = adapter.to_order(raw_order, "STORE_KR1", "BRAND_001")
        assert result.waiter_id == "WAITER_KR_002"

    def test_maps_items(self, adapter, raw_order):
        result = adapter.to_order(raw_order, "STORE_KR1", "BRAND_001")
        assert len(result.items) == 2
        assert result.items[0].dish_id == "SKU_001"
        assert result.items[0].dish_name == "夫妻肺片"
        assert result.items[0].quantity == 1
        assert result.items[0].unit_price == Decimal("158.00")
        assert result.items[1].quantity == 2
        assert result.items[1].unit_price == Decimal("3.00")

    def test_maps_notes(self, adapter, raw_order):
        result = adapter.to_order(raw_order, "STORE_KR1", "BRAND_001")
        assert result.notes == "少辣"

    def test_datetime_string_parsed(self, adapter, raw_order):
        result = adapter.to_order(raw_order, "STORE_KR1", "BRAND_001")
        assert isinstance(result.created_at, datetime)
        assert result.created_at.year == 2024

    def test_order_type_is_dine_in(self, adapter, raw_order):
        from schemas.restaurant_standard_schema import OrderType
        result = adapter.to_order(raw_order, "STORE_KR1", "BRAND_001")
        assert result.order_type == OrderType.DINE_IN

    def test_empty_items(self, adapter, raw_order):
        raw_order["items"] = []
        result = adapter.to_order(raw_order, "STORE_KR1", "BRAND_001")
        assert result.items == []

    def test_unix_timestamp_parsed(self, adapter, raw_order):
        raw_order["create_time"] = 1709280000
        result = adapter.to_order(raw_order, "STORE_KR1", "BRAND_001")
        assert isinstance(result.created_at, datetime)


class TestToStaffAction:
    def test_maps_action_type(self, adapter, raw_staff_action):
        result = adapter.to_staff_action(raw_staff_action, "STORE_KR1", "BRAND_001")
        assert result.action_type == "void_item"

    def test_maps_store_and_brand(self, adapter, raw_staff_action):
        result = adapter.to_staff_action(raw_staff_action, "STORE_KR1", "BRAND_001")
        assert result.store_id == "STORE_KR1"
        assert result.brand_id == "BRAND_001"

    def test_maps_operator_from_staff_id(self, adapter, raw_staff_action):
        result = adapter.to_staff_action(raw_staff_action, "STORE_KR1", "BRAND_001")
        assert result.operator_id == "STAFF_KR_001"

    def test_converts_amount_fen_to_yuan(self, adapter, raw_staff_action):
        result = adapter.to_staff_action(raw_staff_action, "STORE_KR1", "BRAND_001")
        assert result.amount == Decimal("30.00")

    def test_maps_reason_and_approver(self, adapter, raw_staff_action):
        result = adapter.to_staff_action(raw_staff_action, "STORE_KR1", "BRAND_001")
        assert result.reason == "顾客不满意"
        assert result.approved_by == "MGR_KR_001"

    def test_datetime_string_parsed(self, adapter, raw_staff_action):
        result = adapter.to_staff_action(raw_staff_action, "STORE_KR1", "BRAND_001")
        assert isinstance(result.created_at, datetime)

    def test_no_amount_is_none(self, adapter, raw_staff_action):
        del raw_staff_action["amount"]
        result = adapter.to_staff_action(raw_staff_action, "STORE_KR1", "BRAND_001")
        assert result.amount is None

    def test_unix_timestamp_parsed(self, adapter, raw_staff_action):
        raw_staff_action["operate_time"] = 1709282200
        result = adapter.to_staff_action(raw_staff_action, "STORE_KR1", "BRAND_001")
        assert isinstance(result.created_at, datetime)
