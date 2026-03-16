"""
品智 POS Webhook — 归一化 + 签名验证测试
"""
import hashlib
from collections import OrderedDict
from unittest.mock import patch

import pytest

from src.api.pos_webhook import (
    _normalize_pinzhi,
    _verify_pinzhi_signature,
)


# ── 测试数据 ──


def _make_pinzhi_order(
    bill_id="PZ20260316001",
    bill_no="B001",
    table_no="A3",
    bill_status=1,
    dish_price_total=10400,
    special_offer_price=500,
    real_price=9900,
    open_time="2026-03-16T11:30:00",
    pay_time="2026-03-16T12:05:00",
):
    """构造品智原始订单 payload"""
    return {
        "billId": bill_id,
        "billNo": bill_no,
        "tableNo": table_no,
        "billStatus": bill_status,
        "orderSource": 1,
        "dishPriceTotal": dish_price_total,
        "specialOfferPrice": special_offer_price,
        "realPrice": real_price,
        "openTime": open_time,
        "payTime": pay_time,
        "vipCard": "VIP_TEST_001",
        "openOrderUser": "张三",
        "cashiers": "李四",
        "remark": "少辣",
        "dishList": [
            {
                "dishId": "D001",
                "dishName": "宫保鸡丁",
                "dishPrice": 3800,
                "dishNum": 2,
            },
            {
                "dishId": "D002",
                "dishName": "麻婆豆腐",
                "dishPrice": 2800,
                "dishNum": 1,
            },
        ],
    }


# ── 归一化测试 ──


class TestNormalizePinzhi:

    def test_basic_fields(self):
        """基本字段映射正确"""
        raw = _make_pinzhi_order()
        payload = _normalize_pinzhi(raw)

        assert payload.source == "pinzhi"
        assert payload.external_order_id == "PZ20260316001"
        assert payload.table_number == "A3"
        assert payload.customer_name == "VIP_TEST_001"
        assert payload.notes == "少辣"

    def test_amounts_in_fen(self):
        """金额直接透传（品智单位：分）"""
        raw = _make_pinzhi_order(
            dish_price_total=10400,
            special_offer_price=500,
            real_price=9900,
        )
        payload = _normalize_pinzhi(raw)

        assert payload.total_amount == 10400
        assert payload.discount_amount == 500
        assert payload.final_amount == 9900

    def test_bill_status_completed(self):
        """billStatus=1 → completed"""
        raw = _make_pinzhi_order(bill_status=1)
        payload = _normalize_pinzhi(raw)
        assert payload.status == "completed"

    def test_bill_status_pending(self):
        """billStatus=0 → pending"""
        raw = _make_pinzhi_order(bill_status=0)
        payload = _normalize_pinzhi(raw)
        assert payload.status == "pending"

    def test_bill_status_cancelled(self):
        """billStatus=2 → cancelled"""
        raw = _make_pinzhi_order(bill_status=2)
        payload = _normalize_pinzhi(raw)
        assert payload.status == "cancelled"

    def test_dish_list_items(self):
        """菜品列表正确映射"""
        raw = _make_pinzhi_order()
        payload = _normalize_pinzhi(raw)

        assert len(payload.items) == 2

        item0 = payload.items[0]
        assert item0.item_id == "D001"
        assert item0.item_name == "宫保鸡丁"
        assert item0.quantity == 2
        assert item0.unit_price == 3800
        assert item0.subtotal == 7600  # 3800 * 2

        item1 = payload.items[1]
        assert item1.item_id == "D002"
        assert item1.item_name == "麻婆豆腐"
        assert item1.quantity == 1
        assert item1.unit_price == 2800
        assert item1.subtotal == 2800

    def test_empty_dish_list(self):
        """无菜品列表时 items 为空"""
        raw = _make_pinzhi_order()
        raw.pop("dishList")
        payload = _normalize_pinzhi(raw)
        assert payload.items == []

    def test_order_time_uses_pay_time(self):
        """order_time 优先用 payTime"""
        raw = _make_pinzhi_order(
            open_time="2026-03-16T11:30:00",
            pay_time="2026-03-16T12:05:00",
        )
        payload = _normalize_pinzhi(raw)
        assert payload.order_time == "2026-03-16T12:05:00"

    def test_order_time_fallback_to_open_time(self):
        """payTime 不存在时降级到 openTime"""
        raw = _make_pinzhi_order()
        raw.pop("payTime")
        payload = _normalize_pinzhi(raw)
        assert payload.order_time == "2026-03-16T11:30:00"

    def test_raw_preserved(self):
        """原始 payload 存档"""
        raw = _make_pinzhi_order()
        payload = _normalize_pinzhi(raw)
        assert payload.raw == raw

    def test_fallback_bill_no_as_external_id(self):
        """billId 不存在时用 billNo"""
        raw = _make_pinzhi_order()
        raw.pop("billId")
        payload = _normalize_pinzhi(raw)
        assert payload.external_order_id == "B001"

    def test_alternative_dish_field_names(self):
        """兼容 price/quantity 替代字段名"""
        raw = _make_pinzhi_order()
        raw["dishList"] = [
            {
                "dishId": "D003",
                "dishName": "水煮鱼",
                "price": 6800,
                "quantity": 1,
            },
        ]
        payload = _normalize_pinzhi(raw)
        assert payload.items[0].unit_price == 6800
        assert payload.items[0].quantity == 1
        assert payload.items[0].subtotal == 6800


# ── 签名验证测试 ──


def _generate_test_sign(token: str, params: dict) -> str:
    """复刻品智签名算法用于测试"""
    filtered = {
        k: v
        for k, v in params.items()
        if k not in ("sign", "pageIndex", "pageSize") and v is not None
    }
    ordered = OrderedDict(sorted(filtered.items()))
    param_str = "&".join(f"{k}={v}" for k, v in ordered.items())
    param_str += f"&token={token}"
    return hashlib.md5(param_str.encode("utf-8")).hexdigest()


class TestVerifyPinzhiSignature:

    def test_no_token_configured_skips(self):
        """未配置 PINZHI_WEBHOOK_TOKEN 时跳过验证"""
        with patch("src.api.pos_webhook.PINZHI_WEBHOOK_TOKEN", ""):
            assert _verify_pinzhi_signature({"billId": "123"}) is True

    def test_valid_signature(self):
        """正确签名通过验证"""
        token = "test_token_abc"
        raw = {"billId": "PZ001", "billStatus": 1, "realPrice": 9900}
        raw["sign"] = _generate_test_sign(token, raw)

        with patch("src.api.pos_webhook.PINZHI_WEBHOOK_TOKEN", token):
            assert _verify_pinzhi_signature(raw) is True

    def test_invalid_signature(self):
        """错误签名拒绝"""
        token = "test_token_abc"
        raw = {"billId": "PZ001", "sign": "wrong_sign_value"}

        with patch("src.api.pos_webhook.PINZHI_WEBHOOK_TOKEN", token):
            assert _verify_pinzhi_signature(raw) is False

    def test_missing_sign_field(self):
        """请求缺少 sign 字段时拒绝"""
        with patch("src.api.pos_webhook.PINZHI_WEBHOOK_TOKEN", "some_token"):
            assert _verify_pinzhi_signature({"billId": "PZ001"}) is False
