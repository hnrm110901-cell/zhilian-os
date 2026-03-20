"""
Golden Path 核心链路测试

验证系统 5 条最关键业务链路的端到端正确性：
  1. 行业标准字典完整性 — 枚举、映射、基准线无遗漏
  2. 岗位标准 → 人员分配链路 — JobStandard + Person + EmploymentAssignment
  3. 成本真相引擎数据流 — CostTruth 5因子归因完整性
  4. 流失预测纯函数链路 — turnover_prediction 风险计算正确性
  5. 排班模板匹配链路 — StaffingPattern 技能匹配逻辑

设计原则：
  - 不依赖数据库连接（纯逻辑/模型测试优先）
  - 覆盖核心业务不变式（business invariant）
  - 快速运行（< 2s），适合 CI 每次提交
"""

import uuid
from datetime import date, time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# Golden Path 1: 行业标准字典完整性
# ═══════════════════════════════════════════════════════════════════════════════

class TestIndustryStandardsDictionary:
    """验证行业标准字典枚举的完整性和一致性"""

    def test_cuisine_type_covers_seed_customers(self):
        """种子客户菜系必须在 CuisineType 中有对应值"""
        from src.constants.industry_standards import CuisineType

        # 尝在一起 = 湘菜, 徐记海鲜 = 海鲜, 最黔线 = 黔菜
        assert CuisineType.HUNAN.value == "hunan"
        assert CuisineType.SEAFOOD.value == "seafood"
        assert CuisineType.GUIZHOU.value == "guizhou"

    def test_cuisine_labels_complete(self):
        """每个 CuisineType 都必须有中文标签"""
        from src.constants.industry_standards import CUISINE_LABELS, CuisineType

        for ct in CuisineType:
            assert ct in CUISINE_LABELS, f"CuisineType.{ct.name} 缺少中文标签"
            assert len(CUISINE_LABELS[ct]) > 0

    def test_cost_category_hierarchy(self):
        """二级成本分类必须都能映射到一级"""
        from src.constants.industry_standards import COST_L2_TO_L1, CostCategoryL1, CostCategoryL2

        for l2 in CostCategoryL2:
            assert l2 in COST_L2_TO_L1, f"CostCategoryL2.{l2.name} 无一级映射"
            assert isinstance(COST_L2_TO_L1[l2], CostCategoryL1)

    def test_job_code_matches_seed(self):
        """JobCode 枚举必须与 job_standards_seed.py 的 15 个岗位完全一致"""
        from src.constants.industry_standards import JobCode
        from src.seeds.job_standards_seed import JOB_STANDARDS

        enum_codes = {jc.value for jc in JobCode}
        seed_codes = {js["job_code"] for js in JOB_STANDARDS}

        assert enum_codes == seed_codes, (
            f"枚举多余: {enum_codes - seed_codes}, 种子多余: {seed_codes - enum_codes}"
        )

    def test_job_code_prefix_complete(self):
        """每个 JobCode 都必须有层级编码前缀"""
        from src.constants.industry_standards import JOB_CODE_PREFIX, JobCode

        for jc in JobCode:
            assert jc in JOB_CODE_PREFIX, f"JobCode.{jc.name} 缺少层级编码前缀"
            prefix = JOB_CODE_PREFIX[jc]
            # 编码格式: XX-XXX
            assert "-" in prefix, f"编码格式错误: {prefix}"

    def test_meal_period_hours_complete(self):
        """每个 MealPeriodStandard 都必须有时间范围"""
        from src.constants.industry_standards import MEAL_PERIOD_HOURS, MealPeriodStandard

        for mp in MealPeriodStandard:
            assert mp in MEAL_PERIOD_HOURS, f"MealPeriodStandard.{mp.name} 缺少时间范围"
            start, end = MEAL_PERIOD_HOURS[mp]
            assert ":" in start and ":" in end

    def test_food_cost_benchmark_covers_key_cuisines(self):
        """食材成本基准线必须覆盖所有种子客户菜系"""
        from src.constants.industry_standards import CuisineType, FOOD_COST_BENCHMARK_P50

        for ct in [CuisineType.HUNAN, CuisineType.SEAFOOD, CuisineType.GUIZHOU]:
            assert ct in FOOD_COST_BENCHMARK_P50, f"缺少 {ct.value} 食材成本基准"
            val = FOOD_COST_BENCHMARK_P50[ct]
            assert 20.0 <= val <= 50.0, f"{ct.value} 食材成本率 {val}% 超出合理范围"

    def test_benchmarks_cover_all_18_cuisines(self):
        """食材/人力/租金基准线必须覆盖全部 18 个菜系"""
        from src.constants.industry_standards import (
            CuisineType, FOOD_COST_BENCHMARK_P50,
            LABOR_COST_BENCHMARK_P50, RENT_COST_BENCHMARK_P50,
        )

        all_cuisines = set(CuisineType)
        for name, benchmark in [
            ("FOOD_COST", FOOD_COST_BENCHMARK_P50),
            ("LABOR_COST", LABOR_COST_BENCHMARK_P50),
            ("RENT_COST", RENT_COST_BENCHMARK_P50),
        ]:
            missing = all_cuisines - set(benchmark.keys())
            assert not missing, f"{name} 缺少菜系: {[c.name for c in missing]}"

    def test_meal_period_compat_map_complete(self):
        """MEAL_PERIOD_COMPAT_MAP 必须覆盖全部 MealPeriodStandard"""
        from src.constants.industry_standards import (
            MEAL_PERIOD_COMPAT_MAP, MealPeriodStandard,
        )

        for mp in MealPeriodStandard:
            assert mp in MEAL_PERIOD_COMPAT_MAP, (
                f"MealPeriodStandard.{mp.name} 缺少兼容映射"
            )

    def test_constants_package_exports(self):
        """constants 包 __init__.py 必须导出所有枚举和映射字典"""
        import src.constants as const_pkg

        # 枚举
        for enum_name in [
            "CuisineType", "CostCategoryL1", "CostCategoryL2",
            "MealPeriodStandard", "JobCode", "JobLevel",
        ]:
            assert hasattr(const_pkg, enum_name), f"constants 包缺少导出: {enum_name}"

        # 映射字典
        for dict_name in [
            "CUISINE_LABELS", "COST_L2_TO_L1", "MEAL_PERIOD_HOURS",
            "JOB_CODE_PREFIX", "FOOD_COST_BENCHMARK_P50",
            "LABOR_COST_BENCHMARK_P50", "RENT_COST_BENCHMARK_P50",
        ]:
            assert hasattr(const_pkg, dict_name), f"constants 包缺少导出: {dict_name}"


