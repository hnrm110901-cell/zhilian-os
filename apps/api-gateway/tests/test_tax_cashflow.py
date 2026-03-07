"""
Tests for Phase 5 Month 2 — 税务智能引擎 + 现金流预测
"""
import os
import sys
import json
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

with patch("src.core.config", create=True):
    from src.services.tax_engine_service import (
        DEFAULT_TAX_RATES,
        DEFAULT_TAX_NAMES,
        RISK_THRESHOLDS,
        compute_tax_for_type,
        _assess_risk,
        compute_tax_calculation,
    )
    from src.services.cashflow_forecast_service import (
        FORECAST_DAYS,
        LOOKBACK_DAYS,
        WEEKDAY_FACTORS,
        INFLOW_TYPES,
        OUTFLOW_TYPES,
        compute_daily_avg,
        project_cash_flow,
        compute_cashflow_forecast,
    )
    from src.api.tax_cashflow import (
        _safe_float,
        _format_action,
    )

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# TestTaxConstants
# ═══════════════════════════════════════════════════════════════════════════════

class TestTaxConstants:
    def test_default_rates_exist(self):
        assert "vat_small"   in DEFAULT_TAX_RATES
        assert "vat_general" in DEFAULT_TAX_RATES
        assert "income_tax"  in DEFAULT_TAX_RATES
        assert "stamp_duty"  in DEFAULT_TAX_RATES

    def test_vat_small_rate(self):
        assert DEFAULT_TAX_RATES["vat_small"] == 0.03

    def test_income_tax_rate(self):
        assert DEFAULT_TAX_RATES["income_tax"] == 0.25

    def test_risk_thresholds_ordered(self):
        assert RISK_THRESHOLDS["critical"] > RISK_THRESHOLDS["high"] > RISK_THRESHOLDS["medium"]

    def test_names_match_rates(self):
        for t in DEFAULT_TAX_RATES:
            assert t in DEFAULT_TAX_NAMES


# ═══════════════════════════════════════════════════════════════════════════════
# TestAssessRisk
# ═══════════════════════════════════════════════════════════════════════════════

class TestAssessRisk:
    def test_low(self):
        assert _assess_risk(0.02) == "low"

    def test_medium(self):
        assert _assess_risk(0.07) == "medium"

    def test_high(self):
        assert _assess_risk(0.15) == "high"

    def test_critical(self):
        assert _assess_risk(0.25) == "critical"

    def test_negative_deviation_uses_abs(self):
        # 多申报（负偏差）也应按绝对值评估
        assert _assess_risk(-0.15) == "high"

    def test_zero(self):
        assert _assess_risk(0.0) == "low"


# ═══════════════════════════════════════════════════════════════════════════════
# TestComputeTaxForType
# ═══════════════════════════════════════════════════════════════════════════════

class TestComputeTaxForType:
    def test_vat_small_basic(self):
        result = compute_tax_for_type(
            tax_type="vat_small",
            net_revenue_yuan=103000.0,
            gross_profit_yuan=30000.0,
            total_sales_yuan=103000.0,
        )
        assert result["tax_type"] == "vat_small"
        # 不含税 = 103000 / 1.03 ≈ 100000
        assert abs(result["taxable_base"] - 100000.0) < 1.0
        assert abs(result["tax_amount"] - 3000.0) < 1.0

    def test_vat_small_custom_rate(self):
        result = compute_tax_for_type(
            tax_type="vat_small",
            net_revenue_yuan=100000.0,
            gross_profit_yuan=20000.0,
            total_sales_yuan=100000.0,
            tax_rate=0.01,  # 小规模疫情减免税率
        )
        # 不含税 = 100000/1.01 ≈ 99009.9
        expected_tax = round(100000.0 / 1.01 * 0.01, 2)
        assert abs(result["tax_amount"] - expected_tax) < 0.5

    def test_income_tax_positive_profit(self):
        result = compute_tax_for_type(
            tax_type="income_tax",
            net_revenue_yuan=100000.0,
            gross_profit_yuan=40000.0,
            total_sales_yuan=100000.0,
        )
        assert result["taxable_base"] == 40000.0
        assert result["tax_amount"] == round(40000.0 * 0.25, 2)

    def test_income_tax_no_loss(self):
        # 亏损不产生应纳所得税
        result = compute_tax_for_type(
            tax_type="income_tax",
            net_revenue_yuan=100000.0,
            gross_profit_yuan=-5000.0,
            total_sales_yuan=100000.0,
        )
        assert result["taxable_base"] == 0.0
        assert result["tax_amount"] == 0.0

    def test_stamp_duty(self):
        result = compute_tax_for_type(
            tax_type="stamp_duty",
            net_revenue_yuan=100000.0,
            gross_profit_yuan=20000.0,
            total_sales_yuan=500000.0,
        )
        expected = round(500000.0 * 0.0003, 2)
        assert result["tax_amount"] == expected

    def test_result_has_required_keys(self):
        result = compute_tax_for_type(
            tax_type="vat_small",
            net_revenue_yuan=100000.0,
            gross_profit_yuan=20000.0,
            total_sales_yuan=100000.0,
        )
        for k in ("tax_type", "tax_name", "tax_rate", "taxable_base", "tax_amount", "detail"):
            assert k in result


