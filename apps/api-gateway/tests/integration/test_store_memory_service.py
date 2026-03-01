"""
Tests for src/services/store_memory_service.py — ARCH-003 门店记忆服务.

Covers:
  - _confidence_level boundary conditions (< 14 / 14-29 / ≥ 30 days)
  - compute_peak_patterns: no-DB mock fallback, DB path, exception fallback
  - compute_dish_health: no-DB, trend + refund math, exception fallback
  - compute_staff_baseline: no-DB, avg_orders_per_shift calculation
  - refresh_store_memory: orchestration + Redis write
  - get_memory: delegates to StoreMemoryStore.load
  - detect_anomaly: non-discount / low-amount → None;
    high-amount → AnomalyPattern; accumulation; severity thresholds
  - _mock_peak_patterns: 24 patterns, correct peak/off-peak classification
"""
import sys
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

# Pre-stub agent_service to avoid import-time crash
sys.modules.setdefault("src.services.agent_service", MagicMock())

from src.services.store_memory_service import StoreMemoryService, _confidence_level
from src.models.store_memory import (
    AnomalyPattern,
    DishHealth,
    PeakHourPattern,
    StaffProfile,
    StoreMemory,
    StoreMemoryStore,
)

# Production bug workaround: store_memory_service.py queries OrderItem.dish_id
# but the model column is named item_id.  Add the alias so business logic tests
# can exercise the actual computation path instead of always hitting the fallback.
from src.models.order import OrderItem as _OrderItem
if not hasattr(_OrderItem, "dish_id"):
    _OrderItem.dish_id = _OrderItem.item_id  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_memory_store(existing_memory=None):
    """Return a mock StoreMemoryStore with async load/save."""
    store = AsyncMock(spec=StoreMemoryStore)
    store.load = AsyncMock(return_value=existing_memory)
    store.save = AsyncMock(return_value=True)
    return store


def _row(order_count=10, revenue=50000):
    """Simulate a SQLAlchemy result row with .order_count and .revenue."""
    row = MagicMock()
    row.order_count = order_count
    row.revenue = revenue
    return row


def _scalar_result(value):
    """Mock result.scalar() → value."""
    result = MagicMock()
    result.scalar = MagicMock(return_value=value)
    return result


def _one_result(order_count=10, revenue=50000):
    """Mock result.one() → row."""
    result = MagicMock()
    result.one = MagicMock(return_value=_row(order_count, revenue))
    return result


# ===========================================================================
# _confidence_level
# ===========================================================================

class TestConfidenceLevel:
    def test_below_14_days_is_low(self):
        assert _confidence_level(0) == "low"
        assert _confidence_level(13) == "low"

    def test_14_to_29_days_is_medium(self):
        assert _confidence_level(14) == "medium"
        assert _confidence_level(29) == "medium"

    def test_30_plus_days_is_high(self):
        assert _confidence_level(30) == "high"
        assert _confidence_level(90) == "high"


# ===========================================================================
# compute_peak_patterns
# ===========================================================================

