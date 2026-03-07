"""Tests for dish_health_service — Phase 6 Month 8"""
import pytest
from unittest.mock import AsyncMock, MagicMock

import sys, types

cfg_mod = types.ModuleType("src.core.config")
cfg_mod.settings = MagicMock(
    database_url="postgresql+asyncpg://x:x@localhost/x",
    redis_url="redis://localhost",
    secret_key="test",
)
sys.modules.setdefault("src.core.config", cfg_mod)
sys.modules.setdefault("src.core.database", types.ModuleType("src.core.database"))

from src.services.dish_health_service import (
    compute_profitability_score,
    compute_growth_score,
    compute_benchmark_score,
    compute_forecast_score,
    classify_health_tier,
    determine_action_priority,
    find_top_components,
    compute_health_impact,
    build_health_score_record,
    compute_health_scores,
    get_health_scores,
    get_health_summary,
    get_action_priorities,
    get_dish_health_history,
    PHASE_GROWTH_BASE,
    BENCHMARK_TIER_SCORES,
)


# ── DB helper ─────────────────────────────────────────────────────────────────
def _make_db(call_returns: list):
    db = AsyncMock()
    results = iter(call_returns)
    async def execute(sql, params=None):
        result = MagicMock()
        try:
            result.fetchall.return_value = next(results)
        except StopIteration:
            result.fetchall.return_value = []
        result.rowcount = 1
        return result
    db.execute = execute
    db.commit = AsyncMock()
    return db


# ── TestComputeProfitabilityScore ─────────────────────────────────────────────
class TestComputeProfitabilityScore:
    def test_at_average_is_half_max(self):
        # gpm == avg_gpm, fcr == avg_fcr → each sub-score = 6.25 → total 12.5
        result = compute_profitability_score(50.0, 50.0, 30.0, 30.0)
        assert result == pytest.approx(12.5, abs=0.1)

    def test_double_gpm_half_fcr_is_max(self):
        # gpm = 2*avg → gpm_score=12.5; fcr = 0.5*avg → fcr_score=12.5
        result = compute_profitability_score(100.0, 50.0, 15.0, 30.0)
        assert result == pytest.approx(25.0, abs=0.1)

    def test_zero_gpm_is_zero_gpm_score(self):
        result = compute_profitability_score(0.0, 50.0, 30.0, 30.0)
        assert result == pytest.approx(6.25, abs=0.1)  # fcr neutral

    def test_zero_avg_gpm_returns_neutral(self):
        result = compute_profitability_score(50.0, 0.0, 30.0, 30.0)
        assert result == pytest.approx(12.5, abs=0.1)

    def test_high_fcr_penalized(self):
        # fcr = 2*avg → fcr_score = 6.25*0.5 = 3.125
        result = compute_profitability_score(50.0, 50.0, 60.0, 30.0)
        assert result < 12.5

    def test_score_capped_at_25(self):
        # Even with extreme values, score never exceeds 25
        result = compute_profitability_score(1000.0, 50.0, 1.0, 30.0)
        assert result <= 25.0

    def test_score_never_negative(self):
        result = compute_profitability_score(0.0, 100.0, 99.0, 10.0)
        assert result >= 0.0


# ── TestComputeGrowthScore ────────────────────────────────────────────────────
class TestComputeGrowthScore:
    def test_growth_phase_flat_trend(self):
        score = compute_growth_score(0.0, 0.0, 'growth')
        assert score == pytest.approx(PHASE_GROWTH_BASE['growth'], abs=0.1)

    def test_peak_phase_flat_trend(self):
        score = compute_growth_score(0.0, 0.0, 'peak')
        assert score == pytest.approx(PHASE_GROWTH_BASE['peak'], abs=0.1)

    def test_exit_phase_flat_trend(self):
        score = compute_growth_score(0.0, 0.0, 'exit')
        assert score == pytest.approx(PHASE_GROWTH_BASE['exit'], abs=0.1)

    def test_strong_uptrend_adds_modifier(self):
        base = compute_growth_score(0.0, 0.0, 'peak')
        with_trend = compute_growth_score(15.0, 15.0, 'peak')
        assert with_trend > base

    def test_strong_downtrend_subtracts_modifier(self):
        base = compute_growth_score(0.0, 0.0, 'peak')
        with_decline = compute_growth_score(-15.0, -15.0, 'peak')
        assert with_decline < base

    def test_exit_strong_downtrend_clamped_to_zero(self):
        score = compute_growth_score(-30.0, -30.0, 'exit')
        assert score == 0.0

    def test_growth_strong_uptrend_capped_at_25(self):
        score = compute_growth_score(20.0, 20.0, 'growth')
        assert score <= 25.0

    def test_unknown_phase_uses_fallback(self):
        score = compute_growth_score(0.0, 0.0, 'unknown')
        assert 0.0 <= score <= 25.0