# ═══════════════════════════════════════════════════════════════════════════════
# TestComputeTaxCalculation (mocked DB)
# ═══════════════════════════════════════════════════════════════════════════════

class TestComputeTaxCalculation:
    def _make_db(self, net_revenue=100000.0, gross_profit=30000.0, gross_revenue=105000.0):
        db = AsyncMock()
        call_count = [0]

        async def side_effect(q, params=None):
            call_count[0] += 1
            result = MagicMock()

            q_str = str(q)
            if "COUNT(*)" in q_str and "tax_calculations" in q_str:
                # cache check
                result.scalar = MagicMock(return_value=0)
                return result
            if "profit_attribution_results" in q_str:
                # profit row
                row = MagicMock()
                row.net_revenue_yuan   = net_revenue
                row.gross_revenue_yuan = gross_revenue
                row.gross_profit_yuan  = gross_profit
                result.fetchone = MagicMock(return_value=row)
                return result
            if "invoice" in q_str and "tax_paid" in q_str:
                # declared amount
                row = MagicMock()
                row.declared_total = 0.0
                result.fetchone = MagicMock(return_value=row)
                return result
            if "tax_rules" in q_str:
                result.fetchall = MagicMock(return_value=[])
                return result
            if "SELECT id FROM tax_calculations" in q_str:
                result.fetchone = MagicMock(return_value=None)
                return result
            if "agent_action_log" in q_str:
                return result
            # INSERT
            result.fetchone = MagicMock(return_value=None)
            result.fetchall = MagicMock(return_value=[])
            return result

        db.execute = side_effect
        db.commit  = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_returns_list(self):
        db = self._make_db()
        results = await compute_tax_calculation(db, "s001", "2026-03", force=True)
        assert isinstance(results, list)
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_includes_vat_small(self):
        db = self._make_db()
        results = await compute_tax_calculation(db, "s001", "2026-03", force=True)
        types = [r["tax_type"] for r in results]
        assert "vat_small" in types

    @pytest.mark.asyncio
    async def test_income_tax_when_profitable(self):
        db = self._make_db(gross_profit=30000.0)
        results = await compute_tax_calculation(db, "s001", "2026-03", force=True)
        types = [r["tax_type"] for r in results]
        assert "income_tax" in types

    @pytest.mark.asyncio
    async def test_no_income_tax_when_loss(self):
        db = self._make_db(gross_profit=-5000.0)
        results = await compute_tax_calculation(db, "s001", "2026-03", force=True)
        types = [r["tax_type"] for r in results]
        assert "income_tax" not in types

    @pytest.mark.asyncio
    async def test_risk_level_present(self):
        db = self._make_db()
        results = await compute_tax_calculation(db, "s001", "2026-03", force=True)
        for r in results:
            assert r["risk_level"] in ("low", "medium", "high", "critical")


# ═══════════════════════════════════════════════════════════════════════════════
# TestCashflowConstants
# ═══════════════════════════════════════════════════════════════════════════════

class TestCashflowConstants:
    def test_forecast_days(self):
        assert FORECAST_DAYS == 30

    def test_lookback_days(self):
        assert LOOKBACK_DAYS == 90

    def test_weekday_factors_all_present(self):
        for i in range(7):
            assert i in WEEKDAY_FACTORS

    def test_weekend_higher_than_weekday(self):
        # 周末（5,6）应高于周一（0）
        assert WEEKDAY_FACTORS[6] > WEEKDAY_FACTORS[0]
        assert WEEKDAY_FACTORS[5] > WEEKDAY_FACTORS[1]

    def test_inflow_outflow_no_overlap(self):
        assert INFLOW_TYPES.isdisjoint(OUTFLOW_TYPES)


