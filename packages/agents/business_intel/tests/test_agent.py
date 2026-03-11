"""
BusinessIntelAgent 单元测试 — Phase 12
32个纯函数测试 + 19个Agent集成测试 = 51个
"""
from __future__ import annotations

import sys
import types
from decimal import Decimal
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch


# ─────────────────────────────────────────────
# sys.modules 注入（在 import agent 之前）
# ─────────────────────────────────────────────

def _make_model_class(name: str):
    class _Col:
        def __eq__(self, other): return MagicMock()
        def __ge__(self, other): return MagicMock()
        def __le__(self, other): return MagicMock()
        def __ne__(self, other): return MagicMock()
        def in_(self, other):    return MagicMock()

    _col = _Col()

    class _ModelStub:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                object.__setattr__(self, k, v)

    class _Meta(type):
        def __getattr__(cls, item): return _col

    return _Meta(name, (_ModelStub,), {})


def _chainable_mock(*args, **kwargs):
    m = MagicMock()
    m.where = _chainable_mock
    m.order_by = _chainable_mock
    m.limit = _chainable_mock
    return m


# 构建 src 树桩
_src = types.ModuleType("src")
_models = types.ModuleType("src.models")
_bi = types.ModuleType("src.models.business_intel")

BizMetricSnapshotStub  = _make_model_class("BizMetricSnapshot")
RevenueAlertStub       = _make_model_class("RevenueAlert")
KpiScorecardStub       = _make_model_class("KpiScorecard")
OrderForecastStub      = _make_model_class("OrderForecast")
BizDecisionStub        = _make_model_class("BizDecision")
ScenarioRecordStub     = _make_model_class("ScenarioRecord")
BizIntelLogStub        = _make_model_class("BizIntelLog")

for stub_name, stub in [
    ("BizMetricSnapshot", BizMetricSnapshotStub),
    ("RevenueAlert", RevenueAlertStub),
    ("KpiScorecard", KpiScorecardStub),
    ("OrderForecast", OrderForecastStub),
    ("BizDecision", BizDecisionStub),
    ("ScenarioRecord", ScenarioRecordStub),
    ("BizIntelLog", BizIntelLogStub),
]:
    setattr(_bi, stub_name, stub)

for enum_name in [
    "AnomalyLevelEnum", "KpiStatusEnum", "DecisionPriorityEnum",
    "ScenarioTypeEnum", "BizIntelAgentTypeEnum", "DecisionStatusEnum",
]:
    setattr(_bi, enum_name, MagicMock())

_src.models = _models
_models.business_intel = _bi
sys.modules.setdefault("src", _src)
sys.modules.setdefault("src.models", _models)
sys.modules.setdefault("src.models.business_intel", _bi)
sys.modules.setdefault("src.core", types.ModuleType("src.core"))
sys.modules.setdefault("src.core.llm", types.ModuleType("src.core.llm"))

import importlib
_agent_module = importlib.import_module("packages.agents.business_intel.src.agent")
_agent_module.select = _chainable_mock
_agent_module.and_ = lambda *a, **kw: MagicMock()
_agent_module.desc = lambda x: MagicMock()
_agent_module.func = MagicMock()
_agent_module._LLM_ENABLED = False   # 测试环境关闭LLM调用


# ─────────────────────────────────────────────
# 从模块拿纯函数 & Agent类
# ─────────────────────────────────────────────

compute_deviation_pct        = _agent_module.compute_deviation_pct
classify_anomaly_level       = _agent_module.classify_anomaly_level
estimate_revenue_impact_yuan = _agent_module.estimate_revenue_impact_yuan
compute_kpi_achievement      = _agent_module.compute_kpi_achievement
compute_health_score         = _agent_module.compute_health_score
classify_kpi_status          = _agent_module.classify_kpi_status
compute_trend_slope          = _agent_module.compute_trend_slope
predict_next_period          = _agent_module.predict_next_period
compute_forecast_confidence  = _agent_module.compute_forecast_confidence
score_recommendation         = _agent_module.score_recommendation
classify_scenario            = _agent_module.classify_scenario