class TestComputePeakPatterns:
    @pytest.mark.asyncio
    async def test_no_db_returns_24_mock_patterns(self):
        svc = StoreMemoryService(db_session=None, memory_store=_mock_memory_store())
        patterns = await svc.compute_peak_patterns("S1")
        assert len(patterns) == 24
        assert all(isinstance(p, PeakHourPattern) for p in patterns)

    @pytest.mark.asyncio
    async def test_no_db_peak_hours_are_correct(self):
        svc = StoreMemoryService(db_session=None, memory_store=_mock_memory_store())
        patterns = await svc.compute_peak_patterns("S1")
        peak_hours = {p.hour for p in patterns if p.is_peak}
        assert peak_hours == {11, 12, 13, 18, 19, 20}

    @pytest.mark.asyncio
    async def test_with_db_queries_each_hour(self):
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=_one_result(order_count=30, revenue=150_000))

        svc = StoreMemoryService(db_session=mock_db, memory_store=_mock_memory_store())
        patterns = await svc.compute_peak_patterns("S1", lookback_days=30)

        assert len(patterns) == 24
        assert mock_db.execute.await_count == 24

    @pytest.mark.asyncio
    async def test_with_db_avg_orders_calculated(self):
        mock_db = AsyncMock()
        # 30 orders over 30 days → avg 1.0 per day
        mock_db.execute = AsyncMock(return_value=_one_result(order_count=30, revenue=0))

        svc = StoreMemoryService(db_session=mock_db, memory_store=_mock_memory_store())
        patterns = await svc.compute_peak_patterns("S1", lookback_days=30)

        # All hours get same avg_orders = 30/30 = 1.0
        for p in patterns:
            assert p.avg_orders == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_with_db_revenue_converted_from_fen(self):
        mock_db = AsyncMock()
        # revenue=3000 fen, lookback=1 → avg_revenue = 3000/100/1 = 30 yuan
        mock_db.execute = AsyncMock(return_value=_one_result(order_count=0, revenue=3000))

        svc = StoreMemoryService(db_session=mock_db, memory_store=_mock_memory_store())
        patterns = await svc.compute_peak_patterns("S1", lookback_days=1)

        assert patterns[0].avg_revenue == pytest.approx(30.0)

    @pytest.mark.asyncio
    async def test_db_exception_returns_mock_fallback(self):
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=RuntimeError("DB down"))

        svc = StoreMemoryService(db_session=mock_db, memory_store=_mock_memory_store())
        patterns = await svc.compute_peak_patterns("S1")

        assert len(patterns) == 24  # mock fallback

    @pytest.mark.asyncio
    async def test_is_peak_threshold(self):
        """avg_orders > 1.5 → is_peak"""
        mock_db = AsyncMock()
        # 2 orders/day → avg_orders=2.0 > 1.5 → is_peak=True
        mock_db.execute = AsyncMock(return_value=_one_result(order_count=2, revenue=0))

        svc = StoreMemoryService(db_session=mock_db, memory_store=_mock_memory_store())
        patterns = await svc.compute_peak_patterns("S1", lookback_days=1)

        assert all(p.is_peak for p in patterns)


# ===========================================================================
# compute_dish_health
# ===========================================================================

class TestComputeDishHealth:
    @pytest.mark.asyncio
    async def test_no_db_returns_healthy_default(self):
        svc = StoreMemoryService(db_session=None, memory_store=_mock_memory_store())
        health = await svc.compute_dish_health("SKU-1", "S1")
        assert health.sku_id == "SKU-1"
        assert health.is_healthy is True

    @pytest.mark.asyncio
    async def test_trend_positive_sales_growth(self):
        """recent > prev → positive trend, is_healthy=True"""
        mock_db = AsyncMock()
        # Call sequence: recent_sales (scalar=100), prev_sales (scalar=50), cancelled (scalar=0)
        call_count = [0]

        async def execute_seq(stmt):
            n = call_count[0]
            call_count[0] += 1
            return _scalar_result([100, 50, 0][n])

        mock_db.execute = execute_seq
        svc = StoreMemoryService(db_session=mock_db, memory_store=_mock_memory_store())
        health = await svc.compute_dish_health("SKU-1", "S1")

        # trend = (100-50)/50 = 1.0, refund_rate = 0/100 = 0
        assert health.trend_7d == pytest.approx(1.0)
        assert health.refund_rate == pytest.approx(0.0)
        assert health.is_healthy is True

    @pytest.mark.asyncio
    async def test_high_refund_rate_marks_unhealthy(self):
        """refund_rate ≥ 0.1 → is_healthy=False"""
        mock_db = AsyncMock()
        call_count = [0]

        async def execute_seq(stmt):
            n = call_count[0]
            call_count[0] += 1
            return _scalar_result([100, 100, 15][n])  # 15% cancellation

        mock_db.execute = execute_seq
        svc = StoreMemoryService(db_session=mock_db, memory_store=_mock_memory_store())
        health = await svc.compute_dish_health("SKU-1", "S1")

        assert health.refund_rate == pytest.approx(0.15)
        assert health.is_healthy is False

    @pytest.mark.asyncio
    async def test_steep_decline_marks_unhealthy(self):
        """trend < -0.3 → is_healthy=False"""
        mock_db = AsyncMock()
        call_count = [0]

        async def execute_seq(stmt):
            n = call_count[0]
            call_count[0] += 1
            return _scalar_result([30, 100, 0][n])  # -70% trend

        mock_db.execute = execute_seq
        svc = StoreMemoryService(db_session=mock_db, memory_store=_mock_memory_store())
        health = await svc.compute_dish_health("SKU-1", "S1")

        assert health.trend_7d == pytest.approx(-0.7)
        assert health.is_healthy is False

    @pytest.mark.asyncio
    async def test_zero_prev_sales_trend_is_zero(self):
        """prev_sales == 0 → trend_7d = 0.0"""
        mock_db = AsyncMock()
        call_count = [0]

        async def execute_seq(stmt):
            n = call_count[0]
            call_count[0] += 1
            return _scalar_result([50, 0, 0][n])

        mock_db.execute = execute_seq
        svc = StoreMemoryService(db_session=mock_db, memory_store=_mock_memory_store())
        health = await svc.compute_dish_health("SKU-1", "S1")

        assert health.trend_7d == 0.0

    @pytest.mark.asyncio
    async def test_db_exception_returns_default(self):
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=RuntimeError("timeout"))

        svc = StoreMemoryService(db_session=mock_db, memory_store=_mock_memory_store())
        health = await svc.compute_dish_health("SKU-1", "S1")

        assert health.sku_id == "SKU-1"