# ═══════════════════════════════════════════════════════════════════════════════
# Golden Path 2: 岗位标准 → 人员分配链路
# ═══════════════════════════════════════════════════════════════════════════════

class TestJobStandardPersonChain:
    """验证 JobStandard → EmploymentAssignment → Person 数据链路"""

    def test_job_standards_seed_integrity(self):
        """每个岗位标准必须有完整字段"""
        from src.seeds.job_standards_seed import JOB_STANDARDS

        required_fields = {
            "job_code", "job_name", "job_level", "job_category",
            "job_objective", "responsibilities", "kpi_targets", "sort_order",
        }

        for js in JOB_STANDARDS:
            for field in required_fields:
                assert field in js, f"岗位 {js.get('job_code', '?')} 缺少字段: {field}"
            # responsibilities 不能为空
            assert len(js["responsibilities"]) > 0, f"{js['job_code']} 职责为空"
            # kpi_targets 不能为空
            assert len(js["kpi_targets"]) > 0, f"{js['job_code']} KPI目标为空"
            # job_level 必须合法
            assert js["job_level"] in ("hq", "region", "store", "kitchen", "support"), (
                f"{js['job_code']} job_level={js['job_level']} 不合法"
            )

    def test_employment_assignment_has_job_standard_id(self):
        """EmploymentAssignment 必须有 job_standard_id 字段"""
        from src.models.hr.employment_assignment import EmploymentAssignment

        table = EmploymentAssignment.__table__
        assert "job_standard_id" in table.columns, "EmploymentAssignment 缺少 job_standard_id 列"

    def test_person_model_has_profile_ext(self):
        """Person 必须有 profile_ext JSONB 字段"""
        from src.models.hr.person import Person

        table = Person.__table__
        assert "profile_ext" in table.columns, "Person 缺少 profile_ext 列"
        assert "preferences" in table.columns, "Person 缺少 preferences 列"

    def test_sop_data_structure(self):
        """SOP 数据结构完整性"""
        from src.seeds.job_standards_seed import JOB_SOPS

        valid_types = {"pre_shift", "during_service", "peak_hour", "post_shift", "handover", "emergency"}
        for sop in JOB_SOPS:
            assert sop["sop_type"] in valid_types, f"SOP类型 {sop['sop_type']} 不合法"
            assert len(sop["steps"]) > 0, f"SOP {sop['sop_name']} 步骤为空"
            for step in sop["steps"]:
                assert "step_no" in step
                assert "action" in step
                assert "standard" in step


