"""
AgentOKRService 单元测试 — P1 统一量化日志
纯函数层测试（无DB依赖）
"""
import os
for _k, _v in {
    "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
    "REDIS_URL": "redis://localhost:6379/0",
    "CELERY_BROKER_URL": "redis://localhost:6379/0",
    "CELERY_RESULT_BACKEND": "redis://localhost:6379/0",
    "SECRET_KEY": "test-secret",
    "JWT_SECRET": "test-jwt",
}.items():
    os.environ.setdefault(_k, _v)

import pytest
from src.services.agent_okr_service import (
    compute_adoption_rate,
    compute_prediction_error,
    check_okr_adoption,
    check_okr_accuracy,
    check_okr_latency,
    build_okr_status_label,
    OKR_TARGETS,
)


class TestComputeAdoptionRate:
    def test_normal(self):
        assert compute_adoption_rate(7, 3) == pytest.approx(0.7)

    def test_all_adopted(self):
        assert compute_adoption_rate(10, 0) == pytest.approx(1.0)

    def test_all_rejected(self):
        assert compute_adoption_rate(0, 10) == pytest.approx(0.0)

    def test_zero_total(self):
        assert compute_adoption_rate(0, 0) is None

    def test_rounds_to_4_decimals(self):
        rate = compute_adoption_rate(1, 3)
        assert rate == pytest.approx(0.25)


class TestComputePredictionError:
    def test_exact_match(self):
        assert compute_prediction_error(100, 100) == pytest.approx(0.0)

    def test_over_prediction(self):
        # |110-100|/100 * 100 = 10%
        assert compute_prediction_error(110, 100) == pytest.approx(10.0)

    def test_under_prediction(self):
        assert compute_prediction_error(90, 100) == pytest.approx(10.0)

    def test_zero_actual(self):
        assert compute_prediction_error(100, 0) is None

    def test_large_error(self):
        assert compute_prediction_error(200, 100) == pytest.approx(100.0)


class TestCheckOKRAdoption:
    def test_business_intel_meets_70pct(self):
        assert check_okr_adoption("business_intel", 0.70) is True

    def test_business_intel_below_70pct(self):
        assert check_okr_adoption("business_intel", 0.69) is False

    def test_ops_flow_meets_90pct(self):
        assert check_okr_adoption("ops_flow", 0.90) is True

    def test_ops_flow_below_90pct(self):
        assert check_okr_adoption("ops_flow", 0.85) is False

    def test_banquet_meets_40pct(self):
        assert check_okr_adoption("banquet", 0.40) is True

    def test_none_adoption_rate(self):
        assert check_okr_adoption("business_intel", None) is None

    def test_unknown_agent(self):
        assert check_okr_adoption("unknown_agent", 0.8) is None


class TestCheckOKRAccuracy:
    def test_business_intel_within_5pct(self):
        assert check_okr_accuracy("business_intel", 4.9) is True

    def test_business_intel_exceeds_5pct(self):
        assert check_okr_accuracy("business_intel", 5.1) is False

    def test_ops_flow_within_10pct(self):
        assert check_okr_accuracy("ops_flow", 9.0) is True

    def test_zero_error_always_met(self):
        assert check_okr_accuracy("business_intel", 0.0) is True

    def test_none_error_returns_none(self):
        assert check_okr_accuracy("business_intel", None) is None


class TestCheckOKRLatency:
    def test_ops_flow_within_300s(self):
        assert check_okr_latency("ops_flow", 250.0) is True

    def test_ops_flow_exceeds_300s(self):
        assert check_okr_latency("ops_flow", 350.0) is False

    def test_banquet_within_7200s(self):
        assert check_okr_latency("banquet", 3600.0) is True

    def test_no_target_returns_none(self):
        # business_intel 没有时效要求
        assert check_okr_latency("business_intel", 99999.0) is None

    def test_none_latency_returns_none(self):
        assert check_okr_latency("ops_flow", None) is None


class TestBuildOKRStatusLabel:
    def test_met(self):
        assert "✅" in build_okr_status_label(True)

    def test_not_met(self):
        assert "❌" in build_okr_status_label(False)

    def test_insufficient_data(self):
        assert "⏳" in build_okr_status_label(None)


class TestOKRTargetsConfig:
    def test_all_agents_have_adoption_rate(self):
        for agent in ["business_intel", "ops_flow", "people", "marketing", "banquet"]:
            assert "adoption_rate" in OKR_TARGETS[agent]

    def test_ops_flow_has_latency_target(self):
        assert OKR_TARGETS["ops_flow"]["latency_seconds"] == 300

    def test_banquet_has_latency_target(self):
        assert OKR_TARGETS["banquet"]["latency_seconds"] == 7200

    def test_business_intel_no_latency(self):
        assert OKR_TARGETS["business_intel"]["latency_seconds"] is None
