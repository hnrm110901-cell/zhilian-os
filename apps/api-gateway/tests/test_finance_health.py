"""
Phase 5 Month 5 — 财务健康评分系统测试

覆盖:
  - 纯函数:  score_profit / score_cash / score_tax / score_settlement / score_budget
  - compute_grade
  - generate_insights
  - DB函数:  compute_health_score / get_health_score / get_health_trend
             get_profit_trend / get_brand_health_summary / get_finance_dashboard

Run: pytest tests/test_finance_health.py -v
"""
from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock
import pytest

# ── Mock pydantic-settings before any src.* import ────────────────────────────
_mock_cfg = MagicMock()
_mock_cfg.database_url = "postgresql+asyncpg://test:test@localhost/test"
sys.modules.setdefault(
    'src.core.config',
    MagicMock(get_settings=MagicMock(return_value=_mock_cfg)),
)

from src.services.finance_health_service import (   # noqa: E402
    GRADE_THRESHOLDS,
    MAX_SCORES,
    compute_grade,
    compute_health_score,
    generate_insights,
    get_brand_health_summary,
    get_finance_dashboard,
    get_finance_insights,
    get_health_score,
    get_health_trend,
    get_profit_trend,
    score_budget,
    score_cash,
    score_profit,
    score_settlement,
    score_tax,
)


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

class TestHealthConstants:
    def test_grade_thresholds_keys(self):
        assert set(GRADE_THRESHOLDS.keys()) == {"A", "B", "C"}

    def test_max_scores_sum_100(self):
        assert sum(MAX_SCORES.values()) == 100.0

    def test_max_scores_dimensions(self):
        assert set(MAX_SCORES.keys()) == {"profit", "cash", "tax", "settlement", "budget"}


# ─────────────────────────────────────────────────────────────────────────────
# score_profit
# ─────────────────────────────────────────────────────────────────────────────

class TestScoreProfit:
    def test_zero_margin_zero_score(self):
        assert score_profit(0.0, 0.0) == 0.0

    def test_20pct_margin_full_score(self):
        assert score_profit(20.0, 100_000) == 30.0

    def test_above_20pct_capped_at_30(self):
        assert score_profit(40.0, 100_000) == 30.0

    def test_10pct_margin_half_score(self):
        assert score_profit(10.0, 100_000) == 15.0

    def test_negative_profit_zero_score(self):
        assert score_profit(5.0, -10_000) == 0.0

    def test_score_increases_with_margin(self):
        assert score_profit(15.0, 100_000) > score_profit(5.0, 100_000)


# ─────────────────────────────────────────────────────────────────────────────
# score_cash
# ─────────────────────────────────────────────────────────────────────────────

class TestScoreCash:
    def test_zero_gap_days_full_score(self):
        assert score_cash(0) == 20.0

    def test_10_gap_days_zero_score(self):
        assert score_cash(10) == 0.0

    def test_5_gap_days_half_score(self):
        assert score_cash(5) == 10.0

    def test_excess_gap_days_floored_at_zero(self):
        assert score_cash(100) == 0.0

    def test_score_decreases_with_gap_days(self):
        assert score_cash(2) > score_cash(5)


# ─────────────────────────────────────────────────────────────────────────────
# score_tax
# ─────────────────────────────────────────────────────────────────────────────

class TestScoreTax:
    def test_zero_deviation_full_score(self):
        assert score_tax(0.0) == 20.0

    def test_20pct_deviation_zero_score(self):
        assert score_tax(20.0) == 0.0

    def test_10pct_deviation_half_score(self):
        assert score_tax(10.0) == 10.0

    def test_large_deviation_floored_at_zero(self):
        assert score_tax(50.0) == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# score_settlement
# ─────────────────────────────────────────────────────────────────────────────

class TestScoreSettlement:
    def test_no_records_full_score(self):
        assert score_settlement(0, 0) == 15.0

    def test_all_high_risk_zero_score(self):
        assert score_settlement(10, 10) == 0.0

    def test_half_high_risk_half_score(self):
        assert score_settlement(5, 10) == pytest.approx(7.5, rel=1e-3)

    def test_zero_high_risk_full_score(self):
        assert score_settlement(0, 20) == 15.0

    def test_score_decreases_with_risk_rate(self):
        assert score_settlement(1, 10) > score_settlement(5, 10)