# ═══════════════════════════════════════════════════════════════════════════════
# Golden Path 3: 成本真相引擎数据流
# ═══════════════════════════════════════════════════════════════════════════════

class TestCostTruthDataFlow:
    """验证 CostTruth 5因子归因模型的完整性"""

    def test_attribution_factors_complete(self):
        """5因子归因必须完整覆盖"""
        from src.models.cost_truth import AttributionFactor

        expected = {"price_change", "usage_overrun", "waste_loss", "yield_variance", "mix_shift"}
        actual = {f.value for f in AttributionFactor}
        assert actual == expected, f"缺少因子: {expected - actual}, 多余: {actual - expected}"

    def test_variance_severity_levels(self):
        """方差严重等级必须有4级"""
        from src.models.cost_truth import VarianceSeverity

        expected = {"ok", "watch", "warning", "critical"}
        actual = {s.value for s in VarianceSeverity}
        assert actual == expected

    def test_cost_truth_daily_stores_fen(self):
        """CostTruthDaily 金额字段必须是分(fen)"""
        from src.models.cost_truth import CostTruthDaily

        table = CostTruthDaily.__table__
        fen_columns = ["revenue_fen", "theoretical_cost_fen", "actual_cost_fen", "variance_fen"]
        for col in fen_columns:
            assert col in table.columns, f"CostTruthDaily 缺少 {col} 列"

    def test_industry_benchmark_has_percentiles(self):
        """IndustryBenchmark 必须有 4 档分位数"""
        from src.models.knowledge_rule import IndustryBenchmark

        table = IndustryBenchmark.__table__
        for col in ["p25_value", "p50_value", "p75_value", "p90_value"]:
            assert col in table.columns, f"IndustryBenchmark 缺少 {col} 列"

    def test_benchmark_seed_data_validity(self):
        """基准种子数据数值合理性验证"""
        from src.seeds.industry_benchmarks_seed import BENCHMARKS

        for row in BENCHMARKS:
            _, metric, _, p25, p50, p75, p90, _, direction, _ = row
            # p25 <= p50 <= p75 <= p90（对 lower_better 和 higher_better 都成立）
            assert p25 <= p50 <= p75 <= p90, (
                f"{metric}: p25={p25} p50={p50} p75={p75} p90={p90} 不单调递增"
            )
            # 所有值必须为正数
            assert p25 >= 0, f"{metric} p25={p25} 为负数"

    def test_benchmark_covers_all_seed_customer_cuisines(self):
        """基准数据必须覆盖所有种子客户的菜系"""
        from src.seeds.industry_benchmarks_seed import BENCHMARKS

        cuisines_in_seed = {row[0].value for row in BENCHMARKS}
        # 尝在一起=hunan, 徐记海鲜=seafood, 最黔线=guizhou
        required = {"hunan", "seafood", "guizhou"}
        missing = required - cuisines_in_seed
        assert not missing, f"基准数据缺少种子客户菜系: {missing}"

    def test_benchmark_has_food_cost_for_all_cuisines(self):
        """每个有基准数据的菜系都必须有 food_cost_ratio"""
        from src.seeds.industry_benchmarks_seed import BENCHMARKS

        cuisines = {row[0].value for row in BENCHMARKS}
        food_cost_cuisines = {row[0].value for row in BENCHMARKS if row[1] == "food_cost_ratio"}
        missing = cuisines - food_cost_cuisines
        assert not missing, f"以下菜系缺少 food_cost_ratio 基准: {missing}"


