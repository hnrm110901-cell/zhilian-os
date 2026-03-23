"""
影子模式 + 灰度切换完整测试 — Phase P2.1

覆盖：
  1. ShadowModeEngine: 会话/记录/对比 (10 tests)
  2. ConsistencyChecker: 每日一致性报告 (8 tests)
  3. CutoverController: 状态机/推进/回退/灰度 (12 tests)
"""

import os

for _k, _v in {
    "APP_ENV": "test",
    "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
    "REDIS_URL": "redis://localhost:6379/0",
    "CELERY_BROKER_URL": "redis://localhost:6379/0",
    "CELERY_RESULT_BACKEND": "redis://localhost:6379/0",
    "SECRET_KEY": "test-secret-key",
    "JWT_SECRET": "test-jwt-secret",
}.items():
    os.environ.setdefault(_k, _v)

import pytest
from src.services.shadow_mode_engine import (
    ShadowModeEngine,
    ConsistencyChecker,
    CutoverController,
)


# ═══════════════════════════════════════════════════════════════════════════════
# ShadowModeEngine Tests (10)
# ═══════════════════════════════════════════════════════════════════════════════

class TestShadowModeEngine:

    def test_create_session(self):
        engine = ShadowModeEngine()
        session = engine.create_session("B001", "S001", "pinzhi")
        assert session["status"] == "active"
        assert session["store_id"] == "S001"

    def test_record_shadow_data(self):
        engine = ShadowModeEngine()
        session = engine.create_session("B001", "S001", "pinzhi")
        record = engine.record_shadow(
            session["id"], "order", "ORD-001",
            source_data={"total": 15800, "items": 3},
            source_amount_fen=15800,
            shadow_data={"total": 15800, "items": 3},
            shadow_amount_fen=15800,
        )
        assert record["source_id"] == "ORD-001"
        assert record["source_amount_fen"] == 15800

    def test_compare_consistent_record(self):
        engine = ShadowModeEngine()
        session = engine.create_session("B001", "S001", "pinzhi")
        record = engine.record_shadow(
            session["id"], "order", "ORD-001",
            source_data={"total": 15800},
            source_amount_fen=15800,
            shadow_data={"total": 15800},
            shadow_amount_fen=15800,
        )
        result = engine.compare_record(record)
        assert result.is_consistent is True
        assert result.diff_amount_fen == 0

    def test_compare_inconsistent_record(self):
        engine = ShadowModeEngine()
        session = engine.create_session("B001", "S001", "pinzhi")
        record = engine.record_shadow(
            session["id"], "order", "ORD-002",
            source_data={"total": 15800, "discount": 500},
            source_amount_fen=15800,
            shadow_data={"total": 15300, "discount": 500},
            shadow_amount_fen=15300,
        )
        result = engine.compare_record(record)
        assert result.is_consistent is False
        assert "total" in result.diff_fields
        assert result.diff_amount_fen == 500

    def test_session_stats(self):
        engine = ShadowModeEngine()
        session = engine.create_session("B001", "S001", "pinzhi")
        # 写入并对比3条记录
        for i in range(3):
            r = engine.record_shadow(
                session["id"], "order", f"ORD-{i}",
                source_data={"total": 100},
                source_amount_fen=100,
                shadow_data={"total": 100},
                shadow_amount_fen=100,
            )
            engine.compare_record(r)

        stats = engine.get_session_stats(session["id"])
        assert stats["consistent_records"] == 3
        assert stats["consistency_rate"] == 1.0

    def test_record_to_inactive_session(self):
        engine = ShadowModeEngine()
        session = engine.create_session("B001", "S001", "pinzhi")
        session["status"] = "paused"
        engine._sessions[session["id"]] = session
        result = engine.record_shadow(session["id"], "order", "X", {})
        assert "error" in result

    def test_record_nonexistent_session(self):
        engine = ShadowModeEngine()
        result = engine.record_shadow("fake-id", "order", "X", {})
        assert "error" in result

    def test_stats_nonexistent_session(self):
        engine = ShadowModeEngine()
        assert engine.get_session_stats("fake") is None

    def test_compare_with_diff_fields_only(self):
        """字段不同但金额相同"""
        engine = ShadowModeEngine()
        session = engine.create_session("B001", "S001", "pinzhi")
        record = engine.record_shadow(
            session["id"], "order", "ORD-X",
            source_data={"status": "paid"},
            source_amount_fen=100,
            shadow_data={"status": "completed"},
            shadow_amount_fen=100,
        )
        result = engine.compare_record(record)
        assert result.is_consistent is False
        assert "status" in result.diff_fields
        assert result.diff_amount_fen == 0

    def test_compare_with_amount_diff_only(self):
        """字段相同但金额不同"""
        engine = ShadowModeEngine()
        session = engine.create_session("B001", "S001", "pinzhi")
        record = engine.record_shadow(
            session["id"], "order", "ORD-Y",
            source_data={"status": "paid"},
            source_amount_fen=10000,
            shadow_data={"status": "paid"},
            shadow_amount_fen=9800,
        )
        result = engine.compare_record(record)
        assert result.is_consistent is False
        assert result.diff_amount_fen == 200


