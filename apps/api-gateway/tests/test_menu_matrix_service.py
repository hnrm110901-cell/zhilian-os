"""tests/test_menu_matrix_service.py — Phase 6 Month 10"""

import pytest
from unittest.mock import MagicMock, AsyncMock

import src.core.config  # noqa: F401

from src.services.menu_matrix_service import (
    _prev_period,
    compute_percentile,
    compute_delta_pct,
    classify_quadrant,
    determine_action,
    determine_priority,
    compute_impact,
    compute_contribution_pct,
    build_matrix_record,
    compute_menu_matrix,
    get_menu_matrix,
    get_matrix_summary,
    get_top_actions,
    get_dish_quadrant_history,
)


# ── _prev_period ──────────────────────────────────────────────────────────────

class TestPrevPeriod:
    def test_mid_year(self):
        assert _prev_period('2025-06') == '2025-05'

    def test_january(self):
        assert _prev_period('2025-01') == '2024-12'


# ── compute_percentile ────────────────────────────────────────────────────────

class TestComputePercentile:
    def test_empty_list(self):
        assert compute_percentile(100.0, []) == 50.0

    def test_single_element(self):
        # rank=0 (no element less than 100), pct = 0/1*100 = 0.0
        assert compute_percentile(100.0, [100.0]) == 0.0

    def test_highest(self):
        # [10, 20, 30, 40, 50] → value=50, rank=4, pct=4/5*100=80
        assert compute_percentile(50.0, [10.0, 20.0, 30.0, 40.0, 50.0]) == 80.0

    def test_lowest(self):
        assert compute_percentile(10.0, [10.0, 20.0, 30.0, 40.0, 50.0]) == 0.0

    def test_middle(self):
        # value=30, rank=2, pct=2/5*100=40
        assert compute_percentile(30.0, [10.0, 20.0, 30.0, 40.0, 50.0]) == 40.0

    def test_all_same(self):
        # rank=0 for all → 0.0
        assert compute_percentile(5.0, [5.0, 5.0, 5.0]) == 0.0


# ── compute_delta_pct ─────────────────────────────────────────────────────────

class TestComputeDeltaPct:
    def test_increase(self):
        assert compute_delta_pct(120.0, 100.0) == 20.0

    def test_decrease(self):
        assert compute_delta_pct(80.0, 100.0) == -20.0

    def test_zero_previous(self):
        assert compute_delta_pct(100.0, 0.0) is None

    def test_no_change(self):
        assert compute_delta_pct(100.0, 100.0) == 0.0


# ── classify_quadrant ─────────────────────────────────────────────────────────

class TestClassifyQuadrant:
    def test_star(self):
        assert classify_quadrant(75.0, 80.0) == 'star'

    def test_cash_cow(self):
        assert classify_quadrant(80.0, 30.0) == 'cash_cow'

    def test_question_mark(self):
        assert classify_quadrant(20.0, 90.0) == 'question_mark'

    def test_dog(self):
        assert classify_quadrant(10.0, 10.0) == 'dog'

    def test_boundary_50_50(self):
        # exactly 50 is NOT > 50, so it's dog quadrant
        assert classify_quadrant(50.0, 50.0) == 'dog'

    def test_boundary_51_51(self):
        assert classify_quadrant(51.0, 51.0) == 'star'


# ── determine_action ──────────────────────────────────────────────────────────

class TestDetermineAction:
    def test_star_promote(self):
        assert determine_action('star') == 'promote'

    def test_cash_cow_maintain(self):
        assert determine_action('cash_cow') == 'maintain'

    def test_question_mark_develop(self):
        assert determine_action('question_mark') == 'develop'

    def test_dog_retire(self):
        assert determine_action('dog') == 'retire'


# ── determine_priority ────────────────────────────────────────────────────────