# ═══════════════════════════════════════════════════════════════════════════════
# Golden Path 4: 流失预测纯函数链路
# ═══════════════════════════════════════════════════════════════════════════════

class TestTurnoverPredictionPureFunctions:
    """验证流失预测服务的纯函数计算逻辑"""

    def test_replacement_cost_basic(self):
        """离职替换成本 = 月薪 × 50%"""
        from src.services.turnover_prediction_service import estimate_replacement_cost

        assert estimate_replacement_cost(10000.0) == 5000.0
        assert estimate_replacement_cost(0.0) == 0.0
        assert estimate_replacement_cost(-100.0) == 0.0  # 负数安全

    def test_attendance_risk_normalization(self):
        """考勤异常风险归一化：0次=0, 8次=1, 超过8次上限为1"""
        from src.services.turnover_prediction_service import normalize_attendance_risk

        assert normalize_attendance_risk(0) == 0.0
        assert normalize_attendance_risk(4) == 0.5
        assert normalize_attendance_risk(8) == 1.0
        assert normalize_attendance_risk(16) == 1.0  # 上限
        assert normalize_attendance_risk(-1) == 0.0  # 负数安全

    def test_fairness_risk_normalization(self):
        """公平性得分风险：100分=0风险, 0分=1风险"""
        from src.services.turnover_prediction_service import normalize_fairness_risk

        assert normalize_fairness_risk(100.0) == 0.0
        assert normalize_fairness_risk(0.0) == 1.0
        assert normalize_fairness_risk(50.0) == 0.5

    def test_consecutive_days_risk(self):
        """连续工作天数风险：≤6天=0, >6天线性增加"""
        from src.services.turnover_prediction_service import normalize_consecutive_days_risk

        assert normalize_consecutive_days_risk(5) == 0.0
        assert normalize_consecutive_days_risk(6) == 0.0
        assert normalize_consecutive_days_risk(10) == 0.5
        assert normalize_consecutive_days_risk(14) == 1.0
        assert normalize_consecutive_days_risk(20) == 1.0  # 上限

    def test_salary_volatility_risk(self):
        """工资波动率风险：0%=0, 30%=1"""
        from src.services.turnover_prediction_service import normalize_salary_volatility_risk

        assert normalize_salary_volatility_risk(0.0) == 0.0
        assert normalize_salary_volatility_risk(0.15) == 0.5
        assert normalize_salary_volatility_risk(0.30) == 1.0
        assert normalize_salary_volatility_risk(0.50) == 1.0  # 上限

    def test_risk_score_weights_sum_to_1(self):
        """风险权重之和必须为1.0"""
        from src.services.turnover_prediction_service import compute_turnover_risk_score

        # 通过给所有因子设为1.0来验证权重和
        all_max = {"attendance": 1.0, "fairness": 1.0, "consecutive_days": 1.0, "salary_volatility": 1.0}
        score = compute_turnover_risk_score(all_max)
        assert score == 1.0, f"全满分时风险应为1.0，实际为{score}"

        all_zero = {"attendance": 0.0, "fairness": 0.0, "consecutive_days": 0.0, "salary_volatility": 0.0}
        score = compute_turnover_risk_score(all_zero)
        assert score == 0.0

    def test_top_risk_factors_ranking(self):
        """最主要风险因子排序正确"""
        from src.services.turnover_prediction_service import top_risk_factors

        risks = {"attendance": 0.8, "fairness": 0.3, "consecutive_days": 0.9, "salary_volatility": 0.1}
        top2 = top_risk_factors(risks, top_n=2)
        assert len(top2) == 2
        assert top2[0][0] == "consecutive_days"
        assert top2[1][0] == "attendance"

    def test_risk_score_boundary_invariant(self):
        """风险分数必须在 [0, 1] 范围内"""
        from src.services.turnover_prediction_service import compute_turnover_risk_score

        # 测试各种极端组合
        test_cases = [
            {"attendance": 0.0, "fairness": 0.0, "consecutive_days": 0.0, "salary_volatility": 0.0},
            {"attendance": 1.0, "fairness": 1.0, "consecutive_days": 1.0, "salary_volatility": 1.0},
            {"attendance": 0.5, "fairness": 0.5, "consecutive_days": 0.5, "salary_volatility": 0.5},
            {"attendance": 2.0, "fairness": 2.0},  # 超界值
            {},  # 空字典
        ]
        for case in test_cases:
            score = compute_turnover_risk_score(case)
            assert 0.0 <= score <= 1.0, f"风险分 {score} 超出 [0,1]，输入: {case}"