# ═══════════════════════════════════════════════════════════════════════════════
# ConsistencyChecker Tests (8)
# ═══════════════════════════════════════════════════════════════════════════════

class TestConsistencyChecker:

    def _make_records(self, total: int, inconsistent: int, record_type: str = "order") -> list:
        records = []
        for i in range(total):
            is_ok = i >= inconsistent
            records.append({
                "source_id": f"R-{i}",
                "record_type": record_type,
                "is_consistent": is_ok,
                "diff_fields": [] if is_ok else ["total"],
                "diff_amount_fen": 0 if is_ok else 500,
            })
        return records

    def test_perfect_consistency(self):
        checker = ConsistencyChecker()
        result = checker.check_daily("S1", "S001", self._make_records(100, 0))
        assert result.level == "perfect"
        assert result.consistency_rate == 1.0
        assert result.is_pass is True

    def test_acceptable_consistency(self):
        checker = ConsistencyChecker()
        # 1000条中1条不一致 = 99.9%
        result = checker.check_daily("S1", "S001", self._make_records(1000, 1))
        assert result.level == "acceptable"
        assert result.is_pass is True

    def test_warning_consistency(self):
        checker = ConsistencyChecker()
        # 100条中1条不一致 = 99%
        result = checker.check_daily("S1", "S001", self._make_records(100, 1))
        assert result.level == "warning"
        assert result.is_pass is False

    def test_critical_consistency(self):
        checker = ConsistencyChecker()
        # 100条中5条不一致 = 95%
        result = checker.check_daily("S1", "S001", self._make_records(100, 5))
        assert result.level == "critical"
        assert result.is_pass is False

    def test_empty_records(self):
        checker = ConsistencyChecker()
        result = checker.check_daily("S1", "S001", [])
        assert result.total_compared == 0

    def test_type_breakdown(self):
        checker = ConsistencyChecker()
        records = self._make_records(50, 0, "order") + self._make_records(30, 2, "inventory")
        result = checker.check_daily("S1", "S001", records)
        assert result.order_consistency_rate == 1.0
        assert result.inventory_consistency_rate is not None
        assert result.inventory_consistency_rate < 1.0

    def test_top_diffs(self):
        checker = ConsistencyChecker()
        records = self._make_records(50, 5)
        result = checker.check_daily("S1", "S001", records)
        assert len(result.top_diffs) == 5

    def test_recommendations(self):
        checker = ConsistencyChecker()
        records = self._make_records(100, 10)  # 90% → critical
        result = checker.check_daily("S1", "S001", records)
        assert len(result.recommendations) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# CutoverController Tests (12)
# ═══════════════════════════════════════════════════════════════════════════════

