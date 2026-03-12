"""
食材成本真相引擎 — 单元测试

覆盖：
  - classify_severity: 4级分级
  - compute_dish_variance: 正常/空/单菜品
  - compute_ingredient_variance: 超标/节约/空
  - attribute_variance: 完整归因/仅损耗/仅价格/零差异
  - predict_month_end_cost_rate: 正常/月初/零收入
  - build_cost_truth_report: 端到端
  - generate_one_sentence_insight: 超标/正常
  - generate_actionable_decision: critical/ok
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

import pytest
from src.services.cost_truth_engine import (
    DishSale, IngredientUsage, WasteRecord,
    classify_severity,
    compute_dish_variance,
    compute_ingredient_variance,
    attribute_variance,
    predict_month_end_cost_rate,
    build_cost_truth_report,
    generate_one_sentence_insight,
    generate_actionable_decision,
    _yuan, _safe_pct,
)


# ── Helpers ──

def _sale(dish_id="D1", name="鱼", qty=10, rev=10000, bom=300):
    return DishSale(dish_id, name, qty, rev, bom)

def _usage(iid="I1", name="鲈鱼", theo=5.0, actual=6.0, unit="kg", cost=1800, prev=1800):
    return IngredientUsage(iid, name, theo, actual, unit, cost, prev)

def _waste(iid="I1", name="鲈鱼", qty=0.5, unit="kg", cost=1800, cause="staff_error"):
    return WasteRecord(iid, name, qty, unit, cost, cause)


# ── classify_severity ──

class TestClassifySeverity:
    def test_ok(self):
        assert classify_severity(0.5) == "ok"

    def test_watch(self):
        assert classify_severity(1.5) == "watch"

    def test_warning(self):
        assert classify_severity(2.5) == "warning"

    def test_critical(self):
        assert classify_severity(4.0) == "critical"

    def test_negative_uses_abs(self):
        assert classify_severity(-3.5) == "critical"

    def test_zero(self):
        assert classify_severity(0.0) == "ok"

    def test_boundary_1(self):
        assert classify_severity(1.0) == "ok"

    def test_boundary_2(self):
        assert classify_severity(2.0) == "watch"

    def test_boundary_3(self):
        assert classify_severity(3.0) == "warning"


# ── compute_dish_variance ──

class TestComputeDishVariance:
    def test_normal(self):
        sales = [_sale("D1", "鱼", 10, 10000, 300), _sale("D2", "肉", 5, 5000, 200)]
        usages = [_usage("I1", "鱼", 3.5, 4.0, "kg", 1000)]
        result = compute_dish_variance(sales, usages)
        assert len(result) == 2
        assert result[0].dish_name in ("鱼", "肉")

    def test_empty_sales(self):
        assert compute_dish_variance([], [_usage()]) == []

    def test_single_dish(self):
        sales = [_sale("D1", "鱼", 20, 20000, 500)]
        usages = [_usage("I1", "鱼", 10.0, 12.0, "kg", 1000)]
        result = compute_dish_variance(sales, usages)
        assert len(result) == 1
        assert result[0].variance_fen != 0

    def test_sorted_by_variance_abs(self):
        sales = [
            _sale("D1", "A", 10, 10000, 100),
            _sale("D2", "B", 10, 10000, 500),
        ]
        usages = [_usage("I1", "x", 5, 7, "kg", 1000)]
        result = compute_dish_variance(sales, usages)
        assert abs(result[0].variance_fen) >= abs(result[1].variance_fen)


# ── compute_ingredient_variance ──

class TestComputeIngredientVariance:
    def test_overrun(self):
        usages = [_usage("I1", "鲈鱼", 5.0, 6.0, "kg", 1800)]
        result = compute_ingredient_variance(usages)
        assert len(result) == 1
        assert result[0]["variance_qty"] == pytest.approx(1.0)
        assert result[0]["variance_cost_fen"] == 1800

    def test_saving(self):
        usages = [_usage("I1", "鲈鱼", 5.0, 4.0, "kg", 1800)]
        result = compute_ingredient_variance(usages)
        assert result[0]["variance_qty"] == pytest.approx(-1.0)
        assert result[0]["variance_cost_fen"] == -1800

    def test_empty(self):
        assert compute_ingredient_variance([]) == []

    def test_sorted_by_abs(self):
        usages = [
            _usage("I1", "A", 5, 5.5, "kg", 100),
            _usage("I2", "B", 5, 7.0, "kg", 1000),
        ]
        result = compute_ingredient_variance(usages)
        assert abs(result[0]["variance_cost_fen"]) >= abs(result[1]["variance_cost_fen"])


# ── attribute_variance ──

class TestAttributeVariance:
    def test_zero_variance(self):
        assert attribute_variance(0, [], [], []) == []

    def test_waste_only(self):
        usages = [_usage("I1", "鱼", 5.0, 5.5, "kg", 1800)]
        wastes = [_waste("I1", "鱼", 0.5, "kg", 1800)]
        result = attribute_variance(900, usages, wastes, [_sale()])
        factor_names = [r.factor for r in result]
        assert "waste_loss" in factor_names

    def test_price_change(self):
        usages = [_usage("I1", "鱼", 5.0, 5.0, "kg", 2000, prev=1800)]
        result = attribute_variance(1000, usages, [], [_sale()])
        factor_names = [r.factor for r in result]
        assert "price_change" in factor_names
        price_attr = [r for r in result if r.factor == "price_change"][0]
        assert price_attr.contribution_fen == 5 * (2000 - 1800)

    def test_overrun(self):
        usages = [_usage("I1", "鱼", 5.0, 7.0, "kg", 1800)]
        result = attribute_variance(3600, usages, [], [_sale()])
        factor_names = [r.factor for r in result]
        assert "usage_overrun" in factor_names

    def test_mix_shift_is_residual(self):
        usages = [_usage("I1", "鱼", 5.0, 5.0, "kg", 1800)]
        # No price change, no waste, no overrun → all goes to mix_shift
        result = attribute_variance(500, usages, [], [_sale()])
        mix = [r for r in result if r.factor == "mix_shift"]
        assert len(mix) == 1
        assert mix[0].contribution_fen == 500

    def test_all_factors(self):
        usages = [_usage("I1", "鱼", 5.0, 7.0, "kg", 2000, prev=1800)]
        wastes = [_waste("I1", "鱼", 0.5, "kg", 2000)]
        total = 5000
        result = attribute_variance(total, usages, wastes, [_sale()])
        assert len(result) >= 3
        total_explained = sum(r.contribution_fen for r in result)
        assert total_explained == total

    def test_sorted_by_contribution(self):
        usages = [
            _usage("I1", "鱼", 5.0, 7.0, "kg", 2000, prev=1800),
            _usage("I2", "肉", 3.0, 3.5, "kg", 1500),
        ]
        wastes = [_waste("I1", "鱼", 0.3, "kg", 2000)]
        result = attribute_variance(5000, usages, wastes, [_sale()])
        for i in range(len(result) - 1):
            assert abs(result[i].contribution_fen) >= abs(result[i + 1].contribution_fen)


# ── predict_month_end_cost_rate ──

class TestPredictMonthEnd:
    def test_normal(self):
        rate = predict_month_end_cost_rate(100000, 33000, 10, 30)
        assert rate == pytest.approx(33.0, abs=0.1)

    def test_early_month(self):
        rate = predict_month_end_cost_rate(30000, 10500, 3, 30)
        assert rate == pytest.approx(35.0, abs=0.1)

    def test_zero_revenue(self):
        assert predict_month_end_cost_rate(0, 0, 5, 30) == 0.0

    def test_zero_days(self):
        assert predict_month_end_cost_rate(100000, 33000, 0, 30) == 0.0


# ── build_cost_truth_report ──

class TestBuildReport:
    def _build(self):
        sales = [_sale("D1", "酸菜鱼", 42, 285600, 2850)]
        usages = [_usage("I1", "鲈鱼", 14.7, 17.2, "kg", 1800, 1650)]
        wastes = [_waste("I1", "鲈鱼", 1.2, "kg", 1800)]
        return build_cost_truth_report(
            store_id="S001", truth_date="2026-03-11",
            revenue_fen=285600, sales=sales, usages=usages, wastes=wastes,
            target_pct=32.0,
            mtd_revenue_fen=285600 * 11,
            mtd_actual_cost_fen=int(285600 * 0.34 * 11),
            days_elapsed=11, days_in_month=31,
        )

    def test_report_fields(self):
        r = self._build()
        assert r.store_id == "S001"
        assert r.revenue_fen == 285600
        assert r.theoretical_cost_fen > 0
        assert r.actual_cost_fen > 0
        assert r.severity in ("ok", "watch", "warning", "critical")

    def test_dish_details(self):
        r = self._build()
        assert len(r.dish_details) == 1
        assert r.dish_details[0].dish_name == "酸菜鱼"

    def test_attributions_exist(self):
        r = self._build()
        assert len(r.attributions) > 0

    def test_prediction(self):
        r = self._build()
        assert r.predicted_eom_pct is not None
        assert r.mtd_actual_pct is not None

    def test_target(self):
        r = self._build()
        assert r.target_pct == 32.0


# ── generate_one_sentence_insight ──

class TestInsight:
    def test_over_target(self):
        r = build_cost_truth_report(
            "S1", "2026-03-11", 100000,
            [_sale("D1", "鱼", 10, 100000, 3500)],
            [_usage("I1", "鱼", 5.0, 6.5, "kg", 1800)],
            [_waste("I1", "鱼", 0.5, "kg", 1800)],
            target_pct=30.0,
        )
        insight = generate_one_sentence_insight(r)
        assert "成本率" in insight

    def test_under_control(self):
        r = build_cost_truth_report(
            "S1", "2026-03-11", 100000,
            [_sale("D1", "鱼", 10, 100000, 2000)],
            [_usage("I1", "鱼", 5.0, 4.8, "kg", 1000)],
            [],
        )
        insight = generate_one_sentence_insight(r)
        assert "控制良好" in insight or "成本率" in insight


# ── generate_actionable_decision ──

class TestActionableDecision:
    def test_critical_generates_decision(self):
        r = build_cost_truth_report(
            "S1", "2026-03-11", 100000,
            [_sale("D1", "鱼", 50, 100000, 3500)],
            [_usage("I1", "鱼", 17.5, 25.0, "kg", 1800)],
            [_waste("I1", "鱼", 2.0, "kg", 1800)],
            target_pct=30.0,
        )
        decision = generate_actionable_decision(r)
        assert decision is not None
        assert decision["source"] == "cost_truth_engine"
        assert decision["expected_monthly_saving_yuan"] > 0

    def test_ok_no_decision(self):
        r = build_cost_truth_report(
            "S1", "2026-03-11", 100000,
            [_sale("D1", "鱼", 10, 100000, 500)],
            [_usage("I1", "鱼", 5.0, 5.0, "kg", 1000)],
            [],
        )
        assert generate_actionable_decision(r) is None


# ── _yuan / _safe_pct ──

class TestHelpers:
    def test_yuan(self):
        assert _yuan(12345) == 123.45

    def test_yuan_zero(self):
        assert _yuan(0) == 0.0

    def test_yuan_none(self):
        assert _yuan(None) == 0.0

    def test_safe_pct(self):
        assert _safe_pct(35, 100) == 35.0

    def test_safe_pct_zero_denom(self):
        assert _safe_pct(35, 0) == 0.0