# ═══════════════════════════════════════════════════════════════════════════════
# TestComputeDailyAvg
# ═══════════════════════════════════════════════════════════════════════════════

class TestComputeDailyAvg:
    def test_basic(self):
        totals = {"sale": 900000.0, "purchase": 300000.0, "expense": 90000.0}
        avg = compute_daily_avg(totals, 90)
        assert avg["daily_inflow"]  == round(900000.0 / 90, 2)
        assert avg["daily_outflow"] == round((300000.0 + 90000.0) / 90, 2)

    def test_refund_reduces_inflow(self):
        totals = {"sale": 900000.0, "refund": 90000.0}
        avg = compute_daily_avg(totals, 90)
        assert avg["daily_inflow"] == round((900000.0 - 90000.0) / 90, 2)

    def test_empty_totals(self):
        avg = compute_daily_avg({}, 90)
        assert avg["daily_inflow"]  == 0.0
        assert avg["daily_outflow"] == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# TestProjectCashFlow
# ═══════════════════════════════════════════════════════════════════════════════

class TestProjectCashFlow:
    def test_returns_correct_days(self):
        daily_avg  = {"daily_inflow": 10000.0, "daily_outflow": 8000.0}
        start_date = date.today() + timedelta(days=1)
        result = project_cash_flow(daily_avg, 0.0, start_date, days=30)
        assert len(result) == 30

    def test_balance_accumulates(self):
        daily_avg  = {"daily_inflow": 10000.0, "daily_outflow": 8000.0}
        start_date = date(2026, 3, 9)  # 周一
        result = project_cash_flow(daily_avg, 0.0, start_date, days=2)
        # Day 1 net → balance
        assert result[0]["balance_yuan"] == result[0]["net_yuan"]
        # Day 2 balance = Day 1 balance + Day 2 net
        assert abs(result[1]["balance_yuan"] - (result[0]["balance_yuan"] + result[1]["net_yuan"])) < 0.01

    def test_opening_balance_offset(self):
        daily_avg  = {"daily_inflow": 0.0, "daily_outflow": 0.0}
        start_date = date.today() + timedelta(days=1)
        result = project_cash_flow(daily_avg, 5000.0, start_date, days=5)
        # With zero net, balance stays at opening_balance
        for fc in result:
            assert fc["balance_yuan"] == 5000.0

    def test_confidence_decreases(self):
        daily_avg  = {"daily_inflow": 5000.0, "daily_outflow": 3000.0}
        start_date = date.today() + timedelta(days=1)
        result = project_cash_flow(daily_avg, 0.0, start_date, days=30)
        assert result[0]["confidence"] > result[-1]["confidence"]

    def test_weekday_factor_applied(self):
        # 周日入账应高于周一入账
        daily_avg  = {"daily_inflow": 10000.0, "daily_outflow": 5000.0}
        sunday  = date(2026, 3, 8)   # 2026-03-08 = 周日
        monday  = date(2026, 3, 9)   # 2026-03-09 = 周一
        r_sun = project_cash_flow(daily_avg, 0.0, sunday,  days=1)[0]
        r_mon = project_cash_flow(daily_avg, 0.0, monday,  days=1)[0]
        assert r_sun["inflow_yuan"] > r_mon["inflow_yuan"]

    def test_cash_gap_detected(self):
        # 出大于入 → 余额转负
        daily_avg  = {"daily_inflow": 1000.0, "daily_outflow": 5000.0}
        start_date = date.today() + timedelta(days=1)
        result = project_cash_flow(daily_avg, 0.0, start_date, days=5)
        # First day already negative
        assert result[0]["balance_yuan"] < 0


# ═══════════════════════════════════════════════════════════════════════════════
# TestComputeCashflowForecast (mocked DB)
# ═══════════════════════════════════════════════════════════════════════════════

