"""
PeopleAgent 单元测试 — Phase 12B
纯函数 + Agent 类的隔离测试（sys.modules 注入，无 DB 依赖）
"""
import sys
import types
from unittest.mock import MagicMock, AsyncMock
import pytest

# ── sys.modules 注入：屏蔽 SQLAlchemy / DB 依赖 ──────────────────────────────

def _chainable_mock(*args, **kwargs):
    m = MagicMock()
    m.where = _chainable_mock
    m.order_by = _chainable_mock
    m.limit = _chainable_mock
    m.offset = _chainable_mock
    m.filter = _chainable_mock
    return m


_sa = types.ModuleType("sqlalchemy")
_sa.select = _chainable_mock
_sa.and_ = lambda *a, **kw: MagicMock()
_sa.desc = lambda x: MagicMock()
_sa.func = MagicMock()
_sa.text = MagicMock()
sys.modules.setdefault("sqlalchemy", _sa)

_sa_ext = types.ModuleType("sqlalchemy.ext")
sys.modules.setdefault("sqlalchemy.ext", _sa_ext)
_sa_ext_async = types.ModuleType("sqlalchemy.ext.asyncio")
_sa_ext_async.AsyncSession = MagicMock
sys.modules.setdefault("sqlalchemy.ext.asyncio", _sa_ext_async)

_src_db = types.ModuleType("src.db")
_src_db.get_db = MagicMock()
sys.modules.setdefault("src.db", _src_db)

_src_models = types.ModuleType("src.models")
sys.modules.setdefault("src.models", _src_models)

_people_models = types.ModuleType("src.models.people_agent")
for _cls in [
    "PeopleShiftRecord", "PeoplePerformanceScore", "PeopleLaborCostRecord",
    "PeopleAttendanceAlert", "PeopleStaffingDecision", "PeopleAgentLog",
]:
    setattr(_people_models, _cls, MagicMock())
sys.modules.setdefault("src.models.people_agent", _people_models)

_anthropic = types.ModuleType("anthropic")
_anthropic.Anthropic = MagicMock()
sys.modules.setdefault("anthropic", _anthropic)

# ── 导入被测模块 ───────────────────────────────────────────────────────────────

import importlib, importlib.util, pathlib

_agent_path = pathlib.Path(__file__).parent.parent / "src" / "agent.py"
_spec = importlib.util.spec_from_file_location("people_agent_module", _agent_path)
_mod = importlib.util.module_from_spec(_spec)
_mod._LLM_ENABLED = False  # 关闭 LLM 调用
_spec.loader.exec_module(_mod)

(
    compute_coverage_rate,
    classify_shift_status,
    compute_kpi_achievement,
    compute_performance_score,
    classify_performance_rating,
    compute_commission,
    compute_labor_cost_ratio,
    compute_revenue_per_employee,
    compute_optimization_potential,
    classify_attendance_severity,
    score_staffing_recommendation,
    compute_optimal_headcount,
    ShiftOptimizerAgent,
    PerformanceScoreAgent,
    LaborCostAgent,
    AttendanceWarnAgent,
    StaffingPlanAgent,
) = (
    _mod.compute_coverage_rate,
    _mod.classify_shift_status,
    _mod.compute_kpi_achievement,
    _mod.compute_performance_score,
    _mod.classify_performance_rating,
    _mod.compute_commission,
    _mod.compute_labor_cost_ratio,
    _mod.compute_revenue_per_employee,
    _mod.compute_optimization_potential,
    _mod.classify_attendance_severity,
    _mod.score_staffing_recommendation,
    _mod.compute_optimal_headcount,
    _mod.ShiftOptimizerAgent,
    _mod.PerformanceScoreAgent,
    _mod.LaborCostAgent,
    _mod.AttendanceWarnAgent,
    _mod.StaffingPlanAgent,
)


# ══════════════════════════════════════════════════════════════════════════════
# 纯函数测试
# ══════════════════════════════════════════════════════════════════════════════

class TestComputeCoverageRate:
    def test_full_coverage(self):
        assert compute_coverage_rate(10, 10) == 1.0

    def test_partial_coverage(self):
        assert abs(compute_coverage_rate(8, 10) - 0.8) < 1e-9

    def test_over_coverage_capped_at_1_5(self):
        # 上限 1.5，不是1.0
        result = compute_coverage_rate(12, 10)
        assert result == pytest.approx(1.2)

    def test_zero_required(self):
        assert compute_coverage_rate(5, 0) == 1.0