# ── TestComputeBenchmarkScore ─────────────────────────────────────────────────
class TestComputeBenchmarkScore:
    def test_top_is_max(self):
        assert compute_benchmark_score('top') == pytest.approx(25.0)

    def test_laggard_is_min(self):
        assert compute_benchmark_score('laggard') == pytest.approx(3.0)

    def test_above_avg(self):
        assert compute_benchmark_score('above_avg') == pytest.approx(18.0)

    def test_below_avg(self):
        assert compute_benchmark_score('below_avg') == pytest.approx(10.0)

    def test_none_returns_neutral(self):
        assert compute_benchmark_score(None) == pytest.approx(12.5)

    def test_unknown_tier_returns_neutral(self):
        assert compute_benchmark_score('mystery') == pytest.approx(12.5)


# ── TestComputeForecastScore ──────────────────────────────────────────────────
class TestComputeForecastScore:
    def test_none_returns_low(self):
        assert compute_forecast_score(None) == pytest.approx(10.0)

    def test_6_periods_is_max(self):
        assert compute_forecast_score(6) == pytest.approx(25.0)

    def test_more_than_6_is_also_max(self):
        assert compute_forecast_score(12) == pytest.approx(25.0)

    def test_1_period_low(self):
        assert compute_forecast_score(1) == pytest.approx(13.0)

    def test_increasing_with_periods(self):
        scores = [compute_forecast_score(n) for n in range(1, 7)]
        assert scores == sorted(scores)


# ── TestClassifyHealthTier ────────────────────────────────────────────────────
class TestClassifyHealthTier:
    def test_excellent(self):
        assert classify_health_tier(80.0) == 'excellent'
        assert classify_health_tier(100.0) == 'excellent'

    def test_good(self):
        assert classify_health_tier(60.0) == 'good'
        assert classify_health_tier(79.9) == 'good'

    def test_fair(self):
        assert classify_health_tier(40.0) == 'fair'
        assert classify_health_tier(59.9) == 'fair'

    def test_poor(self):
        assert classify_health_tier(39.9) == 'poor'
        assert classify_health_tier(0.0) == 'poor'


# ── TestDetermineActionPriority ───────────────────────────────────────────────
class TestDetermineActionPriority:
    def test_poor_is_always_immediate(self):
        assert determine_action_priority('poor', 'peak') == 'immediate'
        assert determine_action_priority('poor', 'growth') == 'immediate'

    def test_fair_decline_is_immediate(self):
        assert determine_action_priority('fair', 'decline') == 'immediate'

    def test_fair_exit_is_immediate(self):
        assert determine_action_priority('fair', 'exit') == 'immediate'

    def test_fair_peak_is_monitor(self):
        assert determine_action_priority('fair', 'peak') == 'monitor'

    def test_good_is_maintain(self):
        assert determine_action_priority('good', 'peak') == 'maintain'

    def test_excellent_is_promote(self):
        assert determine_action_priority('excellent', 'any') == 'promote'


# ── TestFindTopComponents ─────────────────────────────────────────────────────
class TestFindTopComponents:
    def test_identifies_max_and_min(self):
        strength, weakness = find_top_components(20.0, 10.0, 15.0, 5.0)
        assert strength == 'profitability'
        assert weakness == 'forecast'

    def test_all_equal_consistent(self):
        strength, weakness = find_top_components(12.5, 12.5, 12.5, 12.5)
        # Any component is fine; just check they are valid names
        valid = {'profitability', 'growth', 'benchmark', 'forecast'}
        assert strength in valid
        assert weakness in valid


# ── TestComputeHealthImpact ───────────────────────────────────────────────────
class TestComputeHealthImpact:
    def test_immediate_25_pct(self):
        assert compute_health_impact(10000.0, 'immediate') == pytest.approx(2500.0)

    def test_promote_15_pct(self):
        assert compute_health_impact(10000.0, 'promote') == pytest.approx(1500.0)

    def test_maintain_3_pct(self):
        assert compute_health_impact(10000.0, 'maintain') == pytest.approx(300.0)

    def test_zero_revenue_zero_impact(self):
        assert compute_health_impact(0.0, 'immediate') == 0.0


