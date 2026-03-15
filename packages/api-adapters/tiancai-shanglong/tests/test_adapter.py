"""
天财商龙（吾享）适配器单元测试

覆盖重点：
  1. to_order()    — getserialdata billList 字段映射
  2. to_staff_action() — 操作记录映射
  3. fetch_orders_by_date / pull_daily_orders — 分页拉取逻辑
  4. get_serial_data 入参校验
  5. 初始化参数（新 OAuth2 凭据字段）
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


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def adapter():
    config = {
        "base_url": "https://cysms.wuuxiang.com",
        "appid": "test_appid",
        "accessid": "test_accessid",
        "center_id": "TEST_CENTER",
        "shop_id": "TEST_SHOP",
        "timeout": 30,
        "retry_times": 1,
    }
    return TiancaiShanglongAdapter(config)


@pytest.fixture
def raw_order():
    """
    模拟 getserialdata billList 单条记录（真实 API 字段名）。
    参考文档 #/46：bs_id / bs_code / state / settle_time /
               point_code / last_total / disc_total / orig_total /
               member_card_no / waiter_code / item[]
    """
    return {
        "bs_id": "TC_20240301_001",
        "bs_code": "TC20240301001",
        "point_code": "A03",
        "state": 1,                    # 1=已结账
        "last_total": 13600,           # 实收 136.00 元（分）
        "disc_total": 1000,            # 折扣 10.00 元（分）
        "orig_total": 14600,           # 折前 146.00 元（分）
        "settle_time": "2024-03-01 12:30:00",
        "open_time": "2024-03-01 11:00:00",
        "member_card_no": "MBR_001",
        "waiter_code": "STAFF_002",
        "item": [
            {
                "item_id": "item_001",
                "item_code": "DISH_001",
                "item_name": "红烧肉",
                "last_qty": 1,
                "orig_qty": 1,
                "last_price": 8800,
                "orig_price": 8800,
                "last_total": 8800,
            },
            {
                "item_id": "item_002",
                "item_code": "DISH_002",
                "item_name": "白米饭",
                "last_qty": 2,
                "orig_qty": 2,
                "last_price": 400,
                "orig_price": 400,
                "last_total": 800,
            },
        ],
    }


@pytest.fixture
def raw_staff_action():
    return {
        "action_type": "discount_apply",
        "operator_id": "STAFF_001",
        "amount": 2000,            # 20.00 元（分）
        "reason": "VIP 优惠",
        "approved_by": "MGR_001",
        "action_time": "2024-03-01 13:00:00",
    }


# ── 初始化测试 ─────────────────────────────────────────────────────────────────

class TestTiancaiShanglongAdapterInit:
    def test_init_success(self, adapter):
        assert adapter.appid == "test_appid"
        assert adapter.accessid == "test_accessid"
        assert adapter.center_id == "TEST_CENTER"
        assert adapter.shop_id == "TEST_SHOP"
        assert adapter.base_url == "https://cysms.wuuxiang.com"

    def test_init_missing_credentials_does_not_raise(self, monkeypatch):
        """缺少凭据时仅记录 warning，不抛异常（降级模式）"""
        monkeypatch.delenv("TIANCAI_APPID", raising=False)
        monkeypatch.delenv("TIANCAI_ACCESSID", raising=False)
        adapter = TiancaiShanglongAdapter({"base_url": "https://cysms.wuuxiang.com"})
        assert adapter is not None

    def test_default_base_url(self, monkeypatch):
        monkeypatch.delenv("TIANCAI_BASE_URL", raising=False)
        adapter = TiancaiShanglongAdapter({})
        assert "cysms.wuuxiang.com" in adapter.base_url

    def test_token_cache_initialized_empty(self, adapter):
        assert adapter._access_token == ""
        assert adapter._token_expires_at == 0.0


# ── to_order：字段映射 ─────────────────────────────────────────────────────────

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

    def test_maps_status_completed_when_state_1(self, adapter, raw_order):
        from schemas.restaurant_standard_schema import OrderStatus
        result = adapter.to_order(raw_order, "STORE_TC1", "BRAND_001")
        assert result.order_status == OrderStatus.COMPLETED

    def test_maps_status_pending_when_state_0(self, adapter, raw_order):
        from schemas.restaurant_standard_schema import OrderStatus
        raw_order["state"] = 0
        result = adapter.to_order(raw_order, "STORE_TC1", "BRAND_001")
        assert result.order_status == OrderStatus.PENDING

    def test_maps_status_special_state_as_completed(self, adapter, raw_order):
        """state 非 0/1 的特殊账单（押金/存酒等）按 COMPLETED 处理"""
        from schemas.restaurant_standard_schema import OrderStatus
        raw_order["state"] = 5
        result = adapter.to_order(raw_order, "STORE_TC1", "BRAND_001")
        assert result.order_status == OrderStatus.COMPLETED

    def test_converts_fen_to_yuan(self, adapter, raw_order):
        result = adapter.to_order(raw_order, "STORE_TC1", "BRAND_001")
        assert result.total == Decimal("136.00")
        assert result.discount == Decimal("10.00")

    def test_maps_table_number_from_point_code(self, adapter, raw_order):
        result = adapter.to_order(raw_order, "STORE_TC1", "BRAND_001")
        assert result.table_number == "A03"

    def test_maps_customer_id_from_member_card_no(self, adapter, raw_order):
        result = adapter.to_order(raw_order, "STORE_TC1", "BRAND_001")
        assert result.customer_id == "MBR_001"

    def test_maps_waiter_id_from_waiter_code(self, adapter, raw_order):
        result = adapter.to_order(raw_order, "STORE_TC1", "BRAND_001")
        assert result.waiter_id == "STAFF_002"

    def test_maps_items_count(self, adapter, raw_order):
        result = adapter.to_order(raw_order, "STORE_TC1", "BRAND_001")
        assert len(result.items) == 2

    def test_maps_item_fields(self, adapter, raw_order):
        result = adapter.to_order(raw_order, "STORE_TC1", "BRAND_001")
        item0 = result.items[0]
        assert item0.dish_id == "DISH_001"       # from item_code
        assert item0.dish_name == "红烧肉"        # from item_name
        assert item0.quantity == 1                # from last_qty
        assert item0.unit_price == Decimal("88.00")  # last_price=8800 分

    def test_maps_item_second(self, adapter, raw_order):
        result = adapter.to_order(raw_order, "STORE_TC1", "BRAND_001")
        item1 = result.items[1]
        assert item1.quantity == 2
        assert item1.unit_price == Decimal("4.00")   # last_price=400 分

    def test_datetime_from_settle_time(self, adapter, raw_order):
        result = adapter.to_order(raw_order, "STORE_TC1", "BRAND_001")
        assert isinstance(result.created_at, datetime)
        assert result.created_at.year == 2024
        assert result.created_at.month == 3

    def test_fallback_to_open_time_when_settle_missing(self, adapter, raw_order):
        del raw_order["settle_time"]
        result = adapter.to_order(raw_order, "STORE_TC1", "BRAND_001")
        assert isinstance(result.created_at, datetime)
        assert result.created_at.year == 2024

    def test_invalid_date_falls_back_to_utcnow(self, adapter, raw_order):
        raw_order["settle_time"] = "bad-date"
        raw_order.pop("open_time", None)
        result = adapter.to_order(raw_order, "STORE_TC1", "BRAND_001")
        assert isinstance(result.created_at, datetime)

    def test_order_type_is_dine_in(self, adapter, raw_order):
        from schemas.restaurant_standard_schema import OrderType
        result = adapter.to_order(raw_order, "STORE_TC1", "BRAND_001")
        assert result.order_type == OrderType.DINE_IN

    def test_empty_item_list(self, adapter, raw_order):
        raw_order["item"] = []
        result = adapter.to_order(raw_order, "STORE_TC1", "BRAND_001")
        assert result.items == []

    def test_subtotal_from_orig_total(self, adapter, raw_order):
        result = adapter.to_order(raw_order, "STORE_TC1", "BRAND_001")
        assert result.subtotal == Decimal("146.00")  # orig_total=14600


# ── to_staff_action ────────────────────────────────────────────────────────────

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


# ── get_serial_data 入参校验 ───────────────────────────────────────────────────

class TestGetSerialDataValidation:
    @pytest.mark.asyncio
    async def test_raises_if_no_date_params(self, adapter):
        with pytest.raises(ValueError, match="settle_date"):
            await adapter.get_serial_data(page_no=1, page_size=10)

    @pytest.mark.asyncio
    async def test_raises_if_page_size_exceeds_max(self, adapter):
        with pytest.raises(ValueError, match="page_size"):
            await adapter.get_serial_data(page_no=1, page_size=9999, settle_date="2024-01-01")

    @pytest.mark.asyncio
    async def test_raises_if_page_size_zero(self, adapter):
        with pytest.raises(ValueError, match="page_size"):
            await adapter.get_serial_data(page_no=1, page_size=0, settle_date="2024-01-01")

    @pytest.mark.asyncio
    async def test_accepts_begin_end_date(self, adapter):
        from unittest.mock import AsyncMock, patch
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"billList": [], "pageInfo": {"total": 0}}
            result = await adapter.get_serial_data(
                page_no=1, page_size=10,
                begin_date="2024-01-01 00:00:00",
                end_date="2024-01-01 23:59:59",
            )
        assert result == {"billList": [], "pageInfo": {"total": 0}}

    @pytest.mark.asyncio
    async def test_body_contains_center_and_shop_id(self, adapter):
        from unittest.mock import AsyncMock, patch
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"billList": [], "pageInfo": {"total": 0}}
            await adapter.get_serial_data(page_no=1, page_size=10, settle_date="2024-01-01")
        body = mock_req.call_args[0][1]
        assert body["centerId"] == "TEST_CENTER"
        assert body["shopId"] == "TEST_SHOP"
        assert body["pageNo"] == 1
        assert body["pageSize"] == 10
        assert body["settleDate"] == "2024-01-01"


# ── fetch_orders_by_date（mock _request） ────────────────────────────────────

class TestFetchOrdersByDate:
    """_request 已提取 data 层，mock 返回值应为 billList/pageInfo 结构"""

    @pytest.mark.asyncio
    async def test_returns_items_and_pagination(self, adapter):
        from unittest.mock import AsyncMock, patch

        mock_data = {
            "billList": [
                {"bs_id": "O001", "bs_code": "N001", "state": 1,
                 "last_total": 5000, "settle_time": "2026-03-04 12:00:00",
                 "point_code": "A01", "item": []},
            ],
            "pageInfo": {"total": 1},
        }
        with patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_data):
            result = await adapter.fetch_orders_by_date("2026-03-04", page=1)

        assert len(result["items"]) == 1
        assert result["total"] == 1
        assert result["has_more"] is False

    @pytest.mark.asyncio
    async def test_has_more_true_when_more_pages(self, adapter):
        from unittest.mock import AsyncMock, patch

        mock_data = {
            "billList": [
                {"bs_id": f"O{i:03d}", "state": 1, "last_total": 1000,
                 "settle_time": "2026-03-04 10:00:00", "item": []}
                for i in range(100)
            ],
            "pageInfo": {"total": 250},
        }
        with patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_data):
            result = await adapter.fetch_orders_by_date("2026-03-04", page=1, page_size=100)

        assert result["has_more"] is True

    @pytest.mark.asyncio
    async def test_empty_bill_list(self, adapter):
        from unittest.mock import AsyncMock, patch

        mock_data = {"billList": [], "pageInfo": {"total": 0}}
        with patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_data):
            result = await adapter.fetch_orders_by_date("2026-03-04")

        assert result["items"] == []
        assert result["total"] == 0
        assert result["has_more"] is False


# ── pull_daily_orders（自动分页） ─────────────────────────────────────────────

class TestPullDailyOrders:
    @pytest.mark.asyncio
    async def test_returns_order_schemas(self, adapter):
        from unittest.mock import patch

        page1_items = [
            {
                "bs_id": "O001", "bs_code": "N001", "state": 1,
                "last_total": 5000, "disc_total": 0, "orig_total": 5000,
                "settle_time": "2026-03-04 12:00:00",
                "point_code": "B02",
                "item": [
                    {"item_id": "I1", "item_code": "D1", "item_name": "红烧肉",
                     "last_qty": 1, "last_price": 5000, "last_total": 5000}
                ],
            }
        ]

        async def mock_fetch(date_str, page=1, page_size=100):
            if page == 1:
                return {"items": page1_items, "page": 1, "page_size": 100,
                        "total": 1, "has_more": False}
            return {"items": [], "page": page, "page_size": 100,
                    "total": 1, "has_more": False}

        with patch.object(adapter, "fetch_orders_by_date", side_effect=mock_fetch):
            orders = await adapter.pull_daily_orders("2026-03-04", "BRAND_001")

        assert len(orders) == 1
        assert orders[0].order_id == "O001"
        assert orders[0].total == Decimal("50.00")

    @pytest.mark.asyncio
    async def test_stops_after_last_page(self, adapter):
        from unittest.mock import patch

        call_count = 0

        async def mock_fetch(date_str, page=1, page_size=100):
            nonlocal call_count
            call_count += 1
            return {"items": [], "page": page, "page_size": 100,
                    "total": 0, "has_more": False}

        with patch.object(adapter, "fetch_orders_by_date", side_effect=mock_fetch):
            orders = await adapter.pull_daily_orders("2026-03-04", "BRAND_001")

        assert orders == []
        assert call_count == 1  # 只调用一次，第一页就没数据了

    @pytest.mark.asyncio
    async def test_bad_order_skipped_with_warning(self, adapter):
        """to_order 抛异常时，跳过该条记录继续处理其余"""
        from unittest.mock import patch

        page_items = [
            # 第一条：缺少 item_name（仍能处理）
            {"bs_id": "O001", "state": 1, "last_total": 1000,
             "settle_time": "2026-03-04 10:00:00", "item": []},
            # 第二条：bs_id 为 None，to_order 也应能容错
            {"bs_id": None, "state": 1, "last_total": 500,
             "settle_time": "2026-03-04 11:00:00", "item": []},
        ]

        async def mock_fetch(date_str, page=1, page_size=100):
            return {"items": page_items, "page": 1, "page_size": 100,
                    "total": 2, "has_more": False}

        with patch.object(adapter, "fetch_orders_by_date", side_effect=mock_fetch):
            orders = await adapter.pull_daily_orders("2026-03-04", "BRAND_001")

        # 两条都能映射（不报错）
        assert len(orders) == 2
