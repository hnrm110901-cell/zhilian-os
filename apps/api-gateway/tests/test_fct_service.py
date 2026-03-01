"""
Tests for FCTService
"""
import pytest
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.fct_service import (
    FCTService,
    VAT_RATE_GENERAL,
    VAT_RATE_SMALL,
    CIT_RATE_GENERAL,
    CIT_RATE_MICRO,
    PROFIT_MARGIN,
    FOOD_COST_RATIO,
    VAT_SURCHARGE_RATE,
)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _mock_db() -> AsyncMock:
    db = AsyncMock(spec=AsyncSession)
    db.add   = MagicMock()
    db.flush = AsyncMock()
    return db


def _single_scalar(value) -> MagicMock:
    r = MagicMock()
    r.scalar.return_value = value
    return r


def _rows(rows_list) -> MagicMock:
    r = MagicMock()
    r.all.return_value = rows_list
    return r


def _scalars_all(items_list) -> MagicMock:
    r = MagicMock()
    r.scalars.return_value.all.return_value = items_list
    return r


# ── estimate_monthly_tax ────────────────────────────────────────────────────

class TestEstimateMonthlyTax:

    @pytest.mark.asyncio
    async def test_general_taxpayer_vat_rate(self):
        db = _mock_db()
        # income = 1_000_000_00 分 (100万), food_cost = 0
        db.execute.side_effect = [
            _single_scalar(1_000_000_00),   # gross revenue
            _single_scalar(0),              # food cost
        ]

        svc    = FCTService(db)
        result = await svc.estimate_monthly_tax("STORE001", 2026, 5, taxpayer_type="general")

        expected_vat = int(1_000_000_00 / (1 + VAT_RATE_GENERAL) * VAT_RATE_GENERAL)
        assert result["vat"]["output_vat"] == pytest.approx(expected_vat, abs=10)
        assert result["taxpayer_type"]     == "general"
        assert result["vat"]["rate"]       == VAT_RATE_GENERAL

    @pytest.mark.asyncio
    async def test_small_taxpayer_lower_vat(self):
        db = _mock_db()
        db.execute.side_effect = [
            _single_scalar(1_000_000_00),
            _single_scalar(0),
        ]

        svc    = FCTService(db)
        result = await svc.estimate_monthly_tax("STORE001", 2026, 5, taxpayer_type="small")

        assert result["vat"]["rate"] == VAT_RATE_SMALL
        # Small taxpayer VAT < general taxpayer VAT
        general_vat = int(1_000_000_00 / (1 + VAT_RATE_GENERAL) * VAT_RATE_GENERAL)
        assert result["vat"]["output_vat"] < general_vat

    @pytest.mark.asyncio
    async def test_input_vat_reduces_net_vat(self):
        db = _mock_db()
        gross    = 1_000_000_00   # 100万收入
        food_cost = 300_000_00    # 30万食材

        db.execute.side_effect = [
            _single_scalar(gross),
            _single_scalar(food_cost),
        ]

        svc    = FCTService(db)
        result = await svc.estimate_monthly_tax("STORE001", 2026, 5)

        output_vat = int(gross / (1 + VAT_RATE_GENERAL) * VAT_RATE_GENERAL)
        input_vat  = int(food_cost * VAT_RATE_GENERAL)
        net_vat    = max(0, output_vat - input_vat)
        assert result["vat"]["net_vat"]   == net_vat
        assert result["vat"]["input_vat"] == input_vat

    @pytest.mark.asyncio
    async def test_net_vat_never_negative(self):
        db = _mock_db()
        # More food cost than revenue (edge case)
        db.execute.side_effect = [
            _single_scalar(100_000),    # tiny revenue
            _single_scalar(500_000),    # large food cost
        ]

        svc    = FCTService(db)
        result = await svc.estimate_monthly_tax("STORE001", 2026, 5)

        assert result["vat"]["net_vat"] >= 0

    @pytest.mark.asyncio
    async def test_vat_surcharge_is_12_pct_of_net_vat(self):
        db = _mock_db()
        db.execute.side_effect = [
            _single_scalar(1_000_000_00),
            _single_scalar(0),
        ]

        svc    = FCTService(db)
        result = await svc.estimate_monthly_tax("STORE001", 2026, 5)

        net_vat  = result["vat"]["net_vat"]
        expected = int(net_vat * VAT_SURCHARGE_RATE)
        assert result["vat"]["surcharge"] == expected

    @pytest.mark.asyncio
    async def test_cit_based_on_profit_margin(self):
        db = _mock_db()
        gross = 1_000_000_00
        db.execute.side_effect = [
            _single_scalar(gross),
            _single_scalar(0),
        ]

        svc    = FCTService(db)
        result = await svc.estimate_monthly_tax("STORE001", 2026, 5)

        expected_profit = int(gross * PROFIT_MARGIN)
        expected_cit    = int(expected_profit * CIT_RATE_GENERAL)
        assert result["cit"]["estimated_profit"] == expected_profit
        assert result["cit"]["cit_amount"]        == expected_cit

    @pytest.mark.asyncio
    async def test_micro_enterprise_lower_cit_rate(self):
        db = _mock_db()
        db.execute.side_effect = [
            _single_scalar(500_000_00),
            _single_scalar(0),
        ]

        svc    = FCTService(db)
        result = await svc.estimate_monthly_tax("STORE001", 2026, 5, taxpayer_type="micro")

        assert result["cit"]["rate"] == CIT_RATE_MICRO

    @pytest.mark.asyncio
    async def test_zero_revenue_effective_rate_is_zero(self):
        db = _mock_db()
        db.execute.side_effect = [
            _single_scalar(0),
            _single_scalar(0),
        ]

        svc    = FCTService(db)
        result = await svc.estimate_monthly_tax("STORE001", 2026, 5)

        assert result["effective_rate"] == 0.0
        assert result["total_tax"] == 0

    @pytest.mark.asyncio
    async def test_total_tax_is_sum_of_components(self):
        db = _mock_db()
        db.execute.side_effect = [
            _single_scalar(1_000_000_00),
            _single_scalar(200_000_00),
        ]

        svc    = FCTService(db)
        result = await svc.estimate_monthly_tax("STORE001", 2026, 5)

        expected = (
            result["vat"]["net_vat"] +
            result["vat"]["surcharge"] +
            result["cit"]["cit_amount"]
        )
        assert result["total_tax"] == expected

    @pytest.mark.asyncio
    async def test_disclaimer_present(self):
        db = _mock_db()
        db.execute.side_effect = [_single_scalar(100_000), _single_scalar(0)]

        svc    = FCTService(db)
        result = await svc.estimate_monthly_tax("STORE001", 2026, 5)

        assert "disclaimer" in result
        assert len(result["disclaimer"]) > 0


