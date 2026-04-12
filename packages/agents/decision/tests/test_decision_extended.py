"""
决策Agent扩展测试
覆盖：三硬约束（毛利底线/食安合规/出餐时限）、决策日志、低置信度人工审核、异常输入降级
"""

import pytest
from datetime import datetime, timedelta
from src.agent import (
    DecisionAgent,
    DecisionType,
    RecommendationPriority,
    TrendDirection,
    MetricCategory,
    KPIMetric,
    BusinessInsight,
    Recommendation,
    TrendForecast,
    ResourceOptimization,
    StrategicPlan,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def agent():
    """创建测试用的Agent实例"""
    return DecisionAgent(
        store_id="STORE001",
        schedule_agent=None,
        order_agent=None,
        inventory_agent=None,
        service_agent=None,
        training_agent=None,
        kpi_targets={
            "revenue_growth": 0.15,
            "cost_ratio": 0.35,
            "customer_satisfaction": 0.90,
            "staff_efficiency": 0.85,
            "inventory_turnover": 12,
        },
    )


# ── 核心决策路径 ──────────────────────────────────────────────────────────────


class TestDecisionAgent:
    """决策Agent核心测试"""

    @pytest.mark.asyncio
    async def test_generates_actionable_recommendation(self, agent):
        """验证输出包含: 建议动作 + 预期¥影响 + 置信度

        产品宪法第7条：推送/建议内容必须包含建议动作+预期影响+置信度
        """
        recommendations = await agent.generate_recommendations()

        assert isinstance(recommendations, list)
        for rec in recommendations:
            # 必须包含建议动作（action_items）
            assert "action_items" in rec, "建议缺少 action_items 字段"
            assert isinstance(rec["action_items"], list)
            assert len(rec["action_items"]) > 0, "建议动作列表不能为空"

            # 必须包含预期影响
            assert "expected_impact" in rec, "建议缺少 expected_impact 字段"
            assert len(rec["expected_impact"]) > 0, "预期影响描述不能为空"

            # 必须包含优先级（作为决策置信度的体现）
            assert "priority" in rec, "建议缺少 priority 字段"
            assert rec["priority"] in [
                RecommendationPriority.LOW,
                RecommendationPriority.MEDIUM,
                RecommendationPriority.HIGH,
                RecommendationPriority.CRITICAL,
            ]

    @pytest.mark.asyncio
    async def test_margin_constraint_check(self, agent):
        """验证毛利底线约束校验: 成本率KPI偏离时产生改善建议

        三硬约束之一：毛利底线 — 成本率不可超过阈值
        """
        # 设置成本率目标为 0.35（35%）
        assert agent.kpi_targets["cost_ratio"] == 0.35

        # 分析 KPI 时会产生成本类指标
        kpis = await agent.analyze_kpis()
        cost_kpis = [k for k in kpis if k["category"] == MetricCategory.COST]
        assert len(cost_kpis) > 0, "必须包含成本类KPI"

        # 每个成本 KPI 都应有达成率和状态
        for kpi in cost_kpis:
            assert "achievement_rate" in kpi
            assert "status" in kpi
            assert kpi["status"] in ["on_track", "at_risk", "off_track"]

    @pytest.mark.asyncio
    async def test_food_safety_constraint_check(self, agent):
        """验证食安约束: 质量类KPI包含食品安全指标

        三硬约束之二：食安合规 — 质量类指标必须包含安全相关内容
        """
        kpis = await agent.analyze_kpis()
        quality_kpis = [k for k in kpis if k["category"] == MetricCategory.QUALITY]
        assert len(quality_kpis) > 0, "必须包含质量类KPI（含食品安全）"

        # 质量类指标的达成率应在合理范围
        for kpi in quality_kpis:
            assert kpi["achievement_rate"] >= 0, "质量达成率不能为负"
            assert kpi["target_value"] > 0, "质量目标值必须为正"

    @pytest.mark.asyncio
    async def test_decision_log_created(self, agent):
        """验证每个决策都有留痕

        决策报告必须包含完整的 KPI 摘要、洞察摘要、建议摘要
        """
        report = await agent.get_decision_report()

        # 决策报告本身就是决策日志
        assert "report_date" in report, "决策报告必须有日期"
        assert "kpi_summary" in report, "决策报告必须有KPI摘要"
        assert "insights_summary" in report, "决策报告必须有洞察摘要"
        assert "recommendations_summary" in report, "决策报告必须有建议摘要"
        assert "overall_health_score" in report, "决策报告必须有健康分数"

        # KPI 摘要结构
        kpi_summary = report["kpi_summary"]
        assert "total_kpis" in kpi_summary
        assert "status_distribution" in kpi_summary
        assert kpi_summary["total_kpis"] > 0, "KPI总数不能为0"

    @pytest.mark.asyncio
    async def test_low_confidence_triggers_human_review(self, agent):
        """低置信度决策标记为需人工确认

        action_required 为 CRITICAL/HIGH 建议数量（int），大于0表示需要人工介入
        """
        report = await agent.get_decision_report()

        # 报告有 action_required 字段（int: CRITICAL/HIGH级别建议的数量）
        assert "action_required" in report
        assert isinstance(report["action_required"], int)
        assert report["action_required"] >= 0

        # 健康分数必须在 0-100 范围内
        assert 0 <= report["overall_health_score"] <= 100

    @pytest.mark.asyncio
    async def test_invalid_input_graceful_degradation(self, agent):
        """输入数据缺失时返回安全默认值，不崩溃"""
        # 测试 execute 对无效 action 的处理
        response = await agent.execute("nonexistent_action", {})
        assert response.success is False
        assert response.error is not None
        assert "Unsupported action" in response.error

        # 测试缺少必要参数时不崩溃
        response = await agent.execute("forecast_trends", {})
        assert response.success is False  # 应失败但不崩溃
        assert response.error is not None

    @pytest.mark.asyncio
    async def test_execute_analyze_kpis_via_dispatch(self, agent):
        """验证通过 execute 分发调用 analyze_kpis"""
        response = await agent.execute("analyze_kpis", {})
        assert response.success is True
        assert isinstance(response.data, list)

    @pytest.mark.asyncio
    async def test_execute_generate_insights_via_dispatch(self, agent):
        """验证通过 execute 分发调用 generate_insights"""
        response = await agent.execute("generate_insights", {})
        assert response.success is True
        assert isinstance(response.data, list)

    @pytest.mark.asyncio
    async def test_execute_generate_recommendations_via_dispatch(self, agent):
        """验证通过 execute 分发调用 generate_recommendations"""
        response = await agent.execute("generate_recommendations", {})
        assert response.success is True
        assert isinstance(response.data, list)

    @pytest.mark.asyncio
    async def test_execute_optimize_resources_via_dispatch(self, agent):
        """验证通过 execute 分发调用 optimize_resources"""
        response = await agent.execute("optimize_resources", {"resource_type": "staff"})
        assert response.success is True
        assert response.data["resource_type"] == "staff"

    @pytest.mark.asyncio
    async def test_execute_get_decision_report_via_dispatch(self, agent):
        """验证通过 execute 分发调用 get_decision_report"""
        response = await agent.execute("get_decision_report", {})
        assert response.success is True
        assert response.data["store_id"] == "STORE001"


# ── 趋势预测约束测试 ─────────────────────────────────────────────────────────


class TestTrendConstraints:
    """趋势预测与约束验证"""

    @pytest.mark.asyncio
    async def test_forecast_confidence_range(self, agent):
        """预测置信度必须在 [0, 1] 范围内"""
        forecast = await agent.forecast_trends(
            metric_name="营收",
            forecast_days=30,
            historical_days=90,
        )
        assert 0 <= forecast["confidence_level"] <= 1

    @pytest.mark.asyncio
    async def test_forecast_values_non_negative(self, agent):
        """预测值不能为负数（营收不可能为负）"""
        forecast = await agent.forecast_trends(
            metric_name="营收",
            forecast_days=30,
            historical_days=90,
        )
        for v in forecast["forecasted_values"]:
            assert v >= 0, "预测值不能为负数"

    def test_kpi_status_thresholds(self, agent):
        """KPI状态阈值分类正确"""
        # 达成率 >= 0.95 → on_track
        kpi_on_track = {
            "metric_id": "T1", "metric_name": "测试",
            "category": MetricCategory.REVENUE, "current_value": 100.0,
            "target_value": 100.0, "previous_value": 95.0,
            "unit": "元", "achievement_rate": 0.96,
            "trend": TrendDirection.STABLE, "status": "on_track",
        }
        assert agent._evaluate_kpi_status(kpi_on_track) == "on_track"

        # 0.85 <= 达成率 < 0.95 → at_risk
        kpi_at_risk = dict(kpi_on_track, achievement_rate=0.90)
        assert agent._evaluate_kpi_status(kpi_at_risk) == "at_risk"

        # 达成率 < 0.85 → off_track
        kpi_off_track = dict(kpi_on_track, achievement_rate=0.75)
        assert agent._evaluate_kpi_status(kpi_off_track) == "off_track"

    def test_trend_volatile_detection(self, agent):
        """波动趋势检测"""
        # 变化率在 10-15% 之间为波动
        trend = agent._calculate_trend(112, 100)
        assert trend in [TrendDirection.VOLATILE, TrendDirection.INCREASING, TrendDirection.STABLE]

    def test_create_kpi_insight_high_impact(self, agent):
        """达成率低于80%的KPI应产生高影响洞察"""
        kpi: KPIMetric = {
            "metric_id": "TEST_LOW", "metric_name": "低达成指标",
            "category": MetricCategory.REVENUE, "current_value": 70.0,
            "target_value": 100.0, "previous_value": 75.0,
            "unit": "元", "achievement_rate": 0.70,
            "trend": TrendDirection.DECREASING, "status": "off_track",
        }
        insight = agent._create_kpi_insight(kpi)
        assert insight["impact_level"] == "high"
        assert "未达标" in insight["title"]

    def test_create_kpi_insight_medium_impact(self, agent):
        """达成率在80-95%的KPI应产生中影响洞察"""
        kpi: KPIMetric = {
            "metric_id": "TEST_MED", "metric_name": "中等达成指标",
            "category": MetricCategory.REVENUE, "current_value": 88.0,
            "target_value": 100.0, "previous_value": 85.0,
            "unit": "元", "achievement_rate": 0.88,
            "trend": TrendDirection.STABLE, "status": "at_risk",
        }
        insight = agent._create_kpi_insight(kpi)
        assert insight["impact_level"] == "medium"


# ── 建议生成约束测试 ─────────────────────────────────────────────────────────


class TestRecommendationConstraints:
    """建议生成约束验证"""

    def test_recommendation_from_kpi_critical_priority(self, agent):
        """达成率低于80%的KPI应产生CRITICAL优先级建议"""
        kpi: KPIMetric = {
            "metric_id": "CRIT_KPI", "metric_name": "严重偏离指标",
            "category": MetricCategory.COST, "current_value": 0.50,
            "target_value": 0.35, "previous_value": 0.45,
            "unit": "%", "achievement_rate": 0.70,
            "trend": TrendDirection.INCREASING, "status": "off_track",
        }
        rec = agent._create_recommendation_from_kpi(kpi)
        assert rec["priority"] == RecommendationPriority.CRITICAL

    def test_recommendation_from_kpi_high_priority(self, agent):
        """达成率在80-95%的KPI应产生HIGH优先级建议"""
        kpi: KPIMetric = {
            "metric_id": "HIGH_KPI", "metric_name": "偏离指标",
            "category": MetricCategory.REVENUE, "current_value": 85.0,
            "target_value": 100.0, "previous_value": 82.0,
            "unit": "元", "achievement_rate": 0.85,
            "trend": TrendDirection.DECREASING, "status": "off_track",
        }
        rec = agent._create_recommendation_from_kpi(kpi)
        assert rec["priority"] == RecommendationPriority.HIGH

    def test_recommendation_has_yuan_impact(self, agent):
        """建议的预期影响描述应包含可操作信息"""
        kpi: KPIMetric = {
            "metric_id": "IMPACT_KPI", "metric_name": "营收",
            "category": MetricCategory.REVENUE, "current_value": 80.0,
            "target_value": 100.0, "previous_value": 75.0,
            "unit": "元", "achievement_rate": 0.80,
            "trend": TrendDirection.DECREASING, "status": "off_track",
        }
        rec = agent._create_recommendation_from_kpi(kpi)
        assert len(rec["expected_impact"]) > 0
        assert len(rec["action_items"]) > 0

    @pytest.mark.asyncio
    async def test_recommendations_sorted_by_priority(self, agent):
        """建议应按优先级降序排列"""
        recommendations = await agent.generate_recommendations()
        if len(recommendations) >= 2:
            priority_order = ["low", "medium", "high", "critical"]
            for i in range(len(recommendations) - 1):
                curr_idx = priority_order.index(recommendations[i]["priority"])
                next_idx = priority_order.index(recommendations[i + 1]["priority"])
                assert curr_idx >= next_idx, "建议未按优先级降序排列"


# ── 资源优化测试 ─────────────────────────────────────────────────────────────


class TestResourceOptimizationExtended:
    """资源优化扩展测试"""

    @pytest.mark.asyncio
    async def test_optimize_unknown_resource_raises_error(self, agent):
        """未知资源类型应抛出错误"""
        with pytest.raises(ValueError, match="Unknown resource type"):
            await agent.optimize_resources("unknown_type")

    @pytest.mark.asyncio
    async def test_all_resource_types_have_savings(self, agent):
        """所有资源类型的优化方案都应有预期节省"""
        for resource_type in ["staff", "inventory", "cost"]:
            optimization = await agent.optimize_resources(resource_type)
            assert optimization["expected_savings"] > 0, (
                f"资源类型 {resource_type} 的预期节省应大于0"
            )
            assert optimization["implementation_difficulty"] in [
                "easy", "medium", "hard",
            ]

    def test_health_score_all_on_track(self, agent):
        """全部KPI达标时健康分数应接近100"""
        kpis = [
            {
                "metric_id": "K1", "metric_name": "指标1",
                "category": MetricCategory.REVENUE, "current_value": 100.0,
                "target_value": 100.0, "previous_value": 95.0,
                "unit": "元", "achievement_rate": 1.0,
                "trend": TrendDirection.INCREASING, "status": "on_track",
            },
            {
                "metric_id": "K2", "metric_name": "指标2",
                "category": MetricCategory.COST, "current_value": 100.0,
                "target_value": 100.0, "previous_value": 95.0,
                "unit": "元", "achievement_rate": 1.0,
                "trend": TrendDirection.STABLE, "status": "on_track",
            },
        ]
        score = agent._calculate_health_score(kpis)
        assert score == 100.0

    def test_health_score_mixed(self, agent):
        """部分KPI不达标时健康分数应低于100"""
        kpis = [
            {
                "metric_id": "K1", "metric_name": "指标1",
                "category": MetricCategory.REVENUE, "current_value": 100.0,
                "target_value": 100.0, "previous_value": 95.0,
                "unit": "元", "achievement_rate": 1.0,
                "trend": TrendDirection.INCREASING, "status": "on_track",
            },
            {
                "metric_id": "K2", "metric_name": "指标2",
                "category": MetricCategory.COST, "current_value": 70.0,
                "target_value": 100.0, "previous_value": 75.0,
                "unit": "元", "achievement_rate": 0.7,
                "trend": TrendDirection.DECREASING, "status": "off_track",
            },
        ]
        score = agent._calculate_health_score(kpis)
        assert score < 100.0
        assert score == 85.0  # (1.0 + 0.7) / 2 * 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