# ═══════════════════════════════════════════════════════════════════════════════
# Golden Path 5: 排班模板匹配链路
# ═══════════════════════════════════════════════════════════════════════════════

class TestStaffingPatternLogic:
    """验证排班模板的日期类型推断和时间解析"""

    def test_day_type_inference(self):
        """日期类型推断：工作日 vs 周末"""
        from src.services.staffing_pattern_service import infer_day_type

        # 2026-03-20 是周五（工作日）
        assert infer_day_type(date(2026, 3, 20)) == "weekday"
        # 2026-03-21 是周六（周末）
        assert infer_day_type(date(2026, 3, 21)) == "weekend"
        # 2026-03-22 是周日（周末）
        assert infer_day_type(date(2026, 3, 22)) == "weekend"
        # 2026-03-23 是周一（工作日）
        assert infer_day_type(date(2026, 3, 23)) == "weekday"

    def test_hhmm_parse(self):
        """HH:MM 时间字符串解析"""
        from src.services.staffing_pattern_service import _parse_hhmm

        assert _parse_hhmm("09:00") == time(9, 0)
        assert _parse_hhmm("17:30") == time(17, 30)
        assert _parse_hhmm("00:00") == time(0, 0)
        assert _parse_hhmm("23:59") == time(23, 59)

    def test_hhmm_parse_invalid_raises(self):
        """非法时间格式应抛出异常"""
        from src.services.staffing_pattern_service import _parse_hhmm

        with pytest.raises((ValueError, IndexError)):
            _parse_hhmm("invalid")


# ═══════════════════════════════════════════════════════════════════════════════
# Golden Path 6: EmployeeRepository 合约验证
# ═══════════════════════════════════════════════════════════════════════════════

class TestEmployeeRepositoryContract:
    """验证 EmployeeRepository 返回 Person 而非 Employee 的合约"""

    def test_repository_methods_exist(self):
        """EmployeeRepository 必须提供3个标准方法"""
        from src.repositories import EmployeeRepository

        assert hasattr(EmployeeRepository, "get_by_store")
        assert hasattr(EmployeeRepository, "get_by_id")
        assert hasattr(EmployeeRepository, "get_with_assignment")

    def test_repository_get_by_id_queries_person(self):
        """get_by_id 必须查询 Person.legacy_employee_id，而非 Employee.id"""
        import inspect
        from src.repositories import EmployeeRepository

        source = inspect.getsource(EmployeeRepository.get_by_id)
        assert "Person" in source, "get_by_id 必须查询 Person 表"
        assert "legacy_employee_id" in source, "get_by_id 必须通过 legacy_employee_id 查找"


# ═══════════════════════════════════════════════════════════════════════════════
# Golden Path 7: 金额单位不变式
# ═══════════════════════════════════════════════════════════════════════════════

class TestCurrencyInvariant:
    """验证金额存储和展示的一致性"""

    def test_cost_truth_uses_fen(self):
        """CostTruthDaily 金额字段命名以 _fen 结尾"""
        from src.models.cost_truth import CostTruthDaily

        table = CostTruthDaily.__table__
        money_cols = [c.name for c in table.columns if "cost" in c.name or "revenue" in c.name or "variance" in c.name]
        # 金额列名必须以 _fen 结尾（除了百分比/文本/元字段）
        non_money_suffixes = ("pct", "rate", "dish", "yuan", "count")
        for col_name in money_cols:
            if not any(col_name.endswith(s) for s in non_money_suffixes):
                assert col_name.endswith("_fen"), (
                    f"CostTruthDaily.{col_name} 金额列未以 _fen 命名（分为单位约定）"
                )

    def test_attribution_uses_fen(self):
        """CostVarianceAttribution 贡献金额以分为单位"""
        from src.models.cost_truth import CostVarianceAttribution

        table = CostVarianceAttribution.__table__
        assert "contribution_fen" in table.columns

    def test_daily_wage_uses_fen(self):
        """EmploymentAssignment.daily_wage_standard_fen 以分为单位"""
        from src.models.hr.employment_assignment import EmploymentAssignment

        table = EmploymentAssignment.__table__
        assert "daily_wage_standard_fen" in table.columns