# ─────────────────────────────────────────────────────────────────────────────
# score_budget
# ─────────────────────────────────────────────────────────────────────────────

class TestScoreBudget:
    def test_no_budget_neutral_score(self):
        assert score_budget(0.0, 0.0) == 7.0

    def test_100pct_achievement_full_score(self):
        assert score_budget(100_000, 100_000) == 15.0

    def test_over_achievement_capped_at_15(self):
        assert score_budget(200_000, 100_000) == 15.0

    def test_80pct_achievement(self):
        assert score_budget(80_000, 100_000) == pytest.approx(12.0, rel=1e-3)

    def test_zero_actual_zero_score(self):
        assert score_budget(0.0, 100_000) == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# compute_grade
# ─────────────────────────────────────────────────────────────────────────────

class TestComputeGrade:
    def test_grade_a_at_80(self):
        assert compute_grade(80.0) == "A"

    def test_grade_a_above_80(self):
        assert compute_grade(95.0) == "A"

    def test_grade_b_at_60(self):
        assert compute_grade(60.0) == "B"

    def test_grade_b_at_79(self):
        assert compute_grade(79.9) == "B"

    def test_grade_c_at_40(self):
        assert compute_grade(40.0) == "C"

    def test_grade_d_below_40(self):
        assert compute_grade(39.9) == "D"

    def test_grade_d_zero(self):
        assert compute_grade(0.0) == "D"


# ─────────────────────────────────────────────────────────────────────────────
# generate_insights
# ─────────────────────────────────────────────────────────────────────────────

class TestGenerateInsights:
    def _call(self, **kwargs):
        defaults = {
            "profit_margin_pct":    15.0,
            "gross_profit_yuan":    50_000.0,
            "cash_gap_days":        0,
            "avg_tax_deviation":    2.0,
            "high_risk_settlement": 0,
            "total_settlement":     10,
            "revenue_actual":       100_000.0,
            "revenue_budget":       100_000.0,
            "scores": {
                "profit_score": 22.5, "cash_score": 20.0,
                "tax_score": 18.0, "settlement_score": 15.0, "budget_score": 15.0,
            },
        }
        defaults.update(kwargs)
        return generate_insights(**defaults)

    def test_negative_profit_high_priority_insight(self):
        insights = self._call(gross_profit_yuan=-10_000)
        profit_ins = [i for i in insights if i["insight_type"] == "profit"]
        assert len(profit_ins) == 1
        assert profit_ins[0]["priority"] == "high"
        assert "亏损" in profit_ins[0]["content"]

    def test_high_profit_margin_low_priority(self):
        insights = self._call(
            profit_margin_pct=25.0, gross_profit_yuan=80_000,
            scores={
                "profit_score": 30.0, "cash_score": 20.0,
                "tax_score": 20.0, "settlement_score": 15.0, "budget_score": 15.0,
            },
        )
        profit_ins = [i for i in insights if i["insight_type"] == "profit"]
        assert profit_ins[0]["priority"] == "low"

    def test_cash_gap_triggers_high_priority(self):
        insights = self._call(
            cash_gap_days=8,
            scores={
                "profit_score": 22.5, "cash_score": 4.0,
                "tax_score": 18.0, "settlement_score": 15.0, "budget_score": 15.0,
            },
        )
        cash_ins = [i for i in insights if i["insight_type"] == "cash"]
        assert len(cash_ins) == 1
        assert cash_ins[0]["priority"] == "high"

    def test_high_tax_deviation_warning(self):
        insights = self._call(avg_tax_deviation=18.0)
        tax_ins = [i for i in insights if i["insight_type"] == "tax"]
        assert len(tax_ins) == 1
        assert tax_ins[0]["priority"] == "high"

    def test_high_settlement_risk_triggers_insight(self):
        insights = self._call(high_risk_settlement=3, total_settlement=10)
        sr_ins = [i for i in insights if i["insight_type"] == "settlement"]
        assert len(sr_ins) == 1
        assert sr_ins[0]["priority"] == "high"

    def test_budget_overachievement_low_priority(self):
        insights = self._call(revenue_actual=120_000, revenue_budget=100_000)
        bud_ins = [i for i in insights if i["insight_type"] == "budget"]
        assert len(bud_ins) == 1
        assert bud_ins[0]["priority"] == "low"

    def test_budget_underachievement_medium_priority(self):
        insights = self._call(revenue_actual=70_000, revenue_budget=100_000)
        bud_ins = [i for i in insights if i["insight_type"] == "budget"]
        assert bud_ins[0]["priority"] == "medium"

    def test_no_cash_gap_no_cash_insight(self):
        insights = self._call(cash_gap_days=0)
        cash_ins = [i for i in insights if i["insight_type"] == "cash"]
        assert len(cash_ins) == 0


