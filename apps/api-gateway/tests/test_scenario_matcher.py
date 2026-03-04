"""
ScenarioMatcher 单元测试

覆盖：
  - classify_scenario：7种场景分类（纯函数）
  - score_case_similarity：相似度评分（纯函数）
  - get_scenario_label：标签映射
  - identify_current_scenario：场景识别（mock DB）
  - find_similar_cases：历史案例检索（mock DB）
"""

import pytest
from datetime import date
from unittest.mock import AsyncMock, MagicMock

from src.services.scenario_matcher import (
    ScenarioMatcher,
    classify_scenario,
    score_case_similarity,
    get_scenario_label,
    SCENARIO_HOLIDAY_PEAK,
    SCENARIO_WEEKDAY_NORMAL,
    SCENARIO_HIGH_COST,
    SCENARIO_REVENUE_DOWN,
    SCENARIO_NEW_DISH,
    SCENARIO_HIGH_WASTE,
    SCENARIO_WEEKEND,
)


# ── classify_scenario ────────────────────────────────────────────────────────

class TestClassifyScenario:
    def test_high_cost_takes_priority(self):
        """高成本率优先级最高（即使是节假日）"""
        result = classify_scenario(
            cost_rate_pct=38.0,
            waste_rate_pct=6.0,
            revenue_wow_pct=10.0,
            day_of_week=0,
            is_holiday=True,
        )
        assert result == SCENARIO_HIGH_COST

    def test_high_waste_second_priority(self):
        """损耗高发优先级第二（成本正常时）"""
        result = classify_scenario(
            cost_rate_pct=28.0,   # ok
            waste_rate_pct=6.0,   # high
            revenue_wow_pct=5.0,
            day_of_week=0,
        )
        assert result == SCENARIO_HIGH_WASTE

    def test_holiday_peak_identified(self):
        result = classify_scenario(
            cost_rate_pct=28.0,
            waste_rate_pct=2.0,
            revenue_wow_pct=15.0,
            day_of_week=1,
            is_holiday=True,
        )
        assert result == SCENARIO_HOLIDAY_PEAK

    def test_revenue_down_identified(self):
        result = classify_scenario(
            cost_rate_pct=28.0,
            waste_rate_pct=2.0,
            revenue_wow_pct=-15.0,  # 下降15%
            day_of_week=1,
        )
        assert result == SCENARIO_REVENUE_DOWN

    def test_weekend_identified(self):
        result = classify_scenario(
            cost_rate_pct=28.0,
            waste_rate_pct=2.0,
            revenue_wow_pct=5.0,
            day_of_week=5,   # 周六
        )
        assert result == SCENARIO_WEEKEND

    def test_sunday_is_weekend(self):
        result = classify_scenario(
            cost_rate_pct=28.0, waste_rate_pct=2.0,
            revenue_wow_pct=5.0, day_of_week=6,  # 周日
        )
        assert result == SCENARIO_WEEKEND

    def test_new_dish_identified(self):
        result = classify_scenario(
            cost_rate_pct=28.0,
            waste_rate_pct=2.0,
            revenue_wow_pct=5.0,
            day_of_week=2,
            new_dish_count=3,
        )
        assert result == SCENARIO_NEW_DISH

    def test_weekday_normal_as_fallback(self):
        result = classify_scenario(
            cost_rate_pct=28.0,
            waste_rate_pct=2.0,
            revenue_wow_pct=0.0,
            day_of_week=2,
        )
        assert result == SCENARIO_WEEKDAY_NORMAL

    def test_revenue_exactly_at_threshold_is_normal(self):
        """营收下行阈值 -10%，-10.0 刚好触发"""
        result = classify_scenario(
            cost_rate_pct=28.0, waste_rate_pct=2.0,
            revenue_wow_pct=-10.0, day_of_week=2,
        )
        assert result == SCENARIO_REVENUE_DOWN

    def test_revenue_just_above_threshold_is_normal(self):
        result = classify_scenario(
            cost_rate_pct=28.0, waste_rate_pct=2.0,
            revenue_wow_pct=-9.5, day_of_week=2,
        )
        assert result == SCENARIO_WEEKDAY_NORMAL


# ── get_scenario_label ───────────────────────────────────────────────────────

class TestGetScenarioLabel:
    def test_known_scenario_returns_chinese_label(self):
        assert get_scenario_label(SCENARIO_HIGH_COST) == "成本超标期"
        assert get_scenario_label(SCENARIO_HOLIDAY_PEAK) == "节假日高峰期"
        assert get_scenario_label(SCENARIO_WEEKDAY_NORMAL) == "工作日正常期"

    def test_unknown_scenario_returns_fallback(self):
        result = get_scenario_label("unknown_scenario")
        assert result == "未知场景"


# ── score_case_similarity ────────────────────────────────────────────────────

