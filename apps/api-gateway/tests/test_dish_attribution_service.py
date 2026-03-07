"""tests/test_dish_attribution_service.py — Phase 6 Month 9"""

import pytest
from unittest.mock import MagicMock, AsyncMock

import src.core.config  # noqa: F401  (must import before service)

from src.services.dish_attribution_service import (
    _prev_period,
    compute_avg_price,
    compute_price_effect,
    compute_volume_effect,
    compute_interaction,
    compute_delta_pct,
    classify_driver,
    build_attribution_record,
    compute_revenue_attribution,
    get_revenue_attribution,
    get_attribution_summary,
    get_top_movers,
    get_dish_attribution_history,
)


# ── _prev_period ──────────────────────────────────────────────────────────────

class TestPrevPeriod:
    def test_mid_year(self):
        assert _prev_period('2025-06') == '2025-05'

    def test_january(self):
        assert _prev_period('2025-01') == '2024-12'

    def test_december(self):
        assert _prev_period('2025-12') == '2025-11'

    def test_year_boundary(self):
        assert _prev_period('2024-01') == '2023-12'


# ── compute_avg_price ─────────────────────────────────────────────────────────

class TestComputeAvgPrice:
    def test_normal(self):
        assert compute_avg_price(1000.0, 10) == 100.0

    def test_zero_orders(self):
        assert compute_avg_price(500.0, 0) == 0.0

    def test_negative_orders(self):
        assert compute_avg_price(500.0, -1) == 0.0

    def test_rounding(self):
        assert compute_avg_price(100.0, 3) == 33.33


# ── compute_price_effect ──────────────────────────────────────────────────────

class TestComputePriceEffect:
    def test_positive(self):
        assert compute_price_effect(100, 5.0) == 500.0

    def test_negative(self):
        assert compute_price_effect(100, -3.0) == -300.0

    def test_zero(self):
        assert compute_price_effect(100, 0.0) == 0.0

    def test_rounding(self):
        assert compute_price_effect(10, 1.5) == 15.0


# ── compute_volume_effect ─────────────────────────────────────────────────────

class TestComputeVolumeEffect:
    def test_positive(self):
        assert compute_volume_effect(50.0, 10) == 500.0

    def test_negative(self):
        assert compute_volume_effect(50.0, -5) == -250.0

    def test_zero(self):
        assert compute_volume_effect(50.0, 0) == 0.0


# ── compute_interaction ───────────────────────────────────────────────────────

class TestComputeInteraction:
    def test_positive(self):
        assert compute_interaction(5.0, 10) == 50.0

    def test_negative_price(self):
        assert compute_interaction(-3.0, 10) == -30.0

    def test_negative_volume(self):
        assert compute_interaction(5.0, -4) == -20.0

    def test_both_negative(self):
        assert compute_interaction(-3.0, -4) == 12.0


# ── compute_delta_pct ─────────────────────────────────────────────────────────

class TestComputeDeltaPct:
    def test_increase(self):
        assert compute_delta_pct(120.0, 100.0) == 20.0

    def test_decrease(self):
        assert compute_delta_pct(80.0, 100.0) == -20.0

    def test_zero_previous(self):
        assert compute_delta_pct(100.0, 0.0) == 0.0

    def test_no_change(self):
        assert compute_delta_pct(100.0, 100.0) == 0.0


# ── classify_driver ───────────────────────────────────────────────────────────

class TestClassifyDriver:
    def test_stable_small_delta(self):
        assert classify_driver(0.5, 0.3, 0.1, 0.5) == 'stable'

    def test_price_dominant(self):
        # price=600, volume=100, interaction=100 → total=800, price=75%
        result = classify_driver(600.0, 100.0, 100.0, 800.0)
        assert result == 'price'

    def test_volume_dominant(self):
        result = classify_driver(50.0, 800.0, 50.0, 900.0)
        assert result == 'volume'

    def test_interaction_dominant(self):
        result = classify_driver(10.0, 20.0, 200.0, 230.0)
        assert result == 'interaction'

    def test_mixed(self):
        # all equal
        result = classify_driver(100.0, 100.0, 100.0, 300.0)
        assert result == 'mixed'

    def test_all_zero_effects(self):
        # total==0 → stable
        result = classify_driver(0.0, 0.0, 0.0, 5.0)
        assert result == 'stable'

    def test_negative_effects(self):
        # abs values: price=600, volume=50, interaction=50 → price dominant
        result = classify_driver(-600.0, 50.0, 50.0, -500.0)
        assert result == 'price'


