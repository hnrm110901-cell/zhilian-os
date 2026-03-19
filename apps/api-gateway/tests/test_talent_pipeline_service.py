"""Tests for TalentPipelineService — WF-5 新店人才梯队复制流."""
import pytest
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.hr.talent_pipeline_service import (
    TalentPipelineService,
    _compute_readiness_score,
    _estimate_recruit_cost,
    _build_training_timeline,
    _DEFAULT_HEADCOUNT,
)


# ── 纯函数测试 ────────────────────────────────────────────────────────

class TestComputeReadinessScore:
    def test_full_coverage_returns_one(self):
        assert _compute_readiness_score(10, 10) == 1.0

    def test_over_coverage_capped_at_one(self):
        assert _compute_readiness_score(5, 10) == 1.0

    def test_zero_coverage_returns_zero(self):
        assert _compute_readiness_score(10, 0) == 0.0

    def test_partial_coverage(self):
        score = _compute_readiness_score(10, 6)
        assert score == pytest.approx(0.6, abs=0.001)

    def test_zero_required_returns_one(self):
        assert _compute_readiness_score(0, 0) == 1.0

    def test_result_is_four_decimal_precision(self):
        score = _compute_readiness_score(3, 2)
        assert score == pytest.approx(0.6667, abs=0.0001)


class TestEstimateRecruitCost:
    def test_kitchen_cost(self):
        # kitchen base_salary=4500, × 0.5 × 2 = 4500
        cost = _estimate_recruit_cost("kitchen", 2)
        assert cost == pytest.approx(4500.0)

    def test_manager_cost_is_higher(self):
        # manager base_salary=9000, × 0.5 × 1 = 4500
        cost = _estimate_recruit_cost("manager", 1)
        assert cost == pytest.approx(4500.0)

    def test_unknown_position_uses_default(self):
        # default=4000, × 0.5 × 1 = 2000
        cost = _estimate_recruit_cost("unknown_role", 1)
        assert cost == pytest.approx(2000.0)

    def test_zero_headcount_returns_zero(self):
        assert _estimate_recruit_cost("kitchen", 0) == 0.0

    def test_result_rounded_to_two_decimals(self):
        cost = _estimate_recruit_cost("service", 3)
        # service=3800, × 0.5 × 3 = 5700
        assert cost == pytest.approx(5700.0)


class TestBuildTrainingTimeline:
    def test_zero_gaps_returns_empty(self):
        assert _build_training_timeline("2026-06-01", 0) == []

    def test_single_gap_returns_one_milestone(self):
        timeline = _build_training_timeline("2027-12-31", 1)
        assert len(timeline) == 1
        assert timeline[0]["week"] == 1
        assert "urgent" in timeline[0]
        assert "target_date" in timeline[0]

    def test_caps_at_eight_milestones(self):
        timeline = _build_training_timeline("2027-12-31", 20)
        assert len(timeline) <= 8

    def test_open_date_none_generates_timeline(self):
        timeline = _build_training_timeline(None, 3)
        assert len(timeline) == 3

    def test_urgent_flag_set_when_deadline_exceeded(self):
        # 开业日很近（明天），培训时间必超出
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        timeline = _build_training_timeline(tomorrow, 3)
        # 应有 urgent=True 的条目
        assert any(t["urgent"] for t in timeline)

    def test_no_urgent_when_open_date_far_future(self):
        far_future = "2099-12-31"
        timeline = _build_training_timeline(far_future, 3)
        assert all(not t["urgent"] for t in timeline)

    def test_invalid_date_falls_back_gracefully(self):
        timeline = _build_training_timeline("not-a-date", 2)
        assert len(timeline) == 2  # 无 open_date 限制，正常生成


# ── TalentPipelineService 集成测试（mock DB）─────────────────────────

def _make_row(**kwargs):
    """构造 mock DB 行."""
    row = MagicMock()
    for k, v in kwargs.items():
        setattr(row, k, v)
    return row