class TestClassifyShiftStatus:
    def test_understaffed(self):
        assert classify_shift_status(0.6, 0.25) == "understaffed"

    def test_overstaffed_by_coverage(self):
        assert classify_shift_status(1.5, 0.20) == "overstaffed"

    def test_overstaffed_by_high_cost(self):
        # labor_cost_ratio > 0.32 → "overstaffed"
        assert classify_shift_status(0.9, 0.40) == "overstaffed"

    def test_high_cost(self):
        # 0.28 < labor_cost_ratio <= 0.32
        assert classify_shift_status(0.9, 0.30) == "high_cost"

    def test_optimal(self):
        assert classify_shift_status(0.9, 0.25) == "optimal"


class TestComputeKpiAchievement:
    def test_at_target(self):
        assert compute_kpi_achievement(100, 100) == 1.0

    def test_above_target_higher_is_better(self):
        assert compute_kpi_achievement(120, 100, higher_is_better=True) == pytest.approx(1.2)

    def test_below_target_lower_is_better(self):
        # lower_is_better: 实际20%，目标30% → 达成率 = 30/20 = 1.5
        assert compute_kpi_achievement(20, 30, higher_is_better=False) == pytest.approx(1.5)

    def test_zero_target_returns_one(self):
        # target<=0 → return 1.0 (视为满分)
        assert compute_kpi_achievement(50, 0) == 1.0


class TestComputePerformanceScore:
    def test_returns_tuple(self):
        kpi_values = {"revenue_achievement": 1.1, "customer_satisfaction": 4.8}
        score, details = compute_performance_score(kpi_values, role="store_manager")
        assert 0 <= score <= 100
        assert isinstance(details, list)

    def test_unknown_role_uses_default(self):
        score, details = compute_performance_score({"task_completion": 0.9}, role="unknown_role")
        assert 0 <= score <= 100

    def test_empty_kpis_returns_50(self):
        # 无KPI数据 → 返回 50.0（中性得分）
        score, details = compute_performance_score({}, role="waiter")
        assert score == 50.0
        assert details == []


class TestClassifyPerformanceRating:
    def test_outstanding(self):
        assert classify_performance_rating(95) == "outstanding"

    def test_exceeds(self):
        assert classify_performance_rating(82) == "exceeds"

    def test_meets(self):
        assert classify_performance_rating(72) == "meets"

    def test_below(self):
        assert classify_performance_rating(58) == "below"

    def test_unsatisfactory(self):
        assert classify_performance_rating(40) == "unsatisfactory"


class TestComputeCommission:
    def test_high_score_bonus(self):
        base, bonus = compute_commission(92, base_salary=5000, role="waiter")
        assert bonus > 0

    def test_low_score_no_bonus(self):
        _, bonus = compute_commission(55, base_salary=5000, role="waiter")
        assert bonus == 0.0

    def test_base_proportion(self):
        base, _ = compute_commission(80, base_salary=10000, role="store_manager")
        assert base > 0


class TestComputeLaborCostRatio:
    def test_normal(self):
        ratio = compute_labor_cost_ratio(28000, 100000)
        assert abs(ratio - 28.0) < 1e-9

    def test_zero_revenue(self):
        assert compute_labor_cost_ratio(1000, 0) == 0.0


class TestComputeRevenuePerEmployee:
    def test_normal(self):
        rev_per_emp = compute_revenue_per_employee(100000, 10)
        assert abs(rev_per_emp - 10000.0) < 1e-9

    def test_zero_headcount(self):
        assert compute_revenue_per_employee(100000, 0) == 0.0


class TestComputeOptimizationPotential:
    def test_above_target(self):
        # 当前30%，目标28% → 有优化空间（以%为单位传入）
        potential = compute_optimization_potential(30.0, 28.0, 100000)
        assert potential > 0

    def test_at_or_below_target(self):
        potential = compute_optimization_potential(26.0, 28.0, 100000)
        assert potential == 0.0


class TestClassifyAttendanceSeverity:
    def test_absent_is_critical(self):
        sev = classify_attendance_severity("absent", 1)
        assert sev == "critical"

    def test_three_lates_is_critical(self):
        sev = classify_attendance_severity("late", 3)
        assert sev == "critical"

    def test_late_once_is_info(self):
        sev = classify_attendance_severity("late", 1)
        assert sev == "info"

    def test_overtime_is_warning(self):
        sev = classify_attendance_severity("overtime", 1)
        assert sev == "warning"


class TestScoreStaffingRecommendation:
    def test_high_impact_high_score(self):
        score = score_staffing_recommendation(50000, 3, 0.9)
        assert score > 0

    def test_low_impact_low_score(self):
        low = score_staffing_recommendation(1000, 30, 0.5)
        high = score_staffing_recommendation(50000, 3, 0.9)
        assert high > low


