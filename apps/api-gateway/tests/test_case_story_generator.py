"""
CaseStoryGenerator 单元测试

覆盖：
  - _compute_cost_metrics：成本率计算 + _yuan 字段 + 状态分级
  - _summarize_decisions：决策汇总（采纳率/总节省¥）
  - _narrative_sentence：叙述文字生成
  - generate_daily_story：日维度（mock DB）
  - generate_weekly_story：周维度 + 环比（mock DB）
  - generate_monthly_story：月维度 + weekly_trend（mock DB）
"""

import pytest
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.case_story_generator import (
    CaseStoryGenerator,
    _compute_cost_metrics,
    _summarize_decisions,
    _narrative_sentence,
    _fen_to_yuan,
)


# ── _fen_to_yuan ──────────────────────────────────────────────────────────────

class TestFenToYuan:
    def test_converts_correctly(self):
        assert _fen_to_yuan(100) == 1.0
        assert _fen_to_yuan(1234567) == 12345.67
        assert _fen_to_yuan(0) == 0.0

    def test_float_input(self):
        assert _fen_to_yuan(99.9) == 1.0  # round(99.9/100, 2) = 1.0


# ── _compute_cost_metrics ────────────────────────────────────────────────────

class TestComputeCostMetrics:
    def test_all_yuan_fields_present(self):
        m = _compute_cost_metrics(100_000, 30_000, 5_000)
        assert "revenue_yuan" in m
        assert "actual_cost_yuan" in m
        assert "waste_cost_yuan" in m

    def test_cost_rate_calculated_correctly(self):
        # 300_000 fen revenue, 90_000 fen cost → 30.0%
        m = _compute_cost_metrics(300_000, 90_000, 0)
        assert m["actual_cost_pct"] == 30.0

    def test_status_ok_when_below_30_pct(self):
        m = _compute_cost_metrics(1_000_000, 250_000, 0)  # 25%
        assert m["cost_rate_status"] == "ok"

    def test_status_warning_when_32_to_35_pct(self):
        m = _compute_cost_metrics(1_000_000, 320_000, 0)  # 32%
        assert m["cost_rate_status"] == "warning"

    def test_status_critical_when_above_40_pct(self):
        m = _compute_cost_metrics(1_000_000, 420_000, 0)  # 42%
        assert m["cost_rate_status"] == "critical"

    def test_zero_revenue_returns_zero_pct(self):
        m = _compute_cost_metrics(0, 5_000, 2_000)
        assert m["actual_cost_pct"] == 0.0
        assert m["waste_pct"] == 0.0

    def test_yuan_equals_fen_divided_by_100(self):
        m = _compute_cost_metrics(500_000, 150_000, 10_000)
        assert m["revenue_yuan"] == 5000.0
        assert m["actual_cost_yuan"] == 1500.0
        assert m["waste_cost_yuan"] == 100.0


# ── _summarize_decisions ─────────────────────────────────────────────────────

class TestSummarizeDecisions:
    def _make_decision(self, status="PENDING", outcome=None, saving=0.0):
        return {
            "id": "D1", "action": "test", "confidence": 0.8,
            "status": status, "outcome": outcome,
            "expected_saving_yuan": saving, "created_at": "2026-03-04",
        }

    def test_empty_returns_zero_counts(self):
        s = _summarize_decisions([])
        assert s["total"] == 0
        assert s["adoption_rate_pct"] == 0.0
        assert s["total_saving_yuan"] == 0.0

    def test_adoption_rate_calculated(self):
        decisions = [
            self._make_decision(status="APPROVED"),
            self._make_decision(status="APPROVED"),
            self._make_decision(status="REJECTED"),
            self._make_decision(status="PENDING"),
        ]
        s = _summarize_decisions(decisions)
        assert s["adoption_rate_pct"] == 50.0  # 2/4

    def test_total_saving_sums_approved_only(self):
        decisions = [
            self._make_decision(status="APPROVED", saving=1000.0),
            self._make_decision(status="APPROVED", saving=500.0),
            self._make_decision(status="REJECTED", saving=999.0),  # 不算
        ]
        s = _summarize_decisions(decisions)
        assert s["total_saving_yuan"] == 1500.0

    def test_successful_count(self):
        decisions = [
            self._make_decision(status="EXECUTED", outcome="success"),
            self._make_decision(status="EXECUTED", outcome="failure"),
            self._make_decision(status="APPROVED", outcome=None),
        ]
        s = _summarize_decisions(decisions)
        assert s["successful"] == 1


# ── _narrative_sentence ──────────────────────────────────────────────────────

class TestNarrativeSentence:
    def test_contains_store_id(self):
        m = _compute_cost_metrics(1_000_000, 300_000, 50_000)
        s = _summarize_decisions([])
        text = _narrative_sentence("S001", "2026年3月", m, s)
        assert "S001" in text

    def test_contains_cost_rate(self):
        m = _compute_cost_metrics(1_000_000, 300_000, 0)
        s = _summarize_decisions([])
        text = _narrative_sentence("S001", "2026年3月", m, s)
        assert "30.0%" in text

    def test_contains_saving_when_positive(self):
        m = _compute_cost_metrics(1_000_000, 300_000, 0)
        d = {"id": "D1", "status": "APPROVED", "outcome": None,
             "action": "x", "confidence": 0.9, "expected_saving_yuan": 2000.0, "created_at": ""}
        s = _summarize_decisions([d])
        text = _narrative_sentence("S001", "周期", m, s)
        assert "2000" in text

    def test_contains_waste_when_nonzero(self):
        m = _compute_cost_metrics(1_000_000, 300_000, 50_000)
        s = _summarize_decisions([])
        text = _narrative_sentence("S001", "周期", m, s)
        assert "500.0" in text  # waste_yuan = 500元