RevenueAnomalyAgent  = _agent_module.RevenueAnomalyAgent
KpiScorecardAgent    = _agent_module.KpiScorecardAgent
OrderForecastAgent   = _agent_module.OrderForecastAgent
BizInsightAgent      = _agent_module.BizInsightAgent
ScenarioMatchAgent   = _agent_module.ScenarioMatchAgent


# ─────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────

def make_db(scalar=None, scalars=None):
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(
        scalar_one_or_none=MagicMock(return_value=scalar),
        scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=scalars or []))),
        scalar=MagicMock(return_value=0),
    ))
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


def make_snapshot(**kwargs):
    defaults = dict(
        order_count=100, revenue_yuan=Decimal("50000"),
        food_cost_ratio=0.38, labor_cost_ratio=0.28,
        revenue_deviation_pct=2.0, complaint_count=0,
        trend_slope=None,
    )
    defaults.update(kwargs)
    return BizMetricSnapshotStub(**defaults)


import pytest


# ─────────────────────────────────────────────
# 纯函数测试
# ─────────────────────────────────────────────

class TestComputeDeviationPct:
    def test_above_expected(self):
        assert compute_deviation_pct(110, 100) == 10.0

    def test_below_expected(self):
        assert compute_deviation_pct(85, 100) == -15.0

    def test_equal(self):
        assert compute_deviation_pct(100, 100) == 0.0

    def test_zero_expected(self):
        assert compute_deviation_pct(100, 0) == 0.0

    def test_large_deviation(self):
        assert compute_deviation_pct(150, 100) == 50.0


class TestClassifyAnomalyLevel:
    def test_normal(self):
        assert classify_anomaly_level(3) == "normal"

    def test_warning(self):
        assert classify_anomaly_level(-10) == "warning"

    def test_critical(self):
        assert classify_anomaly_level(-20) == "critical"

    def test_severe(self):
        assert classify_anomaly_level(-35) == "severe"

    def test_positive_severe(self):
        assert classify_anomaly_level(32) == "severe"


class TestEstimateRevenueImpactYuan:
    def test_negative_impact(self):
        impact = estimate_revenue_impact_yuan(-20, 100000)
        assert impact == -20000.0

    def test_positive_impact(self):
        impact = estimate_revenue_impact_yuan(10, 50000)
        assert impact == 5000.0

    def test_zero_deviation(self):
        assert estimate_revenue_impact_yuan(0, 100000) == 0.0


class TestComputeKpiAchievement:
    def test_on_target(self):
        assert compute_kpi_achievement(100, 100) == 1.0

    def test_over_target(self):
        assert compute_kpi_achievement(110, 100) == 1.1

    def test_under_target(self):
        assert compute_kpi_achievement(80, 100) == 0.8

    def test_zero_target(self):
        assert compute_kpi_achievement(50, 0) == 1.0


class TestComputeHealthScore:
    def test_all_on_track(self):
        score = compute_health_score([1.0, 1.0, 1.0], [0.33, 0.33, 0.34])
        assert score == 80.0

    def test_overachieve(self):
        score = compute_health_score([1.2], [1.0])
        assert score > 80.0

    def test_underperform(self):
        score = compute_health_score([0.5], [1.0])
        assert score < 80.0

    def test_empty(self):
        assert compute_health_score([], []) == 50.0


class TestClassifyKpiStatus:
    def test_excellent(self):
        assert classify_kpi_status(1.15) == "excellent"

    def test_on_track(self):
        assert classify_kpi_status(1.05) == "on_track"

    def test_at_risk(self):
        assert classify_kpi_status(0.90) == "at_risk"

    def test_off_track(self):
        assert classify_kpi_status(0.80) == "off_track"


class TestComputeTrendSlope:
    def test_increasing(self):
        slope = compute_trend_slope([100, 110, 120, 130])
        assert slope > 0

    def test_decreasing(self):
        slope = compute_trend_slope([130, 120, 110, 100])
        assert slope < 0

    def test_flat(self):
        slope = compute_trend_slope([100, 100, 100, 100])
        assert slope == 0.0

    def test_single_point(self):
        assert compute_trend_slope([100]) == 0.0