class TestComputeOptimalHeadcount:
    def test_normal(self):
        optimal = compute_optimal_headcount(100000, 10000, min_headcount=3)
        assert optimal == 10

    def test_min_headcount_floor(self):
        optimal = compute_optimal_headcount(10000, 100000, min_headcount=5)
        assert optimal == 5


# ══════════════════════════════════════════════════════════════════════════════
# Agent 类测试（异步，AsyncMock DB）
# ══════════════════════════════════════════════════════════════════════════════

def _make_db():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(
        scalars=MagicMock(return_value=MagicMock(
            all=MagicMock(return_value=[]),
            first=MagicMock(return_value=None),
        ))
    ))
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


class TestShiftOptimizerAgent:
    @pytest.mark.asyncio
    async def test_optimize_returns_dict(self):
        agent = ShiftOptimizerAgent()
        db = _make_db()
        result = await agent.optimize(
            db=db,
            brand_id="B001",
            store_id="S001",
            shift_date="2026-03-15",
            required_headcount=8,
            scheduled_headcount=7,
            shift_assignments=[],
            estimated_labor_cost_yuan=5600.0,
            revenue_yuan=25000.0,
        )
        assert "record_id" in result
        assert "coverage_rate" in result
        assert "shift_status" in result

    @pytest.mark.asyncio
    async def test_optimize_coverage_rate(self):
        agent = ShiftOptimizerAgent()
        db = _make_db()
        result = await agent.optimize(
            db=db, brand_id="B001", store_id="S001",
            shift_date="2026-03-15",
            required_headcount=10, scheduled_headcount=8,
            shift_assignments=[], estimated_labor_cost_yuan=8000.0,
            revenue_yuan=30000.0,
        )
        assert abs(result["coverage_rate"] - 0.8) < 1e-6


class TestPerformanceScoreAgent:
    @pytest.mark.asyncio
    async def test_score_returns_dict(self):
        agent = PerformanceScoreAgent()
        db = _make_db()
        result = await agent.score(
            db=db,
            brand_id="B001",
            store_id="S001",
            employee_id="E001",
            employee_name="张三",
            role="waiter",
            period="2026-03",
            kpi_values={"avg_per_table": 220.0, "good_review_rate": 0.97},
            base_salary=4000.0,
        )
        assert "record_id" in result
        assert "overall_score" in result
        assert "rating" in result
        assert "total_commission_yuan" in result


class TestLaborCostAgent:
    @pytest.mark.asyncio
    async def test_analyze_returns_dict(self):
        agent = LaborCostAgent()
        db = _make_db()
        result = await agent.analyze(
            db=db,
            brand_id="B001",
            store_id="S001",
            period="2026-03",
            total_labor_cost_yuan=140000.0,
            revenue_yuan=500000.0,
            avg_headcount=14.0,
            overtime_hours=20.0,
            overtime_cost_yuan=3000.0,
            cost_breakdown={"waiter": 60000, "chef": 80000},
        )
        assert "record_id" in result
        assert "labor_cost_ratio_pct" in result
        assert abs(result["labor_cost_ratio_pct"] - 28.0) < 0.01


class TestAttendanceWarnAgent:
    @pytest.mark.asyncio
    async def test_warn_returns_dict(self):
        agent = AttendanceWarnAgent()
        db = _make_db()
        result = await agent.warn(
            db=db,
            brand_id="B001",
            store_id="S001",
            employee_id="E002",
            employee_name="李四",
            alert_date="2026-03-15",
            alert_type="late",
            count_in_period=2,
            estimated_impact_yuan=500.0,
        )
        assert "record_id" in result
        assert "severity" in result
        assert "recommended_action" in result


class TestStaffingPlanAgent:
    @pytest.mark.asyncio
    async def test_plan_returns_dict(self):
        agent = StaffingPlanAgent()
        db = _make_db()
        result = await agent.plan(
            db=db,
            brand_id="B001",
            store_id="S001",
            current_headcount=12,
            revenue_yuan=600000.0,
            target_revenue_per_person=50000.0,
            role_gaps={"waiter": -2, "chef": 1},
        )
        assert "record_id" in result
        assert "optimal_headcount" in result
        assert "top3_recommendations" in result
        assert isinstance(result["top3_recommendations"], list)

    @pytest.mark.asyncio
    async def test_plan_optimal_headcount(self):
        agent = StaffingPlanAgent()
        db = _make_db()
        result = await agent.plan(
            db=db,
            brand_id="B001",
            store_id="S001",
            current_headcount=10,
            revenue_yuan=600000.0,
            target_revenue_per_person=50000.0,
        )
        # 600000 / 50000 = 12
        assert result["optimal_headcount"] == 12
        assert result["headcount_gap"] == 2