# ── build_attribution_record ──────────────────────────────────────────────────

class TestBuildAttributionRecord:
    def _make(self, curr_orders=100, curr_rev=10000.0, prev_orders=80, prev_rev=8000.0):
        return build_attribution_record(
            'S001', '2025-06', '2025-05',
            'D001', '红烧肉', '主菜',
            curr_orders, curr_rev, prev_orders, prev_rev,
        )

    def test_keys_present(self):
        r = self._make()
        for k in ['store_id', 'period', 'prev_period', 'dish_id', 'dish_name', 'category',
                  'current_revenue', 'prev_revenue', 'revenue_delta', 'revenue_delta_pct',
                  'current_orders', 'prev_orders', 'order_delta', 'order_delta_pct',
                  'current_avg_price', 'prev_avg_price', 'price_delta', 'price_delta_pct',
                  'price_effect_yuan', 'volume_effect_yuan', 'interaction_yuan', 'primary_driver']:
            assert k in r

    def test_revenue_delta(self):
        r = self._make(curr_rev=10000.0, prev_rev=8000.0)
        assert r['revenue_delta'] == 2000.0

    def test_pvm_math_identity(self):
        """price_effect + volume_effect + interaction == revenue_delta (within rounding)"""
        r = self._make(curr_orders=110, curr_rev=12100.0, prev_orders=100, prev_rev=10000.0)
        pvm_sum = round(
            r['price_effect_yuan'] + r['volume_effect_yuan'] + r['interaction_yuan'], 2
        )
        assert pvm_sum == r['revenue_delta']

    def test_avg_price_computed(self):
        r = self._make(curr_orders=100, curr_rev=10000.0, prev_orders=80, prev_rev=8000.0)
        assert r['current_avg_price'] == 100.0
        assert r['prev_avg_price'] == 100.0

    def test_order_delta(self):
        r = self._make(curr_orders=110, prev_orders=100)
        assert r['order_delta'] == 10

    def test_category_none(self):
        r = build_attribution_record(
            'S001', '2025-06', '2025-05',
            'D001', '红烧肉', None,
            100, 10000.0, 100, 10000.0,
        )
        assert r['category'] is None
        assert r['primary_driver'] == 'stable'

    def test_price_only_change(self):
        # same orders, price goes up 10
        r = build_attribution_record(
            'S001', '2025-06', '2025-05',
            'D001', '菜A', None,
            100, 11000.0, 100, 10000.0,
        )
        # volume_effect = 100 * 0 = 0, interaction = 10 * 0 = 0
        assert r['volume_effect_yuan'] == 0.0
        assert r['interaction_yuan'] == 0.0
        assert r['price_effect_yuan'] == 1000.0
        assert r['primary_driver'] == 'price'


# ── DB-level helpers (async, mock) ────────────────────────────────────────────

def _make_db(call_returns: list):
    """Return an AsyncSession mock that cycles through call_returns for each execute() call."""
    returns_iter = iter(call_returns)
    db = MagicMock()
    db.commit = AsyncMock()

    async def _execute(sql, params=None):
        try:
            rows = next(returns_iter)
        except StopIteration:
            rows = []
        result = MagicMock()
        result.fetchall.return_value = rows
        return result

    db.execute = _execute
    return db


# ── compute_revenue_attribution ───────────────────────────────────────────────

class TestComputeRevenueAttribution:
    @pytest.mark.asyncio
    async def test_basic(self):
        curr = [('D001', '红烧肉', '主菜', 100, 10000.0)]
        prev = [('D001', '红烧肉', '主菜', 80, 8000.0)]
        db = _make_db([curr, prev, []])  # fetch curr, fetch prev, upsert (no return)
        result = await compute_revenue_attribution(db, 'S001', '2025-06')
        assert result['dish_count'] == 1
        assert result['new_dishes'] == 0
        assert result['discontinued_dishes'] == 0
        assert result['total_revenue_delta'] == 2000.0

    @pytest.mark.asyncio
    async def test_new_and_discontinued(self):
        curr = [('D001', '菜A', None, 100, 5000.0), ('D002', '菜B', None, 50, 2500.0)]
        prev = [('D001', '菜A', None, 80, 4000.0), ('D003', '菜C', None, 60, 3000.0)]
        db = _make_db([curr, prev, []])
        result = await compute_revenue_attribution(db, 'S001', '2025-06')
        assert result['dish_count'] == 1       # only D001 in both
        assert result['new_dishes'] == 1       # D002
        assert result['discontinued_dishes'] == 1  # D003

    @pytest.mark.asyncio
    async def test_prev_period_default(self):
        db = _make_db([[], []])
        result = await compute_revenue_attribution(db, 'S001', '2025-03')
        assert result['prev_period'] == '2025-02'

    @pytest.mark.asyncio
    async def test_prev_period_explicit(self):
        curr = [('D001', '菜A', None, 100, 5000.0)]
        prev = [('D001', '菜A', None, 90, 4500.0)]
        db = _make_db([curr, prev, []])
        result = await compute_revenue_attribution(db, 'S001', '2025-06', '2025-04')
        assert result['prev_period'] == '2025-04'


