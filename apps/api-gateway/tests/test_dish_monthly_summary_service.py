"""tests/test_dish_monthly_summary_service.py — Phase 6 Month 12"""

import pytest
from unittest.mock import MagicMock, AsyncMock

import src.core.config  # noqa: F401

from src.services.dish_monthly_summary_service import (
    _prev_period,
    compute_revenue_delta_pct,
    compute_data_sources_available,
    generate_insight_text,
    build_dish_monthly_summary,
    get_dish_monthly_summary,
    get_summary_history,
)


# ── _prev_period ──────────────────────────────────────────────────────────────

class TestPrevPeriod:
    def test_mid_year(self):
        assert _prev_period('2025-08') == '2025-07'

    def test_january(self):
        assert _prev_period('2025-01') == '2024-12'


# ── compute_revenue_delta_pct ─────────────────────────────────────────────────

class TestComputeRevenueDeltaPct:
    def test_increase(self):
        assert compute_revenue_delta_pct(110000.0, 100000.0) == 10.0

    def test_decrease(self):
        assert compute_revenue_delta_pct(90000.0, 100000.0) == -10.0

    def test_zero_previous(self):
        assert compute_revenue_delta_pct(100000.0, 0.0) is None

    def test_no_change(self):
        assert compute_revenue_delta_pct(100000.0, 100000.0) == 0.0


# ── compute_data_sources_available ───────────────────────────────────────────

class TestComputeDataSourcesAvailable:
    def test_all_present(self):
        assert compute_data_sources_available({'a': 1}, {'b': 2}, [1], 'x', 5.0) == 5

    def test_some_none(self):
        assert compute_data_sources_available({'a': 1}, None, None, 'x', None) == 2

    def test_all_none(self):
        assert compute_data_sources_available(None, None, None, None, None) == 0

    def test_single(self):
        assert compute_data_sources_available({'a': 1}) == 1


# ── generate_insight_text ─────────────────────────────────────────────────────

class TestGenerateInsightText:
    def _call(self, **kwargs):
        defaults = dict(
            total_dishes=20,
            revenue_delta_pct=None,
            avg_health_score=None,
            star_count=None,
            dog_count=None,
            total_expected_saving=None,
            dominant_driver=None,
            worsening_fcr_count=None,
        )
        defaults.update(kwargs)
        return generate_insight_text(**defaults)

    def test_default_text(self):
        text = self._call()
        assert '平稳' in text

    def test_strong_revenue_growth(self):
        text = self._call(revenue_delta_pct=15.0)
        assert '大幅增长' in text

    def test_moderate_growth(self):
        text = self._call(revenue_delta_pct=5.0)
        assert '稳健增长' in text

    def test_large_decline(self):
        text = self._call(revenue_delta_pct=-12.0)
        assert '大幅下滑' in text

    def test_small_decline(self):
        text = self._call(revenue_delta_pct=-5.0)
        assert '小幅下滑' in text

    def test_good_health_score(self):
        text = self._call(avg_health_score=80.0)
        assert '健康' in text or '优质' in text

    def test_poor_health_score(self):
        text = self._call(avg_health_score=40.0)
        assert '偏低' in text

    def test_high_star_ratio(self):
        text = self._call(star_count=8, dog_count=2, total_dishes=20)
        assert '明星菜' in text

    def test_high_dog_ratio(self):
        text = self._call(star_count=2, dog_count=8, total_dishes=20)
        assert '瘦狗菜' in text

    def test_large_saving(self):
        text = self._call(total_expected_saving=60000.0)
        assert '年化成本压缩' in text

    def test_moderate_saving(self):
        text = self._call(total_expected_saving=15000.0)
        assert '年化成本压缩' in text

    def test_dominant_driver_price(self):
        text = self._call(dominant_driver='price')
        assert '价格变动' in text

    def test_dominant_driver_volume(self):
        text = self._call(dominant_driver='volume')
        assert '销量变动' in text

    def test_max_4_parts(self):
        text = self._call(
            revenue_delta_pct=15.0,
            avg_health_score=80.0,
            star_count=8, dog_count=9, total_dishes=20,
            total_expected_saving=60000.0,
            dominant_driver='price',
        )
        # max 4 segments separated by ；
        assert text.count('；') <= 3

    def test_no_stable_in_nonempty_insight(self):
        text = self._call(revenue_delta_pct=20.0)
        assert '平稳' not in text


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
        result.fetchone.return_value = rows[0] if rows else None
        result.fetchall.return_value = rows
        return result

    db.execute = _execute
    return db


# ── build_dish_monthly_summary ────────────────────────────────────────────────