# ═══════════════════════════════════════════════════════════════════════════════
# Golden Path 8: 决策自动化分级 — 置信度×风险×信任阶段联动
# ═══════════════════════════════════════════════════════════════════════════════

class TestDecisionAutoExecutionTiers:
    """验证决策自动化分级的核心不变式"""

    def _make_service(self):
        from unittest.mock import MagicMock
        from src.services.human_in_the_loop_service import HumanInTheLoopService
        return HumanInTheLoopService(db=MagicMock())

    def test_critical_never_downgraded(self):
        """CRITICAL 操作无论置信度多高都不降级"""
        from src.services.human_in_the_loop_service import (
            OperationType, RiskLevel, TrustPhase,
        )
        svc = self._make_service()
        for op in [OperationType.FUND_TRANSFER, OperationType.DATA_DELETION,
                    OperationType.PERMISSION_CHANGE, OperationType.CONTRACT_SIGNING]:
            level = svc.classify_risk_level(op, {}, TrustPhase.AUTONOMOUS, confidence_score=0.99)
            assert level == RiskLevel.CRITICAL, f"{op.value} 应始终为 CRITICAL"

    def test_high_not_downgraded_by_confidence(self):
        """HIGH 操作（人事/供应商）不受高置信度降级"""
        from src.services.human_in_the_loop_service import (
            OperationType, RiskLevel, TrustPhase,
        )
        svc = self._make_service()
        level = svc.classify_risk_level(
            OperationType.STAFF_TRANSFER, {}, TrustPhase.AUTONOMOUS, confidence_score=0.99,
        )
        assert level == RiskLevel.HIGH

    def test_medium_escalated_on_low_confidence(self):
        """MEDIUM 操作 + 低置信度 → 升级为 HIGH（强制审批）"""
        from src.services.human_in_the_loop_service import (
            OperationType, RiskLevel, TrustPhase,
        )
        svc = self._make_service()
        level = svc.classify_risk_level(
            OperationType.AUTO_PURCHASE, {}, TrustPhase.ASSISTANCE, confidence_score=0.70,
        )
        assert level == RiskLevel.HIGH, "低置信度应升级为 HIGH"

    def test_medium_stays_medium_normal_confidence(self):
        """MEDIUM 操作 + 正常置信度 → 保持 MEDIUM"""
        from src.services.human_in_the_loop_service import (
            OperationType, RiskLevel, TrustPhase,
        )
        svc = self._make_service()
        level = svc.classify_risk_level(
            OperationType.AUTO_SCHEDULING, {}, TrustPhase.ASSISTANCE, confidence_score=0.90,
        )
        assert level == RiskLevel.MEDIUM

    def test_medium_downgraded_on_high_confidence_autonomous(self):
        """MEDIUM 操作 + 高置信度 + 自主期 → 降级为 LOW"""
        from src.services.human_in_the_loop_service import (
            OperationType, RiskLevel, TrustPhase,
        )
        svc = self._make_service()
        level = svc.classify_risk_level(
            OperationType.AUTO_PURCHASE, {}, TrustPhase.AUTONOMOUS, confidence_score=0.96,
        )
        assert level == RiskLevel.LOW, "自主期+高置信度应降级为 LOW"

    def test_medium_not_downgraded_in_assistance_phase(self):
        """MEDIUM 操作 + 高置信度但非自主期 → 保持 MEDIUM（不降级）"""
        from src.services.human_in_the_loop_service import (
            OperationType, RiskLevel, TrustPhase,
        )
        svc = self._make_service()
        level = svc.classify_risk_level(
            OperationType.AUTO_PURCHASE, {}, TrustPhase.ASSISTANCE, confidence_score=0.96,
        )
        assert level == RiskLevel.MEDIUM, "辅助期不应降级"

    def test_observation_phase_escalates_medium_to_high(self):
        """观察期 → MEDIUM 操作强制升级为 HIGH（原有逻辑保留）"""
        from src.services.human_in_the_loop_service import (
            OperationType, RiskLevel, TrustPhase,
        )
        svc = self._make_service()
        level = svc.classify_risk_level(
            OperationType.COUPON_DISTRIBUTION, {}, TrustPhase.OBSERVATION, confidence_score=0.99,
        )
        assert level == RiskLevel.HIGH, "观察期即使高置信度也应为 HIGH"

    def test_confidence_thresholds_configurable(self):
        """置信度阈值可通过类属性配置"""
        from src.services.human_in_the_loop_service import HumanInTheLoopService
        assert "low_confidence" in HumanInTheLoopService.CONFIDENCE_THRESHOLDS
        assert "high_confidence" in HumanInTheLoopService.CONFIDENCE_THRESHOLDS
        low = HumanInTheLoopService.CONFIDENCE_THRESHOLDS["low_confidence"]
        high = HumanInTheLoopService.CONFIDENCE_THRESHOLDS["high_confidence"]
        assert 0.0 < low < high <= 1.0, f"阈值不合理: low={low}, high={high}"


