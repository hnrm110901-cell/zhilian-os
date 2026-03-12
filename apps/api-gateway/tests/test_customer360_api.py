"""
private_domain.py — GET /customer360/{store_id}/{customer_id} 测试

覆盖：
  - 正常返回完整画像（member + journeys + orders + pricing_offer）
  - 会员不存在返回 404
  - DB 异常（member 查询）返回 500
  - 旅程查询失败时静默降级（返回空列表）
  - 订单查询失败时静默降级（返回空列表）
  - DynamicPricingService 异常时 pricing_offer 为 None
  - monetary_yuan 换算正确（分 → 元）
  - total_amount_yuan 换算正确（分 → 元）
  - birth_date None 时序列化为 null
  - 旅程 completed_at 为 None 时正确处理
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("APP_ENV", "test")

from unittest.mock import AsyncMock, MagicMock, patch
import pytest


# ════════════════════════════════════════════════════════════════════════════
# 辅助工厂
# ════════════════════════════════════════════════════════════════════════════

def _member_row(
    customer_id="C001", rfm_level="S2", lifecycle_state="repeat",
    birth_date=None, wechat_openid="wx001", channel_source="wxwork",
    recency_days=5, frequency=8, monetary=50000,
    last_visit="2026-03-01", is_active=True, created_at="2025-01-10",
):
    row = MagicMock()
    vals = (
        customer_id, rfm_level, lifecycle_state, birth_date,
        wechat_openid, channel_source, recency_days, frequency,
        monetary, last_visit, is_active, created_at,
    )
    row.__getitem__ = lambda self, i: vals[i]
    return row


def _journey_row(
    journey_type="member_activation", status="completed",
    started_at="2026-02-01", completed_at="2026-02-02",
):
    row = MagicMock()
    vals = (journey_type, status, started_at, completed_at)
    row.__getitem__ = lambda self, i: vals[i]
    return row


def _order_row(
    order_id="ORD001", total_amount=12345,
    created_at="2026-03-01 12:00:00", status="completed",
):
    row = MagicMock()
    vals = (order_id, total_amount, created_at, status)
    row.__getitem__ = lambda self, i: vals[i]
    return row


def _make_db(call_results):
    """
    call_results: list of (fetchone | fetchall | raise_exc) per execute call.
    Each item is a dict: {"fetchone": ..., "fetchall": ..., "raise": Exception}
    """
    db = AsyncMock()
    call_count = [0]

    async def execute(sql, params=None):
        idx = call_count[0]
        call_count[0] += 1
        spec = call_results[idx] if idx < len(call_results) else {}
        if "raise" in spec:
            raise spec["raise"]
        mock_result = MagicMock()
        if "fetchone" in spec:
            mock_result.fetchone = MagicMock(return_value=spec["fetchone"])
        if "fetchall" in spec:
            mock_result.fetchall = MagicMock(return_value=spec["fetchall"])
        return mock_result

    db.execute = execute
    return db


def _mock_pricing(maslow_level=2):
    """返回一个假的 PricingOffer dataclass-like 对象（能被 asdict 处理）。"""
    from dataclasses import dataclass

    _level = maslow_level

    @dataclass
    class FakeOffer:
        offer_type: str = "discount_coupon"
        title: str = "回头客专属优惠"
        description: str = "享 88折"
        discount_pct: float = 8.8
        maslow_level: int = _level
        strategy_note: str = "test"
        is_peak_hour: bool = False
        confidence: float = 0.86

    return FakeOffer()


# ════════════════════════════════════════════════════════════════════════════
# 正常流程
# ════════════════════════════════════════════════════════════════════════════

class TestGetCustomer360Normal:

    @pytest.mark.asyncio
    async def test_returns_complete_profile(self):
        from src.api.private_domain import get_customer360

        db = _make_db([
            {"fetchone": _member_row()},        # member query
            {"fetchall": [_journey_row()]},     # journeys query
            {"fetchall": [_order_row()]},       # orders query
        ])
        mock_user = MagicMock()

        with patch(
            "src.services.dynamic_pricing_service.DynamicPricingService.recommend",
            new_callable=AsyncMock,
            return_value=_mock_pricing(),
        ):
            result = await get_customer360(
                store_id="S001", customer_id="C001",
                current_user=mock_user, db=db,
            )

        assert result["store_id"] == "S001"
        assert result["customer_id"] == "C001"
        assert result["member"]["customer_id"] == "C001"
        assert result["member"]["rfm_level"] == "S2"
        assert len(result["recent_journeys"]) == 1
        assert len(result["recent_orders"]) == 1
        assert result["pricing_offer"] is not None

    @pytest.mark.asyncio
    async def test_monetary_yuan_conversion(self):
        """monetary 50000 分 → monetary_yuan 500.00 元。"""
        from src.api.private_domain import get_customer360

        db = _make_db([
            {"fetchone": _member_row(monetary=50000)},
            {"fetchall": []},
            {"fetchall": []},
        ])
        with patch("src.services.dynamic_pricing_service.DynamicPricingService.recommend",
                   new_callable=AsyncMock, return_value=_mock_pricing()):
            result = await get_customer360("S001", "C001", MagicMock(), db)

        assert result["member"]["monetary_yuan"] == 500.0

    @pytest.mark.asyncio
    async def test_order_amount_yuan_conversion(self):
        """total_amount 12345 分 → total_amount_yuan 123.45 元。"""
        from src.api.private_domain import get_customer360

        db = _make_db([
            {"fetchone": _member_row()},
            {"fetchall": []},
            {"fetchall": [_order_row(total_amount=12345)]},
        ])
        with patch("src.services.dynamic_pricing_service.DynamicPricingService.recommend",
                   new_callable=AsyncMock, return_value=_mock_pricing()):
            result = await get_customer360("S001", "C001", MagicMock(), db)

        assert result["recent_orders"][0]["total_amount_yuan"] == 123.45

    @pytest.mark.asyncio
    async def test_birth_date_none_serialized_as_null(self):
        from src.api.private_domain import get_customer360

        db = _make_db([
            {"fetchone": _member_row(birth_date=None)},
            {"fetchall": []},
            {"fetchall": []},
        ])
        with patch("src.services.dynamic_pricing_service.DynamicPricingService.recommend",
                   new_callable=AsyncMock, return_value=_mock_pricing()):
            result = await get_customer360("S001", "C001", MagicMock(), db)

        assert result["member"]["birth_date"] is None

    @pytest.mark.asyncio
    async def test_journey_completed_at_none(self):
        from src.api.private_domain import get_customer360

        db = _make_db([
            {"fetchone": _member_row()},
            {"fetchall": [_journey_row(status="running", completed_at=None)]},
            {"fetchall": []},
        ])
        with patch("src.services.dynamic_pricing_service.DynamicPricingService.recommend",
                   new_callable=AsyncMock, return_value=_mock_pricing()):
            result = await get_customer360("S001", "C001", MagicMock(), db)

        assert result["recent_journeys"][0]["completed_at"] is None
        assert result["recent_journeys"][0]["status"] == "running"

    @pytest.mark.asyncio
    async def test_empty_journeys_and_orders(self):
        from src.api.private_domain import get_customer360

        db = _make_db([
            {"fetchone": _member_row()},
            {"fetchall": []},
            {"fetchall": []},
        ])
        with patch("src.services.dynamic_pricing_service.DynamicPricingService.recommend",
                   new_callable=AsyncMock, return_value=_mock_pricing()):
            result = await get_customer360("S001", "C001", MagicMock(), db)

        assert result["recent_journeys"] == []
        assert result["recent_orders"] == []


# ════════════════════════════════════════════════════════════════════════════
# 错误处理 / 降级
# ════════════════════════════════════════════════════════════════════════════

class TestGetCustomer360Errors:

    @pytest.mark.asyncio
    async def test_member_not_found_raises_404(self):
        from src.api.private_domain import get_customer360
        from fastapi import HTTPException

        db = _make_db([{"fetchone": None}])
        with pytest.raises(HTTPException) as exc_info:
            await get_customer360("S001", "NO_EXIST", MagicMock(), db)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_member_db_error_raises_500(self):
        from src.api.private_domain import get_customer360
        from fastapi import HTTPException

        db = _make_db([{"raise": Exception("DB down")}])
        with pytest.raises(HTTPException) as exc_info:
            await get_customer360("S001", "C001", MagicMock(), db)
        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_journeys_db_error_graceful_degradation(self):
        """旅程查询失败时返回空列表，不抛出。"""
        from src.api.private_domain import get_customer360

        db = _make_db([
            {"fetchone": _member_row()},
            {"raise": Exception("journeys DB error")},
            {"fetchall": []},
        ])
        with patch("src.services.dynamic_pricing_service.DynamicPricingService.recommend",
                   new_callable=AsyncMock, return_value=_mock_pricing()):
            result = await get_customer360("S001", "C001", MagicMock(), db)

        assert result["recent_journeys"] == []
        assert result["member"]["customer_id"] == "C001"

    @pytest.mark.asyncio
    async def test_orders_db_error_graceful_degradation(self):
        """订单查询失败时返回空列表，不抛出。"""
        from src.api.private_domain import get_customer360

        db = _make_db([
            {"fetchone": _member_row()},
            {"fetchall": [_journey_row()]},
            {"raise": Exception("orders DB error")},
        ])
        with patch("src.services.dynamic_pricing_service.DynamicPricingService.recommend",
                   new_callable=AsyncMock, return_value=_mock_pricing()):
            result = await get_customer360("S001", "C001", MagicMock(), db)

        assert result["recent_orders"] == []
        assert len(result["recent_journeys"]) == 1

    @pytest.mark.asyncio
    async def test_pricing_service_error_returns_none(self):
        """DynamicPricingService 异常时 pricing_offer 为 None，不中断。"""
        from src.api.private_domain import get_customer360

        db = _make_db([
            {"fetchone": _member_row()},
            {"fetchall": []},
            {"fetchall": []},
        ])
        with patch("src.services.dynamic_pricing_service.DynamicPricingService.recommend",
                   new_callable=AsyncMock, side_effect=Exception("pricing error")):
            result = await get_customer360("S001", "C001", MagicMock(), db)

        assert result["pricing_offer"] is None
        assert result["member"] is not None
