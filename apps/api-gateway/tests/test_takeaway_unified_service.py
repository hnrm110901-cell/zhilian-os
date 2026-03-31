"""
外卖统一接单服务测试

覆盖：多平台订单聚合、接单后库存扣减、自动接单配置更新、统计数据汇总
"""

import os
import sys

# 确保测试环境变量在导入 src.* 之前设置
for _k, _v in {
    "APP_ENV": "test",
    "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
    "REDIS_URL": "redis://localhost:6379/0",
    "SECRET_KEY": "test-secret-key",
    "JWT_SECRET": "test-jwt-secret",
}.items():
    os.environ.setdefault(_k, _v)

from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
import pytest


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def store_id() -> str:
    return "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def service():
    """创建服务实例（不依赖真实DB或平台API）"""
    from src.services.takeaway_unified_service import TakeawayUnifiedService
    return TakeawayUnifiedService()


# ── Test 1: 标准化美团订单格式 ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_normalize_meituan_order(service):
    """美团原始订单应被正确标准化为统一格式"""
    raw = {
        "orderId": "MT001",
        "status": 1,
        "totalPrice": 8800,  # 分
        "detail": [
            {"skuId": "S1", "skuName": "红烧肉", "quantity": 2, "price": 3000},
        ],
        "recipientAddress": "湖南省长沙市xx区xx路1号",
        "estimatedDeliveryTime": 40,
        "ctime": "2026-03-31T12:00:00",
        "remark": "少辣",
    }
    result = await service._normalize_meituan_order(raw)

    assert result["platform"] == "meituan"
    assert result["platform_order_id"] == "MT001"
    assert result["unified_id"].startswith("mt_")
    assert result["status"] == "pending"
    assert result["amount_yuan"] == 88.0
    assert len(result["items"]) == 1
    assert result["items"][0]["name"] == "红烧肉"
    assert result["items"][0]["quantity"] == 2
    assert result["customer_address"] == "湖南省长沙市xx区xx路1号"
    assert result["estimated_delivery_min"] == 40


# ── Test 2: 标准化饿了么订单格式 ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_normalize_eleme_order(service):
    """饿了么原始订单应被正确标准化"""
    raw = {
        "id": "ELE002",
        "statusCode": "NEW",
        "totalPrice": 56.5,
        "groups": [
            {
                "items": [
                    {"id": "D1", "name": "剁椒鱼头", "quantity": 1, "price": 56.5},
                ]
            }
        ],
        "address": {"text": "长沙市开福区xx街道"},
        "deliveryTime": 35,
        "createdAt": "2026-03-31T12:05:00",
        "description": "不要葱",
    }
    result = await service._normalize_eleme_order(raw)

    assert result["platform"] == "eleme"
    assert result["platform_order_id"] == "ELE002"
    assert result["unified_id"].startswith("ele_")
    assert result["status"] == "pending"
    assert result["amount_yuan"] == 56.5
    assert result["items"][0]["name"] == "剁椒鱼头"
    assert result["customer_address"] == "长沙市开福区xx街道"


# ── Test 3: 标准化抖音订单格式 ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_normalize_douyin_order(service):
    """抖音原始订单应被正确标准化"""
    raw = {
        "order_id": "DY003",
        "order_status": "1",
        "amount": 12800,  # 分
        "sku_list": [
            {"sku_id": "K1", "sku_name": "酸辣粉", "num": 3, "sale_price": 1800},
        ],
        "address": {"detail": "长沙市雨花区xx小区"},
        "create_time": "2026-03-31T12:10:00",
    }
    result = await service._normalize_douyin_order(raw)

    assert result["platform"] == "douyin"
    assert result["platform_order_id"] == "DY003"
    assert result["unified_id"].startswith("dy_")
    assert result["status"] == "pending"
    assert result["amount_yuan"] == 128.0
    assert result["items"][0]["name"] == "酸辣粉"
    assert result["items"][0]["quantity"] == 3


# ── Test 4: 多平台订单聚合并按时间排序 ────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_pending_orders_aggregates_all_platforms(service, store_id):
    """get_pending_orders 应聚合三平台订单并按时间升序排列"""
    mt_order = {
        "platform": "meituan",
        "platform_order_id": "MT001",
        "unified_id": "mt_MT001",
        "status": "pending",
        "amount_yuan": 88.0,
        "items": [],
        "customer_address": "",
        "estimated_delivery_min": 30,
        "created_at": "2026-03-31T12:05:00",
        "remark": "",
        "platform_raw": {},
    }
    ele_order = {
        "platform": "eleme",
        "platform_order_id": "ELE002",
        "unified_id": "ele_ELE002",
        "status": "pending",
        "amount_yuan": 56.5,
        "items": [],
        "customer_address": "",
        "estimated_delivery_min": 35,
        "created_at": "2026-03-31T12:01:00",
        "remark": "",
        "platform_raw": {},
    }

    async def mock_fetch(sid, platform):
        if platform == "meituan":
            return [mt_order]
        if platform == "eleme":
            return [ele_order]
        return []

    service._fetch_platform_pending_orders = mock_fetch

    orders = await service.get_pending_orders(store_id)

    assert len(orders) == 2
    # 饿了么订单时间更早，应排在第一位
    assert orders[0]["platform"] == "eleme"
    assert orders[1]["platform"] == "meituan"


