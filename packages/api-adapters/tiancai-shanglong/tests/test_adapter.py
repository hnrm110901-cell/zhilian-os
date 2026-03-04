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


# ── to_dish ───────────────────────────────────────────────────────────────────

class TestToDish:
    def _raw(self):
        return {
            "dish_id":       "D001",
            "dish_name":     "红油火锅",
            "category_name": "主锅",
            "price":         8800,    # 88.00 元（分）
            "cost":          2800,    # 28.00 元（分）
            "unit":          "份",
            "status":        1,
        }

    def test_basic_fields(self, adapter):
        result = adapter.to_dish(self._raw())
        assert result["pos_dish_id"] == "D001"
        assert result["name"] == "红油火锅"
        assert result["category"] == "主锅"

    def test_price_fen_to_yuan(self, adapter):
        result = adapter.to_dish(self._raw())
        assert result["price_yuan"] == 88.0

    def test_cost_fen_to_yuan(self, adapter):
        result = adapter.to_dish(self._raw())
        assert result["cost_yuan"] == 28.0
        assert result["cost_fen"] == 2800

    def test_is_available_true_when_status_1(self, adapter):
        result = adapter.to_dish(self._raw())
        assert result["is_available"] is True

    def test_is_available_false_when_status_0(self, adapter):
        raw = self._raw()
        raw["status"] = 0
        result = adapter.to_dish(raw)
        assert result["is_available"] is False

    def test_default_unit_is_fen(self, adapter):
        raw = self._raw()
        del raw["unit"]
        result = adapter.to_dish(raw)
        assert result["unit"] == "份"

    def test_missing_price_is_zero(self, adapter):
        raw = self._raw()
        del raw["price"]
        result = adapter.to_dish(raw)
        assert result["price_yuan"] == 0.0


# ── to_inventory_item ─────────────────────────────────────────────────────────

class TestToInventoryItem:
    def _raw(self):
        return {
            "material_id":   "MAT-001",
            "material_name": "鸡腿",
            "category":      "meat",
            "unit":          "kg",
            "current_qty":   20.5,
            "min_qty":       10.0,
            "unit_cost":     1500,    # 15元/kg（分）
            "supplier_name": "优鲜供应商",
        }

    def test_basic_fields(self, adapter):
        result = adapter.to_inventory_item(self._raw())
        assert result["pos_material_id"] == "MAT-001"
        assert result["name"] == "鸡腿"
        assert result["category"] == "meat"
        assert result["unit"] == "kg"

    def test_unit_cost_fen_large_treated_as_fen(self, adapter):
        result = adapter.to_inventory_item(self._raw())
        assert result["unit_cost_fen"] == 1500
        assert result["unit_cost_yuan"] == 15.0

    def test_unit_cost_small_treated_as_yuan(self, adapter):
        raw = self._raw()
        raw["unit_cost"] = 15.0     # 小于1000，推断为元
        result = adapter.to_inventory_item(raw)
        assert result["unit_cost_fen"] == 1500
        assert result["unit_cost_yuan"] == 15.0

    def test_quantities_mapped(self, adapter):
        result = adapter.to_inventory_item(self._raw())
        assert result["current_quantity"] == 20.5
        assert result["min_quantity"] == 10.0

    def test_supplier_name(self, adapter):
        result = adapter.to_inventory_item(self._raw())
        assert result["supplier_name"] == "优鲜供应商"


# ── fetch_orders_by_date（mock HTTP） ─────────────────────────────────────────

