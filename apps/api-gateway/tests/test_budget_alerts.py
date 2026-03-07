"""
Phase 5 Month 4 — 预算管理 + 财务预警体系

测试覆盖:
  - budget_service:          compute_variance / FSM transitions / CRUD / variance calc
  - financial_alert_service: _check_threshold / _format_alert_message / metric fetchers /
                              rule CRUD / alert evaluation / alert FSM

Run:  pytest tests/test_budget_alerts.py -v
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

from src.services.budget_service import (          # noqa: E402
    BUDGET_CATEGORIES,
    CATEGORY_TO_ACTUAL_COL,
    VALID_BUDGET_TRANSITIONS,
    compute_variance,
    create_or_update_budget_plan,
    get_budget_variance,
    transition_budget_status,
)
from src.services.financial_alert_service import (  # noqa: E402
    SUPPORTED_METRICS,
    VALID_ALERT_TRANSITIONS,
    _check_threshold,
    _format_alert_message,
    _get_metric_value,
    create_or_update_rule,
    evaluate_store_alerts,
    transition_alert_status,
)


# ─────────────────────────────────────────────────────────────────────────────
# Budget constants
# ─────────────────────────────────────────────────────────────────────────────

class TestBudgetConstants:
    def test_all_categories_present(self):
        expected = {"revenue", "food_cost", "labor_cost",
                    "platform_commission", "waste", "other_expense", "tax"}
        assert set(BUDGET_CATEGORIES) == expected

    def test_category_to_actual_col_keys(self):
        # "tax" has no direct column (computed separately) — only 6 mapped
        assert "revenue" in CATEGORY_TO_ACTUAL_COL
        assert "food_cost" in CATEGORY_TO_ACTUAL_COL
        assert "tax" not in CATEGORY_TO_ACTUAL_COL

    def test_valid_transitions_structure(self):
        assert "draft"    in VALID_BUDGET_TRANSITIONS
        assert "approved" in VALID_BUDGET_TRANSITIONS
        assert "active"   in VALID_BUDGET_TRANSITIONS
        assert "closed"   in VALID_BUDGET_TRANSITIONS


# ─────────────────────────────────────────────────────────────────────────────
# compute_variance
# ─────────────────────────────────────────────────────────────────────────────

class TestComputeVariance:
    def test_positive_variance(self):
        r = compute_variance(100_000, 120_000)
        assert r["variance_yuan"] == 20_000.0
        assert r["variance_pct"]  == 20.0

    def test_negative_variance(self):
        r = compute_variance(100_000, 80_000)
        assert r["variance_yuan"] == -20_000.0
        assert r["variance_pct"]  == -20.0

    def test_zero_variance(self):
        r = compute_variance(50_000, 50_000)
        assert r["variance_yuan"] == 0.0
        assert r["variance_pct"]  == 0.0

    def test_zero_budget_no_division_error(self):
        r = compute_variance(0.0, 30_000)
        assert r["variance_yuan"] == 30_000.0
        assert r["variance_pct"]  == 0.0

    def test_rounding_yuan(self):
        r = compute_variance(3.0, 4.0)
        # variance_yuan should be a float with at most 2 decimal places
        assert isinstance(r["variance_yuan"], float)

    def test_rounding_pct(self):
        r = compute_variance(3.0, 4.0)
        assert r["variance_pct"] == round(100 / 3, 1)


# ─────────────────────────────────────────────────────────────────────────────
# Budget FSM transitions
# ─────────────────────────────────────────────────────────────────────────────

class TestBudgetFSMTransitions:
    def test_draft_to_approved(self):
        assert "approved" in VALID_BUDGET_TRANSITIONS["draft"]

    def test_approved_to_active(self):
        assert "active" in VALID_BUDGET_TRANSITIONS["approved"]

    def test_approved_back_to_draft(self):
        assert "draft" in VALID_BUDGET_TRANSITIONS["approved"]

    def test_active_to_closed(self):
        assert "closed" in VALID_BUDGET_TRANSITIONS["active"]

    def test_closed_is_terminal(self):
        assert len(VALID_BUDGET_TRANSITIONS["closed"]) == 0

    def test_draft_cannot_go_active(self):
        assert "active" not in VALID_BUDGET_TRANSITIONS["draft"]


# ─────────────────────────────────────────────────────────────────────────────
# transition_budget_status
# ─────────────────────────────────────────────────────────────────────────────

class TestTransitionBudgetStatus:
    def _make_db(self, plan_row):
        db = AsyncMock()
        call_count = [0]

        async def side_effect(q, params=None):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.fetchone = MagicMock(return_value=plan_row)
            else:
                result.fetchone = MagicMock(return_value=None)
            return result

        db.execute = side_effect
        db.commit   = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_valid_draft_to_approved(self):
        db = self._make_db(("plan-1", "draft"))
        result = await transition_budget_status(db, "plan-1", "approved")
        assert result["new_status"] == "approved"
        assert result["old_status"] == "draft"

    @pytest.mark.asyncio
    async def test_valid_approved_to_active(self):
        db = self._make_db(("plan-1", "approved"))
        result = await transition_budget_status(db, "plan-1", "active")
        assert result["new_status"] == "active"

    @pytest.mark.asyncio
    async def test_invalid_transition_returns_error(self):
        db = self._make_db(("plan-1", "draft"))
        result = await transition_budget_status(db, "plan-1", "closed")
        assert "error" in result
        assert "Cannot transition" in result["error"]

    @pytest.mark.asyncio
    async def test_plan_not_found_returns_error(self):
        db = self._make_db(None)
        result = await transition_budget_status(db, "missing", "approved")
        assert result["error"] == "Plan not found"

    @pytest.mark.asyncio
    async def test_approved_sets_approved_at_column(self):
        """Verify that approving calls execute twice (SELECT + UPDATE with approved_at)."""
        db = self._make_db(("plan-1", "draft"))
        calls = []
        original = db.execute

        async def recording_execute(q, params=None):
            calls.append(str(q))
            return await original(q, params)

        db.execute = recording_execute
        await transition_budget_status(db, "plan-1", "approved")
        assert len(calls) == 2
        assert any("approved_at" in c for c in calls)


# ─────────────────────────────────────────────────────────────────────────────
# create_or_update_budget_plan
# ─────────────────────────────────────────────────────────────────────────────

class TestCreateOrUpdateBudgetPlan:
    def _make_db_new(self):
        """Simulate no existing plan."""
        db = AsyncMock()
        insert_calls = [0]

        async def side_effect(q, params=None):
            insert_calls[0] += 1
            result = MagicMock()
            if insert_calls[0] == 1:
                result.fetchone = MagicMock(return_value=None)
            return result

        db.execute = side_effect
        db.commit   = AsyncMock()
        return db, insert_calls

    def _make_db_existing_draft(self, plan_id="plan-draft"):
        db = AsyncMock()
        call_count = [0]

        async def side_effect(q, params=None):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.fetchone = MagicMock(return_value=(plan_id, "draft"))
            return result

        db.execute = side_effect
        db.commit   = AsyncMock()
        return db

    def _make_db_existing_approved(self, plan_id="plan-approved"):
        db = AsyncMock()

        async def side_effect(q, params=None):
            result = MagicMock()
            result.fetchone = MagicMock(return_value=(plan_id, "approved"))
            return result

        db.execute = side_effect
        db.commit   = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_create_new_plan(self):
        db, _ = self._make_db_new()
        result = await create_or_update_budget_plan(
            db, "s1", "2026-03", "monthly", None,
            500_000, 300_000, 200_000, None, [],
        )
        assert result["action"] == "created"
        assert result["status"] == "draft"
        assert "plan_id" in result

    @pytest.mark.asyncio
    async def test_update_existing_draft(self):
        db = self._make_db_existing_draft()
        result = await create_or_update_budget_plan(
            db, "s1", "2026-03", "monthly", None,
            600_000, 350_000, 250_000, None, [],
        )
        assert result["action"] == "updated"
        assert result["plan_id"] == "plan-draft"

    @pytest.mark.asyncio
    async def test_cannot_update_approved_plan(self):
        db = self._make_db_existing_approved()
        result = await create_or_update_budget_plan(
            db, "s1", "2026-03", "monthly", None,
            600_000, 350_000, 250_000, None, [],
        )
        assert "error" in result
        assert "approved" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_category_is_skipped(self):
        db, insert_calls = self._make_db_new()
        line_items = [
            {"category": "revenue",  "budget_yuan": 500_000},
            {"category": "invalid!", "budget_yuan": 10_000},
        ]
        result = await create_or_update_budget_plan(
            db, "s1", "2026-03", "monthly", None,
            500_000, 300_000, 200_000, None, line_items,
        )
        assert result["action"] == "created"
        # "invalid!" category should be silently skipped (no error)

    @pytest.mark.asyncio
    async def test_line_items_all_valid_categories(self):
        db, _ = self._make_db_new()
        line_items = [
            {"category": cat, "budget_yuan": 10_000}
            for cat in BUDGET_CATEGORIES if cat != "tax"
        ]
        result = await create_or_update_budget_plan(
            db, "s1", "2026-02", "monthly", "brand-1",
            500_000, 300_000, 200_000, "test notes", line_items,
        )
        assert result["action"] == "created"


# ─────────────────────────────────────────────────────────────────────────────
# get_budget_variance
# ─────────────────────────────────────────────────────────────────────────────

class TestGetBudgetVariance:
    def _make_db_with_plan(self, actuals_row=None):
        db = AsyncMock()
        call_count = [0]

        plan_row  = ("plan-1", "s1", "2026-03", "monthly", "active",
                     500_000, 300_000, 200_000, None, None, None, None)
        li_rows   = [
            ("li-1", "revenue",   None, 500_000),
            ("li-2", "food_cost", None, 200_000),
        ]

        async def side_effect(q, params=None):
            call_count[0] += 1
            result = MagicMock()
            c = call_count[0]
            if c == 1:    # budget_plans SELECT
                result.fetchone = MagicMock(return_value=plan_row)
            elif c == 2:  # budget_line_items SELECT
                result.fetchall = MagicMock(return_value=li_rows)
            elif c == 3:  # profit_attribution_results SELECT
                result.fetchone = MagicMock(return_value=actuals_row)
            return result

        db.execute = side_effect
        return db

    @pytest.mark.asyncio
    async def test_variance_with_actuals(self):
        actuals = (480_000, 210_000, 50_000, 30_000, 5_000, 15_000,
                   310_000, 170_000, 35.4)
        db = self._make_db_with_plan(actuals)
        result = await get_budget_variance(db, "plan-1")
        assert result is not None
        assert result["plan_id"] == "plan-1"
        assert result["summary"]["revenue_actual"] == 480_000.0
        # Revenue variance: 480k - 500k = -20k
        assert result["summary"]["revenue_variance"]["variance_yuan"] == -20_000.0

    @pytest.mark.asyncio
    async def test_variance_no_actuals(self):
        db = self._make_db_with_plan(actuals_row=None)
        result = await get_budget_variance(db, "plan-1")
        assert result is not None
        # All actuals should default to 0
        assert result["summary"]["revenue_actual"] == 0.0
        assert result["summary"]["profit_margin_pct"] == 0.0

    @pytest.mark.asyncio
    async def test_plan_not_found_returns_none(self):
        db = AsyncMock()

        async def side_effect(q, params=None):
            r = MagicMock()
            r.fetchone = MagicMock(return_value=None)
            r.fetchall = MagicMock(return_value=[])
            return r

        db.execute = side_effect
        result = await get_budget_variance(db, "nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_line_item_variance_calculation(self):
        actuals = (480_000, 220_000, 50_000, 30_000, 5_000, 15_000,
                   320_000, 160_000, 33.3)
        db = self._make_db_with_plan(actuals)
        result = await get_budget_variance(db, "plan-1")
        li = {item["category"]: item for item in result["line_items"]}
        # food_cost: budget=200k, actual=220k → +20k
        assert li["food_cost"]["variance_yuan"] == 20_000.0
        assert li["food_cost"]["variance_pct"]  == 10.0


# ─────────────────────────────────────────────────────────────────────────────
# Alert constants
# ─────────────────────────────────────────────────────────────────────────────

class TestAlertConstants:
    def test_supported_metrics_count(self):
        assert len(SUPPORTED_METRICS) == 7

    def test_key_metrics_present(self):
        for m in ("profit_margin_pct", "food_cost_rate", "cash_gap_days"):
            assert m in SUPPORTED_METRICS

    def test_alert_transitions_structure(self):
        assert "open"         in VALID_ALERT_TRANSITIONS
        assert "acknowledged" in VALID_ALERT_TRANSITIONS
        assert "resolved"     in VALID_ALERT_TRANSITIONS

    def test_resolved_is_terminal(self):
        assert len(VALID_ALERT_TRANSITIONS["resolved"]) == 0


# ─────────────────────────────────────────────────────────────────────────────
# _check_threshold
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckThreshold:
    def test_above_triggered(self):
        assert _check_threshold(25.0, "above", 20.0) is True

    def test_above_not_triggered(self):
        assert _check_threshold(15.0, "above", 20.0) is False

    def test_above_boundary_not_triggered(self):
        assert _check_threshold(20.0, "above", 20.0) is False   # strict >

    def test_below_triggered(self):
        assert _check_threshold(5.0, "below", 10.0) is True

    def test_below_not_triggered(self):
        assert _check_threshold(15.0, "below", 10.0) is False

    def test_abs_above_triggered_negative(self):
        assert _check_threshold(-25.0, "abs_above", 20.0) is True

    def test_abs_above_positive(self):
        assert _check_threshold(25.0, "abs_above", 20.0) is True

    def test_unknown_type_returns_false(self):
        assert _check_threshold(100.0, "unknown_type", 10.0) is False


# ─────────────────────────────────────────────────────────────────────────────
# _format_alert_message
# ─────────────────────────────────────────────────────────────────────────────

class TestFormatAlertMessage:
    def test_profit_margin_pct(self):
        msg = _format_alert_message("profit_margin_pct", 8.0, "below", 10.0)
        assert "利润率" in msg
        assert "8.0%" in msg
        assert "低于" in msg

    def test_food_cost_rate_above(self):
        msg = _format_alert_message("food_cost_rate", 42.0, "above", 35.0)
        assert "食材成本率" in msg
        assert "超过" in msg

    def test_revenue_yuan(self):
        msg = _format_alert_message("net_revenue_yuan", 50_000, "below", 80_000)
        assert "净收入" in msg
        assert "¥" in msg

    def test_cash_gap_days(self):
        msg = _format_alert_message("cash_gap_days", 5.0, "above", 3.0)
        assert "现金缺口" in msg

    def test_unknown_metric_fallback(self):
        msg = _format_alert_message("unknown_metric", 99.0, "above", 50.0)
        assert "99" in msg


# ─────────────────────────────────────────────────────────────────────────────
# Alert FSM transitions
# ─────────────────────────────────────────────────────────────────────────────

class TestAlertFSMTransitions:
    def test_open_can_be_acknowledged(self):
        assert "acknowledged" in VALID_ALERT_TRANSITIONS["open"]

    def test_open_can_be_resolved(self):
        assert "resolved" in VALID_ALERT_TRANSITIONS["open"]

    def test_acknowledged_can_be_resolved(self):
        assert "resolved" in VALID_ALERT_TRANSITIONS["acknowledged"]

    def test_acknowledged_cannot_reopen(self):
        assert "open" not in VALID_ALERT_TRANSITIONS["acknowledged"]

    def test_resolved_terminal(self):
        assert len(VALID_ALERT_TRANSITIONS["resolved"]) == 0


# ─────────────────────────────────────────────────────────────────────────────
# transition_alert_status
# ─────────────────────────────────────────────────────────────────────────────

class TestTransitionAlertStatus:
    def _make_db(self, alert_row):
        db = AsyncMock()
        call_count = [0]

        async def side_effect(q, params=None):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.fetchone = MagicMock(return_value=alert_row)
            return result

        db.execute = side_effect
        db.commit   = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_acknowledge_open_alert(self):
        db = self._make_db(("a-1", "open"))
        result = await transition_alert_status(db, "a-1", "acknowledged")
        assert result["new_status"] == "acknowledged"
        assert result["old_status"] == "open"

    @pytest.mark.asyncio
    async def test_resolve_acknowledged_alert(self):
        db = self._make_db(("a-1", "acknowledged"))
        result = await transition_alert_status(db, "a-1", "resolved")
        assert result["new_status"] == "resolved"

    @pytest.mark.asyncio
    async def test_invalid_transition_returns_error(self):
        db = self._make_db(("a-1", "resolved"))
        result = await transition_alert_status(db, "a-1", "open")
        assert "error" in result
        assert "Cannot transition" in result["error"]

    @pytest.mark.asyncio
    async def test_alert_not_found_returns_error(self):
        db = self._make_db(None)
        result = await transition_alert_status(db, "missing", "acknowledged")
        assert result["error"] == "Alert not found"

    @pytest.mark.asyncio
    async def test_resolve_sets_resolved_at(self):
        db = self._make_db(("a-1", "open"))
        calls = []
        original = db.execute

        async def recording(q, params=None):
            calls.append(str(q))
            return await original(q, params)

        db.execute = recording
        await transition_alert_status(db, "a-1", "resolved")
        update_calls = [c for c in calls if "UPDATE" in c]
        assert any("resolved_at" in c for c in update_calls)


# ─────────────────────────────────────────────────────────────────────────────
# create_or_update_rule
# ─────────────────────────────────────────────────────────────────────────────

class TestCreateOrUpdateRule:
    def _make_db(self, find_row=None):
        db = AsyncMock()
        call_count = [0]

        async def side_effect(q, params=None):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.fetchone = MagicMock(return_value=find_row)
            return result

        db.execute = side_effect
        db.commit   = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_create_new_rule(self):
        db = self._make_db()
        result = await create_or_update_rule(
            db, store_id="s1", metric="profit_margin_pct",
            threshold_type="below", threshold_value=10.0,
            severity="warning", cooldown_minutes=60,
        )
        assert result["action"] == "created"
        assert "rule_id" in result

    @pytest.mark.asyncio
    async def test_unsupported_metric_returns_error(self):
        db = self._make_db()
        result = await create_or_update_rule(
            db, store_id="s1", metric="nonexistent_kpi",
            threshold_type="above", threshold_value=100.0,
            severity="warning", cooldown_minutes=60,
        )
        assert "error" in result
        assert "Unsupported metric" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_threshold_type_returns_error(self):
        db = self._make_db()
        result = await create_or_update_rule(
            db, store_id="s1", metric="profit_margin_pct",
            threshold_type="greater_than",   # invalid
            threshold_value=10.0, severity="warning", cooldown_minutes=60,
        )
        assert "error" in result
        assert "threshold_type" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_severity_returns_error(self):
        db = self._make_db()
        result = await create_or_update_rule(
            db, store_id="s1", metric="profit_margin_pct",
            threshold_type="below", threshold_value=10.0,
            severity="ultra_critical",   # invalid
            cooldown_minutes=60,
        )
        assert "error" in result
        assert "severity" in result["error"]

    @pytest.mark.asyncio
    async def test_update_existing_rule(self):
        db = self._make_db(find_row=("rule-1",))
        result = await create_or_update_rule(
            db, store_id="s1", metric="food_cost_rate",
            threshold_type="above", threshold_value=40.0,
            severity="critical", cooldown_minutes=120,
            rule_id="rule-1",
        )
        assert result["action"] == "updated"
        assert result["rule_id"] == "rule-1"


# ─────────────────────────────────────────────────────────────────────────────
# _get_metric_value
# ─────────────────────────────────────────────────────────────────────────────

class TestGetMetricValue:
    def _make_db_par(self, fetchone_row):
        """Single-query mock that returns a fetchone row."""
        db = AsyncMock()

        async def side_effect(q, params=None):
            result = MagicMock()
            result.fetchone = MagicMock(return_value=fetchone_row)
            return result

        db.execute = side_effect
        return db

    @pytest.mark.asyncio
    async def test_profit_margin_pct(self):
        db = self._make_db_par((100_000, 40_000, 25_000, 25.0))
        v = await _get_metric_value(db, "s1", "2026-03", "profit_margin_pct")
        assert v == 25.0

    @pytest.mark.asyncio
    async def test_food_cost_rate(self):
        db = self._make_db_par((100_000, 35_000, 25_000, 25.0))
        v = await _get_metric_value(db, "s1", "2026-03", "food_cost_rate")
        assert v == pytest.approx(35.0, rel=1e-2)

    @pytest.mark.asyncio
    async def test_net_revenue_yuan(self):
        db = self._make_db_par((120_000, 40_000, 30_000, 25.0))
        v = await _get_metric_value(db, "s1", "2026-03", "net_revenue_yuan")
        assert v == 120_000.0

    @pytest.mark.asyncio
    async def test_cash_gap_days(self):
        db = self._make_db_par((7,))
        v = await _get_metric_value(db, "s1", "2026-03", "cash_gap_days")
        assert v == 7.0

    @pytest.mark.asyncio
    async def test_settlement_high_risk(self):
        db = self._make_db_par((3,))
        v = await _get_metric_value(db, "s1", "2026-03", "settlement_high_risk")
        assert v == 3.0

    @pytest.mark.asyncio
    async def test_tax_deviation_pct(self):
        db = self._make_db_par((12.5,))
        v = await _get_metric_value(db, "s1", "2026-03", "tax_deviation_pct")
        assert v == pytest.approx(12.5, rel=1e-3)

    @pytest.mark.asyncio
    async def test_no_data_returns_none(self):
        db = self._make_db_par(None)
        v = await _get_metric_value(db, "s1", "2026-03", "profit_margin_pct")
        assert v is None

    @pytest.mark.asyncio
    async def test_unsupported_metric_returns_none(self):
        db = self._make_db_par((999,))
        v = await _get_metric_value(db, "s1", "2026-03", "nonexistent")
        assert v is None


# ─────────────────────────────────────────────────────────────────────────────
# evaluate_store_alerts
# ─────────────────────────────────────────────────────────────────────────────

class TestEvaluateStoreAlerts:
    @pytest.mark.asyncio
    async def test_no_enabled_rules(self):
        db = AsyncMock()

        async def side_effect(q, params=None):
            r = MagicMock()
            r.fetchall  = MagicMock(return_value=[])
            r.fetchone  = MagicMock(return_value=None)
            return r

        db.execute = side_effect
        db.commit   = AsyncMock()
        result = await evaluate_store_alerts(db, "s1", "2026-03")
        assert result["rules_evaluated"]  == 0
        assert result["alerts_triggered"] == 0

    @pytest.mark.asyncio
    async def test_rule_not_triggered(self):
        """Rule says profit_margin_pct < 10%, actual is 25% → no alert."""
        db = AsyncMock()
        call_count = [0]

        async def side_effect(q, params=None):
            call_count[0] += 1
            r = MagicMock()
            if call_count[0] == 1:
                # Rules query
                r.fetchall = MagicMock(return_value=[
                    ("rule-1", "profit_margin_pct", "below", 10.0, "warning", 60),
                ])
            elif call_count[0] == 2:
                # Metric query → margin=25%
                r.fetchone = MagicMock(return_value=(100_000, 35_000, 25_000, 25.0))
            return r

        db.execute = side_effect
        db.commit   = AsyncMock()
        result = await evaluate_store_alerts(db, "s1", "2026-03")
        assert result["alerts_triggered"] == 0

    @pytest.mark.asyncio
    async def test_rule_triggered_creates_event(self):
        """Rule says profit_margin_pct < 10%, actual is 5% → alert created."""
        db = AsyncMock()
        call_count = [0]

        async def side_effect(q, params=None):
            call_count[0] += 1
            r = MagicMock()
            if call_count[0] == 1:
                r.fetchall = MagicMock(return_value=[
                    ("rule-1", "profit_margin_pct", "below", 10.0, "warning", 60),
                ])
            elif call_count[0] == 2:
                r.fetchone = MagicMock(return_value=(100_000, 35_000, 5_000, 5.0))
            elif call_count[0] == 3:
                # Cooldown check → no recent event
                r.fetchone = MagicMock(return_value=None)
            return r

        db.execute = side_effect
        db.commit   = AsyncMock()
        result = await evaluate_store_alerts(db, "s1", "2026-03")
        assert result["alerts_triggered"] == 1

    @pytest.mark.asyncio
    async def test_cooldown_skip(self):
        """If recent event exists within cooldown, skip."""
        db = AsyncMock()
        call_count = [0]

        async def side_effect(q, params=None):
            call_count[0] += 1
            r = MagicMock()
            if call_count[0] == 1:
                r.fetchall = MagicMock(return_value=[
                    ("rule-1", "profit_margin_pct", "below", 10.0, "critical", 120),
                ])
            elif call_count[0] == 2:
                r.fetchone = MagicMock(return_value=(100_000, 35_000, 3_000, 3.0))
            elif call_count[0] == 3:
                # Cooldown check → recent event found
                r.fetchone = MagicMock(return_value=("event-existing",))
            return r

        db.execute = side_effect
        db.commit   = AsyncMock()
        result = await evaluate_store_alerts(db, "s1", "2026-03")
        assert result["alerts_triggered"] == 0
        assert result["cooldown_skipped"] == 1