# ─────────────────────────────────────────────────────────────────────────────
# compute_health_score (with DB mocks)
# ─────────────────────────────────────────────────────────────────────────────

class TestComputeHealthScore:
    def _make_db(
        self,
        profit_row=None,
        cash_count=0,
        tax_avg=0.0,
        sr_counts=(0, 0),
        budget_row=None,
        existing_score_row=None,
    ):
        """Build a mock db whose execute() returns appropriate data per call order."""
        db = AsyncMock()
        call_count = [0]

        async def side_effect(q, params=None):
            call_count[0] += 1
            r = MagicMock()
            c = call_count[0]

            if c == 1:   # profit_attribution_results
                r.fetchone = MagicMock(return_value=profit_row)
            elif c == 2: # cashflow_forecasts COUNT
                r.fetchone = MagicMock(return_value=(cash_count,))
            elif c == 3: # tax_calculations AVG
                r.fetchone = MagicMock(return_value=(tax_avg,))
            elif c == 4: # settlement_records COUNT + SUM
                r.fetchone = MagicMock(return_value=sr_counts)
            elif c == 5: # budget_plans
                r.fetchone = MagicMock(return_value=budget_row)
            elif c == 6: # existing score check
                r.fetchone = MagicMock(return_value=existing_score_row)
            # c >= 7: INSERT/UPDATE + DELETE insights + INSERT insights → return None
            return r

        db.execute = side_effect
        db.commit   = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_no_profit_data_gives_zero_profit_score(self):
        db = self._make_db(profit_row=None, cash_count=0, tax_avg=0, sr_counts=(0, 0))
        result = await compute_health_score(db, "s1", "2026-03")
        assert result["dimensions"]["profit_score"] == 0.0

    @pytest.mark.asyncio
    async def test_full_profit_data(self):
        db = self._make_db(
            profit_row=(100_000, 25_000, 25.0, 35_000),
            cash_count=0, tax_avg=2.0, sr_counts=(0, 5),
            budget_row=None,
        )
        result = await compute_health_score(db, "s1", "2026-03")
        assert result["dimensions"]["profit_score"] == pytest.approx(30.0, rel=1e-2)
        assert result["total_score"] > 60

    @pytest.mark.asyncio
    async def test_grade_a_for_healthy_store(self):
        db = self._make_db(
            profit_row=(100_000, 22_000, 22.0, 35_000),
            cash_count=0, tax_avg=1.0, sr_counts=(0, 10),
            budget_row=(100_000,),
        )
        result = await compute_health_score(db, "s1", "2026-03")
        assert result["grade"] in ("A", "B")

    @pytest.mark.asyncio
    async def test_grade_d_for_distressed_store(self):
        db = self._make_db(
            profit_row=(50_000, -5_000, -10.0, 40_000),
            cash_count=10, tax_avg=18.0, sr_counts=(8, 10),
            budget_row=None,
        )
        result = await compute_health_score(db, "s1", "2026-03")
        assert result["grade"] in ("C", "D")

    @pytest.mark.asyncio
    async def test_insights_included_in_result(self):
        db = self._make_db(
            profit_row=(100_000, 25_000, 25.0, 35_000),
            cash_count=0, tax_avg=2.0, sr_counts=(0, 5),
        )
        result = await compute_health_score(db, "s1", "2026-03")
        assert isinstance(result["insights"], list)

    @pytest.mark.asyncio
    async def test_upsert_updates_existing_score(self):
        db = self._make_db(
            profit_row=(100_000, 20_000, 20.0, 35_000),
            existing_score_row=("existing-id",),
        )
        calls = []
        original = db.execute

        async def recording(q, params=None):
            calls.append(str(q))
            return await original(q, params)

        db.execute = recording
        await compute_health_score(db, "s1", "2026-03")
        update_calls = [c for c in calls if "UPDATE" in c and "finance_health_scores" in c]
        assert len(update_calls) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# get_health_score