class TestPredictNextPeriod:
    def test_growing(self):
        result = predict_next_period(100, 5, 7)
        assert result == 135.0

    def test_no_growth(self):
        assert predict_next_period(100, 0, 7) == 100.0

    def test_no_negative(self):
        result = predict_next_period(10, -5, 10)
        assert result == 0.0


class TestComputeForecastConfidence:
    def test_lots_of_data(self):
        conf = compute_forecast_confidence(30, 0.1)
        assert conf > 0.7

    def test_little_data(self):
        conf = compute_forecast_confidence(5, 0.5)
        assert conf < 0.7

    def test_max_cap(self):
        conf = compute_forecast_confidence(100, 0.0)
        assert conf <= 0.95


class TestScoreRecommendation:
    def test_high_saving_urgent(self):
        score = score_recommendation(50000, 1, 0.9)
        assert score > 50

    def test_low_saving_not_urgent(self):
        score = score_recommendation(100, 48, 0.5)
        assert score < 50


class TestClassifyScenario:
    def test_peak_revenue(self):
        assert classify_scenario(20, 0.38, 0.28, 0) == "peak_revenue"

    def test_revenue_slump(self):
        assert classify_scenario(-20, 0.38, 0.28, 0) == "revenue_slump"

    def test_cost_overrun(self):
        assert classify_scenario(0, 0.45, 0.28, 0) == "cost_overrun"

    def test_normal_ops(self):
        assert classify_scenario(2, 0.38, 0.28, 0) == "normal_ops"


# ─────────────────────────────────────────────
# Agent 集成测试
# ─────────────────────────────────────────────

@pytest.mark.asyncio
class TestRevenueAnomalyAgent:
    async def test_normal_no_alert_saved(self):
        agent = RevenueAnomalyAgent()
        db = make_db()
        result = await agent.detect("B1", "S1", date.today(), 102000, 100000, db, save=True)
        assert result["anomaly_level"] == "normal"
        assert result["ai_insight"] is None   # LLM disabled

    async def test_critical_alert_created(self):
        agent = RevenueAnomalyAgent()
        db = make_db(scalar=None)  # 无已有预警
        result = await agent.detect("B1", "S1", date.today(), 70000, 100000, db, save=True)
        assert result["anomaly_level"] in ("critical", "severe")
        assert result["impact_yuan"] > 0
        assert result["deviation_pct"] < 0

    async def test_severe_level_detected(self):
        agent = RevenueAnomalyAgent()
        db = make_db(scalar=None)
        result = await agent.detect("B1", "S1", date.today(), 50000, 100000, db, save=False)
        assert result["anomaly_level"] == "severe"
        assert result["deviation_pct"] == -50.0


@pytest.mark.asyncio
class TestKpiScorecardAgent:
    async def test_all_on_track(self):
        agent = KpiScorecardAgent()
        db = make_db()
        kpi_values = {
            "revenue_achievement": 1.05,
            "food_cost_ratio": 0.37,
            "labor_cost_ratio": 0.27,
            "table_turnover": 4.0,
            "complaint_rate": 0.005,
        }
        result = await agent.snapshot("B1", "S1", "2026-03", db, kpi_values=kpi_values, save=False)
        assert result["overall_health_score"] > 70
        assert result["off_track_count"] == 0

    async def test_cost_overrun_detected(self):
        agent = KpiScorecardAgent()
        db = make_db()
        kpi_values = {"food_cost_ratio": 0.46, "revenue_achievement": 0.90}
        result = await agent.snapshot("B1", "S1", "2026-03", db, kpi_values=kpi_values, save=False)
        assert result["off_track_count"] >= 1 or result["at_risk_count"] >= 1

    async def test_no_kpi_values_returns_default(self):
        agent = KpiScorecardAgent()
        db = make_db()
        result = await agent.snapshot("B1", "S1", "2026-03", db, kpi_values={}, save=False)
        assert result["overall_health_score"] == 50.0


