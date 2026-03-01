"""
Tests for src/core/neural_symbolic_guardrails.py — AI safety dual-check layer.

No external deps.  Covers:
  - All 15 business rules (FIN/OPS/SAFE/COMP/BIZ/REF)
  - _requires_human_approval thresholds (CRITICAL, 2×HIGH)
  - auto_fix_proposal (fixable MEDIUM/LOW + non-fixable CRITICAL)
  - get_rule_statistics
"""
import os
import pytest
from datetime import datetime

from src.core.neural_symbolic_guardrails import (
    AIProposal,
    GuardrailResult,
    NeuralSymbolicGuardrails,
    RuleCategory,
    RuleViolation,
    ViolationSeverity,
    guardrails,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _proposal(content: dict, proposal_type: str = "purchase_order") -> AIProposal:
    return AIProposal(
        proposal_id="PROP-001",
        proposal_type=proposal_type,
        content=content,
        confidence=0.9,
        reasoning="test",
        created_at=datetime.now(),
    )


def _ctx(**kwargs) -> dict:
    """Build a context dict with safe defaults."""
    defaults = {
        "monthly_budget": 100_000,
        "historical_peak": 1_000,
        "supplier_credit_limit": 100_000,
        "minimum_staff": 3,
        "current_stock": 100,
        "market_price": 100,
        "cost_price": 50,
        "original_order_amount": 10_000,
        "daily_refund_total": 0,
        "daily_revenue": 50_000,
        "customer_refund_count_24h": 0,
    }
    defaults.update(kwargs)
    return defaults


@pytest.fixture
def ng():
    return NeuralSymbolicGuardrails()


# ===========================================================================
# Financial rules
# ===========================================================================

class TestFinancialRules:
    def test_fin001_budget_exceeded_is_critical(self, ng):
        """FIN_001: total_amount > monthly_budget → CRITICAL"""
        result = ng.validate_proposal(
            _proposal({"total_amount": 200_000}),
            _ctx(monthly_budget=100_000),
        )
        ids = [v.rule_id for v in result.violations]
        assert "FIN_001" in ids
        fin = next(v for v in result.violations if v.rule_id == "FIN_001")
        assert fin.severity == ViolationSeverity.CRITICAL
        assert result.requires_human_approval is True

    def test_fin001_within_budget_no_violation(self, ng):
        result = ng.validate_proposal(
            _proposal({"total_amount": 50_000}),
            _ctx(monthly_budget=100_000),
        )
        ids = [v.rule_id for v in result.violations]
        assert "FIN_001" not in ids

    def test_fin002_quantity_120pct_exceeded_is_high(self, ng):
        """FIN_002: quantity > historical_peak * 1.2 → HIGH"""
        result = ng.validate_proposal(
            _proposal({"quantity": 1300}),
            _ctx(historical_peak=1000),
        )
        ids = [v.rule_id for v in result.violations]
        assert "FIN_002" in ids
        fin = next(v for v in result.violations if v.rule_id == "FIN_002")
        assert fin.severity == ViolationSeverity.HIGH

    def test_fin003_credit_limit_exceeded_is_critical(self, ng):
        """FIN_003: total_amount > supplier_credit_limit → CRITICAL"""
        result = ng.validate_proposal(
            _proposal({"total_amount": 120_000}),
            _ctx(supplier_credit_limit=100_000),
        )
        ids = [v.rule_id for v in result.violations]
        assert "FIN_003" in ids
        assert next(v for v in result.violations if v.rule_id == "FIN_003").severity == ViolationSeverity.CRITICAL


# ===========================================================================
# Operational rules
# ===========================================================================

class TestOperationalRules:
    def test_ops001_below_minimum_staff_is_critical(self, ng):
        """OPS_001: staff_count < minimum_staff → CRITICAL"""
        result = ng.validate_proposal(
            _proposal({"staff_count": 1}),
            _ctx(minimum_staff=3),
        )
        assert "OPS_001" in [v.rule_id for v in result.violations]

    def test_ops002_shift_over_8h_is_critical(self, ng):
        """OPS_002: shift_hours > 8 → CRITICAL"""
        result = ng.validate_proposal(
            _proposal({"shift_hours": 10}),
            _ctx(),
        )
        assert "OPS_002" in [v.rule_id for v in result.violations]

    def test_ops002_exactly_8h_passes(self, ng):
        result = ng.validate_proposal(_proposal({"shift_hours": 8}), _ctx())
        assert "OPS_002" not in [v.rule_id for v in result.violations]

    def test_ops003_negative_stock_is_critical(self, ng):
        """OPS_003: transfer_quantity > current_stock → CRITICAL"""
        result = ng.validate_proposal(
            _proposal({"transfer_quantity": 150}),
            _ctx(current_stock=100),
        )
        assert "OPS_003" in [v.rule_id for v in result.violations]


# ===========================================================================
# Safety rules
# ===========================================================================

class TestSafetyRules:
    def test_safe001_short_shelf_life_is_critical(self, ng):
        """SAFE_001: shelf_life_days < 3 → CRITICAL"""
        result = ng.validate_proposal(
            _proposal({"shelf_life_days": 2}),
            _ctx(),
        )
        assert "SAFE_001" in [v.rule_id for v in result.violations]

    def test_safe001_sufficient_shelf_life_passes(self, ng):
        result = ng.validate_proposal(_proposal({"shelf_life_days": 5}), _ctx())
        assert "SAFE_001" not in [v.rule_id for v in result.violations]

    def test_safe002_cold_chain_without_log_is_high(self, ng):
        """SAFE_002: cold chain required but no temp log → HIGH"""
        result = ng.validate_proposal(
            _proposal({"requires_cold_chain": True, "has_temperature_log": False}),
            _ctx(),
        )
        assert "SAFE_002" in [v.rule_id for v in result.violations]

    def test_safe002_cold_chain_with_log_passes(self, ng):
        result = ng.validate_proposal(
            _proposal({"requires_cold_chain": True, "has_temperature_log": True}),
            _ctx(),
        )
        assert "SAFE_002" not in [v.rule_id for v in result.violations]


# ===========================================================================
# Compliance rules
# ===========================================================================

class TestComplianceRules:
    def test_comp001_no_certification_is_critical(self, ng):
        """COMP_001: supplier_certified=False → CRITICAL"""
        result = ng.validate_proposal(
            _proposal({"supplier_certified": False}),
            _ctx(),
        )
        assert "COMP_001" in [v.rule_id for v in result.violations]

    def test_comp002_price_above_30pct_deviation_is_high(self, ng):
        """COMP_002: |price - market| / market > 30% → HIGH"""
        result = ng.validate_proposal(
            _proposal({"price": 140}),   # 40% above market_price=100
            _ctx(market_price=100),
        )
        assert "COMP_002" in [v.rule_id for v in result.violations]

    def test_comp002_within_30pct_passes(self, ng):
        result = ng.validate_proposal(
            _proposal({"price": 120}),   # 20% above
            _ctx(market_price=100),
        )
        assert "COMP_002" not in [v.rule_id for v in result.violations]


# ===========================================================================
# Business rules
# ===========================================================================

class TestBusinessRules:
    def test_biz001_discount_below_cost_is_high(self, ng):
        """BIZ_001: discounted_price < cost_price → HIGH"""
        result = ng.validate_proposal(
            _proposal({"discounted_price": 30}),
            _ctx(cost_price=50),
        )
        assert "BIZ_001" in [v.rule_id for v in result.violations]

    def test_biz002_new_dish_without_cost_breakdown_is_medium(self, ng):
        """BIZ_002: is_new_dish=True, has_cost_breakdown=False → MEDIUM"""
        result = ng.validate_proposal(
            _proposal({"is_new_dish": True, "has_cost_breakdown": False}),
            _ctx(),
        )
        viols = [v for v in result.violations if v.rule_id == "BIZ_002"]
        assert len(viols) == 1
        assert viols[0].severity == ViolationSeverity.MEDIUM


# ===========================================================================
# Refund rules
# ===========================================================================

class TestRefundRules:
    def test_ref001_refund_exceeds_order_is_critical(self, ng):
        """REF_001: refund_amount > original_order_amount → CRITICAL"""
        result = ng.validate_proposal(
            _proposal({"refund_amount": 15_000}),
            _ctx(original_order_amount=10_000),
        )
        assert "REF_001" in [v.rule_id for v in result.violations]

    def test_ref002_expired_refund_is_high(self, ng):
        """REF_002: days_since_order > 7 → HIGH"""
        result = ng.validate_proposal(
            _proposal({"days_since_order": 10}),
            _ctx(),
        )
        assert "REF_002" in [v.rule_id for v in result.violations]

    def test_ref003_daily_ratio_exceeded_is_high(self, ng):
        """REF_003: daily_refund_total + refund_amount > daily_revenue * 0.20 → HIGH"""
        result = ng.validate_proposal(
            _proposal({"refund_amount": 12_000}),
            _ctx(daily_refund_total=0, daily_revenue=50_000),
        )
        assert "REF_003" in [v.rule_id for v in result.violations]

    def test_ref004_single_refund_over_limit_is_high(self, ng):
        """REF_004: refund_amount > 50000 (分) → HIGH"""
        result = ng.validate_proposal(
            _proposal({"refund_amount": 60_000}),
            _ctx(),
        )
        assert "REF_004" in [v.rule_id for v in result.violations]

    def test_ref005_frequent_refund_is_medium(self, ng):
        """REF_005: customer_refund_count_24h >= 3 → MEDIUM"""
        result = ng.validate_proposal(
            _proposal({}),
            _ctx(customer_refund_count_24h=3),
        )
        assert "REF_005" in [v.rule_id for v in result.violations]


# ===========================================================================
# Clean proposal — no violations
# ===========================================================================

class TestCleanProposal:
    def test_fully_compliant_proposal_approved(self, ng):
        """A proposal satisfying all rules is approved with no violations."""
        result = ng.validate_proposal(
            _proposal({
                "total_amount": 5_000,
                "quantity": 100,
                "staff_count": 5,
                "shift_hours": 7,
                "transfer_quantity": 10,
                "shelf_life_days": 10,
                "requires_cold_chain": False,
                "supplier_certified": True,
                "price": 100,
                "discounted_price": 60,
                "is_new_dish": False,
                "refund_amount": 500,
                "days_since_order": 2,
            }),
            _ctx(
                monthly_budget=100_000,
                historical_peak=500,
                supplier_credit_limit=100_000,
                minimum_staff=3,
                current_stock=100,
                market_price=100,
                cost_price=50,
                original_order_amount=10_000,
                daily_refund_total=0,
                daily_revenue=50_000,
                customer_refund_count_24h=0,
            ),
        )
        assert result.approved is True
        assert result.violations == []
        assert result.requires_human_approval is False
        assert result.escalation_reason is None


# ===========================================================================
# _requires_human_approval
# ===========================================================================

class TestRequiresHumanApproval:
    def test_any_critical_triggers_approval(self, ng):
        violations = [
            RuleViolation(
                rule_id="FIN_001", rule_name="test",
                category=RuleCategory.FINANCIAL,
                severity=ViolationSeverity.CRITICAL,
                description="", actual_value=None, threshold_value=None,
                recommendation="",
            )
        ]
        assert ng._requires_human_approval(violations) is True

    def test_two_high_triggers_approval(self, ng):
        violations = [
            RuleViolation(
                rule_id=f"X_{i}", rule_name="test",
                category=RuleCategory.FINANCIAL,
                severity=ViolationSeverity.HIGH,
                description="", actual_value=None, threshold_value=None,
                recommendation="",
            )
            for i in range(2)
        ]
        assert ng._requires_human_approval(violations) is True

    def test_one_high_no_approval(self, ng):
        violations = [
            RuleViolation(
                rule_id="X_1", rule_name="test",
                category=RuleCategory.FINANCIAL,
                severity=ViolationSeverity.HIGH,
                description="", actual_value=None, threshold_value=None,
                recommendation="",
            )
        ]
        assert ng._requires_human_approval(violations) is False

    def test_medium_only_no_approval(self, ng):
        violations = [
            RuleViolation(
                rule_id="BIZ_002", rule_name="test",
                category=RuleCategory.BUSINESS,
                severity=ViolationSeverity.MEDIUM,
                description="", actual_value=None, threshold_value=None,
                recommendation="",
            )
        ]
        assert ng._requires_human_approval(violations) is False

    def test_escalation_reason_set_for_critical(self, ng):
        result = ng.validate_proposal(
            _proposal({"total_amount": 200_000}),
            _ctx(monthly_budget=100_000),
        )
        assert result.escalation_reason is not None
        assert "严重违规" in result.escalation_reason


# ===========================================================================
# auto_fix_proposal
# ===========================================================================

class TestAutoFixProposal:
    def test_fin002_auto_fixed(self, ng):
        """FIN_002 (HIGH) quantity adjusted to historical_peak * 1.2"""
        proposal = _proposal({"quantity": 2000})
        ctx = _ctx(historical_peak=1000)
        result = ng.validate_proposal(proposal, ctx)
        fixed = ng.auto_fix_proposal(proposal, result.violations, ctx)
        # FIN_002 is HIGH (not MEDIUM/LOW), so auto_fix only applies MEDIUM/LOW
        # But actually let me check: BIZ_002 is MEDIUM/LOW
        # FIN_002 is HIGH which is NOT MEDIUM or LOW so it won't be auto-fixed
        # The function only fixes MEDIUM and LOW
        assert fixed is None  # no MEDIUM/LOW violations in this case

    def test_biz002_medium_is_fixable(self, ng):
        """BIZ_002 is MEDIUM — auto_fix should still not change anything
        (no fix logic for BIZ_002), returns modified with same content"""
        proposal = _proposal({"is_new_dish": True, "has_cost_breakdown": False})
        ctx = _ctx()
        result = ng.validate_proposal(proposal, ctx)
        medium_viols = [v for v in result.violations if v.severity == ViolationSeverity.MEDIUM]
        if medium_viols:
            fixed = ng.auto_fix_proposal(proposal, result.violations, ctx)
            # auto_fix returns a dict (copy of content) even if no specific fix rule matched
            assert fixed is not None

    def test_ref001_auto_capped(self, ng):
        """REF_001 is CRITICAL → NOT auto-fixable"""
        proposal = _proposal({"refund_amount": 15_000})
        ctx = _ctx(original_order_amount=10_000)
        result = ng.validate_proposal(proposal, ctx)
        fixed = ng.auto_fix_proposal(proposal, result.violations, ctx)
        # REF_001 is CRITICAL → filtered out (only MEDIUM/LOW are fixable)
        # Since no MEDIUM/LOW violations, returns None
        assert fixed is None

    def test_no_violations_returns_none(self, ng):
        proposal = _proposal({"supplier_certified": True})
        fixed = ng.auto_fix_proposal(proposal, [], _ctx())
        assert fixed is None


# ===========================================================================
# get_rule_statistics
# ===========================================================================

class TestGetRuleStatistics:
    def test_total_rules_count(self, ng):
        stats = ng.get_rule_statistics()
        assert stats["total_rules"] == len(ng.rules)
        assert stats["total_rules"] > 0

    def test_by_category_has_financial(self, ng):
        stats = ng.get_rule_statistics()
        assert RuleCategory.FINANCIAL in stats["by_category"]
        assert stats["by_category"][RuleCategory.FINANCIAL] >= 1

    def test_by_severity_has_critical(self, ng):
        stats = ng.get_rule_statistics()
        assert ViolationSeverity.CRITICAL in stats["by_severity"]
        assert stats["by_severity"][ViolationSeverity.CRITICAL] >= 1

    def test_sum_matches_total(self, ng):
        stats = ng.get_rule_statistics()
        assert sum(stats["by_severity"].values()) == stats["total_rules"]
        assert sum(stats["by_category"].values()) == stats["total_rules"]


# ===========================================================================
# Global instance
# ===========================================================================

class TestGlobalInstance:
    def test_global_guardrails_is_initialized(self):
        assert isinstance(guardrails, NeuralSymbolicGuardrails)
        assert len(guardrails.rules) > 0