# ═══════════════════════════════════════════════════════════════════════════════
# Golden Path 9: 技能图谱前置依赖验证（PostgreSQL 替代 Neo4j）
# ═══════════════════════════════════════════════════════════════════════════════

class TestSkillGraphTraversal:
    """验证技能图谱拓扑排序和依赖验证的正确性"""

    def test_valid_skill_order(self):
        """合法学习顺序：前置技能在后续技能之前"""
        from src.services.hr.knowledge_service import HrKnowledgeService

        graph = {
            "wok_basic": [],
            "wok_advanced": ["wok_basic"],
            "fire_control": ["wok_basic"],
            "stir_fry_master": ["wok_advanced", "fire_control"],
        }
        order = ["wok_basic", "wok_advanced", "fire_control", "stir_fry_master"]
        is_valid, violations = HrKnowledgeService.validate_skill_order(graph, order)
        assert is_valid
        assert violations == []

    def test_invalid_skill_order_missing_prereq(self):
        """非法学习顺序：跳过前置技能"""
        from src.services.hr.knowledge_service import HrKnowledgeService

        graph = {
            "wok_basic": [],
            "wok_advanced": ["wok_basic"],
            "stir_fry_master": ["wok_advanced"],
        }
        # 跳过了 wok_basic 直接学 wok_advanced
        order = ["wok_advanced", "stir_fry_master"]
        is_valid, violations = HrKnowledgeService.validate_skill_order(graph, order)
        assert not is_valid
        assert len(violations) == 1
        assert "wok_basic" in violations[0]

    def test_empty_graph_always_valid(self):
        """空图：任何顺序都合法"""
        from src.services.hr.knowledge_service import HrKnowledgeService

        is_valid, violations = HrKnowledgeService.validate_skill_order({}, ["a", "b"])
        assert is_valid

    def test_no_prereqs_always_valid(self):
        """无前置技能的节点：任何顺序都合法"""
        from src.services.hr.knowledge_service import HrKnowledgeService

        graph = {"a": [], "b": [], "c": []}
        is_valid, violations = HrKnowledgeService.validate_skill_order(graph, ["c", "a", "b"])
        assert is_valid

    def test_multiple_violations_detected(self):
        """多个违规同时检测"""
        from src.services.hr.knowledge_service import HrKnowledgeService

        graph = {
            "a": [],
            "b": ["a"],
            "c": ["a", "b"],
        }
        # c 在 a 和 b 之前，两个前置都缺失
        order = ["c", "a", "b"]
        is_valid, violations = HrKnowledgeService.validate_skill_order(graph, order)
        assert not is_valid
        assert len(violations) == 2


# ═══════════════════════════════════════════════════════════════════════════════
# Golden Path 10: Worker 进程分离配置
# ═══════════════════════════════════════════════════════════════════════════════

