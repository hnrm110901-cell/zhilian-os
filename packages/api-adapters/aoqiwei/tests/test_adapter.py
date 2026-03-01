"""
奥琦韦供应链适配器单元测试
"""
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
_repo_root = os.path.abspath(os.path.join(_here, "../../../.."))
_gateway_src = os.path.join(_repo_root, "apps", "api-gateway", "src")
if _gateway_src not in sys.path:
    sys.path.insert(0, _gateway_src)

import pytest
from datetime import datetime
from decimal import Decimal
from src.adapter import AoqiweiAdapter


class TestAoqiweiAdapterInit:
    """适配器初始化测试（供应链模式）"""

    def test_init_success(self):
        config = {
            "base_url": "https://openapi.acescm.cn",
            "app_key": "test_key",
            "app_secret": "test_secret",
            "timeout": 30,
            "retry_times": 3,
        }
        adapter = AoqiweiAdapter(config)
        assert adapter.base_url == "https://openapi.acescm.cn"
        assert adapter.app_key == "test_key"
        assert adapter.app_secret == "test_secret"
        assert adapter.timeout == 30
        assert adapter.retry_times == 3

    def test_init_with_env_fallback(self, monkeypatch):
        """未配置 credentials 时适配器仍可初始化（降级模式）"""
        monkeypatch.delenv("AOQIWEI_APP_KEY", raising=False)
        monkeypatch.delenv("AOQIWEI_APP_SECRET", raising=False)
        config = {"base_url": "https://openapi.acescm.cn"}
        # 应能初始化（降级模式），不抛异常
        adapter = AoqiweiAdapter(config)
        assert adapter is not None


# ---------------------------------------------------------------------------
# ARCH-001: to_order() / to_staff_action() 标准数据总线接口测试
# ---------------------------------------------------------------------------

@pytest.fixture
def supply_chain_adapter():
    """奥琦玮供应链适配器（真实实现）"""
    config = {
        "base_url": "https://openapi.acescm.cn",
        "app_key": "test_key",
        "app_secret": "test_secret",
    }
    return AoqiweiAdapter(config)


@pytest.fixture
def raw_pos_order():
    return {
        "orderId": "AQ20240101001",
        "orderNo": "AQ-2024-001",
        "orderDate": "2024-01-01 12:00:00",
        "orderStatus": "2",
        "shopCode": "SH001",
        "tableNo": "5",
        "memberId": "M001",
        "totalAmount": 18400,
        "discountAmount": 2000,
        "remark": "少辣",
        "waiterId": "W001",
        "items": [
            {"orderItemNo": "AQ20240101001_1", "goodCode": "G001", "goodName": "宫保鸡丁", "qty": 2, "price": 5800},
            {"orderItemNo": "AQ20240101001_2", "goodCode": "G002", "goodName": "麻婆豆腐", "qty": 1, "price": 4200},
        ],
    }


@pytest.fixture
def raw_pos_staff_action():
    return {
        "actionType": "discount_apply",
        "operatorId": "STAFF_001",
        "amount": 2000,
        "reason": "会员折扣",
        "approvedBy": "MGR_001",
        "actionTime": "2024-01-01 12:05:00",
    }


