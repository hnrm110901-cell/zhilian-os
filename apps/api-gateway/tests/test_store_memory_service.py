"""
Tests for StoreMemoryService

Covers:
- compute_peak_patterns: single-query + exponential-decay + dynamic threshold
- compute_dish_health:   trend / refund-rate calculations
- compute_staff_baseline: per-shift averages
- detect_anomaly:         discount_spike rule
- refresh_store_memory:   orchestration + Redis write
"""
import os

for _k, _v in {
    "DATABASE_URL":          "postgresql+asyncpg://test:test@localhost/test",
    "REDIS_URL":             "redis://localhost:6379/0",
    "CELERY_BROKER_URL":     "redis://localhost:6379/0",
    "CELERY_RESULT_BACKEND": "redis://localhost:6379/0",
    "SECRET_KEY":            "test-secret-key",
    "JWT_SECRET":            "test-jwt-secret",
}.items():
    os.environ.setdefault(_k, _v)

import math
import pytest
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from src.services.store_memory_service import StoreMemoryService, _confidence_level
from src.models.store_memory import (
    PeakHourPattern, StoreMemory, AnomalyPattern, StoreMemoryStore,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _mock_db() -> AsyncMock:
    return AsyncMock()


def _row(day, hour, order_count, revenue):
    """Build a fake SQLAlchemy row for GROUP-BY query."""
    r = MagicMock()
    r.day         = day
    r.hour        = float(hour)
    r.order_count = order_count
    r.revenue     = revenue
    return r


def _rows_result(rows_list) -> MagicMock:
    r = MagicMock()
    r.all.return_value = rows_list
    return r


def _scalar_result(value) -> MagicMock:
    r = MagicMock()
    r.scalar.return_value = value
    return r


def _one_result(order_count, revenue) -> MagicMock:
    r = MagicMock()
    row = MagicMock()
    row.order_count = order_count
    row.revenue     = revenue
    r.one.return_value = row
    return r


# ── _confidence_level ─────────────────────────────────────────────────────────

class TestConfidenceLevel:
    def test_high_at_30_days(self):
        assert _confidence_level(30) == "high"

    def test_high_above_30(self):
        assert _confidence_level(90) == "high"

    def test_medium_at_14_days(self):
        assert _confidence_level(14) == "medium"

    def test_medium_between_14_and_29(self):
        assert _confidence_level(20) == "medium"

    def test_low_below_14(self):
        assert _confidence_level(7)  == "low"
        assert _confidence_level(0)  == "low"


# ── compute_peak_patterns ─────────────────────────────────────────────────────

class TestComputePeakPatterns:

    @pytest.mark.asyncio
    async def test_no_db_returns_mock(self):
        svc = StoreMemoryService(db_session=None)
        patterns = await svc.compute_peak_patterns("S1")

        assert len(patterns) == 24
        peak_hours = {p.hour for p in patterns if p.is_peak}
        # Mock fixture has lunch + dinner peaks
        assert 12 in peak_hours
        assert 19 in peak_hours

    @pytest.mark.asyncio
    async def test_returns_24_patterns(self):
        db = _mock_db()
        today = date.today()
        db.execute.return_value = _rows_result([
            _row(today, h, 5, 100_00) for h in [12, 13, 19]
        ])

        svc     = StoreMemoryService(db_session=db)
        results = await svc.compute_peak_patterns("S1", lookback_days=7)

        assert len(results) == 24
        assert all(isinstance(p, PeakHourPattern) for p in results)
        assert all(0 <= p.hour <= 23 for p in results)

    @pytest.mark.asyncio
    async def test_peak_hours_identified_above_mean_threshold(self):
        """Hours 12,13,19 with 5x more orders than other hours → flagged as peak."""
        db = _mock_db()
        today = date.today()
        rows = [_row(today, h, 10, 1000_00) for h in [12, 13, 19]]
        rows += [_row(today, h, 1,   80_00) for h in range(24) if h not in {12, 13, 19}]
        db.execute.return_value = _rows_result(rows)

        svc      = StoreMemoryService(db_session=db)
        patterns = await svc.compute_peak_patterns("S1", lookback_days=7)

        peak_hours = {p.hour for p in patterns if p.is_peak}
        assert 12 in peak_hours
        assert 13 in peak_hours
        assert 19 in peak_hours
        # Off-peak hours should NOT be flagged
        assert 3 not in peak_hours
        assert 4 not in peak_hours

    @pytest.mark.asyncio
    async def test_exponential_decay_recent_data_weighted_more(self):
        """
        Yesterday's data should outweigh data from 10 days ago.
        Two rows at different ages for the same hour; the weighted avg
        must be closer to the recent value.
        """
        db = _mock_db()
        today   = date.today()
        recent  = today - timedelta(days=1)
        old     = today - timedelta(days=10)

        # Recent: 100 orders; Old: 10 orders
        rows = [
            _row(recent, 12, 100, 0),
            _row(old,    12,  10, 0),
        ]
        db.execute.return_value = _rows_result(rows)

        svc      = StoreMemoryService(db_session=db)
        patterns = await svc.compute_peak_patterns("S1")

        p12 = next(p for p in patterns if p.hour == 12)
        # Weighted avg must be > 55 (simple mean of 100+10)/2=55;
        # exponential decay pulls it upward toward 100.
        assert p12.avg_orders > 55.0

    @pytest.mark.asyncio
    async def test_revenue_converted_from_fen_to_yuan(self):
        db = _mock_db()
        today = date.today()
        # 120000 分 = 1200 元
        db.execute.return_value = _rows_result([_row(today, 12, 1, 120_000)])

        svc      = StoreMemoryService(db_session=db)
        patterns = await svc.compute_peak_patterns("S1")

        p12 = next(p for p in patterns if p.hour == 12)
        assert pytest.approx(p12.avg_revenue, abs=1.0) == 1200.0

    @pytest.mark.asyncio
    async def test_empty_data_all_zero_no_peaks(self):
        """No orders at all → avg_orders=0 everywhere, dynamic threshold=0.5, nothing peaks."""
        db = _mock_db()
        db.execute.return_value = _rows_result([])

        svc      = StoreMemoryService(db_session=db)
        patterns = await svc.compute_peak_patterns("S1")

        assert all(p.avg_orders == 0.0 for p in patterns)
        assert all(not p.is_peak  for p in patterns)

    @pytest.mark.asyncio
    async def test_date_as_string_handled(self):
        """func.date() may return a string depending on the DB dialect."""
        db = _mock_db()
        db.execute.return_value = _rows_result([
            _row("2026-01-15", 12, 5, 50_000),
        ])

        svc      = StoreMemoryService(db_session=db)
        # Should not raise
        patterns = await svc.compute_peak_patterns("S1")
        assert len(patterns) == 24

    @pytest.mark.asyncio
    async def test_db_failure_falls_back_to_mock(self):
        db = _mock_db()
        db.execute.side_effect = Exception("DB gone")

        svc      = StoreMemoryService(db_session=db)
        patterns = await svc.compute_peak_patterns("S1")

        # Falls back to the 24-entry mock
        assert len(patterns) == 24
        peak_hours = {p.hour for p in patterns if p.is_peak}
        assert len(peak_hours) == 6  # Mock has exactly 6 peak hours

    @pytest.mark.asyncio
    async def test_weight_stored_in_pattern(self):
        """weight field should reflect accumulated exponential weights."""
        db = _mock_db()
        today = date.today()
        db.execute.return_value = _rows_result([_row(today, 9, 3, 30_000)])

        svc      = StoreMemoryService(db_session=db)
        patterns = await svc.compute_peak_patterns("S1")

        p9 = next(p for p in patterns if p.hour == 9)
        # weight for today (offset=0) → exp(0) = 1.0
        assert p9.weight == pytest.approx(1.0, abs=0.01)

        # All other hours have no data → weight=0
        zero_weight_hours = [p for p in patterns if p.hour != 9]
        assert all(p.weight == 0.0 for p in zero_weight_hours)


# ── compute_dish_health ───────────────────────────────────────────────────────

class TestComputeDishHealth:

    @pytest.mark.asyncio
    async def test_no_db_returns_healthy_default(self):
        svc = StoreMemoryService(db_session=None)
        h   = await svc.compute_dish_health("SKU1", "S1")
        assert h.sku_id    == "SKU1"
        assert h.is_healthy is True

    @pytest.mark.asyncio
    async def test_positive_trend_when_sales_increasing(self):
        db = _mock_db()
        # recent=100, prev=80 → trend=(100-80)/80=0.25
        db.execute.side_effect = [
            _scalar_result(100),  # recent_sales
            _scalar_result(80),   # prev_sales
            _scalar_result(0),    # cancelled
        ]
        svc = StoreMemoryService(db_session=db)
        h   = await svc.compute_dish_health("SKU1", "S1")

        assert h.trend_7d == pytest.approx(0.25, abs=0.01)
        assert h.is_healthy is True

    @pytest.mark.asyncio
    async def test_negative_trend_below_minus30pct_is_unhealthy(self):
        db = _mock_db()
        # recent=60, prev=100 → trend=-0.40
        db.execute.side_effect = [
            _scalar_result(60),   # recent
            _scalar_result(100),  # prev
            _scalar_result(0),    # cancelled
        ]
        svc = StoreMemoryService(db_session=db)
        h   = await svc.compute_dish_health("SKU1", "S1")

        assert h.trend_7d  == pytest.approx(-0.40, abs=0.01)
        assert h.is_healthy is False

    @pytest.mark.asyncio
    async def test_zero_prev_sales_trend_is_zero(self):
        db = _mock_db()
        db.execute.side_effect = [
            _scalar_result(50),
            _scalar_result(0),    # prev=0 → no division, trend=0
            _scalar_result(0),
        ]
        svc = StoreMemoryService(db_session=db)
        h   = await svc.compute_dish_health("SKU1", "S1")

        assert h.trend_7d == 0.0

    @pytest.mark.asyncio
    async def test_high_refund_rate_is_unhealthy(self):
        db = _mock_db()
        # recent=10, cancelled=5 → refund_rate=0.5 > 0.1 → unhealthy
        db.execute.side_effect = [
            _scalar_result(10),
            _scalar_result(10),
            _scalar_result(5),
        ]
        svc = StoreMemoryService(db_session=db)
        h   = await svc.compute_dish_health("SKU1", "S1")

        assert h.refund_rate == pytest.approx(0.5, abs=0.01)
        assert h.is_healthy  is False

    @pytest.mark.asyncio
    async def test_refund_rate_capped_at_1(self):
        db = _mock_db()
        # cancelled > recent → should cap at 1.0
        db.execute.side_effect = [
            _scalar_result(5),    # recent
            _scalar_result(5),    # prev
            _scalar_result(100),  # cancelled >> recent
        ]
        svc = StoreMemoryService(db_session=db)
        h   = await svc.compute_dish_health("SKU1", "S1")

        assert h.refund_rate <= 1.0

    @pytest.mark.asyncio
    async def test_db_failure_returns_default(self):
        db = _mock_db()
        db.execute.side_effect = Exception("DB error")

        svc = StoreMemoryService(db_session=db)
        h   = await svc.compute_dish_health("SKU1", "S1")

        assert h.sku_id == "SKU1"


# ── compute_staff_baseline ────────────────────────────────────────────────────

class TestComputeStaffBaseline:

    @pytest.mark.asyncio
    async def test_no_db_returns_empty_profile(self):
        svc = StoreMemoryService(db_session=None)
        p   = await svc.compute_staff_baseline("W1", "S1")
        assert p.staff_id == "W1"
        assert p.avg_orders_per_shift == 0.0

    @pytest.mark.asyncio
    async def test_per_shift_averages(self):
        db = _mock_db()
        # 300 orders, 1_500_000 分 (= 15,000 元) revenue, across 15 shifts
        db.execute.side_effect = [
            _one_result(300, 15_000_00),  # 1,500,000 fen = 15,000 yuan
            _scalar_result(15),           # distinct shift days
        ]
        svc = StoreMemoryService(db_session=db)
        p   = await svc.compute_staff_baseline("W1", "S1")

        assert p.avg_orders_per_shift  == pytest.approx(20.0, abs=0.01)
        assert p.avg_revenue_per_shift == pytest.approx(1000.0, abs=0.01)  # 15000 / 15 = 1000

    @pytest.mark.asyncio
    async def test_zero_shifts_defaults_to_1(self):
        """Guard against divide-by-zero when no distinct shift dates found."""
        db = _mock_db()
        db.execute.side_effect = [
            _one_result(50, 500_000),
            _scalar_result(0),   # 0 shifts → clamped to 1
        ]
        svc = StoreMemoryService(db_session=db)
        p   = await svc.compute_staff_baseline("W1", "S1")

        assert p.avg_orders_per_shift > 0  # no crash, positive value

    @pytest.mark.asyncio
    async def test_db_failure_returns_default(self):
        db = _mock_db()
        db.execute.side_effect = Exception("DB gone")

        svc = StoreMemoryService(db_session=db)
        p   = await svc.compute_staff_baseline("W1", "S1")
        assert p.staff_id == "W1"


# ── detect_anomaly ────────────────────────────────────────────────────────────

class TestDetectAnomaly:

    def _svc_with_empty_memory(self, store_id="S1"):
        """Service whose store returns no existing memory."""
        mock_store = AsyncMock(spec=StoreMemoryStore)
        mock_store.load.return_value = None
        mock_store.save = AsyncMock(return_value=True)
        return StoreMemoryService(db_session=None, memory_store=mock_store)

    @pytest.mark.asyncio
    async def test_below_threshold_returns_none(self):
        svc = self._svc_with_empty_memory()
        result = await svc.detect_anomaly("S1", {
            "action_type": "discount_apply",
            "amount": 3000,  # 30元 < 50元
        })
        assert result is None

    @pytest.mark.asyncio
    async def test_non_discount_action_returns_none(self):
        svc = self._svc_with_empty_memory()
        result = await svc.detect_anomaly("S1", {
            "action_type": "price_override",
            "amount": 99999,
        })
        assert result is None

    @pytest.mark.asyncio
    async def test_discount_above_threshold_creates_anomaly(self):
        svc = self._svc_with_empty_memory()
        result = await svc.detect_anomaly("S1", {
            "action_type": "discount_apply",
            "amount": 10_000,  # 100元 > 50元
        })
        assert result is not None
        assert result.pattern_type == "discount_spike"
        assert result.severity     == "medium"  # 100元 < 200元

    @pytest.mark.asyncio
    async def test_high_severity_above_200_yuan(self):
        svc = self._svc_with_empty_memory()
        result = await svc.detect_anomaly("S1", {
            "action_type": "discount_apply",
            "amount": 25_000,  # 250元
        })
        assert result.severity == "high"

    @pytest.mark.asyncio
    async def test_existing_anomaly_count_incremented(self):
        """Second discount spike should increment occurrence_count, not add a new entry."""
        existing_pattern = AnomalyPattern(
            pattern_type="discount_spike",
            description="first",
            first_seen=datetime.utcnow(),
            last_seen=datetime.utcnow(),
            occurrence_count=1,
        )
        existing_memory = StoreMemory(
            store_id="S1",
            anomaly_patterns=[existing_pattern],
        )

        mock_store = AsyncMock(spec=StoreMemoryStore)
        mock_store.load.return_value = existing_memory
        mock_store.save = AsyncMock(return_value=True)

        svc = StoreMemoryService(db_session=None, memory_store=mock_store)
        await svc.detect_anomaly("S1", {
            "action_type": "discount_apply",
            "amount": 10_000,
        })

        saved: StoreMemory = mock_store.save.call_args[0][0]
        assert len(saved.anomaly_patterns) == 1        # still one entry
        assert saved.anomaly_patterns[0].occurrence_count == 2

    @pytest.mark.asyncio
    async def test_anomaly_written_to_redis(self):
        mock_store = AsyncMock(spec=StoreMemoryStore)
        mock_store.load.return_value = None
        mock_store.save = AsyncMock(return_value=True)

        svc = StoreMemoryService(db_session=None, memory_store=mock_store)
        await svc.detect_anomaly("S1", {"action_type": "discount_apply", "amount": 10_000})

        mock_store.save.assert_called_once()


# ── refresh_store_memory ──────────────────────────────────────────────────────

class TestRefreshStoreMemory:

    @pytest.mark.asyncio
    async def test_returns_store_memory_with_patterns(self):
        mock_store = AsyncMock(spec=StoreMemoryStore)
        mock_store.save = AsyncMock(return_value=True)

        svc = StoreMemoryService(db_session=None, memory_store=mock_store)
        mem = await svc.refresh_store_memory("S1", brand_id="B1", lookback_days=14)

        assert mem.store_id          == "S1"
        assert mem.brand_id          == "B1"
        assert mem.data_coverage_days == 14
        assert mem.confidence         == "medium"  # 14 days
        assert len(mem.peak_patterns) == 24

    @pytest.mark.asyncio
    async def test_memory_saved_to_redis(self):
        mock_store = AsyncMock(spec=StoreMemoryStore)
        mock_store.save = AsyncMock(return_value=True)

        svc = StoreMemoryService(db_session=None, memory_store=mock_store)
        await svc.refresh_store_memory("S1")

        mock_store.save.assert_called_once()
        saved_mem = mock_store.save.call_args[0][0]
        assert saved_mem.store_id == "S1"

    @pytest.mark.asyncio
    async def test_confidence_high_for_30_days(self):
        mock_store = AsyncMock(spec=StoreMemoryStore)
        mock_store.save = AsyncMock()

        svc = StoreMemoryService(db_session=None, memory_store=mock_store)
        mem = await svc.refresh_store_memory("S1", lookback_days=30)

        assert mem.confidence == "high"


# ── get_memory ────────────────────────────────────────────────────────────────

class TestGetMemory:

    @pytest.mark.asyncio
    async def test_returns_none_when_not_cached(self):
        mock_store = AsyncMock(spec=StoreMemoryStore)
        mock_store.load.return_value = None

        svc = StoreMemoryService(db_session=None, memory_store=mock_store)
        mem = await svc.get_memory("S1")
        assert mem is None

    @pytest.mark.asyncio
    async def test_returns_cached_memory(self):
        cached = StoreMemory(store_id="S1")
        mock_store = AsyncMock(spec=StoreMemoryStore)
        mock_store.load.return_value = cached

        svc = StoreMemoryService(db_session=None, memory_store=mock_store)
        mem = await svc.get_memory("S1")
        assert mem.store_id == "S1"