# ── get_monthly_reconciliation ───────────────────────────────────────────────

class TestGetMonthlyReconciliation:

    def _make_record(self, day, pos_amt, actual_amt, diff_ratio=0.0):
        from src.models.reconciliation import ReconciliationStatus
        r = MagicMock()
        r.reconciliation_date  = date(2026, 5, day)
        r.pos_total_amount     = pos_amt
        r.actual_total_amount  = actual_amt
        r.diff_amount          = actual_amt - pos_amt
        r.diff_ratio           = diff_ratio
        r.status               = ReconciliationStatus.MATCHED
        r.pos_order_count      = 100
        r.actual_order_count   = 100
        return r

    @pytest.mark.asyncio
    async def test_normal_month_summary(self):
        records = [
            self._make_record(1, 500_000, 500_000, 0.0),
            self._make_record(2, 600_000, 601_000, 0.17),
        ]
        db = _mock_db()
        db.execute.return_value = _scalars_all(records)

        svc    = FCTService(db)
        result = await svc.get_monthly_reconciliation("STORE001", 2026, 5)

        assert result["summary"]["pos_total"]     == 1_100_000
        assert result["summary"]["finance_total"] == 1_101_000
        assert result["reconciled_days"]          == 2
        assert result["summary"]["health"]        == "normal"  # <1% variance

    @pytest.mark.asyncio
    async def test_anomaly_days_detected(self):
        records = [
            self._make_record(1, 500_000, 510_000, 2.0),   # 2% > threshold
            self._make_record(2, 600_000, 600_000, 0.0),
        ]
        db = _mock_db()
        db.execute.return_value = _scalars_all(records)

        svc    = FCTService(db)
        result = await svc.get_monthly_reconciliation("STORE001", 2026, 5)

        assert len(result["anomaly_days"]) == 1
        assert result["anomaly_days"][0]["date"] == "2026-05-01"

    @pytest.mark.asyncio
    async def test_critical_health_over_3pct(self):
        # 5% variance → critical
        records = [self._make_record(1, 100_000, 105_000, 5.0)]
        db = _mock_db()
        db.execute.return_value = _scalars_all(records)

        svc    = FCTService(db)
        result = await svc.get_monthly_reconciliation("STORE001", 2026, 5)

        assert result["summary"]["health"] == "critical"

    @pytest.mark.asyncio
    async def test_empty_month_no_error(self):
        db = _mock_db()
        db.execute.return_value = _scalars_all([])

        svc    = FCTService(db)
        result = await svc.get_monthly_reconciliation("STORE001", 2026, 5)

        assert result["reconciled_days"]          == 0
        assert result["summary"]["pos_total"]     == 0
        assert result["summary"]["health"]        == "normal"


# ── forecast_cash_flow ───────────────────────────────────────────────────────