class TestFetchOrdersByDate:
    @pytest.mark.asyncio
    async def test_returns_items_and_pagination(self, adapter):
        from unittest.mock import AsyncMock, patch

        mock_response = {
            "code": 0,
            "data": {
                "list": [
                    {"order_id": "O001", "order_no": "N001", "status": 2,
                     "pay_amount": 5000, "create_time": "2026-03-04 12:00:00",
                     "table_no": "A01", "dishes": []},
                ],
                "total": 1,
            },
        }
        with patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_response):
            result = await adapter.fetch_orders_by_date("2026-03-04", page=1)

        assert len(result["items"]) == 1
        assert result["total"] == 1
        assert result["has_more"] is False

    @pytest.mark.asyncio
    async def test_has_more_true_when_more_pages(self, adapter):
        from unittest.mock import AsyncMock, patch

        mock_response = {
            "code": 0,
            "data": {
                "list": [{"order_id": f"O{i:03d}", "status": 2,
                          "pay_amount": 1000, "create_time": "2026-03-04 10:00:00",
                          "dishes": []} for i in range(100)],
                "total": 250,
            },
        }
        with patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_response):
            result = await adapter.fetch_orders_by_date("2026-03-04", page=1, page_size=100)

        assert result["has_more"] is True


# ── pull_daily_orders（自动分页） ─────────────────────────────────────────────

class TestPullDailyOrders:
    @pytest.mark.asyncio
    async def test_returns_order_schemas(self, adapter):
        from unittest.mock import AsyncMock, patch

        page1_items = [
            {"order_id": "O001", "order_no": "N001", "status": 2,
             "pay_amount": 5000, "discount_amount": 0,
             "create_time": "2026-03-04 12:00:00",
             "table_no": "B02", "dishes": [
                 {"item_id": "I1", "dish_id": "D1", "dish_name": "红烧肉",
                  "quantity": 1, "price": 5000}
             ]}
        ]

        async def mock_fetch(date_str, page=1, page_size=100, status=None):
            if page == 1:
                return {"items": page1_items, "page": 1, "page_size": 100,
                        "total": 1, "has_more": False}
            return {"items": [], "page": page, "page_size": 100,
                    "total": 1, "has_more": False}

        with patch.object(adapter, "fetch_orders_by_date", side_effect=mock_fetch):
            orders = await adapter.pull_daily_orders("2026-03-04", "BRAND_001")

        assert len(orders) == 1
        assert orders[0].order_id == "O001"
        from decimal import Decimal
        assert orders[0].total == Decimal("50.00")

    @pytest.mark.asyncio
    async def test_stops_after_last_page(self, adapter):
        from unittest.mock import AsyncMock, patch

        call_count = 0

        async def mock_fetch(date_str, page=1, page_size=100, status=None):
            nonlocal call_count
            call_count += 1
            return {"items": [], "page": page, "page_size": 100,
                    "total": 0, "has_more": False}

        with patch.object(adapter, "fetch_orders_by_date", side_effect=mock_fetch):
            orders = await adapter.pull_daily_orders("2026-03-04", "BRAND_001")

        assert orders == []
        assert call_count == 1   # 只调用一次，第一页就没数据了


# ── fetch_dishes（mock HTTP） ─────────────────────────────────────────────────

class TestFetchDishes:
    @pytest.mark.asyncio
    async def test_normalizes_dish_items(self, adapter):
        from unittest.mock import AsyncMock, patch

        mock_response = {
            "code": 0,
            "data": {
                "list": [{"dish_id": "D001", "dish_name": "宫保鸡丁",
                          "price": 4800, "cost": 1200, "status": 1}],
                "total": 1,
            },
        }
        with patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_response):
            result = await adapter.fetch_dishes(page=1)

        assert len(result["items"]) == 1
        assert result["items"][0]["pos_dish_id"] == "D001"
        assert result["items"][0]["price_yuan"] == 48.0


# ── _normalize_store ──────────────────────────────────────────────────────────

class TestNormalizeStore:
    def test_basic_store_fields(self, adapter):
        raw = {
            "store_id":   "TC_001",
            "store_name": "北京旗舰店",
            "address":    "北京市朝阳区xxx",
            "phone":      "010-12345678",
            "open_time":  "10:00",
            "close_time": "22:00",
            "status":     1,
        }
        result = adapter._normalize_store(raw)
        assert result["pos_store_id"] == "TC_001"
        assert result["name"] == "北京旗舰店"
        assert result["is_active"] is True

    def test_inactive_store(self, adapter):
        result = adapter._normalize_store({"status": 0})
        assert result["is_active"] is False