class TestScoreCaseSimilarity:
    def test_perfect_match_is_high_score(self):
        score = score_case_similarity(
            current_cost_pct=30.0,
            current_revenue=500_000,
            case_cost_pct=30.0,
            case_revenue=500_000,
            scenario_match=True,
        )
        assert score >= 0.95  # 完全匹配接近1.0

    def test_scenario_mismatch_reduces_score(self):
        match_score = score_case_similarity(30.0, 500_000, 30.0, 500_000, True)
        no_match = score_case_similarity(30.0, 500_000, 30.0, 500_000, False)
        assert match_score > no_match

    def test_large_cost_delta_reduces_score(self):
        close = score_case_similarity(30.0, 500_000, 31.0, 500_000, True)
        far   = score_case_similarity(30.0, 500_000, 50.0, 500_000, True)
        assert close > far

    def test_cost_delta_over_20_gets_zero_cost_component(self):
        score = score_case_similarity(
            current_cost_pct=10.0,
            current_revenue=500_000,
            case_cost_pct=31.0,   # delta=21 > 20
            case_revenue=500_000,
            scenario_match=False,
        )
        # Only revenue similarity contributes
        assert score <= 0.25

    def test_score_in_0_to_1_range(self):
        for cost_delta in [0, 5, 15, 25]:
            score = score_case_similarity(30.0, 500_000, 30.0 + cost_delta, 500_000, True)
            assert 0.0 <= score <= 1.0


# ── identify_current_scenario ────────────────────────────────────────────────

class TestIdentifyCurrentScenario:
    def _mock_db(self, revenue=700_000, prev_revenue=650_000,
                 cost=245_000, waste=21_000, new_dishes=0):
        db = AsyncMock()
        calls = [
            MagicMock(scalar=MagicMock(return_value=revenue)),       # 本周营收
            MagicMock(scalar=MagicMock(return_value=prev_revenue)),  # 上周营收
            MagicMock(scalar=MagicMock(return_value=cost)),          # 本周成本
            MagicMock(scalar=MagicMock(return_value=waste)),         # 本周损耗
            MagicMock(scalar=MagicMock(return_value=new_dishes)),    # 新菜品
        ]
        db.execute = AsyncMock(side_effect=calls)
        return db

    @pytest.mark.asyncio
    async def test_returns_scenario_type(self):
        db = self._mock_db()
        result = await ScenarioMatcher.identify_current_scenario("S001", db)
        assert "scenario_type" in result
        assert result["scenario_type"] in (
            SCENARIO_HOLIDAY_PEAK, SCENARIO_WEEKDAY_NORMAL,
            SCENARIO_HIGH_COST, SCENARIO_REVENUE_DOWN,
            SCENARIO_NEW_DISH, SCENARIO_HIGH_WASTE, SCENARIO_WEEKEND,
        )

    @pytest.mark.asyncio
    async def test_high_cost_detected(self):
        db = self._mock_db(revenue=1_000_000, cost=400_000)  # 40% cost rate
        result = await ScenarioMatcher.identify_current_scenario("S001", db)
        assert result["scenario_type"] == SCENARIO_HIGH_COST

    @pytest.mark.asyncio
    async def test_metrics_contain_yuan_fields(self):
        db = self._mock_db()
        result = await ScenarioMatcher.identify_current_scenario("S001", db)
        assert "revenue_yuan" in result["metrics"]
        assert result["metrics"]["revenue_yuan"] >= 0.0


# ── find_similar_cases ───────────────────────────────────────────────────────

class TestFindSimilarCases:
    def _mock_db_with_cases(self):
        db = AsyncMock()
        row1 = MagicMock()
        row1.id = "DEC_001"
        row1.ai_suggestion = {
            "action": "紧急补货鸡腿",
            "expected_saving_yuan": 2000.0,
            "actual_saving_yuan": 1800.0,
            "scenario_type": SCENARIO_HIGH_COST,
            "theoretical_cost_pct": 36.0,
            "revenue_fen": 500_000,
        }
        row1.outcome = "success"
        row1.created_at = "2026-02-01"

        result = MagicMock()
        result.fetchall = MagicMock(return_value=[row1])
        db.execute = AsyncMock(return_value=result)
        return db

    @pytest.mark.asyncio
    async def test_returns_list_of_cases(self):
        db = self._mock_db_with_cases()
        cases = await ScenarioMatcher.find_similar_cases(
            "S001", SCENARIO_HIGH_COST, 36.0, 500_000, db
        )
        assert isinstance(cases, list)
        assert len(cases) >= 1

    @pytest.mark.asyncio
    async def test_case_has_similarity_score(self):
        db = self._mock_db_with_cases()
        cases = await ScenarioMatcher.find_similar_cases(
            "S001", SCENARIO_HIGH_COST, 36.0, 500_000, db
        )
        assert "similarity_score" in cases[0]
        assert 0.0 <= cases[0]["similarity_score"] <= 1.0

    @pytest.mark.asyncio
    async def test_scenario_match_increases_score(self):
        """同场景案例的相似度 > 不同场景案例"""
        db = self._mock_db_with_cases()
        same_cases = await ScenarioMatcher.find_similar_cases(
            "S001", SCENARIO_HIGH_COST, 36.0, 500_000, db
        )
        db2 = self._mock_db_with_cases()
        diff_cases = await ScenarioMatcher.find_similar_cases(
            "S001", SCENARIO_WEEKDAY_NORMAL, 28.0, 500_000, db2
        )
        # 同场景（HIGH_COST vs HIGH_COST）评分应高于不同场景
        assert same_cases[0]["similarity_score"] >= diff_cases[0]["similarity_score"]

    @pytest.mark.asyncio
    async def test_empty_db_returns_empty_list(self):
        db = AsyncMock()
        result = MagicMock()
        result.fetchall = MagicMock(return_value=[])
        db.execute = AsyncMock(return_value=result)

        cases = await ScenarioMatcher.find_similar_cases(
            "S001", SCENARIO_WEEKDAY_NORMAL, 30.0, 500_000, db
        )
        assert cases == []