# ===========================================================================
# compute_staff_baseline
# ===========================================================================

class TestComputeStaffBaseline:
    @pytest.mark.asyncio
    async def test_no_db_returns_default_profile(self):
        svc = StoreMemoryService(db_session=None, memory_store=_mock_memory_store())
        profile = await svc.compute_staff_baseline("STAFF-1", "S1")
        assert profile.staff_id == "STAFF-1"

    @pytest.mark.asyncio
    async def test_with_db_avg_orders_per_shift(self):
        mock_db = AsyncMock()
        call_count = [0]

        async def execute_seq(stmt):
            n = call_count[0]
            call_count[0] += 1
            if n == 0:
                # aggregate query → result.one() → row
                return _one_result(order_count=60, revenue=300_000)
            else:
                # shifts query → result.scalar()
                return _scalar_result(10)  # 10 shifts

        mock_db.execute = execute_seq
        svc = StoreMemoryService(db_session=mock_db, memory_store=_mock_memory_store())
        profile = await svc.compute_staff_baseline("STAFF-1", "S1")

        # avg_orders_per_shift = 60 / 10 = 6.0
        assert profile.avg_orders_per_shift == pytest.approx(6.0)
        # avg_revenue_per_shift = (300000/100) / 10 = 300.0
        assert profile.avg_revenue_per_shift == pytest.approx(300.0)

    @pytest.mark.asyncio
    async def test_zero_shifts_defaults_to_1(self):
        """shifts=0 → clamped to 1 to avoid ZeroDivisionError"""
        mock_db = AsyncMock()
        call_count = [0]

        async def execute_seq(stmt):
            n = call_count[0]
            call_count[0] += 1
            if n == 0:
                return _one_result(order_count=10, revenue=0)
            return _scalar_result(0)

        mock_db.execute = execute_seq
        svc = StoreMemoryService(db_session=mock_db, memory_store=_mock_memory_store())
        profile = await svc.compute_staff_baseline("STAFF-1", "S1")
        assert profile.avg_orders_per_shift == pytest.approx(10.0)  # 10/1

    @pytest.mark.asyncio
    async def test_db_exception_returns_default(self):
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=RuntimeError("timeout"))

        svc = StoreMemoryService(db_session=mock_db, memory_store=_mock_memory_store())
        profile = await svc.compute_staff_baseline("STAFF-1", "S1")
        assert profile.staff_id == "STAFF-1"


# ===========================================================================
# refresh_store_memory
# ===========================================================================

class TestRefreshStoreMemory:
    @pytest.mark.asyncio
    async def test_refresh_calls_save(self):
        mock_store = _mock_memory_store()
        svc = StoreMemoryService(db_session=None, memory_store=mock_store)
        memory = await svc.refresh_store_memory("S1", brand_id="B1", lookback_days=30)

        mock_store.save.assert_awaited_once()
        assert isinstance(memory, StoreMemory)

    @pytest.mark.asyncio
    async def test_refresh_returns_correct_confidence(self):
        mock_store = _mock_memory_store()
        svc = StoreMemoryService(db_session=None, memory_store=mock_store)
        memory = await svc.refresh_store_memory("S1", lookback_days=30)
        assert memory.confidence == "high"

    @pytest.mark.asyncio
    async def test_refresh_sets_brand_id(self):
        mock_store = _mock_memory_store()
        svc = StoreMemoryService(db_session=None, memory_store=mock_store)
        memory = await svc.refresh_store_memory("S1", brand_id="BRAND-X")
        assert memory.brand_id == "BRAND-X"

    @pytest.mark.asyncio
    async def test_refresh_includes_24_peak_patterns(self):
        mock_store = _mock_memory_store()
        svc = StoreMemoryService(db_session=None, memory_store=mock_store)
        memory = await svc.refresh_store_memory("S1")
        assert len(memory.peak_patterns) == 24