# ── generate_daily_story ─────────────────────────────────────────────────────

class TestGenerateDailyStory:
    def _mock_db(self, revenue=500_000, cost=150_000, waste=20_000):
        db = AsyncMock()
        results = [
            MagicMock(scalar=MagicMock(return_value=revenue)),
            MagicMock(scalar=MagicMock(return_value=cost)),
            MagicMock(scalar=MagicMock(return_value=waste)),
            MagicMock(fetchall=MagicMock(return_value=[])),
        ]
        db.execute = AsyncMock(side_effect=results)
        return db

    @pytest.mark.asyncio
    async def test_returns_daily_period(self):
        db = self._mock_db()
        story = await CaseStoryGenerator.generate_daily_story(
            "S001", date(2026, 3, 4), db
        )
        assert story["period"] == "daily"
        assert story["date"] == "2026-03-04"

    @pytest.mark.asyncio
    async def test_cost_metrics_present(self):
        db = self._mock_db(revenue=500_000, cost=150_000)
        story = await CaseStoryGenerator.generate_daily_story(
            "S001", date(2026, 3, 4), db
        )
        assert "actual_cost_pct" in story["cost_metrics"]
        assert story["cost_metrics"]["actual_cost_pct"] == 30.0

    @pytest.mark.asyncio
    async def test_narrative_is_string(self):
        db = self._mock_db()
        story = await CaseStoryGenerator.generate_daily_story(
            "S001", date(2026, 3, 4), db
        )
        assert isinstance(story["narrative"], str)
        assert len(story["narrative"]) > 10


# ── generate_weekly_story ────────────────────────────────────────────────────

class TestGenerateWeeklyStory:
    def _mock_db_for_weekly(self):
        """周数据（本周+上周各4次查询：营收/成本/损耗/决策，以及上周营收/成本）"""
        db = AsyncMock()
        calls = [
            MagicMock(scalar=MagicMock(return_value=700_000)),   # 本周营收
            MagicMock(scalar=MagicMock(return_value=245_000)),   # 本周成本
            MagicMock(scalar=MagicMock(return_value=35_000)),    # 本周损耗
            MagicMock(fetchall=MagicMock(return_value=[])),      # 本周决策
            MagicMock(scalar=MagicMock(return_value=650_000)),   # 上周营收
            MagicMock(scalar=MagicMock(return_value=240_000)),   # 上周成本
        ]
        db.execute = AsyncMock(side_effect=calls)
        return db

    @pytest.mark.asyncio
    async def test_weekly_story_has_wow_section(self):
        db = self._mock_db_for_weekly()
        story = await CaseStoryGenerator.generate_weekly_story(
            "S001", date(2026, 2, 25), db
        )
        assert "week_over_week" in story
        assert "revenue_wow_pct" in story["week_over_week"]

    @pytest.mark.asyncio
    async def test_revenue_wow_calculated_correctly(self):
        db = self._mock_db_for_weekly()
        story = await CaseStoryGenerator.generate_weekly_story(
            "S001", date(2026, 2, 25), db
        )
        # (700_000 - 650_000) / 650_000 ≈ 7.7%
        wow = story["week_over_week"]["revenue_wow_pct"]
        assert 7.0 < wow < 8.0


# ── generate_monthly_story ────────────────────────────────────────────────────

class TestGenerateMonthlyStory:
    def _mock_db_for_monthly(self):
        """月度数据：5次固定查询 + 5周 × 2次查询"""
        db = AsyncMock()

        scalar_vals = [
            3_000_000,  # 月营收
            990_000,    # 月成本
            120_000,    # 月损耗
        ]
        decision_result = MagicMock(fetchall=MagicMock(return_value=[]))

        # 构造 side_effect：先返回 3次标量，再返回决策，然后每周2次标量
        scalars_iter = iter(
            [MagicMock(scalar=MagicMock(return_value=v)) for v in scalar_vals]
            + [decision_result]
            + [MagicMock(scalar=MagicMock(return_value=500_000)) for _ in range(10)]
        )

        async def side_effect(*args, **kwargs):
            return next(scalars_iter)

        db.execute = AsyncMock(side_effect=side_effect)
        return db

    @pytest.mark.asyncio
    async def test_monthly_story_has_weekly_trend(self):
        db = self._mock_db_for_monthly()
        story = await CaseStoryGenerator.generate_monthly_story(
            "S001", 2026, 3, db
        )
        assert "weekly_trend" in story
        assert isinstance(story["weekly_trend"], list)
        assert len(story["weekly_trend"]) >= 4  # 3月有4-5周

    @pytest.mark.asyncio
    async def test_monthly_story_has_top3_decisions(self):
        db = self._mock_db_for_monthly()
        story = await CaseStoryGenerator.generate_monthly_story(
            "S001", 2026, 3, db
        )
        assert "top3_decisions" in story
        assert isinstance(story["top3_decisions"], list)

    @pytest.mark.asyncio
    async def test_monthly_cost_rate_calculation(self):
        db = self._mock_db_for_monthly()
        story = await CaseStoryGenerator.generate_monthly_story(
            "S001", 2026, 3, db
        )
        # 990_000 / 3_000_000 = 33%
        pct = story["cost_metrics"]["actual_cost_pct"]
        assert abs(pct - 33.0) < 0.5