# ─────────────────────────────────────────────────────────────────────────────

class TestGetHealthScore:
    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        db = AsyncMock()

        async def side_effect(q, params=None):
            r = MagicMock()
            r.fetchone = MagicMock(return_value=None)
            return r

        db.execute = side_effect
        result = await get_health_score(db, "s1", "2026-03")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_dict_when_found(self):
        db = AsyncMock()
        fake_row = (
            "id-1", "s1", "2026-03", 75.0, "B",
            22.5, 18.0, 17.0, 12.0, 5.5,
            18.5, 100_000, 0, 2.0, 1, 95.0, None,
        )

        async def side_effect(q, params=None):
            r = MagicMock()
            r.fetchone = MagicMock(return_value=fake_row)
            return r

        db.execute = side_effect
        result = await get_health_score(db, "s1", "2026-03")
        assert result is not None
        assert result["grade"] == "B"
        assert result["total_score"] == 75.0


# ─────────────────────────────────────────────────────────────────────────────
# get_health_trend
# ─────────────────────────────────────────────────────────────────────────────

class TestGetHealthTrend:
    @pytest.mark.asyncio
    async def test_empty_trend(self):
        db = AsyncMock()

        async def side_effect(q, params=None):
            r = MagicMock()
            r.fetchall = MagicMock(return_value=[])
            return r

        db.execute = side_effect
        result = await get_health_trend(db, "s1", periods=6)
        assert result == []

    @pytest.mark.asyncio
    async def test_ascending_order(self):
        db = AsyncMock()
        # DB returns newest first (DESC)
        rows = [
            ("2026-03", 80.0, "A", 25, 20, 18, 12, 5),
            ("2026-02", 70.0, "B", 20, 18, 15, 12, 5),
            ("2026-01", 60.0, "B", 15, 15, 15, 12, 3),
        ]

        async def side_effect(q, params=None):
            r = MagicMock()
            r.fetchall = MagicMock(return_value=rows)
            return r

        db.execute = side_effect
        result = await get_health_trend(db, "s1", periods=6)
        # Should be reversed (ascending)
        assert result[0]["period"] == "2026-01"
        assert result[-1]["period"] == "2026-03"

    @pytest.mark.asyncio
    async def test_trend_count_limited(self):
        db = AsyncMock()

        async def side_effect(q, params=None):
            r = MagicMock()
            r.fetchall = MagicMock(return_value=[
                ("2026-0" + str(i), 70.0, "B", 20, 18, 15, 12, 5) for i in range(1, 4)
            ])
            return r

        db.execute = side_effect
        result = await get_health_trend(db, "s1", periods=3)
        assert len(result) == 3


# ─────────────────────────────────────────────────────────────────────────────
# get_profit_trend
# ─────────────────────────────────────────────────────────────────────────────