# ── get_revenue_attribution ───────────────────────────────────────────────────

class TestGetRevenueAttribution:
    @pytest.mark.asyncio
    async def test_no_driver_filter(self):
        rows = [
            (1, 'D001', '红烧肉', '主菜',
             10000.0, 8000.0, 2000.0, 25.0,
             100, 80, 20,
             100.0, 100.0, 0.0,
             0.0, 2000.0, 0.0, 'volume', '2025-05'),
        ]
        db = _make_db([rows])
        result = await get_revenue_attribution(db, 'S001', '2025-06')
        assert len(result) == 1
        assert result[0]['dish_id'] == 'D001'

    @pytest.mark.asyncio
    async def test_with_driver_filter(self):
        rows = [
            (2, 'D002', '炒饭', '主食',
             5000.0, 4000.0, 1000.0, 25.0,
             200, 160, 40,
             25.0, 25.0, 0.0,
             0.0, 1000.0, 0.0, 'volume', '2025-05'),
        ]
        db = _make_db([rows])
        result = await get_revenue_attribution(db, 'S001', '2025-06', driver='volume')
        assert len(result) == 1
        assert result[0]['primary_driver'] == 'volume'


# ── get_attribution_summary ───────────────────────────────────────────────────

class TestGetAttributionSummary:
    @pytest.mark.asyncio
    async def test_basic(self):
        rows = [
            ('price',  3, 3000.0, 2500.0,  300.0, 200.0, 2, 1),
            ('volume', 5, 5000.0,  500.0, 4000.0, 500.0, 4, 1),
        ]
        db = _make_db([rows])
        result = await get_attribution_summary(db, 'S001', '2025-06')
        assert len(result['by_driver']) == 2
        assert result['total_delta'] == 8000.0
        assert result['total_price_effect'] == 3000.0

    @pytest.mark.asyncio
    async def test_empty(self):
        db = _make_db([[]])
        result = await get_attribution_summary(db, 'S001', '2025-06')
        assert result['by_driver'] == []
        assert result['total_delta'] == 0.0


# ── get_top_movers ────────────────────────────────────────────────────────────

class TestGetTopMovers:
    def _row(self):
        return ('D001', '红烧肉', '主菜',
                12000.0, 8000.0, 4000.0, 50.0,
                500.0, 3000.0, 500.0, 'volume')

    @pytest.mark.asyncio
    async def test_gain(self):
        db = _make_db([[self._row()]])
        result = await get_top_movers(db, 'S001', '2025-06', direction='gain')
        assert len(result) == 1
        assert result[0]['revenue_delta'] == 4000.0

    @pytest.mark.asyncio
    async def test_loss(self):
        row = ('D002', '凉拌黄瓜', '凉菜',
               2000.0, 5000.0, -3000.0, -60.0,
               -200.0, -2500.0, -300.0, 'volume')
        db = _make_db([[row]])
        result = await get_top_movers(db, 'S001', '2025-06', direction='loss')
        assert result[0]['revenue_delta'] == -3000.0


# ── get_dish_attribution_history ──────────────────────────────────────────────

class TestGetDishAttributionHistory:
    @pytest.mark.asyncio
    async def test_basic(self):
        rows = [
            ('2025-06', '2025-05', 2000.0, 25.0, 0.0, 2000.0, 0.0, 20, 0.0, 'volume'),
            ('2025-05', '2025-04', -500.0, -5.9, -300.0, -200.0,  0.0, -5, -5.0, 'price'),
        ]
        db = _make_db([rows])
        result = await get_dish_attribution_history(db, 'S001', 'D001', periods=6)
        assert len(result) == 2
        assert result[0]['period'] == '2025-06'
        assert result[1]['primary_driver'] == 'price'