class TestCutoverController:

    def test_init_cutover(self):
        ctrl = CutoverController()
        status = ctrl.init_cutover("B001", "S001", "analytics")
        assert status.phase == "shadow"
        assert status.can_advance is False
        assert status.can_rollback is False

    def test_cannot_advance_without_health(self):
        ctrl = CutoverController()
        ctrl.init_cutover("B001", "S001", "analytics")
        with pytest.raises(ValueError, match="达标天数不足"):
            ctrl.advance("S001", "analytics")

    def test_advance_with_health_gate(self):
        ctrl = CutoverController()
        ctrl.init_cutover("B001", "S001", "analytics")
        # 模拟达标
        state = ctrl._states["S001:analytics"]
        state["shadow_pass_days"] = 10
        state["health_gate_passed"] = True
        status = ctrl.advance("S001", "analytics")
        assert status.phase == "canary"
        assert status.previous_phase == "shadow"

    def test_rollback_from_canary(self):
        ctrl = CutoverController()
        ctrl.init_cutover("B001", "S001", "analytics")
        state = ctrl._states["S001:analytics"]
        state["shadow_pass_days"] = 10
        state["health_gate_passed"] = True
        ctrl.advance("S001", "analytics")  # → canary

        status = ctrl.rollback("S001", "analytics", reason="发现问题")
        assert status.phase == "shadow"
        assert status.shadow_pass_days == 0  # 回退后重置

    def test_cannot_rollback_from_shadow(self):
        ctrl = CutoverController()
        ctrl.init_cutover("B001", "S001", "analytics")
        with pytest.raises(ValueError, match="最初阶段"):
            ctrl.rollback("S001", "analytics")

    def test_full_lifecycle(self):
        """完整生命周期：shadow → canary → primary → sole"""
        ctrl = CutoverController()
        ctrl.init_cutover("B001", "S001", "analytics")
        state = ctrl._states["S001:analytics"]

        # shadow → canary
        state["shadow_pass_days"] = 10
        state["health_gate_passed"] = True
        ctrl.advance("S001", "analytics")
        assert state["phase"] == "canary"

        # canary → primary
        state["shadow_pass_days"] = 15
        state["health_gate_passed"] = True
        state["canary_percentage"] = 60
        ctrl.advance("S001", "analytics")
        assert state["phase"] == "primary"

        # primary → sole
        state["shadow_pass_days"] = 31
        state["health_gate_passed"] = True
        ctrl.advance("S001", "analytics")
        assert state["phase"] == "sole"

    def test_cannot_advance_past_sole(self):
        ctrl = CutoverController()
        ctrl.init_cutover("B001", "S001", "analytics")
        state = ctrl._states["S001:analytics"]
        state["phase"] = "sole"
        with pytest.raises(ValueError, match="最终阶段"):
            ctrl.advance("S001", "analytics")

    def test_update_health_pass(self):
        ctrl = CutoverController()
        ctrl.init_cutover("B001", "S001", "analytics")
        for day in range(8):
            ctrl.update_health("S001", "analytics", 0.9995, True)
        status = ctrl.get_status("S001", "analytics")
        assert status.shadow_pass_days == 8
        assert status.health_gate_passed is True

    def test_update_health_fail_resets(self):
        ctrl = CutoverController()
        ctrl.init_cutover("B001", "S001", "analytics")
        for _ in range(5):
            ctrl.update_health("S001", "analytics", 0.9995, True)
        ctrl.update_health("S001", "analytics", 0.98, False)
        status = ctrl.get_status("S001", "analytics")
        assert status.shadow_pass_days == 0

    def test_set_canary_percentage(self):
        ctrl = CutoverController()
        ctrl.init_cutover("B001", "S001", "analytics")
        state = ctrl._states["S001:analytics"]
        state["phase"] = "canary"
        status = ctrl.set_canary_percentage("S001", "analytics", 30)
        assert status.canary_percentage == 30

    def test_canary_percentage_only_in_canary_phase(self):
        ctrl = CutoverController()
        ctrl.init_cutover("B001", "S001", "analytics")
        with pytest.raises(ValueError, match="canary"):
            ctrl.set_canary_percentage("S001", "analytics", 30)

    def test_store_overview(self):
        ctrl = CutoverController()
        ctrl.init_cutover("B001", "S001", "analytics")
        ctrl.init_cutover("B001", "S001", "management")
        overview = ctrl.get_store_overview("S001")
        assert len(overview) == 2
        modules = {s.module for s in overview}
        assert "analytics" in modules
        assert "management" in modules