class TestDeterminePriority:
    def test_star_high_revenue(self):
        assert determine_priority('star', 80.0, 70.0) == 'high'

    def test_star_medium(self):
        assert determine_priority('star', 60.0, 60.0) == 'medium'

    def test_cash_cow_declining(self):
        assert determine_priority('cash_cow', 70.0, 20.0) == 'high'

    def test_cash_cow_medium(self):
        assert determine_priority('cash_cow', 70.0, 40.0) == 'medium'

    def test_question_mark_fast(self):
        assert determine_priority('question_mark', 30.0, 90.0) == 'high'

    def test_question_mark_medium(self):
        assert determine_priority('question_mark', 30.0, 60.0) == 'medium'

    def test_dog_very_low(self):
        assert determine_priority('dog', 10.0, 10.0) == 'high'

    def test_dog_medium(self):
        assert determine_priority('dog', 40.0, 10.0) == 'medium'


# ── compute_impact ────────────────────────────────────────────────────────────

class TestComputeImpact:
    def test_promote(self):
        assert compute_impact(10000.0, 'promote') == 1500.0

    def test_maintain(self):
        assert compute_impact(10000.0, 'maintain') == 500.0

    def test_develop(self):
        assert compute_impact(10000.0, 'develop') == 2500.0

    def test_retire(self):
        assert compute_impact(10000.0, 'retire') == 300.0


# ── compute_contribution_pct ──────────────────────────────────────────────────

class TestComputeContributionPct:
    def test_normal(self):
        assert compute_contribution_pct(2000.0, 10000.0) == 20.0

    def test_zero_total(self):
        assert compute_contribution_pct(2000.0, 0.0) is None


# ── build_matrix_record ───────────────────────────────────────────────────────

class TestBuildMatrixRecord:
    def _make(self, rev_pct=80.0, grow_pct=70.0, rev=10000.0, prev_rev=8000.0):
        return build_matrix_record(
            'S001', '2025-06', '2025-05',
            'D001', '红烧肉', '主菜',
            rev, 100, prev_rev,
            rev_pct, grow_pct, 25.0,
        )

    def test_keys_present(self):
        r = self._make()
        for k in ['store_id', 'period', 'prev_period', 'dish_id', 'dish_name',
                  'category', 'revenue_yuan', 'order_count', 'menu_contribution_pct',
                  'prev_revenue_yuan', 'revenue_delta_pct',
                  'revenue_percentile', 'growth_percentile',
                  'matrix_quadrant', 'optimization_action', 'action_priority',
                  'expected_impact_yuan']:
            assert k in r

    def test_star_promote(self):
        r = self._make(rev_pct=80.0, grow_pct=75.0)
        assert r['matrix_quadrant'] == 'star'
        assert r['optimization_action'] == 'promote'

    def test_dog_retire(self):
        r = self._make(rev_pct=20.0, grow_pct=20.0)
        assert r['matrix_quadrant'] == 'dog'
        assert r['optimization_action'] == 'retire'

    def test_delta_pct(self):
        r = self._make(rev=12000.0, prev_rev=10000.0)
        assert r['revenue_delta_pct'] == 20.0

    def test_no_prev(self):
        r = build_matrix_record(
            'S001', '2025-06', '2025-05',
            'D001', '红烧肉', None,
            10000.0, 100, None, 60.0, 60.0, None,
        )
        assert r['revenue_delta_pct'] is None
        assert r['prev_revenue_yuan'] is None


# ── DB helpers ────────────────────────────────────────────────────────────────

def _make_db(call_returns: list):
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


# ── compute_menu_matrix ───────────────────────────────────────────────────────

class TestComputeMenuMatrix:
    @pytest.mark.asyncio
    async def test_basic(self):
        curr = [
            ('D001', '红烧肉', '主菜', 100, 10000.0),
            ('D002', '炒饭',   '主食',  50,  3000.0),
            ('D003', '凉拌黄瓜', '凉菜', 30,  1000.0),
        ]
        prev = [
            ('D001', '红烧肉', '主菜', 80, 8000.0),
            ('D002', '炒饭',   '主食', 60, 3500.0),
        ]
        db = _make_db([curr, prev, [], [], []])
        result = await compute_menu_matrix(db, 'S001', '2025-06')
        assert result['dish_count'] == 3
        assert result['new_dishes'] == 1   # D003 无上期数据
        assert sum(result['quadrant_counts'].values()) == 3

    @pytest.mark.asyncio
    async def test_empty_period(self):
        db = _make_db([[], []])
        result = await compute_menu_matrix(db, 'S001', '2025-06')
        assert result['dish_count'] == 0
        assert result['quadrant_counts'] == {}

    @pytest.mark.asyncio
    async def test_default_prev_period(self):
        db = _make_db([[], []])
        result = await compute_menu_matrix(db, 'S001', '2025-03')
        assert result['prev_period'] == '2025-02'

    @pytest.mark.asyncio
    async def test_explicit_prev_period(self):
        curr = [('D001', '菜A', None, 100, 5000.0)]
        prev = [('D001', '菜A', None, 80, 4000.0)]
        db = _make_db([curr, prev, []])
        result = await compute_menu_matrix(db, 'S001', '2025-06', '2025-04')
        assert result['prev_period'] == '2025-04'