class TestToOrderMapsCorrectly:
    def test_order_id_mapped(self, supply_chain_adapter, raw_pos_order):
        order = supply_chain_adapter.to_order(raw_pos_order, store_id="STORE_A1", brand_id="BRAND_A")
        assert order.order_id == "AQ20240101001"

    def test_order_number_mapped(self, supply_chain_adapter, raw_pos_order):
        order = supply_chain_adapter.to_order(raw_pos_order, store_id="STORE_A1", brand_id="BRAND_A")
        assert order.order_number == "AQ-2024-001"

    def test_store_id_injected(self, supply_chain_adapter, raw_pos_order):
        order = supply_chain_adapter.to_order(raw_pos_order, store_id="STORE_A1", brand_id="BRAND_A")
        assert order.store_id == "STORE_A1"

    def test_brand_id_injected(self, supply_chain_adapter, raw_pos_order):
        order = supply_chain_adapter.to_order(raw_pos_order, store_id="STORE_A1", brand_id="BRAND_A")
        assert order.brand_id == "BRAND_A"

    def test_total_converted_from_fen(self, supply_chain_adapter, raw_pos_order):
        order = supply_chain_adapter.to_order(raw_pos_order, store_id="STORE_A1", brand_id="BRAND_A")
        assert order.total == Decimal("184.00")

    def test_discount_converted_from_fen(self, supply_chain_adapter, raw_pos_order):
        order = supply_chain_adapter.to_order(raw_pos_order, store_id="STORE_A1", brand_id="BRAND_A")
        assert order.discount == Decimal("20.00")

    def test_items_count(self, supply_chain_adapter, raw_pos_order):
        order = supply_chain_adapter.to_order(raw_pos_order, store_id="STORE_A1", brand_id="BRAND_A")
        assert len(order.items) == 2

    def test_item_name(self, supply_chain_adapter, raw_pos_order):
        order = supply_chain_adapter.to_order(raw_pos_order, store_id="STORE_A1", brand_id="BRAND_A")
        assert order.items[0].dish_name == "宫保鸡丁"

    def test_item_price_converted(self, supply_chain_adapter, raw_pos_order):
        order = supply_chain_adapter.to_order(raw_pos_order, store_id="STORE_A1", brand_id="BRAND_A")
        assert order.items[0].unit_price == Decimal("58.00")

    def test_invalid_date_falls_back(self, supply_chain_adapter, raw_pos_order):
        raw_pos_order["orderDate"] = "bad-date"
        order = supply_chain_adapter.to_order(raw_pos_order, store_id="STORE_A1", brand_id="BRAND_A")
        assert isinstance(order.created_at, datetime)


class TestToStaffActionMapsCorrectly:
    def test_action_type(self, supply_chain_adapter, raw_pos_staff_action):
        action = supply_chain_adapter.to_staff_action(raw_pos_staff_action, store_id="STORE_A1", brand_id="BRAND_A")
        assert action.action_type == "discount_apply"

    def test_store_brand_injected(self, supply_chain_adapter, raw_pos_staff_action):
        action = supply_chain_adapter.to_staff_action(raw_pos_staff_action, store_id="STORE_A1", brand_id="BRAND_A")
        assert action.store_id == "STORE_A1"
        assert action.brand_id == "BRAND_A"

    def test_amount_converted(self, supply_chain_adapter, raw_pos_staff_action):
        action = supply_chain_adapter.to_staff_action(raw_pos_staff_action, store_id="STORE_A1", brand_id="BRAND_A")
        assert action.amount == Decimal("20.00")

    def test_approved_by(self, supply_chain_adapter, raw_pos_staff_action):
        action = supply_chain_adapter.to_staff_action(raw_pos_staff_action, store_id="STORE_A1", brand_id="BRAND_A")
        assert action.approved_by == "MGR_001"


class TestSignRegression:
    """MD5 签名回归测试（原有功能不受影响）"""

    def test_sign_deterministic(self, supply_chain_adapter):
        params = {"appKey": "test_key", "timestamp": "1700000000000", "shopCode": "SH001"}
        assert supply_chain_adapter._sign(params) == supply_chain_adapter._sign(params)

    def test_sign_length(self, supply_chain_adapter):
        params = {"appKey": "k", "timestamp": "1"}
        assert len(supply_chain_adapter._sign(params)) == 32

    def test_sign_excludes_empty(self, supply_chain_adapter):
        p1 = {"a": "1", "b": None, "d": "2"}
        p2 = {"a": "1", "d": "2"}
        assert supply_chain_adapter._sign(p1) == supply_chain_adapter._sign(p2)

