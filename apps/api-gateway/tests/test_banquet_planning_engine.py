"""
Tests for BanquetPlanningEngine
"""
import pytest
from datetime import date, time
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.banquet_planning_engine import (
    BanquetPlanningEngine,
    BanquetCircuitBreaker,
    BANQUET_CIRCUIT_THRESHOLD,
    BANQUET_SAFETY_FACTOR,
    _BANQUET_INGREDIENTS,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────

def banquet(
    rid="RES001",
    party_size=50,
    reservation_time="18:00",
    estimated_budget=500000,
    customer_name="王大明",
    customer_phone="13900000001",
    venue="宴会厅A",
) -> Dict[str, Any]:
    return {
        "reservation_id":   rid,
        "party_size":       party_size,
        "reservation_time": reservation_time,
        "estimated_budget": estimated_budget,
        "customer_name":    customer_name,
        "customer_phone":   customer_phone,
        "venue":            venue,
    }


ENGINE = BanquetPlanningEngine()


# ── check_circuit_breaker ─────────────────────────────────────────────────────

class TestCheckCircuitBreaker:

    def test_above_threshold_triggers(self):
        b  = banquet(party_size=BANQUET_CIRCUIT_THRESHOLD)
        cb = ENGINE.check_circuit_breaker(b)
        assert cb.triggered is True

    def test_below_threshold_not_triggered(self):
        b  = banquet(party_size=BANQUET_CIRCUIT_THRESHOLD - 1)
        cb = ENGINE.check_circuit_breaker(b)
        assert cb.triggered is False

    def test_exactly_threshold_triggers(self):
        b  = banquet(party_size=BANQUET_CIRCUIT_THRESHOLD)
        cb = ENGINE.check_circuit_breaker(b)
        assert cb.triggered is True

    def test_zero_party_size_not_triggered(self):
        b  = banquet(party_size=0)
        cb = ENGINE.check_circuit_breaker(b)
        assert cb.triggered is False

    def test_triggered_has_procurement_addon(self):
        b  = banquet(party_size=40)
        cb = ENGINE.check_circuit_breaker(b)
        assert cb.triggered is True
        assert len(cb.procurement_addon) == len(_BANQUET_INGREDIENTS)

    def test_triggered_has_staffing_addon(self):
        b  = banquet(party_size=40)
        cb = ENGINE.check_circuit_breaker(b)
        assert "roles" in cb.staffing_addon
        assert cb.staffing_addon["total_addon_staff"] > 0

    def test_triggered_has_beo(self):
        b  = banquet(party_size=30)
        cb = ENGINE.check_circuit_breaker(b, store_id="STORE001", plan_date=date(2026, 6, 15))
        assert cb.beo is not None
        assert "beo_id" in cb.beo

    def test_not_triggered_empty_addon(self):
        b  = banquet(party_size=5)
        cb = ENGINE.check_circuit_breaker(b)
        assert cb.triggered is False
        assert cb.procurement_addon == []
        assert cb.staffing_addon == {}
        assert cb.beo is None

    def test_reservation_id_preserved(self):
        b  = banquet(rid="RES_XYZ", party_size=50)
        cb = ENGINE.check_circuit_breaker(b)
        assert cb.reservation_id == "RES_XYZ"

    def test_party_size_preserved(self):
        b  = banquet(party_size=60)
        cb = ENGINE.check_circuit_breaker(b)
        assert cb.party_size == 60


# ── generate_procurement_addon ────────────────────────────────────────────────

class TestGenerateProcurementAddon:

    def test_returns_8_categories(self):
        addon = ENGINE.generate_procurement_addon(banquet(party_size=30))
        assert len(addon) == 8

    def test_zero_party_size_returns_empty(self):
        addon = ENGINE.generate_procurement_addon(banquet(party_size=0))
        assert addon == []

    def test_quantities_scale_with_party_size(self):
        addon_30 = ENGINE.generate_procurement_addon(banquet(party_size=30))
        addon_60 = ENGINE.generate_procurement_addon(banquet(party_size=60))

        # All quantities should double
        for a, b in zip(addon_30, addon_60):
            assert abs(b["recommended_quantity"] - a["recommended_quantity"] * 2) < 0.1, \
                f"{a['item_name']}: qty should double"

    def test_safety_factor_applied(self):
        """Quantities should include BANQUET_SAFETY_FACTOR."""
        party_size = 20
        # premium_meat: 250 g/head → 20 * 250 * 1.1 / 1000 = 5.5 kg
        addon = ENGINE.generate_procurement_addon(banquet(party_size=party_size))
        meat  = next(a for a in addon if a["category"] == "premium_meat")
        expected = round(party_size * 250 * BANQUET_SAFETY_FACTOR / 1000, 2)
        assert meat["recommended_quantity"] == pytest.approx(expected, abs=0.01)

    def test_beverages_in_liters(self):
        addon = ENGINE.generate_procurement_addon(banquet(party_size=20))
        bev   = next(a for a in addon if a["category"] == "beverages")
        assert bev["unit"] == "L"
        expected = round(20 * 500 * BANQUET_SAFETY_FACTOR / 1000, 2)
        assert bev["recommended_quantity"] == pytest.approx(expected, abs=0.01)

    def test_solids_in_kg(self):
        addon = ENGINE.generate_procurement_addon(banquet(party_size=20))
        meat  = next(a for a in addon if a["category"] == "premium_meat")
        assert meat["unit"] == "kg"

    def test_source_field_set(self):
        addon = ENGINE.generate_procurement_addon(banquet(party_size=30))
        for item in addon:
            assert item["source"] == "banquet_circuit_breaker"

    def test_menu_package_override(self):
        """Custom menu_package should override grams_per_head."""
        pkg   = {"premium_meat": {"grams_per_head": 400}}
        addon = ENGINE.generate_procurement_addon(banquet(party_size=20), menu_package=pkg)
        meat  = next(a for a in addon if a["category"] == "premium_meat")
        expected = round(20 * 400 * BANQUET_SAFETY_FACTOR / 1000, 2)
        assert meat["recommended_quantity"] == pytest.approx(expected, abs=0.01)

    def test_alert_levels_present(self):
        addon = ENGINE.generate_procurement_addon(banquet(party_size=30))
        levels = {a["alert_level"] for a in addon}
        assert "high" in levels
        assert "medium" in levels
        assert "low" in levels


# ── generate_staffing_addon ────────────────────────────────────────────────────

class TestGenerateStaffingAddon:

    def test_coordinator_always_1(self):
        addon = ENGINE.generate_staffing_addon(banquet(party_size=30))
        coord = next(r for r in addon["roles"] if r["role"] == "宴会协调员")
        assert coord["count"] == 1

    def test_waiter_scales_with_guests(self):
        # 30 guests → 30 // 10 = 3 waiters
        addon = ENGINE.generate_staffing_addon(banquet(party_size=30))
        waiter = next(r for r in addon["roles"] if r["role"] == "服务员")
        assert waiter["count"] == 3

    def test_senior_chef_at_30_or_more(self):
        addon = ENGINE.generate_staffing_addon(banquet(party_size=30))
        roles = {r["role"] for r in addon["roles"]}
        assert "主厨" in roles

    def test_no_senior_chef_below_threshold(self):
        addon = ENGINE.generate_staffing_addon(banquet(party_size=20))
        roles = {r["role"] for r in addon["roles"]}
        assert "主厨" not in roles

    def test_extra_cashier_at_80_plus(self):
        addon_small = ENGINE.generate_staffing_addon(banquet(party_size=50))
        addon_large = ENGINE.generate_staffing_addon(banquet(party_size=80))
        cash_small  = next(r for r in addon_small["roles"] if r["role"] == "收银")
        cash_large  = next(r for r in addon_large["roles"] if r["role"] == "收银")
        assert cash_large["count"] == cash_small["count"] + 1

    def test_total_staff_reasonable(self):
        addon = ENGINE.generate_staffing_addon(banquet(party_size=50))
        assert addon["total_addon_staff"] >= 5  # at minimum: 1 coord + 5 waiters + ...

    def test_shift_notes_present(self):
        addon = ENGINE.generate_staffing_addon(banquet(party_size=30))
        assert "shift_notes" in addon
        assert len(addon["shift_notes"]) > 0

    def test_shift_times_from_reservation_time(self):
        """shift_start should be 2h before event."""
        addon = ENGINE.generate_staffing_addon(banquet(party_size=30, reservation_time="18:00"))
        # shift_start should be "16:00" (18:00 - 2h)
        assert addon["shift_start"] == "16:00"
        # shift_end should be "19:00" (18:00 + 1h)... unless banquet is >1h
        assert addon["event_start"] == "18:00"

    def test_source_field(self):
        addon = ENGINE.generate_staffing_addon(banquet(party_size=30))
        assert addon["source"] == "banquet_circuit_breaker"


# ── generate_beo ───────────────────────────────────────────────────────────────

class TestGenerateBeo:

    def test_beo_has_required_sections(self):
        beo = ENGINE.generate_beo(banquet(party_size=40), store_id="S001",
                                  plan_date=date(2026, 7, 1))
        for section in ("beo_id", "version", "generated_at", "event",
                         "menu", "procurement", "staffing", "finance"):
            assert section in beo, f"Missing section: {section}"

    def test_beo_id_format(self):
        beo = ENGINE.generate_beo(banquet(rid="RES_ABC", party_size=40),
                                  store_id="S001", plan_date=date(2026, 7, 1))
        assert "S001" in beo["beo_id"]
        assert "RES_ABC" in beo["beo_id"]

    def test_event_section_populated(self):
        b   = banquet(party_size=40, customer_name="李大明")
        beo = ENGINE.generate_beo(b, store_id="S001", plan_date=date(2026, 7, 1))
        assert beo["event"]["customer_name"]  == "李大明"
        assert beo["event"]["party_size"]     == 40

    def test_version_default_is_1(self):
        beo = ENGINE.generate_beo(banquet(party_size=40), store_id="S001")
        assert beo["version"] == 1

    def test_custom_version(self):
        beo = ENGINE.generate_beo(banquet(party_size=40), store_id="S001", version=3)
        assert beo["version"] == 3

    def test_finance_section_has_budget(self):
        b   = banquet(party_size=40, estimated_budget=500000)
        beo = ENGINE.generate_beo(b, store_id="S001")
        assert "estimated_budget" in beo["finance"] or "budget" in str(beo["finance"])

    def test_procurement_section_not_empty(self):
        beo = ENGINE.generate_beo(banquet(party_size=40), store_id="S001")
        assert beo["procurement"]["total_items"] == len(_BANQUET_INGREDIENTS)

    def test_staffing_section_has_roles(self):
        beo = ENGINE.generate_beo(banquet(party_size=40), store_id="S001")
        assert "roles" in beo["staffing"]
        assert len(beo["staffing"]["roles"]) > 0

    def test_change_log_initialized(self):
        beo = ENGINE.generate_beo(banquet(party_size=40), store_id="S001")
        assert "change_log" in beo
        assert isinstance(beo["change_log"], list)


# ── check_resource_conflicts ───────────────────────────────────────────────────

class TestCheckResourceConflicts:

    def _banquet_list(self, party_sizes: List[int], same_date=True) -> List[Dict]:
        # No reservation_time: skip time-overlap detection (capacity only)
        return [
            {
                "reservation_id": f"R{i}",
                "party_size": ps,
                "reservation_date": "2026-06-15" if same_date else f"2026-06-{15 + i}",
            }
            for i, ps in enumerate(party_sizes)
        ]

    def test_no_conflict_within_capacity(self):
        bl = self._banquet_list([80, 60])  # total 140 < 200
        result = ENGINE.check_resource_conflicts(bl, max_capacity=200)
        assert len(result["conflicts"]) == 0

    def test_capacity_conflict_detected(self):
        bl = self._banquet_list([120, 100])  # total 220 > 200
        result = ENGINE.check_resource_conflicts(bl, max_capacity=200)
        assert len(result["conflicts"]) >= 1
        conflict_types = [c.get("type") for c in result["conflicts"]]
        assert any("capacity" in str(t) for t in conflict_types)

    def test_single_banquet_no_conflict(self):
        bl = [banquet(party_size=50)]
        result = ENGINE.check_resource_conflicts(bl, max_capacity=200)
        assert len(result["conflicts"]) == 0

    def test_empty_list_no_conflict(self):
        result = ENGINE.check_resource_conflicts([], max_capacity=200)
        assert result["conflicts"] == []
        assert result["has_conflict"] is False

    def test_different_dates_no_capacity_conflict(self):
        bl = self._banquet_list([80, 60], same_date=False)  # total 140 < 200
        result = ENGINE.check_resource_conflicts(bl, max_capacity=200)
        assert len(result["conflicts"]) == 0

    def test_exact_capacity_no_conflict(self):
        bl = self._banquet_list([100, 100])  # total 200 == 200
        result = ENGINE.check_resource_conflicts(bl, max_capacity=200)
        assert len(result["conflicts"]) == 0


# ── Edge cases ────────────────────────────────────────────────────────────────

class TestEdgeCases:

    def test_missing_party_size_treated_as_zero(self):
        """Banquets with missing party_size should not trigger circuit breaker."""
        b  = {"reservation_id": "R1"}
        cb = ENGINE.check_circuit_breaker(b)
        assert cb.triggered is False

    def test_string_party_size_coerced(self):
        """party_size as string should be coerced to int."""
        b  = banquet(party_size=0)
        b["party_size"] = str(BANQUET_CIRCUIT_THRESHOLD)
        cb = ENGINE.check_circuit_breaker(b)
        assert cb.triggered is True

    def test_procurement_party_size_basis_matches(self):
        party_size = 35
        addon = ENGINE.generate_procurement_addon(banquet(party_size=party_size))
        for item in addon:
            assert item["party_size_basis"] == party_size

    def test_beo_generated_by_default_is_system(self):
        beo = ENGINE.generate_beo(banquet(party_size=40))
        assert beo["generated_by"] == "system"

    def test_beo_operator_override(self):
        beo = ENGINE.generate_beo(banquet(party_size=40), operator="mgr_01")
        assert beo["generated_by"] == "mgr_01"