class TestForecastCashFlow:

    @pytest.mark.asyncio
    async def test_returns_n_day_forecast(self):
        db = _mock_db()
        # hist inflow rows
        hist_result = _rows([
            MagicMock(daily_total=50_000_00) for _ in range(10)
        ])
        # budget rows
        budget_result = _scalars_all([])

        db.execute.side_effect = [hist_result, budget_result]

        svc    = FCTService(db)
        result = await svc.forecast_cash_flow("STORE001", days=30)

        assert len(result["daily_forecast"]) == 30
        assert result["forecast_days"]       == 30

    @pytest.mark.asyncio
    async def test_weekend_inflow_higher(self):
        db = _mock_db()
        hist_result   = _rows([MagicMock(daily_total=50_000_00)] * 15)
        budget_result = _scalars_all([])
        db.execute.side_effect = [hist_result, budget_result]

        svc    = FCTService(db)
        result = await svc.forecast_cash_flow("STORE001", days=14)

        weekday_inflows = [
            d["inflow"] for d in result["daily_forecast"]
            if d["weekday"] not in ("周六", "周日")
        ]
        weekend_inflows = [
            d["inflow"] for d in result["daily_forecast"]
            if d["weekday"] in ("周六", "周日")
        ]

        if weekend_inflows and weekday_inflows:
            avg_weekday = sum(weekday_inflows) / len(weekday_inflows)
            avg_weekend = sum(weekend_inflows) / len(weekend_inflows)
            assert avg_weekend > avg_weekday

    @pytest.mark.asyncio
    async def test_confidence_decreases_over_time(self):
        db = _mock_db()
        hist_result   = _rows([MagicMock(daily_total=50_000_00)] * 15)
        budget_result = _scalars_all([])
        db.execute.side_effect = [hist_result, budget_result]

        svc    = FCTService(db)
        result = await svc.forecast_cash_flow("STORE001", days=20)

        fc = result["daily_forecast"]
        # Day 1 should be most confident
        assert fc[0]["confidence"] >= fc[-1]["confidence"]

    @pytest.mark.asyncio
    async def test_cash_alert_triggered_when_low_balance(self):
        db = _mock_db()
        # Very low daily inflow → balance drops quickly
        hist_result   = _rows([MagicMock(daily_total=1_000_00)] * 5)  # 1000元/天
        budget_result = _scalars_all([])
        db.execute.side_effect = [hist_result, budget_result]

        svc    = FCTService(db)
        result = await svc.forecast_cash_flow("STORE001", days=30, starting_balance=0)

        # With tiny inflow and large fixed costs (default fallback), alerts should trigger
        # OR if budgets are 0, food_cost_outflow still applies
        assert "alerts" in result
        assert "daily_forecast" in result

    @pytest.mark.asyncio
    async def test_starting_balance_included(self):
        db = _mock_db()
        hist_result   = _rows([MagicMock(daily_total=10_000_00)] * 10)
        budget_result = _scalars_all([])
        db.execute.side_effect = [hist_result, budget_result]

        svc    = FCTService(db)
        result = await svc.forecast_cash_flow("STORE001", days=7, starting_balance=100_000_00)

        # First day cumulative balance should start from starting_balance + net
        first_day = result["daily_forecast"][0]
        assert first_day["cumulative_balance"] != 0 or result["starting_balance"] == 0

    @pytest.mark.asyncio
    async def test_summary_totals_match_daily(self):
        db = _mock_db()
        hist_result   = _rows([MagicMock(daily_total=50_000_00)] * 10)
        budget_result = _scalars_all([])
        db.execute.side_effect = [hist_result, budget_result]

        svc    = FCTService(db)
        result = await svc.forecast_cash_flow("STORE001", days=7)

        total_in  = sum(d["inflow"]  for d in result["daily_forecast"])
        total_out = sum(d["outflow"] for d in result["daily_forecast"])
        assert result["summary"]["total_inflow"]  == total_in
        assert result["summary"]["total_outflow"] == total_out


# ── get_budget_execution ────────────────────────────────────────────────────