# ── TestBuildHealthScoreRecord ────────────────────────────────────────────────
class TestBuildHealthScoreRecord:
    def _build(self, gpm=55.0, avg_gpm=50.0, fcr=28.0, avg_fcr=30.0,
               rev_trend=5.0, ord_trend=3.0, phase='peak',
               bench_tier='above_avg', periods=4):
        return build_health_score_record(
            'S001', '2025-01', 'D001', '宫保鸡丁', '热菜',
            5000.0, avg_gpm, avg_fcr, gpm, fcr,
            rev_trend, ord_trend, phase, bench_tier, periods,
        )

    def test_basic_structure(self):
        rec = self._build()
        assert rec['store_id']   == 'S001'
        assert rec['dish_id']    == 'D001'
        assert rec['period']     == '2025-01'
        assert 'total_score' in rec
        assert 'health_tier' in rec
        assert 'action_priority' in rec

    def test_scores_sum_to_total(self):
        rec = self._build()
        expected = (rec['profitability_score'] + rec['growth_score'] +
                    rec['benchmark_score'] + rec['forecast_score'])
        assert rec['total_score'] == pytest.approx(expected, abs=0.1)

    def test_excellent_dish_gets_promote(self):
        # Very good gpm, growth phase, top benchmark, 6 periods
        rec = build_health_score_record(
            'S001', '2025-01', 'D001', 'X', None,
            5000.0, 30.0, 35.0, 60.0, 20.0,
            15.0, 15.0, 'growth', 'top', 6,
        )
        assert rec['health_tier'] == 'excellent'
        assert rec['action_priority'] == 'promote'

    def test_poor_dish_gets_immediate(self):
        # Very poor gpm, exit phase, laggard, no periods
        rec = build_health_score_record(
            'S001', '2025-01', 'D002', 'Y', None,
            1000.0, 50.0, 30.0, 10.0, 55.0,
            -25.0, -25.0, 'exit', 'laggard', None,
        )
        assert rec['health_tier'] == 'poor'
        assert rec['action_priority'] == 'immediate'

    def test_impact_yuan_positive(self):
        rec = self._build()
        assert rec['expected_impact_yuan'] > 0

    def test_no_benchmark_data_still_works(self):
        rec = self._build(bench_tier=None)
        assert rec is not None
        assert rec['benchmark_score'] == pytest.approx(12.5)

    def test_no_forecast_data_still_works(self):
        rec = self._build(periods=None)
        assert rec is not None
        assert rec['forecast_score'] == pytest.approx(10.0)


# ── DB helper rows ────────────────────────────────────────────────────────────
def _prof_row(dish_id='D001', dish_name='宫保鸡丁', category='热菜',
              orders=120, revenue=4560.0, gpm=62.0, fcr=28.0):
    return (dish_id, dish_name, category, orders, revenue, gpm, fcr)

def _lc_row(dish_id='D001', phase='peak', rev_trend=3.0, ord_trend=2.0):
    return (dish_id, phase, rev_trend, ord_trend)

def _bench_row(dish_name='宫保鸡丁', tier='above_avg'):
    return (dish_name, tier)

def _fc_row(dish_id='D001', periods_used=4):
    return (dish_id, periods_used)


# ── TestComputeHealthScores ───────────────────────────────────────────────────
class TestComputeHealthScores:
    @pytest.mark.asyncio
    async def test_basic_computation(self):
        prof = [_prof_row(), _prof_row('D002', '麻婆豆腐', '热菜', 200, 5000.0, 58.0, 30.0)]
        lc   = [_lc_row(), _lc_row('D002', 'growth', 8.0, 6.0)]
        bench= [_bench_row(), _bench_row('麻婆豆腐', 'top')]
        fc   = [_fc_row(), _fc_row('D002', 6)]
        db = _make_db([prof, lc, bench, fc])
        result = await compute_health_scores(db, 'S001', '2025-01')
        assert result['dish_count'] == 2
        assert result['total_impact_yuan'] > 0
        assert len(result['tier_counts']) > 0

    @pytest.mark.asyncio
    async def test_empty_returns_zeros(self):
        db = _make_db([[]])
        result = await compute_health_scores(db, 'S001', '2025-01')
        assert result['dish_count'] == 0
        assert result['total_impact_yuan'] == 0.0

    @pytest.mark.asyncio
    async def test_no_lifecycle_data_defaults_to_peak(self):
        # Only profitability data, no lifecycle/benchmark/forecast
        db = _make_db([[_prof_row()], [], [], []])
        result = await compute_health_scores(db, 'S001', '2025-01')
        assert result['dish_count'] == 1

    @pytest.mark.asyncio
    async def test_tier_counts_populated(self):
        prof = [_prof_row()]
        db = _make_db([prof, [], [], []])
        result = await compute_health_scores(db, 'S001', '2025-01')
        total = sum(result['tier_counts'].values())
        assert total == 1