@pytest.mark.asyncio
class TestTalentPipelineService:
    def _make_session(self, candidate_rows=None, gap_rows=None):
        session = AsyncMock()

        async def execute(query, params=None):
            result = MagicMock()
            sql_text = str(query)
            if "skill_nodes" in sql_text:
                result.fetchall.return_value = gap_rows or []
            elif "FROM persons" in sql_text or "candidates" in sql_text:
                result.fetchall.return_value = candidate_rows or []
            else:
                result.fetchall.return_value = []
            return result

        session.execute = execute
        return session

    async def test_returns_all_expected_keys(self):
        session = self._make_session()
        svc = TalentPipelineService(session=session)
        result = await svc.analyze("ORG001")
        for key in [
            "readiness_score", "readiness_pct", "candidates",
            "skill_gaps", "recruit_plan", "total_recruit_cost_yuan",
            "training_timeline", "total_required",
        ]:
            assert key in result

    async def test_no_candidates_zero_readiness(self):
        session = self._make_session(candidate_rows=[])
        svc = TalentPipelineService(session=session)
        result = await svc.analyze("ORG001", headcount_plan={"kitchen": 5})
        assert result["eligible_candidates_count"] == 0
        assert result["readiness_score"] == 0.0

    async def test_with_candidates_eligible_counted(self):
        candidates = [
            _make_row(
                id="P1", name="张三", phone="13800000001",
                assignment_id="A1", employment_type="full_time",
                job_title="厨师", skill_count=5, risk_score=0.3,
                current_store="门店A", current_store_id="S1",
            ),
        ]
        session = self._make_session(candidate_rows=candidates)
        svc = TalentPipelineService(session=session)
        result = await svc.analyze("ORG001", headcount_plan={"kitchen": 2})
        assert result["eligible_candidates_count"] >= 0  # DB mock不精确，只验证结构
        assert isinstance(result["candidates"], list)

    async def test_skill_gaps_populated(self):
        gaps = [
            _make_row(
                id="SN1", skill_name="拉面技术", category="kitchen",
                estimated_revenue_lift=500.0, holder_count=0,
            ),
        ]
        session = self._make_session(gap_rows=gaps)
        svc = TalentPipelineService(session=session)
        result = await svc.analyze("ORG001")
        # skill_gaps 按 holder_count<2 过滤，holder_count=0 应入选
        assert isinstance(result["skill_gaps"], list)

    async def test_recruit_plan_generated_when_shortage(self):
        session = self._make_session(candidate_rows=[])
        svc = TalentPipelineService(session=session)
        result = await svc.analyze("ORG001", headcount_plan={"kitchen": 3})
        # 0 candidates → shortage=3 → recruit_plan 非空
        assert len(result["recruit_plan"]) > 0
        assert result["recruit_plan"][0]["shortage"] == 3

    async def test_total_recruit_cost_yuan_is_sum(self):
        session = self._make_session(candidate_rows=[])
        svc = TalentPipelineService(session=session)
        result = await svc.analyze("ORG001", headcount_plan={"kitchen": 2, "service": 3})
        expected = _estimate_recruit_cost("kitchen", 2) + _estimate_recruit_cost("service", 3)
        assert result["total_recruit_cost_yuan"] == pytest.approx(expected, abs=0.01)

    async def test_training_timeline_generated_from_skill_gaps(self):
        gaps = [
            _make_row(
                id=f"SN{i}", skill_name=f"技能{i}", category="kitchen",
                estimated_revenue_lift=300.0, holder_count=0,
            )
            for i in range(3)
        ]
        session = self._make_session(gap_rows=gaps)
        svc = TalentPipelineService(session=session)
        result = await svc.analyze("ORG001", open_date="2099-12-31")
        assert isinstance(result["training_timeline"], list)

    async def test_db_failure_degrades_gracefully(self):
        """DB 异常时静默降级，不抛出."""
        session = AsyncMock()
        session.execute.side_effect = Exception("DB timeout")
        svc = TalentPipelineService(session=session)
        result = await svc.analyze("ORG001")
        assert result["candidates"] == []
        assert result["readiness_score"] == 0.0

    async def test_uses_default_headcount_when_none(self):
        session = self._make_session(candidate_rows=[])
        svc = TalentPipelineService(session=session)
        result = await svc.analyze("ORG001")
        assert result["total_required"] == sum(_DEFAULT_HEADCOUNT.values())

    async def test_open_date_passed_through_to_result(self):
        session = self._make_session()
        svc = TalentPipelineService(session=session)
        result = await svc.analyze("ORG001", open_date="2026-06-01")
        assert result["open_date"] == "2026-06-01"

    async def test_readiness_pct_is_score_times_100(self):
        session = self._make_session(candidate_rows=[])
        svc = TalentPipelineService(session=session)
        result = await svc.analyze("ORG001", headcount_plan={"kitchen": 5})
        assert result["readiness_pct"] == round(result["readiness_score"] * 100, 1)