class TestWorkerProcessSeparation:
    """验证 Celery Worker 多角色分离配置正确性"""

    def test_worker_profiles_exist(self):
        """4种 Worker 角色配置必须存在"""
        from start_celery_worker import WORKER_PROFILES

        assert "realtime" in WORKER_PROFILES
        assert "default" in WORKER_PROFILES
        assert "batch" in WORKER_PROFILES
        assert "all" in WORKER_PROFILES

    def test_realtime_only_high_priority(self):
        """realtime Worker 只监听 high_priority 队列"""
        from start_celery_worker import WORKER_PROFILES

        assert WORKER_PROFILES["realtime"]["queues"] == "high_priority"

    def test_batch_has_long_timeout(self):
        """batch Worker 的时间限制 >= 1小时"""
        from start_celery_worker import WORKER_PROFILES

        time_limit = int(WORKER_PROFILES["batch"]["time_limit"])
        assert time_limit >= 3600, f"batch 时限 {time_limit}s 太短，批处理需≥1小时"

    def test_all_profile_backward_compatible(self):
        """all 配置必须监听全部3个队列（向后兼容）"""
        from start_celery_worker import WORKER_PROFILES

        queues = WORKER_PROFILES["all"]["queues"]
        assert "high_priority" in queues
        assert "default" in queues
        assert "low_priority" in queues

    def test_each_profile_has_hostname(self):
        """每个 Worker 角色有独立 hostname（多Worker共存时区分身份）"""
        from start_celery_worker import WORKER_PROFILES

        hostnames = set()
        for name, profile in WORKER_PROFILES.items():
            assert "hostname" in profile, f"{name} 缺少 hostname"
            hostnames.add(profile["hostname"])
        assert len(hostnames) == len(WORKER_PROFILES), "hostname 不唯一"


# ═══════════════════════════════════════════════════════════════════════════════
# Golden Path 11: HR三层模型关系完整性
# ═══════════════════════════════════════════════════════════════════════════════

class TestHRThreeLayerRelationships:
    """验证 Person ↔ EmploymentAssignment ↔ EmploymentContract 的 ORM 关系"""

    def test_person_has_assignments_relationship(self):
        """Person 必须有 .assignments 关系"""
        from src.models.hr.person import Person
        assert hasattr(Person, "assignments"), "Person 缺少 assignments relationship"

    def test_assignment_has_person_relationship(self):
        """EmploymentAssignment 必须有 .person 关系"""
        from src.models.hr.employment_assignment import EmploymentAssignment
        assert hasattr(EmploymentAssignment, "person"), "EA 缺少 person relationship"

    def test_assignment_has_contracts_relationship(self):
        """EmploymentAssignment 必须有 .contracts 关系"""
        from src.models.hr.employment_assignment import EmploymentAssignment
        assert hasattr(EmploymentAssignment, "contracts"), "EA 缺少 contracts relationship"

    def test_contract_has_assignment_relationship(self):
        """EmploymentContract 必须有 .assignment 关系"""
        from src.models.hr.employment_contract import EmploymentContract
        assert hasattr(EmploymentContract, "assignment"), "Contract 缺少 assignment relationship"

    def test_hr_performance_uses_person_not_employee(self):
        """hr_performance.py 合同查询必须通过 Person 而非 Employee"""
        import inspect
        from src.api import hr_performance

        source = inspect.getsource(hr_performance)
        # 不应有 Employee.name 或 Employee.id 引用
        assert "Employee.name" not in source, "hr_performance 仍引用 Employee.name"
        assert "Employee.id)" not in source, "hr_performance 仍引用 Employee.id"
        # 应通过 Person.legacy_employee_id 桥接
        assert "Person.legacy_employee_id" in source, "hr_performance 应使用 Person.legacy_employee_id"

    def test_hr_dashboard_uses_person_not_employee(self):
        """hr_dashboard.py 流失率查询必须通过 Person 而非 Employee"""
        import inspect
        from src.api import hr_dashboard

        source = inspect.getsource(hr_dashboard)
        assert "Employee.id)" not in source, "hr_dashboard 仍引用 Employee.id"
        assert "Employee.store_id" not in source, "hr_dashboard 仍引用 Employee.store_id"