@pytest.mark.asyncio
class TestOrderForecastAgent:
    async def test_with_snapshots(self):
        agent = OrderForecastAgent()
        snaps = [make_snapshot(order_count=100 + i, revenue_yuan=Decimal(str(50000 + i * 100)))
                 for i in range(10)]
        db = make_db(scalars=snaps)
        result = await agent.forecast("B1", "S1", 7, db, save=False)
        assert result["predicted_orders"] > 0
        assert result["predicted_revenue_yuan"] > 0
        assert result["confidence"] > 0

    async def test_no_snapshots_returns_empty(self):
        agent = OrderForecastAgent()
        db = make_db(scalars=[])
        result = await agent.forecast("B1", "S1", 7, db, save=False)
        assert result["predicted_orders"] == 0
        assert result["confidence"] == 0.0

    async def test_horizon_7_days(self):
        agent = OrderForecastAgent()
        snaps = [make_snapshot() for _ in range(15)]
        db = make_db(scalars=snaps)
        result = await agent.forecast("B1", "S1", 7, db, save=False)
        assert result["horizon_days"] == 7


@pytest.mark.asyncio
class TestBizInsightAgent:
    async def test_no_data_returns_system_rec(self):
        agent = BizInsightAgent()
        db = make_db(scalar=None, scalars=[])
        result = await agent.generate("B1", "S1", db, save=False)
        assert len(result["top3_recommendations"]) >= 1
        assert result["top3_recommendations"][0]["rank"] == 1

    async def test_with_alerts_generates_recs(self):
        agent = BizInsightAgent()
        alert = RevenueAlertStub(
            anomaly_level="critical",
            impact_yuan=Decimal("5000"),
            recommended_action="排查营收异常",
            confidence=0.85,
        )
        db = AsyncMock()

        call_count = [0]

        async def mock_execute(q):
            call_count[0] += 1
            m = MagicMock()
            if call_count[0] == 1:
                m.scalar_one_or_none = MagicMock(return_value=make_snapshot(food_cost_ratio=0.41))
            elif call_count[0] == 2:
                m.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[alert])))
            else:
                m.scalar_one_or_none = MagicMock(return_value=None)
            return m

        db.execute = mock_execute
        db.add = MagicMock()
        db.flush = AsyncMock()

        result = await agent.generate("B1", "S1", db, save=False)
        assert result["total_saving_yuan"] >= 0
        assert 1 <= len(result["top3_recommendations"]) <= 3

    async def test_top3_sorted_by_priority(self):
        agent = BizInsightAgent()
        db = make_db(scalar=None, scalars=[])
        result = await agent.generate("B1", "S1", db, save=False)
        ranks = [r["rank"] for r in result["top3_recommendations"]]
        assert ranks == sorted(ranks)


@pytest.mark.asyncio
class TestScenarioMatchAgent:
    async def test_normal_ops_scenario(self):
        agent = ScenarioMatchAgent()
        db = make_db(scalar=make_snapshot(), scalars=[])
        result = await agent.match("B1", "S1", db, save=False)
        assert result["current_scenario"] == "normal_ops"
        assert len(result["recommended_playbook"]) >= 1

    async def test_cost_overrun_scenario(self):
        agent = ScenarioMatchAgent()
        db = make_db(scalar=make_snapshot(food_cost_ratio=0.46), scalars=[])
        result = await agent.match("B1", "S1", db, save=False)
        assert result["current_scenario"] == "cost_overrun"

    async def test_revenue_slump_via_metrics(self):
        agent = ScenarioMatchAgent()
        db = make_db(scalar=None, scalars=[])
        result = await agent.match("B1", "S1", db,
                                   metrics={"revenue_deviation_pct": -25}, save=False)
        assert result["current_scenario"] == "revenue_slump"

    async def test_playbook_has_steps(self):
        agent = ScenarioMatchAgent()
        db = make_db(scalar=None, scalars=[])
        result = await agent.match("B1", "S1", db,
                                   metrics={"revenue_deviation_pct": 20}, save=False)
        assert result["current_scenario"] == "peak_revenue"
        assert all("step" in s and "action" in s for s in result["recommended_playbook"])