class TestComputeCashflowForecast:
    def _make_db(self, event_totals=None):
        db = AsyncMock()
        call_count = [0]
        defaults = {
            "sale":     270000.0,  # 90-day total
            "purchase": 90000.0,
            "expense":  27000.0,
        }
        totals = event_totals or defaults

        async def side_effect(q, params=None):
            call_count[0] += 1
            result = MagicMock()
            q_str = str(q)

            if "COUNT(*)" in q_str and "cashflow_forecasts" in q_str:
                result.scalar = MagicMock(return_value=0)
                return result
            if "GROUP BY event_type" in q_str:
                # Return aggregated event totals
                rows = []
                for etype, total in totals.items():
                    row = MagicMock()
                    row.event_type  = etype
                    row.total_yuan  = total
                    rows.append(row)
                result.fetchall = MagicMock(return_value=rows)
                return result
            if "DELETE FROM cashflow_forecasts" in q_str:
                return result
            if "agent_action_log" in q_str:
                return result
            # INSERT (ON CONFLICT)
            result.fetchone = MagicMock(return_value=None)
            return result

        db.execute = side_effect
        db.commit  = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_returns_30_days(self):
        db = self._make_db()
        result = await compute_cashflow_forecast(db, "s001", force=True)
        assert result["forecast_days"] == 30

    @pytest.mark.asyncio
    async def test_result_structure(self):
        db = self._make_db()
        result = await compute_cashflow_forecast(db, "s001", force=True)
        assert "store_id" in result
        assert "generated_on" in result
        assert "min_balance_yuan" in result
        assert "max_balance_yuan" in result
        assert "forecasts" in result

    @pytest.mark.asyncio
    async def test_each_forecast_has_fields(self):
        db = self._make_db()
        result = await compute_cashflow_forecast(db, "s001", force=True)
        for fc in result["forecasts"]:
            assert "forecast_date" in fc
            assert "inflow_yuan"   in fc
            assert "outflow_yuan"  in fc
            assert "net_yuan"      in fc
            assert "balance_yuan"  in fc
            assert "confidence"    in fc

    @pytest.mark.asyncio
    async def test_positive_cashflow_no_gap(self):
        # High sale, low expense → no cash gap
        db = self._make_db({"sale": 900000.0, "expense": 100000.0})
        result = await compute_cashflow_forecast(db, "s001", opening_balance=50000.0, force=True)
        assert result["cash_gap_days"] == 0

    @pytest.mark.asyncio
    async def test_negative_cashflow_has_gap(self):
        # Low sale, high expense → cash gap
        db = self._make_db({"sale": 9000.0, "expense": 900000.0})
        result = await compute_cashflow_forecast(db, "s001", opening_balance=0.0, force=True)
        assert result["cash_gap_days"] > 0
        assert result["min_balance_yuan"] < 0


# ═══════════════════════════════════════════════════════════════════════════════
# TestSafeFloat
# ═══════════════════════════════════════════════════════════════════════════════

class TestSafeFloat:
    def test_none(self):
        assert _safe_float(None) == 0.0

    def test_decimal(self):
        from decimal import Decimal
        assert _safe_float(Decimal("42.5")) == 42.5

    def test_int(self):
        assert _safe_float(100) == 100.0


# ═══════════════════════════════════════════════════════════════════════════════
# TestFormatAction
# ═══════════════════════════════════════════════════════════════════════════════

class TestFormatAction:
    def _make_row(self, **kwargs):
        row = MagicMock()
        row.id                   = "act-001"
        row.action_level         = "L2"
        row.agent_name           = "TaxAgent"
        row.trigger_type         = "tax_deviation"
        row.title                = "税务偏差预警"
        row.description          = "偏差15%"
        row.recommended_action   = None
        row.expected_impact_yuan = -500.0
        row.confidence           = 0.85
        row.status               = "pending"
        row.period               = "2026-03"
        row.created_at           = None
        for k, v in kwargs.items():
            setattr(row, k, v)
        return row

    def test_basic_format(self):
        row = self._make_row()
        result = _format_action(row)
        assert result["id"]              == "act-001"
        assert result["action_level"]    == "L2"
        assert result["agent_name"]      == "TaxAgent"
        assert result["status"]          == "pending"

    def test_expected_impact_float(self):
        row = self._make_row()
        result = _format_action(row)
        assert isinstance(result["expected_impact_yuan"], float)

    def test_created_at_none(self):
        row = self._make_row()
        result = _format_action(row)
        assert result["created_at"] is None