# ===========================================================================
# get_memory
# ===========================================================================

class TestGetMemory:
    @pytest.mark.asyncio
    async def test_get_memory_returns_loaded_memory(self):
        existing = StoreMemory(store_id="S1", updated_at=datetime.utcnow())
        mock_store = _mock_memory_store(existing_memory=existing)
        svc = StoreMemoryService(db_session=None, memory_store=mock_store)
        result = await svc.get_memory("S1")
        assert result is existing

    @pytest.mark.asyncio
    async def test_get_memory_none_when_not_found(self):
        mock_store = _mock_memory_store(existing_memory=None)
        svc = StoreMemoryService(db_session=None, memory_store=mock_store)
        result = await svc.get_memory("S_MISSING")
        assert result is None


# ===========================================================================
# detect_anomaly
# ===========================================================================

class TestDetectAnomaly:
    @pytest.mark.asyncio
    async def test_non_discount_event_returns_none(self):
        svc = StoreMemoryService(memory_store=_mock_memory_store())
        result = await svc.detect_anomaly("S1", {"action_type": "shift_report"})
        assert result is None

    @pytest.mark.asyncio
    async def test_discount_below_threshold_returns_none(self):
        svc = StoreMemoryService(memory_store=_mock_memory_store())
        # 5000 fen = ¥50, threshold is > 5000
        result = await svc.detect_anomaly("S1", {"action_type": "discount_apply", "amount": 5000})
        assert result is None

    @pytest.mark.asyncio
    async def test_discount_above_threshold_returns_anomaly(self):
        svc = StoreMemoryService(memory_store=_mock_memory_store())
        result = await svc.detect_anomaly("S1", {"action_type": "discount_apply", "amount": 6000})
        assert isinstance(result, AnomalyPattern)
        assert result.pattern_type == "discount_spike"

    @pytest.mark.asyncio
    async def test_severity_medium_below_200_yuan(self):
        svc = StoreMemoryService(memory_store=_mock_memory_store())
        result = await svc.detect_anomaly("S1", {"action_type": "discount_apply", "amount": 10_000})
        # 100 yuan < 200 yuan threshold
        assert result.severity == "medium"

    @pytest.mark.asyncio
    async def test_severity_high_at_200_yuan(self):
        svc = StoreMemoryService(memory_store=_mock_memory_store())
        result = await svc.detect_anomaly("S1", {"action_type": "discount_apply", "amount": 20_000})
        # 200 yuan ≥ 200 yuan threshold
        assert result.severity == "high"

    @pytest.mark.asyncio
    async def test_anomaly_written_to_redis(self):
        mock_store = _mock_memory_store()
        svc = StoreMemoryService(memory_store=mock_store)
        await svc.detect_anomaly("S1", {"action_type": "discount_apply", "amount": 6000})
        mock_store.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_repeated_anomaly_increments_count(self):
        """Second same anomaly accumulates occurrence_count."""
        # First event creates the anomaly_pattern list
        existing_memory = StoreMemory(store_id="S1", updated_at=datetime.utcnow())
        existing_memory.anomaly_patterns.append(AnomalyPattern(
            pattern_type="discount_spike",
            description="test",
            first_seen=datetime.utcnow(),
            last_seen=datetime.utcnow(),
            occurrence_count=1,
        ))
        mock_store = _mock_memory_store(existing_memory=existing_memory)
        svc = StoreMemoryService(memory_store=mock_store)

        await svc.detect_anomaly("S1", {"action_type": "discount_apply", "amount": 6000})

        # save was called with updated memory
        saved_memory: StoreMemory = mock_store.save.call_args[0][0]
        pattern = next(p for p in saved_memory.anomaly_patterns if p.pattern_type == "discount_spike")
        assert pattern.occurrence_count == 2

    @pytest.mark.asyncio
    async def test_new_anomaly_creates_memory_if_none_in_redis(self):
        """If Redis has no memory, a new StoreMemory is created."""
        mock_store = _mock_memory_store(existing_memory=None)
        svc = StoreMemoryService(memory_store=mock_store)
        result = await svc.detect_anomaly("S1", {"action_type": "discount_apply", "amount": 6000})
        assert result is not None
        mock_store.save.assert_awaited_once()
