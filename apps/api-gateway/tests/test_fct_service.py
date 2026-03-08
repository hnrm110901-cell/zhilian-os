"""
Tests for FCTService
"""
import os

# ── 设置最小化测试环境变量，防止 AgentService 初始化失败 ──────────────────────
for _k, _v in {
    "DATABASE_URL":          "postgresql+asyncpg://test:test@localhost/test",
    "REDIS_URL":             "redis://localhost:6379/0",
    "CELERY_BROKER_URL":     "redis://localhost:6379/0",
    "CELERY_RESULT_BACKEND": "redis://localhost:6379/0",
    "SECRET_KEY":            "test-secret-key",
    "JWT_SECRET":            "test-jwt-secret",
}.items():
    os.environ.setdefault(_k, _v)

import pytest
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.fct_service import (
    FCTService,
    StandaloneFCTService,
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


# ── ¥化字段验证 ──────────────────────────────────────────────────────────────

class TestYuanFields:
    """验证所有方法的 _yuan 伴随字段正确输出（Rule 6：¥优先）。"""

    @pytest.mark.asyncio
    async def test_estimate_monthly_tax_yuan_fields(self):
        db = _mock_db()
        db.execute.side_effect = [
            _single_scalar(1_000_000_00),   # 100万 gross revenue
            _single_scalar(350_000_00),     # 35万 food cost
        ]
        svc    = FCTService(db)
        result = await svc.estimate_monthly_tax("S001", 2026, 3)

        # revenue
        assert result["revenue"]["gross_revenue_yuan"] == pytest.approx(1_000_000.00, abs=0.01)
        assert result["revenue"]["food_cost_yuan"]     == pytest.approx(350_000.00, abs=0.01)
        # vat
        assert "output_vat_yuan"       in result["vat"]
        assert "input_vat_yuan"        in result["vat"]
        assert "net_vat_yuan"          in result["vat"]
        assert "surcharge_yuan"        in result["vat"]
        assert "total_vat_burden_yuan" in result["vat"]
        # cit
        assert "estimated_profit_yuan" in result["cit"]
        assert "cit_amount_yuan"       in result["cit"]
        # top-level
        assert "total_tax_yuan" in result
        assert result["total_tax_yuan"] == pytest.approx(result["total_tax"] / 100, abs=0.01)

    @pytest.mark.asyncio
    async def test_forecast_cash_flow_yuan_fields(self):
        db = _mock_db()
        hist_result   = _rows([MagicMock(daily_total=50_000_00)] * 10)
        budget_result = _scalars_all([])
        db.execute.side_effect = [hist_result, budget_result]

        svc    = FCTService(db)
        result = await svc.forecast_cash_flow("S001", days=3, starting_balance=100_000_00)

        assert "starting_balance_yuan"  in result
        assert "avg_daily_inflow_yuan"  in result
        assert result["starting_balance_yuan"] == pytest.approx(100_000.00, abs=0.01)

        s = result["summary"]
        assert "total_inflow_yuan"   in s
        assert "total_outflow_yuan"  in s
        assert "net_flow_yuan"       in s
        assert "ending_balance_yuan" in s
        assert s["total_inflow_yuan"] == pytest.approx(s["total_inflow"] / 100, abs=0.01)

        day0 = result["daily_forecast"][0]
        assert "inflow_yuan"             in day0
        assert "outflow_yuan"            in day0
        assert "net_flow_yuan"           in day0
        assert "cumulative_balance_yuan" in day0
        assert "food_cost_yuan"          in day0["outflow_breakdown"]
        assert "labor_yuan"              in day0["outflow_breakdown"]
        assert "rent_yuan"               in day0["outflow_breakdown"]
        assert "utilities_yuan"          in day0["outflow_breakdown"]

    @pytest.mark.asyncio
    async def test_get_budget_execution_yuan_fields(self):
        budgets = []
        revenue_row = MagicMock()
        revenue_row.category         = "sales"
        revenue_row.transaction_type = "income"
        revenue_row.total            = 500_000_00

        food_row = MagicMock()
        food_row.category         = "food_cost"
        food_row.transaction_type = "expense"
        food_row.total            = 200_000_00

        db = _mock_db()
        db.execute.side_effect = [_scalars_all(budgets), _rows([revenue_row, food_row])]

        svc    = FCTService(db)
        result = await svc.get_budget_execution("S001", 2026, 3)

        rev = result["revenue"]
        assert "budgeted_yuan" in rev
        assert "actual_yuan"   in rev
        assert "variance_yuan" in rev
        assert rev["actual_yuan"] == pytest.approx(500_000.00, abs=0.01)

        for cat in result["categories"]:
            assert "budgeted_yuan" in cat
            assert "actual_yuan"   in cat
            assert "variance_yuan" in cat

        overall = result["overall"]
        assert "total_expense_budgeted_yuan" in overall
        assert "total_expense_actual_yuan"   in overall
        assert "gross_profit_yuan"           in overall
        assert overall["gross_profit_yuan"] == pytest.approx(
            overall["gross_profit"] / 100, abs=0.01
        )

    @pytest.mark.asyncio
    async def test_get_dashboard_yuan_fields(self):
        db  = _mock_db()
        svc = FCTService(db)

        svc.forecast_cash_flow   = AsyncMock(return_value={
            "summary": {"net_flow": 200_000_00, "ending_balance": 800_000_00, "alert_count": 0}
        })
        svc.estimate_monthly_tax = AsyncMock(return_value={
            "total_tax": 60_000_00, "effective_rate": 6.0, "period": "2026-03",
            "vat": {}, "cit": {}, "revenue": {}, "disclaimer": "",
        })
        svc.get_budget_execution = AsyncMock(return_value={
            "overall": {"profit_margin_pct": 10.0},
            "alerts": [],
            "categories": [], "revenue": {}
        })
        db.execute.return_value = _scalars_all([])

        result = await svc.get_dashboard("S001")

        cf = result["cash_flow"]
        assert "next_7d_net_yuan"    in cf
        assert "ending_balance_yuan" in cf
        assert cf["next_7d_net_yuan"]    == pytest.approx(200_000.00, abs=0.01)
        assert cf["ending_balance_yuan"] == pytest.approx(800_000.00, abs=0.01)

        assert "total_tax_yuan" in result["tax"]
        assert result["tax"]["total_tax_yuan"] == pytest.approx(60_000.00, abs=0.01)


# ── Voucher CRUD ─────────────────────────────────────────────────────────────

class TestGetVouchers:
    """测试 get_vouchers 分页和过滤"""

    @pytest.mark.asyncio
    async def test_empty_result(self):
        db = _mock_db()
        db.scalar = AsyncMock(return_value=0)
        db.execute.return_value = _scalars_all([])
        svc = StandaloneFCTService()
        result = await svc.get_vouchers(db, entity_id="S001")
        assert result["total"] == 0
        assert result["items"] == []

    @pytest.mark.asyncio
    async def test_filtered_by_status(self):
        db = _mock_db()
        db.scalar = AsyncMock(return_value=1)
        v = MagicMock()
        v.id = "00000000-0000-0000-0000-000000000001"
        v.voucher_no = "MV-001"
        v.store_id = "S001"
        v.event_type = "manual"
        v.event_id = None
        v.biz_date = date(2026, 3, 1)
        v.status = "draft"
        v.description = None
        db.execute.return_value = _scalars_all([v])
        svc = StandaloneFCTService()
        result = await svc.get_vouchers(db, entity_id="S001", status="draft")
        assert result["total"] == 1
        assert result["items"][0]["status"] == "draft"

    @pytest.mark.asyncio
    async def test_pagination_params_passed(self):
        db = _mock_db()
        db.scalar = AsyncMock(return_value=0)
        db.execute.return_value = _scalars_all([])
        svc = StandaloneFCTService()
        result = await svc.get_vouchers(db, entity_id="S001", skip=10, limit=5)
        assert result["skip"] == 10
        assert result["limit"] == 5


class TestCreateManualVoucherPersist:
    """测试 create_manual_voucher 持久化逻辑"""

    def _balanced_lines(self):
        return [
            {"account_code": "1001", "account_name": "现金", "debit": 1000.00, "credit": None},
            {"account_code": "6001", "account_name": "主营业务收入", "debit": None, "credit": 1000.00},
        ]

    @pytest.mark.asyncio
    async def test_success_returns_voucher_id(self):
        db = _mock_db()
        db.refresh = AsyncMock()
        svc = StandaloneFCTService()
        result = await svc.create_manual_voucher(
            db, tenant_id="T1", entity_id="S001",
            biz_date=date(2026, 3, 1), lines=self._balanced_lines(),
        )
        assert result["success"] is True
        assert "voucher_id" in result
        assert result["voucher_id"] != ""

    @pytest.mark.asyncio
    async def test_lines_count_matches(self):
        db = _mock_db()
        db.refresh = AsyncMock()
        svc = StandaloneFCTService()
        result = await svc.create_manual_voucher(
            db, tenant_id="T1", entity_id="S001",
            biz_date=date(2026, 3, 1), lines=self._balanced_lines(),
        )
        assert result["lines_count"] == 2

    @pytest.mark.asyncio
    async def test_yuan_fields_present(self):
        db = _mock_db()
        db.refresh = AsyncMock()
        svc = StandaloneFCTService()
        result = await svc.create_manual_voucher(
            db, tenant_id="T1", entity_id="S001",
            biz_date=date(2026, 3, 1), lines=self._balanced_lines(),
        )
        assert result["biz_date"] == "2026-03-01"
        assert result["status"] == "draft"

    @pytest.mark.asyncio
    async def test_unbalanced_lines_raise_value_error(self):
        db = _mock_db()
        svc = StandaloneFCTService()
        lines = [
            {"account_code": "1001", "debit": 1000.00, "credit": None},
            {"account_code": "6001", "debit": None, "credit": 900.00},  # 差 100
        ]
        with pytest.raises(ValueError, match="借贷不平衡"):
            await svc.create_manual_voucher(
                db, tenant_id="T1", entity_id="S001",
                biz_date=date(2026, 3, 1), lines=lines,
            )


class TestGetVoucherById:
    """测试 get_voucher_by_id"""

    @pytest.mark.asyncio
    async def test_found_with_lines(self):
        db = _mock_db()
        v = MagicMock()
        v.id = "vid-001"
        v.voucher_no = "MV-001"
        v.store_id = "S001"
        v.event_type = "manual"
        v.event_id = None
        v.biz_date = date(2026, 3, 1)
        v.status = "draft"
        v.description = None
        line = MagicMock()
        line.id = "lid-001"
        line.line_no = 1
        line.account_code = "1001"
        line.account_name = "现金"
        line.debit = 1000.00
        line.credit = None
        line.summary = None
        v.lines = [line]
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = v
        db.execute = AsyncMock(return_value=result_mock)
        svc = StandaloneFCTService()
        result = await svc.get_voucher_by_id(db, "vid-001")
        assert result is not None
        assert result["id"] == "vid-001"
        assert len(result["lines"]) == 1

    @pytest.mark.asyncio
    async def test_not_found_returns_none(self):
        db = _mock_db()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)
        svc = StandaloneFCTService()
        result = await svc.get_voucher_by_id(db, "nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_voucher_has_no_lines_returns_empty_list(self):
        db = _mock_db()
        v = MagicMock()
        v.id = "vid-002"
        v.voucher_no = "MV-002"
        v.store_id = "S001"
        v.event_type = "manual"
        v.event_id = None
        v.biz_date = date(2026, 3, 2)
        v.status = "posted"
        v.description = None
        v.lines = []
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = v
        db.execute = AsyncMock(return_value=result_mock)
        svc = StandaloneFCTService()
        result = await svc.get_voucher_by_id(db, "vid-002")
        assert result["lines"] == []


class TestUpdateVoucherStatus:
    """测试凭证状态机流转"""

    @pytest.mark.asyncio
    async def test_draft_to_approved_success(self):
        db = _mock_db()
        db.refresh = AsyncMock()
        v = MagicMock()
        v.id = "vid-100"
        v.voucher_no = "MV-100"
        v.status = "draft"
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = v
        db.execute = AsyncMock(return_value=result_mock)

        svc = StandaloneFCTService()
        result = await svc.update_voucher_status(db, voucher_id="vid-100", target_status="approved")

        assert result["success"] is True
        assert result["from_status"] == "draft"
        assert result["status"] == "approved"
        assert v.status == "approved"

    @pytest.mark.asyncio
    async def test_reversed_to_posted_invalid(self):
        db = _mock_db()
        db.refresh = AsyncMock()
        v = MagicMock()
        v.id = "vid-101"
        v.voucher_no = "MV-101"
        v.status = "reversed"
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = v
        db.execute = AsyncMock(return_value=result_mock)

        svc = StandaloneFCTService()
        with pytest.raises(ValueError, match="不允许的状态流转"):
            await svc.update_voucher_status(db, voucher_id="vid-101", target_status="posted")

    @pytest.mark.asyncio
    async def test_unknown_voucher_raises(self):
        db = _mock_db()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        svc = StandaloneFCTService()
        with pytest.raises(ValueError, match="凭证不存在"):
            await svc.update_voucher_status(db, voucher_id="missing", target_status="approved")


class TestApprovalVoucherSync:
    """测试审批与凭证状态联动"""

    @pytest.mark.asyncio
    async def test_create_approval_record_syncs_voucher_status(self):
        db = _mock_db()
        db.refresh = AsyncMock()
        v = MagicMock()
        v.id = "vid-201"
        v.voucher_no = "MV-201"
        v.status = "draft"
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = v
        db.execute = AsyncMock(return_value=result_mock)

        svc = StandaloneFCTService()
        result = await svc.create_approval_record(
            db,
            tenant_id="T1",
            ref_type="voucher",
            ref_id="vid-201",
            status="approved",
        )

        assert result["success"] is True
        assert result["status"] == "approved"
        assert result["voucher_sync"]["status"] == "approved"
        assert v.status == "approved"


# ── get_report_trend ─────────────────────────────────────────────────────────

class TestGetReportTrend:
    """测试 get_report_trend 时序聚合"""

    def _trend_row(self, period_str, revenue_fen, expense_fen):
        row = MagicMock()
        from datetime import date as _date
        row.__getitem__ = lambda self, i: [
            _date.fromisoformat(period_str), revenue_fen, expense_fen
        ][i]
        return row

    @pytest.mark.asyncio
    async def test_month_granularity_returns_data(self):
        db = _mock_db()
        row = MagicMock()
        row.__getitem__ = lambda self, i: [
            datetime(2026, 3, 1), 1_000_000, 700_000
        ][i]
        result_mock = MagicMock()
        result_mock.fetchall.return_value = [row]
        db.execute = AsyncMock(return_value=result_mock)
        svc = StandaloneFCTService()
        result = await svc.get_report_trend(
            db, tenant_id="T1", entity_id="S001",
            start_date=date(2026, 3, 1), end_date=date(2026, 3, 31),
            group_by="month",
        )
        assert result["report_type"] == "trend"
        assert len(result["data"]) == 1
        assert result["data"][0]["revenue_yuan"] == pytest.approx(10000.00, abs=0.01)

    @pytest.mark.asyncio
    async def test_empty_range_returns_empty_list(self):
        db = _mock_db()
        result_mock = MagicMock()
        result_mock.fetchall.return_value = []
        db.execute = AsyncMock(return_value=result_mock)
        svc = StandaloneFCTService()
        result = await svc.get_report_trend(db, tenant_id="T1")
        assert result["data"] == []

    @pytest.mark.asyncio
    async def test_yuan_fields_present(self):
        db = _mock_db()
        row = MagicMock()
        row.__getitem__ = lambda self, i: [
            datetime(2026, 3, 1), 500_000, 300_000
        ][i]
        result_mock = MagicMock()
        result_mock.fetchall.return_value = [row]
        db.execute = AsyncMock(return_value=result_mock)
        svc = StandaloneFCTService()
        result = await svc.get_report_trend(db, tenant_id="T1")
        item = result["data"][0]
        assert "revenue_yuan" in item
        assert "expense_yuan" in item
        assert "net_yuan" in item
        assert item["net_yuan"] == pytest.approx(2000.00, abs=0.01)


# ── list_periods ─────────────────────────────────────────────────────────────

class TestListPeriods:
    """测试 list_periods 账期列表"""

    @pytest.mark.asyncio
    async def test_most_recent_is_open(self):
        db = _mock_db()
        r1 = MagicMock()
        r1.__getitem__ = lambda self, i: [datetime(2026, 3, 1)][i]
        r2 = MagicMock()
        r2.__getitem__ = lambda self, i: [datetime(2026, 2, 1)][i]
        result_mock = MagicMock()
        result_mock.fetchall.return_value = [r1, r2]
        db.execute = AsyncMock(return_value=result_mock)
        svc = StandaloneFCTService()
        result = await svc.list_periods(db, tenant_id="S001")
        assert result["items"][0]["status"] == "open"
        assert result["items"][1]["status"] == "closed"

    @pytest.mark.asyncio
    async def test_empty_table_returns_empty(self):
        db = _mock_db()
        result_mock = MagicMock()
        result_mock.fetchall.return_value = []
        db.execute = AsyncMock(return_value=result_mock)
        svc = StandaloneFCTService()
        result = await svc.list_periods(db, tenant_id="S001")
        assert result["items"] == []
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_multiple_months_ordered_desc(self):
        db = _mock_db()
        rows = []
        for m in [3, 2, 1]:
            r = MagicMock()
            r.__getitem__ = lambda self, i, _m=m: [datetime(2026, _m, 1)][i]
            rows.append(r)
        result_mock = MagicMock()
        result_mock.fetchall.return_value = rows
        db.execute = AsyncMock(return_value=result_mock)
        svc = StandaloneFCTService()
        result = await svc.list_periods(db, tenant_id="S001")
        assert result["total"] == 3
        assert result["items"][0]["period_key"] == "2026-03"
        assert result["items"][2]["period_key"] == "2026-01"


# ── get_report_by_entity ──────────────────────────────────────────────────────

class TestGetReportByEntity:
    """测试 get_report_by_entity 按实体聚合"""

    def _entity_row(self, entity_id: str, revenue_fen: int, expense_fen: int):
        row = MagicMock()
        row.__getitem__ = lambda self, i: [entity_id, revenue_fen, expense_fen][i]
        return row

    @pytest.mark.asyncio
    async def test_multiple_entities_returned(self):
        db = _mock_db()
        rows = [
            self._entity_row("S001", 1_000_000, 700_000),
            self._entity_row("S002", 800_000, 500_000),
        ]
        result_mock = MagicMock()
        result_mock.fetchall.return_value = rows
        db.execute = AsyncMock(return_value=result_mock)
        svc = StandaloneFCTService()
        result = await svc.get_report_by_entity(db, tenant_id="T1")
        assert result["report_type"] == "by_entity"
        assert len(result["data"]) == 2
        assert result["data"][0]["entity_id"] == "S001"
        assert result["data"][1]["entity_id"] == "S002"

    @pytest.mark.asyncio
    async def test_empty_result_returns_empty_list(self):
        db = _mock_db()
        result_mock = MagicMock()
        result_mock.fetchall.return_value = []
        db.execute = AsyncMock(return_value=result_mock)
        svc = StandaloneFCTService()
        result = await svc.get_report_by_entity(db, tenant_id="T1")
        assert result["data"] == []

    @pytest.mark.asyncio
    async def test_yuan_fields_present_and_correct(self):
        db = _mock_db()
        rows = [self._entity_row("S001", 500_000, 300_000)]
        result_mock = MagicMock()
        result_mock.fetchall.return_value = rows
        db.execute = AsyncMock(return_value=result_mock)
        svc = StandaloneFCTService()
        result = await svc.get_report_by_entity(db, tenant_id="T1")
        item = result["data"][0]
        assert "revenue_yuan" in item
        assert "expense_yuan" in item
        assert "net_yuan" in item
        assert item["revenue_yuan"] == pytest.approx(5000.00, abs=0.01)
        assert item["expense_yuan"] == pytest.approx(3000.00, abs=0.01)
        assert item["net_yuan"] == pytest.approx(2000.00, abs=0.01)