# ── get_menu_matrix ───────────────────────────────────────────────────────────

class TestGetMenuMatrix:
    def _row(self):
        return (1, 'D001', '红烧肉', '主菜',
                10000.0, 100, 25.0,
                8000.0, 25.0,
                80.0, 75.0,
                'star', 'promote', 'high', 1500.0)

    @pytest.mark.asyncio
    async def test_no_filter(self):
        db = _make_db([[self._row()]])
        result = await get_menu_matrix(db, 'S001', '2025-06')
        assert len(result) == 1
        assert result[0]['matrix_quadrant'] == 'star'

    @pytest.mark.asyncio
    async def test_quadrant_filter(self):
        db = _make_db([[self._row()]])
        result = await get_menu_matrix(db, 'S001', '2025-06', quadrant='star')
        assert result[0]['optimization_action'] == 'promote'

    @pytest.mark.asyncio
    async def test_action_filter(self):
        db = _make_db([[self._row()]])
        result = await get_menu_matrix(db, 'S001', '2025-06', action='promote')
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_priority_filter(self):
        db = _make_db([[self._row()]])
        result = await get_menu_matrix(db, 'S001', '2025-06', priority='high')
        assert len(result) == 1


# ── get_matrix_summary ────────────────────────────────────────────────────────

class TestGetMatrixSummary:
    @pytest.mark.asyncio
    async def test_basic(self):
        rows = [
            ('star',          5, 50000.0, 75.0, 70.0, 7500.0, 3),
            ('cash_cow',      8, 40000.0, 70.0, 30.0, 2000.0, 2),
            ('question_mark', 3, 10000.0, 30.0, 75.0, 2500.0, 2),
            ('dog',           4,  5000.0, 20.0, 20.0,  150.0, 3),
        ]
        db = _make_db([rows])
        result = await get_matrix_summary(db, 'S001', '2025-06')
        assert result['total_dishes'] == 20
        assert result['total_revenue'] == 105000.0
        assert len(result['by_quadrant']) == 4

    @pytest.mark.asyncio
    async def test_empty(self):
        db = _make_db([[]])
        result = await get_matrix_summary(db, 'S001', '2025-06')
        assert result['total_dishes'] == 0


# ── get_top_actions ───────────────────────────────────────────────────────────

class TestGetTopActions:
    @pytest.mark.asyncio
    async def test_basic(self):
        row = ('D001', '红烧肉', '主菜',
               10000.0, 25.0, 80.0, 75.0, 'star', 'high', 1500.0)
        db = _make_db([[row]])
        result = await get_top_actions(db, 'S001', '2025-06', action='promote')
        assert len(result) == 1
        assert result[0]['expected_impact_yuan'] == 1500.0


# ── get_dish_quadrant_history ─────────────────────────────────────────────────

class TestGetDishQuadrantHistory:
    @pytest.mark.asyncio
    async def test_basic(self):
        rows = [
            ('2025-06', 'star',     'promote', 'high',   10000.0, 25.0, 80.0, 75.0, 1500.0),
            ('2025-05', 'cash_cow', 'maintain', 'medium', 8000.0, 10.0, 75.0, 40.0,  400.0),
        ]
        db = _make_db([rows])
        result = await get_dish_quadrant_history(db, 'S001', 'D001', periods=6)
        assert len(result) == 2
        assert result[0]['matrix_quadrant'] == 'star'
        assert result[1]['matrix_quadrant'] == 'cash_cow'