class TestBuildDishMonthlySummary:
    def _prof_row(self):
        # (total_dishes, total_revenue)
        return (20, 150000.0)

    def _prev_row(self):
        return (130000.0,)

    @pytest.mark.asyncio
    async def test_basic_all_sources(self):
        # fetch order: prof_curr, prof_prev, health, matrix,
        #              attrib, attrib_driver, compression, upsert
        health_row = (72.5, 5, 8, 4, 3, 2)
        matrix_row = (6, 7, 4, 3, 15000.0)
        attrib_row = (18, 20000.0, 8000.0, 12000.0)
        attrib_dr  = ('volume', 10)
        compr_row  = (15, 3000.0, 36000.0, 2, 3)

        db = _make_db([
            [self._prof_row()],
            [self._prev_row()],
            [health_row],
            [matrix_row],
            [attrib_row],
            [attrib_dr],
            [compr_row],
            [],  # upsert
        ])
        result = await build_dish_monthly_summary(db, 'S001', '2025-06')

        assert result['total_dishes'] == 20
        assert result['total_revenue'] == 150000.0
        assert result['prev_revenue'] == 130000.0
        assert round(result['revenue_delta_pct'], 1) == 15.4
        assert result['avg_health_score'] == 72.5
        assert result['star_count'] == 6
        assert result['dog_count'] == 3
        assert result['dominant_driver'] == 'volume'
        assert result['total_expected_saving'] == 36000.0
        assert result['data_sources_available'] == 5
        assert isinstance(result['insight_text'], str)
        assert len(result['insight_text']) > 0

    @pytest.mark.asyncio
    async def test_only_profitability(self):
        """其他数据源无数据时，只用营收基线构建报告。"""
        db = _make_db([
            [self._prof_row()],
            [self._prev_row()],
            [],   # health empty
            [],   # matrix empty
            [],   # attrib empty
            [],   # attrib_driver empty
            [],   # compression empty
            [],   # upsert
        ])
        result = await build_dish_monthly_summary(db, 'S001', '2025-06')
        assert result['total_dishes'] == 20
        assert result['avg_health_score'] is None
        assert result['star_count'] is None
        assert result['data_sources_available'] == 1

    @pytest.mark.asyncio
    async def test_no_profitability_returns_error(self):
        """营收基线无数据时返回 error 字段。"""
        db = _make_db([
            [None],  # prof returns no row
        ])
        # fetchone returns None
        result = await build_dish_monthly_summary(db, 'S001', '2025-06')
        assert 'error' in result

    @pytest.mark.asyncio
    async def test_no_prev_period(self):
        """上期无数据时 revenue_delta_pct 为 None。"""
        db = _make_db([
            [self._prof_row()],
            [None],   # prev prof empty
            [], [], [], [], [], [],
        ])
        result = await build_dish_monthly_summary(db, 'S001', '2025-06')
        assert result['revenue_delta_pct'] is None


# ── get_dish_monthly_summary ──────────────────────────────────────────────────

class TestGetDishMonthlySummary:
    def _summary_row(self):
        return (
            'S001', '2025-06', '2025-05',
            20, 150000.0, 130000.0, 15.38,
            72.5, 5, 8, 4, 3, 2,
            6, 7, 4, 3, 15000.0,
            18, 20000.0, 8000.0, 12000.0, 'volume',
            15, 3000.0, 36000.0, 2, 3,
            5, '营收增长15%', '2025-06-01',
        )

    @pytest.mark.asyncio
    async def test_found(self):
        db = _make_db([[self._summary_row()]])
        result = await get_dish_monthly_summary(db, 'S001', '2025-06')
        assert result is not None
        assert result['total_dishes'] == 20
        assert result['dominant_driver'] == 'volume'

    @pytest.mark.asyncio
    async def test_not_found(self):
        db = _make_db([[]])
        result = await get_dish_monthly_summary(db, 'S001', '2025-06')
        assert result is None


# ── get_summary_history ───────────────────────────────────────────────────────

class TestGetSummaryHistory:
    @pytest.mark.asyncio
    async def test_basic(self):
        rows = [
            ('2025-06', 20, 150000.0, 15.38,  72.5, 6, 3, 3000.0, 36000.0, 20000.0, 'volume', 5, '增长'),
            ('2025-05', 18, 130000.0, -2.1,   68.0, 5, 4, 2500.0, 30000.0, -5000.0, 'price',  4, '下滑'),
        ]
        db = _make_db([rows])
        result = await get_summary_history(db, 'S001', periods=6)
        assert len(result) == 2
        assert result[0]['period'] == '2025-06'
        assert result[1]['dominant_driver'] == 'price'

    @pytest.mark.asyncio
    async def test_empty(self):
        db = _make_db([[]])
        result = await get_summary_history(db, 'S001')
        assert result == []
