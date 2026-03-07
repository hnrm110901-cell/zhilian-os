"""Tests for dish_benchmark_service — Phase 6 Month 4"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# ── mock config before import ──────────────────────────────────────────────────
import sys, types

cfg_mod = types.ModuleType("src.core.config")
cfg_mod.settings = MagicMock(
    database_url="postgresql+asyncpg://x:x@localhost/x",
    redis_url="redis://localhost",
    secret_key="test",
)
sys.modules.setdefault("src.core.config", cfg_mod)
sys.modules.setdefault("src.core.database", types.ModuleType("src.core.database"))

from src.services.dish_benchmark_service import (
    compute_cross_store_rank,
    compute_cross_store_percentile,
    find_best_store,
    classify_benchmark_tier,
    compute_gap_pp,
    compute_gap_yuan_impact,
    build_dish_benchmark_records,
    _start_period,
    compute_dish_benchmarks,
    get_dish_benchmark,
    get_store_benchmark_summary,
    get_laggard_dishes,
    get_benchmark_trend,
    get_dish_cross_store_detail,
)

# ── 3-store fixture ────────────────────────────────────────────────────────────
STORE_DATA = [
    {
        'store_id': 'S001', 'food_cost_rate': 35.0,
        'gross_profit_margin': 65.0, 'order_count': 150, 'revenue_yuan': 7500.0,
    },
    {
        'store_id': 'S002', 'food_cost_rate': 42.0,
        'gross_profit_margin': 58.0, 'order_count': 120, 'revenue_yuan': 6000.0,
    },
    {
        'store_id': 'S003', 'food_cost_rate': 50.0,
        'gross_profit_margin': 50.0, 'order_count': 80, 'revenue_yuan': 4000.0,
    },
]


# ── TestComputeCrossStoreRank ──────────────────────────────────────────────────
class TestComputeCrossStoreRank:
    def test_higher_is_better_best(self):
        assert compute_cross_store_rank(65.0, [65.0, 58.0, 50.0], True) == 1

    def test_higher_is_better_middle(self):
        assert compute_cross_store_rank(58.0, [65.0, 58.0, 50.0], True) == 2

    def test_higher_is_better_worst(self):
        assert compute_cross_store_rank(50.0, [65.0, 58.0, 50.0], True) == 3

    def test_lower_is_better_best(self):
        assert compute_cross_store_rank(35.0, [35.0, 42.0, 50.0], False) == 1

    def test_lower_is_better_worst(self):
        assert compute_cross_store_rank(50.0, [35.0, 42.0, 50.0], False) == 3

    def test_tie_returns_same_rank(self):
        # both 42.0 should get rank 2
        assert compute_cross_store_rank(42.0, [35.0, 42.0, 42.0], False) == 2

    def test_single_value(self):
        assert compute_cross_store_rank(42.0, [42.0], True) == 1


# ── TestComputeCrossStorePercentile ───────────────────────────────────────────
class TestComputeCrossStorePercentile:
    def test_single_value_returns_100(self):
        assert compute_cross_store_percentile(42.0, [42.0], True) == 100.0

    def test_best_higher_is_better(self):
        pct = compute_cross_store_percentile(65.0, [65.0, 58.0, 50.0], True)
        assert pct == 100.0

    def test_worst_higher_is_better(self):
        pct = compute_cross_store_percentile(50.0, [65.0, 58.0, 50.0], True)
        assert pct == 0.0

    def test_middle_higher_is_better(self):
        # 1 value below 58 / (3-1) * 100 = 50.0
        pct = compute_cross_store_percentile(58.0, [65.0, 58.0, 50.0], True)
        assert pct == 50.0

    def test_best_lower_is_better(self):
        pct = compute_cross_store_percentile(35.0, [35.0, 42.0, 50.0], False)
        assert pct == 100.0

    def test_worst_lower_is_better(self):
        pct = compute_cross_store_percentile(50.0, [35.0, 42.0, 50.0], False)
        assert pct == 0.0


# ── TestFindBestStore ─────────────────────────────────────────────────────────
class TestFindBestStore:
    def test_higher_is_better(self):
        sv = [('S001', 65.0), ('S002', 58.0), ('S003', 50.0)]
        sid, val = find_best_store(sv, higher_is_better=True)
        assert sid == 'S001' and val == 65.0

    def test_lower_is_better(self):
        sv = [('S001', 35.0), ('S002', 42.0), ('S003', 50.0)]
        sid, val = find_best_store(sv, higher_is_better=False)
        assert sid == 'S001' and val == 35.0

    def test_empty_returns_none(self):
        sid, val = find_best_store([], True)
        assert sid is None and val == 0.0

    def test_single_entry(self):
        sid, val = find_best_store([('S001', 42.0)], True)
        assert sid == 'S001' and val == 42.0


# ── TestClassifyBenchmarkTier ─────────────────────────────────────────────────
class TestClassifyBenchmarkTier:
    def test_top(self):
        assert classify_benchmark_tier(100.0) == 'top'
        assert classify_benchmark_tier(75.0) == 'top'

    def test_above_avg(self):
        assert classify_benchmark_tier(74.9) == 'above_avg'
        assert classify_benchmark_tier(50.0) == 'above_avg'

    def test_below_avg(self):
        assert classify_benchmark_tier(49.9) == 'below_avg'
        assert classify_benchmark_tier(25.0) == 'below_avg'

    def test_laggard(self):
        assert classify_benchmark_tier(24.9) == 'laggard'
        assert classify_benchmark_tier(0.0) == 'laggard'


# ── TestComputeGapPp ──────────────────────────────────────────────────────────
class TestComputeGapPp:
    def test_fcr_gap_best_store(self):
        # S001 is best FCR, gap = 0
        assert compute_gap_pp(35.0, 35.0, higher_is_better=False) == 0.0

    def test_fcr_gap_laggard(self):
        assert compute_gap_pp(50.0, 35.0, higher_is_better=False) == 15.0

    def test_gpm_gap_best_store(self):
        assert compute_gap_pp(65.0, 65.0, higher_is_better=True) == 0.0

    def test_gpm_gap_laggard(self):
        assert compute_gap_pp(50.0, 65.0, higher_is_better=True) == 15.0

    def test_negative_clipped_to_zero(self):
        # if store is better than "best" (shouldn't happen but guard it)
        assert compute_gap_pp(30.0, 35.0, higher_is_better=False) == 0.0


# ── TestComputeGapYuanImpact ──────────────────────────────────────────────────
class TestComputeGapYuanImpact:
    def test_basic(self):
        assert compute_gap_yuan_impact(4000.0, 15.0) == 600.0

    def test_zero_gap(self):
        assert compute_gap_yuan_impact(7500.0, 0.0) == 0.0

    def test_fractional(self):
        result = compute_gap_yuan_impact(6000.0, 7.0)
        assert abs(result - 420.0) < 0.01


# ── TestBuildDishBenchmarkRecords ─────────────────────────────────────────────
class TestBuildDishBenchmarkRecords:
    def test_returns_empty_for_single_store(self):
        recs = build_dish_benchmark_records('2025-01', '宫保鸡丁', [STORE_DATA[0]])
        assert recs == []

    def test_correct_count(self):
        recs = build_dish_benchmark_records('2025-01', '宫保鸡丁', STORE_DATA)
        assert len(recs) == 3

    def test_s001_is_fcr_rank1(self):
        recs = build_dish_benchmark_records('2025-01', '宫保鸡丁', STORE_DATA)
        s001 = next(r for r in recs if r['store_id'] == 'S001')
        assert s001['fcr_rank'] == 1

    def test_s001_fcr_gap_is_zero(self):
        recs = build_dish_benchmark_records('2025-01', '宫保鸡丁', STORE_DATA)
        s001 = next(r for r in recs if r['store_id'] == 'S001')
        assert s001['fcr_gap_pp'] == 0.0
        assert s001['fcr_gap_yuan_impact'] == 0.0

    def test_s003_fcr_laggard(self):
        recs = build_dish_benchmark_records('2025-01', '宫保鸡丁', STORE_DATA)
        s003 = next(r for r in recs if r['store_id'] == 'S003')
        assert s003['fcr_tier'] == 'laggard'
        assert s003['fcr_gap_pp'] == 15.0
        assert s003['fcr_gap_yuan_impact'] == 600.0  # 15/100 * 4000

    def test_s002_fcr_gap(self):
        recs = build_dish_benchmark_records('2025-01', '宫保鸡丁', STORE_DATA)
        s002 = next(r for r in recs if r['store_id'] == 'S002')
        assert s002['fcr_gap_pp'] == 7.0
        assert abs(s002['fcr_gap_yuan_impact'] - 420.0) < 0.01  # 7/100 * 6000

    def test_s001_is_gpm_rank1(self):
        recs = build_dish_benchmark_records('2025-01', '宫保鸡丁', STORE_DATA)
        s001 = next(r for r in recs if r['store_id'] == 'S001')
        assert s001['gpm_rank'] == 1

    def test_s003_gpm_laggard(self):
        recs = build_dish_benchmark_records('2025-01', '宫保鸡丁', STORE_DATA)
        s003 = next(r for r in recs if r['store_id'] == 'S003')
        assert s003['gpm_tier'] == 'laggard'
        assert s003['gpm_gap_pp'] == 15.0

    def test_store_count_field(self):
        recs = build_dish_benchmark_records('2025-01', '宫保鸡丁', STORE_DATA)
        for r in recs:
            assert r['store_count'] == 3

    def test_best_fcr_store_is_s001(self):
        recs = build_dish_benchmark_records('2025-01', '宫保鸡丁', STORE_DATA)
        for r in recs:
            assert r['best_fcr_store_id'] == 'S001'
            assert r['best_fcr_value'] == 35.0

    def test_period_and_dish_name_propagated(self):
        recs = build_dish_benchmark_records('2025-06', '红烧肉', STORE_DATA)
        for r in recs:
            assert r['period'] == '2025-06'
            assert r['dish_name'] == '红烧肉'

    def test_two_stores_minimum(self):
        two = STORE_DATA[:2]
        recs = build_dish_benchmark_records('2025-01', '宫保鸡丁', two)
        assert len(recs) == 2
        s001 = next(r for r in recs if r['store_id'] == 'S001')
        s002 = next(r for r in recs if r['store_id'] == 'S002')
        assert s001['fcr_gap_pp'] == 0.0
        assert s002['fcr_gap_pp'] == 7.0


# ── TestStartPeriod ───────────────────────────────────────────────────────────
class TestStartPeriod:
    def test_no_year_wrap(self):
        assert _start_period('2025-06', 6) == '2025-01'

    def test_year_wrap(self):
        assert _start_period('2025-03', 6) == '2024-10'

    def test_single_period(self):
        assert _start_period('2025-06', 1) == '2025-06'

    def test_january_wrap(self):
        assert _start_period('2025-01', 3) == '2024-11'


# ── DB helper ─────────────────────────────────────────────────────────────────
def _make_db(call_returns: list):
    """Build a minimal AsyncSession mock that returns results in sequence."""
    db = AsyncMock()
    results = iter(call_returns)
    async def execute(sql, params=None):
        result = MagicMock()
        result.fetchall.return_value = next(results)
        return result
    db.execute = execute
    db.commit = AsyncMock()
    return db


# ── TestComputeDishBenchmarks ─────────────────────────────────────────────────
class TestComputeDishBenchmarks:
    @pytest.mark.asyncio
    async def test_basic_two_dishes_two_stores(self):
        # _fetch_cross_store_dish_data returns 4 rows: 2 dishes × 2 stores
        rows = [
            ('宫保鸡丁', 'S001', 35.0, 65.0, 150, 7500.0),
            ('宫保鸡丁', 'S002', 42.0, 58.0, 120, 6000.0),
            ('红烧肉',   'S001', 40.0, 60.0, 100, 5000.0),
            ('红烧肉',   'S002', 48.0, 52.0,  80, 4000.0),
        ]
        db = _make_db([rows])
        result = await compute_dish_benchmarks(db, '2025-01')
        assert result['dish_count'] == 2
        assert result['store_count'] == 2
        assert result['record_count'] == 4
        assert result['skipped_count'] == 0

    @pytest.mark.asyncio
    async def test_single_store_dish_skipped(self):
        rows = [
            ('宫保鸡丁', 'S001', 35.0, 65.0, 150, 7500.0),
            ('宫保鸡丁', 'S002', 42.0, 58.0, 120, 6000.0),
            ('孤独菜',   'S001', 40.0, 60.0, 100, 5000.0),  # only 1 store
        ]
        db = _make_db([rows])
        result = await compute_dish_benchmarks(db, '2025-01')
        assert result['skipped_count'] == 1
        assert result['record_count'] == 2

    @pytest.mark.asyncio
    async def test_empty_returns_zeros(self):
        db = _make_db([[]])
        result = await compute_dish_benchmarks(db, '2025-01')
        assert result['dish_count'] == 0
        assert result['record_count'] == 0


# ── TestGetDishBenchmark ──────────────────────────────────────────────────────
class TestGetDishBenchmark:
    @pytest.mark.asyncio
    async def test_no_filter(self):
        row = (1, '宫保鸡丁', 3, 35.0, 65.0, 150, 7500.0,
               1, 100.0, 'top', 35.0, 'S001', 0.0, 0.0,
               1, 100.0, 'top', 65.0, 'S001', 0.0, 0.0)
        db = _make_db([[row]])
        results = await get_dish_benchmark(db, 'S001', '2025-01')
        assert len(results) == 1
        assert results[0]['dish_name'] == '宫保鸡丁'
        assert results[0]['fcr_tier'] == 'top'

    @pytest.mark.asyncio
    async def test_with_fcr_tier_filter(self):
        row = (2, '红烧肉', 3, 50.0, 50.0, 80, 4000.0,
               3, 0.0, 'laggard', 35.0, 'S001', 15.0, 600.0,
               3, 0.0, 'laggard', 65.0, 'S001', 15.0, 600.0)
        db = _make_db([[row]])
        results = await get_dish_benchmark(db, 'S003', '2025-01', fcr_tier='laggard')
        assert len(results) == 1
        assert results[0]['fcr_tier'] == 'laggard'


# ── TestGetStoreBenchmarkSummary ──────────────────────────────────────────────
class TestGetStoreBenchmarkSummary:
    @pytest.mark.asyncio
    async def test_aggregation(self):
        rows = [
            ('laggard', 3, 800.0, 700.0, 12.0, 10.0),
            ('top',     2, 0.0,   0.0,   0.0,  0.0),
        ]
        db = _make_db([rows])
        result = await get_store_benchmark_summary(db, 'S003', '2025-01')
        assert result['total_dishes'] == 5
        assert result['total_fcr_potential'] == 800.0
        assert len(result['by_tier']) == 2

    @pytest.mark.asyncio
    async def test_empty_store(self):
        db = _make_db([[]])
        result = await get_store_benchmark_summary(db, 'S999', '2025-01')
        assert result['total_dishes'] == 0
        assert result['total_fcr_potential'] == 0.0


# ── TestGetLaggardDishes ──────────────────────────────────────────────────────
class TestGetLaggardDishes:
    @pytest.mark.asyncio
    async def test_returns_dishes(self):
        row = ('红烧肉', 50.0, 50.0, 80, 4000.0, 3, 3,
               35.0, 'S001', 15.0, 600.0, 65.0, 'S001', 15.0, 600.0,
               0.0, 0.0, 'laggard', 'laggard')
        db = _make_db([[row]])
        dishes = await get_laggard_dishes(db, 'S003', '2025-01')
        assert len(dishes) == 1
        assert dishes[0]['dish_name'] == '红烧肉'
        assert dishes[0]['fcr_gap_yuan_impact'] == 600.0

    @pytest.mark.asyncio
    async def test_empty(self):
        db = _make_db([[]])
        dishes = await get_laggard_dishes(db, 'S001', '2025-01')
        assert dishes == []


# ── TestGetBenchmarkTrend ─────────────────────────────────────────────────────
class TestGetBenchmarkTrend:
    @pytest.mark.asyncio
    async def test_trend_rows(self):
        rows = [
            ('2024-11', 5, 2, 1, 8.5, 7.2, 900.0, 800.0),
            ('2024-12', 5, 1, 2, 5.0, 4.0, 500.0, 400.0),
            ('2025-01', 5, 0, 3, 2.0, 1.5, 200.0, 150.0),
        ]
        db = _make_db([rows])
        trend = await get_benchmark_trend(db, 'S003', '2025-01', periods=3)
        assert len(trend) == 3
        assert trend[0]['period'] == '2024-11'
        assert trend[2]['laggard_count'] == 0
        assert trend[2]['top_count'] == 3

    @pytest.mark.asyncio
    async def test_empty_trend(self):
        db = _make_db([[]])
        trend = await get_benchmark_trend(db, 'S999', '2025-01')
        assert trend == []


# ── TestGetDishCrossStoreDetail ───────────────────────────────────────────────
class TestGetDishCrossStoreDetail:
    @pytest.mark.asyncio
    async def test_returns_all_stores_for_dish(self):
        rows = [
            ('S001', 3, 35.0, 65.0, 150, 7500.0, 1, 100.0, 'top', 0.0, 0.0,
             1, 100.0, 'top', 0.0, 0.0),
            ('S002', 3, 42.0, 58.0, 120, 6000.0, 2, 50.0, 'above_avg', 7.0, 420.0,
             2, 50.0, 'above_avg', 7.0, 420.0),
            ('S003', 3, 50.0, 50.0, 80, 4000.0,  3, 0.0, 'laggard', 15.0, 600.0,
             3, 0.0, 'laggard', 15.0, 600.0),
        ]
        db = _make_db([rows])
        detail = await get_dish_cross_store_detail(db, '宫保鸡丁', '2025-01')
        assert len(detail) == 3
        assert detail[0]['store_id'] == 'S001'
        assert detail[2]['fcr_tier'] == 'laggard'
        assert detail[2]['fcr_gap_yuan_impact'] == 600.0

    @pytest.mark.asyncio
    async def test_dish_not_benchmarked(self):
        db = _make_db([[]])
        detail = await get_dish_cross_store_detail(db, '未知菜', '2025-01')
        assert detail == []