# ── Test 5: 平台拉取失败不阻断其他平台 ───────────────────────────────────────


@pytest.mark.asyncio
async def test_get_pending_orders_partial_failure(service, store_id):
    """某平台拉取失败时，其他平台数据仍然返回"""
    async def mock_fetch(sid, platform):
        if platform == "meituan":
            raise RuntimeError("美团API超时")
        if platform == "eleme":
            return [{"platform": "eleme", "platform_order_id": "E1", "created_at": "2026-03-31T12:00:00"}]
        return []

    service._fetch_platform_pending_orders = mock_fetch

    orders = await service.get_pending_orders(store_id)

    # 饿了么的订单应正常返回
    assert len(orders) == 1
    assert orders[0]["platform"] == "eleme"


# ── Test 6: 接单成功 — 平台接单+库存扣减+KDS ──────────────────────────────────


@pytest.mark.asyncio
async def test_accept_order_success(service, store_id):
    """接单成功时应调用平台接单、扣减库存、通知KDS"""
    service._call_platform_accept = AsyncMock(
        return_value={"success": True, "items": [{"skuName": "红烧肉", "quantity": 1}]}
    )
    service._deduct_inventory_for_order = AsyncMock(return_value={"success": True})
    service._notify_kitchen_display = AsyncMock(return_value={"success": True})

    result = await service.accept_order(
        store_id=store_id,
        platform="meituan",
        platform_order_id="MT001",
        estimated_minutes=25,
    )

    assert result["success"] is True
    assert result["platform"] == "meituan"
    assert result["estimated_minutes"] == 25
    assert result["inventory_deducted"] is True
    assert result["kds_notified"] is True

    service._call_platform_accept.assert_called_once_with(
        store_id=store_id,
        platform="meituan",
        platform_order_id="MT001",
        estimated_minutes=25,
    )
    service._deduct_inventory_for_order.assert_called_once()
    service._notify_kitchen_display.assert_called_once()


# ── Test 7: 接单 — 平台返回失败时不调用库存 ───────────────────────────────────


@pytest.mark.asyncio
async def test_accept_order_platform_failure(service, store_id):
    """平台接单失败时应提前返回，不触发库存扣减"""
    service._call_platform_accept = AsyncMock(
        return_value={"success": False, "error": "订单已过期"}
    )
    service._deduct_inventory_for_order = AsyncMock()
    service._notify_kitchen_display = AsyncMock()

    result = await service.accept_order(
        store_id=store_id,
        platform="eleme",
        platform_order_id="ELE999",
    )

    assert result["success"] is False
    assert "订单已过期" in result["error"]
    service._deduct_inventory_for_order.assert_not_called()
    service._notify_kitchen_display.assert_not_called()


# ── Test 8: 拒单成功 ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reject_order_success(service, store_id):
    """拒单应调用平台接口并返回成功结果"""
    service._call_platform_reject = AsyncMock(return_value={"success": True, "error": None})

    result = await service.reject_order(
        store_id=store_id,
        platform="douyin",
        platform_order_id="DY100",
        reason="厨房临时关闭",
    )

    assert result["success"] is True
    assert result["reason"] == "厨房临时关闭"
    service._call_platform_reject.assert_called_once_with(
        store_id=store_id,
        platform="douyin",
        platform_order_id="DY100",
        reason="厨房临时关闭",
    )


# ── Test 9: 不支持的平台应抛出 ValueError ─────────────────────────────────────


@pytest.mark.asyncio
async def test_invalid_platform_raises_error(service, store_id):
    """传入不支持的平台名称应抛出 ValueError"""
    with pytest.raises(ValueError, match="不支持的平台"):
        await service.accept_order(
            store_id=store_id,
            platform="waimai_unknown",
            platform_order_id="X001",
        )

    with pytest.raises(ValueError, match="不支持的平台"):
        await service.reject_order(
            store_id=store_id,
            platform="waimai_unknown",
            platform_order_id="X001",
            reason="test",
        )


# ── Test 10: 统计数据汇总 ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_platform_stats_structure(service, store_id):
    """get_platform_stats 应返回包含三平台的汇总统计结构"""
    mock_row = MagicMock()
    mock_row.__getitem__ = lambda self, k: {
        "channel": "meituan",
        "order_count": 50,
        "revenue_fen": 500000,
        "cancel_rate": 0.04,
        "avg_delivery_min": 32.5,
    }[k]

    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [mock_row]

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    async def fake_get_db():
        yield mock_db

    with patch("src.services.takeaway_unified_service.get_db_session", fake_get_db):
        stats = await service.get_platform_stats(store_id, days=7)

    assert "platforms" in stats
    assert set(stats["platforms"].keys()) == {"meituan", "eleme", "douyin"}
    assert stats["platforms"]["meituan"]["order_count"] == 50
    assert stats["platforms"]["meituan"]["revenue_yuan"] == 5000.0
    # 未出现在查询结果中的平台应有默认值
    assert stats["platforms"]["eleme"]["order_count"] == 0
    assert stats["total_orders"] == 50