# ── TestGetHealthScores ───────────────────────────────────────────────────────
class TestGetHealthScores:
    def _row(self, tier='good'):
        return (
            1, 'D001', '宫保鸡丁', '热菜',
            13.5, 16.0, 18.0, 19.0, 66.5,
            tier, 'benchmark', 'growth',
            'maintain', '保持现状', '保持现有策略',
            150.0, 'peak', 4560.0,
        )

    @pytest.mark.asyncio
    async def test_no_filter(self):
        db = _make_db([[self._row()]])
        recs = await get_health_scores(db, 'S001', '2025-01')
        assert len(recs) == 1
        assert recs[0]['health_tier'] == 'good'

    @pytest.mark.asyncio
    async def test_tier_filter(self):
        db = _make_db([[self._row('excellent')]])
        recs = await get_health_scores(db, 'S001', '2025-01', health_tier='excellent')
        assert len(recs) == 1
        assert recs[0]['health_tier'] == 'excellent'

    @pytest.mark.asyncio
    async def test_empty(self):
        db = _make_db([[]])
        recs = await get_health_scores(db, 'S001', '2025-01')
        assert recs == []


# ── TestGetHealthSummary ──────────────────────────────────────────────────────
class TestGetHealthSummary:
    @pytest.mark.asyncio
    async def test_aggregation(self):
        rows = [
            ('excellent', 4, 85.0, 600.0, 22.0, 23.0, 20.0, 24.0),
            ('good',      6, 67.0, 300.0, 14.0, 16.0, 18.0, 19.0),
            ('fair',      2, 45.0, 500.0,  9.0,  8.0, 10.0, 17.0),
            ('poor',      1, 30.0, 250.0,  5.0,  3.0,  3.0, 10.0),
        ]
        db = _make_db([rows])
        result = await get_health_summary(db, 'S001', '2025-01')
        assert result['total_dishes'] == 13
        assert result['total_impact_yuan'] == pytest.approx(1650.0, abs=1.0)
        assert len(result['by_tier']) == 4

    @pytest.mark.asyncio
    async def test_empty(self):
        db = _make_db([[]])
        result = await get_health_summary(db, 'S001', '2025-01')
        assert result['total_dishes'] == 0
        assert result['total_impact_yuan'] == 0.0


# ── TestGetActionPriorities ───────────────────────────────────────────────────
class TestGetActionPriorities:
    @pytest.mark.asyncio
    async def test_returns_items(self):
        row = ('D001', '宫保鸡丁', '热菜', 'poor', 32.5,
               'growth', '改善成长轨迹', '建议...', 1140.0, 'decline', 4560.0)
        db = _make_db([[row]])
        items = await get_action_priorities(db, 'S001', '2025-01',
                                             priority='immediate')
        assert len(items) == 1
        assert items[0]['dish_name'] == '宫保鸡丁'
        assert items[0]['expected_impact_yuan'] == pytest.approx(1140.0)

    @pytest.mark.asyncio
    async def test_empty(self):
        db = _make_db([[]])
        items = await get_action_priorities(db, 'S001', '2025-01',
                                             priority='promote')
        assert items == []


# ── TestGetDishHealthHistory ──────────────────────────────────────────────────
class TestGetDishHealthHistory:
    @pytest.mark.asyncio
    async def test_returns_history(self):
        rows = [
            ('2025-02', 72.5, 'good',   14.0, 18.0, 18.0, 22.5, 'maintain', 'peak',    217.5),
            ('2025-01', 65.0, 'good',   13.0, 16.0, 18.0, 18.0, 'maintain', 'peak',    195.0),
            ('2024-12', 58.5, 'fair',   11.0, 14.0, 18.0, 15.5, 'monitor',  'decline', 585.0),
        ]
        db = _make_db([rows])
        history = await get_dish_health_history(db, 'S001', 'D001')
        assert len(history) == 3
        assert history[0]['period'] == '2025-02'
        assert history[0]['total_score'] == pytest.approx(72.5)
        assert history[2]['action_priority'] == 'monitor'

    @pytest.mark.asyncio
    async def test_empty(self):
        db = _make_db([[]])
        history = await get_dish_health_history(db, 'S001', 'D999')
        assert history == []