class TestGetProfitTrend:
    @pytest.mark.asyncio
    async def test_empty_trend(self):
        db = AsyncMock()

        async def side_effect(q, params=None):
            r = MagicMock()
            r.fetchall = MagicMock(return_value=[])
            return r

        db.execute = side_effect
        result = await get_profit_trend(db, "s1", periods=6)
        assert result == []

    @pytest.mark.asyncio
    async def test_decimals_converted_to_float(self):
        from decimal import Decimal
        db = AsyncMock()
        # DB returns DESC (newest first), service reverses to ascending
        rows = [
            ("2026-03", Decimal("100000.00"), Decimal("22000.00"), Decimal("22.00"),
             Decimal("36000.00"), Decimal("78000.00")),
            ("2026-02", Decimal("95000.00"), Decimal("20000.00"), Decimal("21.05"),
             Decimal("35000.00"), Decimal("75000.00")),
        ]

        async def side_effect(q, params=None):
            r = MagicMock()
            r.fetchall = MagicMock(return_value=rows)
            return r

        db.execute = side_effect
        result = await get_profit_trend(db, "s1", periods=6)
        assert isinstance(result[0]["net_revenue_yuan"], float)
        assert result[0]["period"] == "2026-02"  # ascending after reverse

    @pytest.mark.asyncio
    async def test_period_is_string(self):
        db = AsyncMock()
        rows = [("2026-03", 100_000, 22_000, 22.0, 36_000, 78_000)]

        async def side_effect(q, params=None):
            r = MagicMock()
            r.fetchall = MagicMock(return_value=rows)
            return r

        db.execute = side_effect
        result = await get_profit_trend(db, "s1", periods=6)
        assert isinstance(result[0]["period"], str)


# ─────────────────────────────────────────────────────────────────────────────
# get_brand_health_summary
# ─────────────────────────────────────────────────────────────────────────────

class TestGetBrandHealthSummary:
    @pytest.mark.asyncio
    async def test_empty_stores(self):
        db = AsyncMock()

        async def side_effect(q, params=None):
            r = MagicMock()
            r.fetchall = MagicMock(return_value=[])
            return r

        db.execute = side_effect
        result = await get_brand_health_summary(db, brand_id=None, period="2026-03")
        assert result["summary"] is None
        assert result["stores"] == []

    @pytest.mark.asyncio
    async def test_summary_computed(self):
        db = AsyncMock()
        rows = [
            ("s1", 85.0, "A", 28.0, 18.0, 120_000, 22.0),
            ("s2", 65.0, "B", 18.0, 14.0, 90_000,  15.0),
            ("s3", 45.0, "C", 10.0, 12.0, 60_000,  8.0),
        ]

        async def side_effect(q, params=None):
            r = MagicMock()
            r.fetchall = MagicMock(return_value=rows)
            return r

        db.execute = side_effect
        result = await get_brand_health_summary(db, brand_id=None, period="2026-03")
        assert result["summary"]["store_count"] == 3
        assert result["summary"]["best_store"]  == "s1"
        assert result["summary"]["worst_store"] == "s3"
        assert result["summary"]["avg_score"]   == pytest.approx(65.0, rel=1e-2)

    @pytest.mark.asyncio
    async def test_grade_distribution(self):
        db = AsyncMock()
        rows = [
            ("s1", 82.0, "A", 28, 18, 120_000, 22.0),
            ("s2", 65.0, "B", 18, 14,  90_000, 15.0),
        ]

        async def side_effect(q, params=None):
            r = MagicMock()
            r.fetchall = MagicMock(return_value=rows)
            return r

        db.execute = side_effect
        result = await get_brand_health_summary(db, brand_id=None, period="2026-03")
        dist = result["summary"]["grade_dist"]
        assert dist["A"] == 1
        assert dist["B"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# get_finance_dashboard (BFF degradation)
# ─────────────────────────────────────────────────────────────────────────────

class TestGetFinanceDashboard:
    @pytest.mark.asyncio
    async def test_returns_structure_even_with_empty_data(self):
        db = AsyncMock()

        async def side_effect(q, params=None):
            r = MagicMock()
            r.fetchone  = MagicMock(return_value=None)
            r.fetchall  = MagicMock(return_value=[])
            return r

        db.execute = side_effect
        result = await get_finance_dashboard(db, "s1", "2026-03")
        assert "store_id"     in result
        assert "score"        in result
        assert "insights"     in result
        assert "profit_trend" in result
        assert "health_trend" in result

    @pytest.mark.asyncio
    async def test_score_none_when_not_computed(self):
        db = AsyncMock()

        async def side_effect(q, params=None):
            r = MagicMock()
            r.fetchone  = MagicMock(return_value=None)
            r.fetchall  = MagicMock(return_value=[])
            return r

        db.execute = side_effect
        result = await get_finance_dashboard(db, "s1", "2026-03")
        assert result["score"] is None