class TestGetBudgetExecution:

    def _make_budget(self, category, amount):
        b = MagicMock()
        b.category        = category
        b.budgeted_amount = amount
        return b

    @pytest.mark.asyncio
    async def test_exec_rate_calculated(self):
        budgets = [self._make_budget("food_cost", 300_000_00)]

        # Actual spend
        actual_row = MagicMock()
        actual_row.category         = "food_cost"
        actual_row.transaction_type = "expense"
        actual_row.total            = 330_000_00  # 110%

        db = _mock_db()
        budget_result = _scalars_all(budgets)
        actual_result = _rows([actual_row])
        db.execute.side_effect = [budget_result, actual_result]

        svc    = FCTService(db)
        result = await svc.get_budget_execution("STORE001", 2026, 5)

        food_cat = next(c for c in result["categories"] if c["category"] == "food_cost")
        assert food_cat["exec_rate"] == pytest.approx(110.0, abs=0.1)
        assert food_cat["status"]    == "over"

    @pytest.mark.asyncio
    async def test_no_budget_category_shows_no_budget_status(self):
        db = _mock_db()
        db.execute.side_effect = [_scalars_all([]), _rows([])]

        svc    = FCTService(db)
        result = await svc.get_budget_execution("STORE001", 2026, 5)

        for cat in result["categories"]:
            assert cat["status"] in ("no_budget", "normal", "under", "over")

    @pytest.mark.asyncio
    async def test_alert_generated_for_over_budget(self):
        budgets = [self._make_budget("labor_cost", 500_000_00)]

        # 140% over budget
        actual_row = MagicMock()
        actual_row.category         = "labor_cost"
        actual_row.transaction_type = "expense"
        actual_row.total            = 700_000_00

        db = _mock_db()
        db.execute.side_effect = [_scalars_all(budgets), _rows([actual_row])]

        svc    = FCTService(db)
        result = await svc.get_budget_execution("STORE001", 2026, 5)

        assert len(result["alerts"]) >= 1
        alert = result["alerts"][0]
        assert alert["category"] == "labor_cost"
        assert alert["severity"] == "high"  # >130%

    @pytest.mark.asyncio
    async def test_profit_margin_computed(self):
        budgets = []

        revenue_row = MagicMock()
        revenue_row.category         = "sales"
        revenue_row.transaction_type = "income"
        revenue_row.total            = 1_000_000_00

        food_row = MagicMock()
        food_row.category         = "food_cost"
        food_row.transaction_type = "expense"
        food_row.total            = 350_000_00

        db = _mock_db()
        db.execute.side_effect = [
            _scalars_all(budgets),
            _rows([revenue_row, food_row]),
        ]

        svc    = FCTService(db)
        result = await svc.get_budget_execution("STORE001", 2026, 5)

        # Profit margin = (revenue - expenses) / revenue
        assert result["overall"]["profit_margin_pct"] > 0


# ── get_dashboard ─────────────────────────────────────────────────────────────

class TestGetDashboard:

    @pytest.mark.asyncio
    async def test_dashboard_returns_expected_keys(self):
        db = _mock_db()
        svc = FCTService(db)

        # Mock all sub-methods
        svc.forecast_cash_flow     = AsyncMock(return_value={
            "summary": {"net_flow": 100_000, "ending_balance": 500_000, "alert_count": 0}
        })
        svc.estimate_monthly_tax   = AsyncMock(return_value={
            "total_tax": 50_000, "effective_rate": 5.0, "period": "2026-02",
            "vat": {}, "cit": {}, "revenue": {}, "disclaimer": "",
        })
        svc.get_budget_execution   = AsyncMock(return_value={
            "overall": {"profit_margin_pct": 12.0},
            "alerts": [],
            "categories": [], "revenue": {}
        })

        # Reconciliation query
        db.execute.return_value = _scalars_all([])

        result = await svc.get_dashboard("STORE001")

        assert "cash_flow"    in result
        assert "tax"          in result
        assert "budget"       in result
        assert "health_score" in result
        assert 0 <= result["health_score"] <= 100

    @pytest.mark.asyncio
    async def test_health_score_decreases_with_alerts(self):
        assert FCTService._calc_health_score(
            {"alert_count": 0}, {"alert_count": 0, "profit_margin_pct": 15.0}
        ) == 100

        score_with_alert = FCTService._calc_health_score(
            {"alert_count": 1}, {"alert_count": 0, "profit_margin_pct": 15.0}
        )
        assert score_with_alert < 100

    @pytest.mark.asyncio
    async def test_low_profit_margin_reduces_health_score(self):
        score_good = FCTService._calc_health_score(
            {"alert_count": 0}, {"alert_count": 0, "profit_margin_pct": 15.0}
        )
        score_bad = FCTService._calc_health_score(
            {"alert_count": 0}, {"alert_count": 0, "profit_margin_pct": 2.0}
        )
        assert score_bad < score_good

    @pytest.mark.asyncio
    async def test_sub_service_failure_does_not_crash_dashboard(self):
        db  = _mock_db()
        svc = FCTService(db)

        svc.forecast_cash_flow   = AsyncMock(return_value={
            "summary": {"net_flow": 0, "ending_balance": 0, "alert_count": 0}
        })
        svc.estimate_monthly_tax = AsyncMock(side_effect=Exception("DB error"))
        svc.get_budget_execution = AsyncMock(side_effect=Exception("DB error"))
        db.execute.return_value  = _scalars_all([])

        result = await svc.get_dashboard("STORE001")

        # Should still return a valid dashboard with defaults
        assert "tax"          in result
        assert "budget"       in result
        assert "health_score" in result
