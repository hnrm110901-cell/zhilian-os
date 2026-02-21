"""
智能决策Agent单元测试
Unit tests for Intelligent Decision Agent
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
    StrategicPlan
)


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
        }
    )


@pytest.mark.asyncio
async def test_analyze_kpis(agent):
    """测试分析KPI指标"""
    kpis = await agent.analyze_kpis()

    assert isinstance(kpis, list)
    assert len(kpis) > 0

    for kpi in kpis:
        assert "metric_id" in kpi
        assert "metric_name" in kpi
        assert "category" in kpi
        assert "current_value" in kpi
        assert "target_value" in kpi
        assert "achievement_rate" in kpi
        assert "trend" in kpi
        assert "status" in kpi
        assert kpi["status"] in ["on_track", "at_risk", "off_track"]


@pytest.mark.asyncio
async def test_analyze_kpis_by_date_range(agent):
    """测试按日期范围分析KPI"""
    start_date = (datetime.now() - timedelta(days=30)).isoformat()
    end_date = datetime.now().isoformat()

    kpis = await agent.analyze_kpis(start_date=start_date, end_date=end_date)

    assert isinstance(kpis, list)


def test_calculate_trend_increasing(agent):
    """测试上升趋势计算"""
    trend = agent._calculate_trend(120, 100)
    assert trend == TrendDirection.INCREASING


def test_calculate_trend_decreasing(agent):
    """测试下降趋势计算"""
    trend = agent._calculate_trend(80, 100)
    assert trend == TrendDirection.DECREASING


def test_calculate_trend_stable(agent):
    """测试稳定趋势计算"""
    trend = agent._calculate_trend(102, 100)
    assert trend == TrendDirection.STABLE


def test_calculate_trend_inverse(agent):
    """测试反向趋势计算(成本类)"""
    # 成本下降是好的
    trend = agent._calculate_trend(80, 100, inverse=True)
    assert trend in [TrendDirection.INCREASING, TrendDirection.STABLE]


def test_evaluate_kpi_status_on_track(agent):
    """测试KPI正常状态评估"""
    kpi: KPIMetric = {
        "metric_id": "TEST001",
        "metric_name": "测试指标",
        "category": MetricCategory.REVENUE,
        "current_value": 100.0,
        "target_value": 100.0,
        "previous_value": 95.0,
        "unit": "元",
        "achievement_rate": 1.0,
        "trend": TrendDirection.INCREASING,
        "status": "on_track"
    }

    status = agent._evaluate_kpi_status(kpi)
    assert status == "on_track"


def test_evaluate_kpi_status_at_risk(agent):
    """测试KPI风险状态评估"""
    kpi: KPIMetric = {
        "metric_id": "TEST002",
        "metric_name": "测试指标",
        "category": MetricCategory.REVENUE,
        "current_value": 88.0,
        "target_value": 100.0,
        "previous_value": 85.0,
        "unit": "元",
        "achievement_rate": 0.88,
        "trend": TrendDirection.STABLE,
        "status": "at_risk"
    }

    status = agent._evaluate_kpi_status(kpi)
    assert status == "at_risk"


def test_evaluate_kpi_status_off_track(agent):
    """测试KPI偏离状态评估"""
    kpi: KPIMetric = {
        "metric_id": "TEST003",
        "metric_name": "测试指标",
        "category": MetricCategory.REVENUE,
        "current_value": 70.0,
        "target_value": 100.0,
        "previous_value": 75.0,
        "unit": "元",
        "achievement_rate": 0.70,
        "trend": TrendDirection.DECREASING,
        "status": "off_track"
    }

    status = agent._evaluate_kpi_status(kpi)
    assert status == "off_track"


@pytest.mark.asyncio
async def test_generate_insights(agent):
    """测试生成业务洞察"""
    insights = await agent.generate_insights()

    assert isinstance(insights, list)
    if len(insights) > 0:
        insight = insights[0]
        assert "insight_id" in insight
        assert "title" in insight
        assert "description" in insight
        assert "category" in insight
        assert "impact_level" in insight
        assert insight["impact_level"] in ["low", "medium", "high"]
        assert "data_points" in insight


@pytest.mark.asyncio
async def test_generate_insights_by_date_range(agent):
    """测试按日期范围生成洞察"""
    start_date = (datetime.now() - timedelta(days=30)).isoformat()
    end_date = datetime.now().isoformat()

    insights = await agent.generate_insights(start_date=start_date, end_date=end_date)

    assert isinstance(insights, list)


@pytest.mark.asyncio
async def test_generate_recommendations(agent):
    """测试生成业务建议"""
    recommendations = await agent.generate_recommendations()

    assert isinstance(recommendations, list)
    if len(recommendations) > 0:
        rec = recommendations[0]
        assert "recommendation_id" in rec
        assert "title" in rec
        assert "description" in rec
        assert "decision_type" in rec
        assert "priority" in rec
        assert "rationale" in rec
        assert "expected_impact" in rec
        assert "action_items" in rec


@pytest.mark.asyncio
async def test_generate_recommendations_by_type(agent):
    """测试按类型生成建议"""
    recommendations = await agent.generate_recommendations(
        decision_type=DecisionType.OPERATIONAL
    )

    assert isinstance(recommendations, list)
    if len(recommendations) > 0:
        assert all(r["decision_type"] == DecisionType.OPERATIONAL for r in recommendations)


@pytest.mark.asyncio
async def test_forecast_trends(agent):
    """测试趋势预测"""
    forecast = await agent.forecast_trends(
        metric_name="营收",
        forecast_days=30,
        historical_days=90
    )

    assert forecast["metric_name"] == "营收"
    assert "current_value" in forecast
    assert "forecasted_values" in forecast
    assert len(forecast["forecasted_values"]) == 30
    assert "confidence_level" in forecast
    assert 0 <= forecast["confidence_level"] <= 1
    assert "trend_direction" in forecast


def test_simple_forecast(agent):
    """测试简单预测算法"""
    historical_data = [100, 105, 110, 115, 120]
    forecasted = agent._simple_forecast(historical_data, 5)

    assert len(forecasted) == 5
    assert all(v >= 0 for v in forecasted)


def test_simple_forecast_empty_data(agent):
    """测试空数据预测"""
    forecasted = agent._simple_forecast([], 5)

    assert len(forecasted) == 5
    assert all(v == 0 for v in forecasted)


def test_calculate_forecast_confidence(agent):
    """测试预测置信度计算"""
    # 稳定数据
    stable_data = [100, 102, 101, 103, 100]
    confidence = agent._calculate_forecast_confidence(stable_data)
    assert confidence > 0.8

    # 波动数据
    volatile_data = [100, 150, 80, 120, 90]
    confidence = agent._calculate_forecast_confidence(volatile_data)
    assert confidence < 0.8


@pytest.mark.asyncio
async def test_optimize_resources_staff(agent):
    """测试优化人员配置"""
    optimization = await agent.optimize_resources("staff")

    assert optimization["resource_type"] == "staff"
    assert "current_allocation" in optimization
    assert "recommended_allocation" in optimization
    assert "expected_savings" in optimization
    assert "expected_improvement" in optimization
    assert "implementation_difficulty" in optimization


@pytest.mark.asyncio
async def test_optimize_resources_inventory(agent):
    """测试优化库存配置"""
    optimization = await agent.optimize_resources("inventory")

    assert optimization["resource_type"] == "inventory"
    assert optimization["expected_savings"] > 0


@pytest.mark.asyncio
async def test_optimize_resources_cost(agent):
    """测试优化成本配置"""
    optimization = await agent.optimize_resources("cost")

    assert optimization["resource_type"] == "cost"
    assert optimization["expected_savings"] > 0


@pytest.mark.asyncio
async def test_create_strategic_plan(agent):
    """测试创建战略规划"""
    plan = await agent.create_strategic_plan(time_horizon="1年")

    assert "plan_id" in plan
    assert "title" in plan
    assert "objectives" in plan
    assert len(plan["objectives"]) > 0
    assert "time_horizon" in plan
    assert plan["time_horizon"] == "1年"
    assert "key_initiatives" in plan
    assert "success_metrics" in plan
    assert "risks" in plan


@pytest.mark.asyncio
async def test_get_decision_report(agent):
    """测试获取决策综合报告"""
    report = await agent.get_decision_report()

    assert report["store_id"] == "STORE001"
    assert "report_date" in report
    assert "kpi_summary" in report
    assert "insights_summary" in report
    assert "recommendations_summary" in report
    assert "overall_health_score" in report
    assert 0 <= report["overall_health_score"] <= 100
    assert "action_required" in report

    # 检查KPI摘要
    kpi_summary = report["kpi_summary"]
    assert "total_kpis" in kpi_summary
    assert "status_distribution" in kpi_summary
    assert "on_track_rate" in kpi_summary

    # 检查洞察摘要
    insights_summary = report["insights_summary"]
    assert "total_insights" in insights_summary
    assert "high_impact" in insights_summary

    # 检查建议摘要
    rec_summary = report["recommendations_summary"]
    assert "total_recommendations" in rec_summary
    assert "priority_distribution" in rec_summary


def test_calculate_health_score(agent):
    """测试健康分数计算"""
    kpis = [
        {
            "metric_id": "KPI001",
            "metric_name": "指标1",
            "category": MetricCategory.REVENUE,
            "current_value": 100.0,
            "target_value": 100.0,
            "previous_value": 95.0,
            "unit": "元",
            "achievement_rate": 1.0,
            "trend": TrendDirection.INCREASING,
            "status": "on_track"
        },
        {
            "metric_id": "KPI002",
            "metric_name": "指标2",
            "category": MetricCategory.COST,
            "current_value": 90.0,
            "target_value": 100.0,
            "previous_value": 85.0,
            "unit": "元",
            "achievement_rate": 0.9,
            "trend": TrendDirection.STABLE,
            "status": "on_track"
        }
    ]

    health_score = agent._calculate_health_score(kpis)
    assert 0 <= health_score <= 100
    assert health_score == 95.0  # (1.0 + 0.9) / 2 * 100


def test_calculate_health_score_empty(agent):
    """测试空KPI列表的健康分数"""
    health_score = agent._calculate_health_score([])
    assert health_score == 0.0


@pytest.mark.asyncio
async def test_concurrent_operations(agent):
    """测试并发操作"""
    import asyncio

    # 同时执行多个操作
    tasks = [
        agent.analyze_kpis(),
        agent.generate_insights(),
        agent.generate_recommendations()
    ]

    results = await asyncio.gather(*tasks)

    assert len(results) == 3
    assert isinstance(results[0], list)  # kpis
    assert isinstance(results[1], list)  # insights
    assert isinstance(results[2], list)  # recommendations


@pytest.mark.asyncio
async def test_collect_revenue_data(agent):
    """测试收集营收数据"""
    data = await agent._collect_revenue_data(None, None)

    assert "total_revenue" in data
    assert "previous_revenue" in data
    assert "target_revenue" in data
    assert "days" in data
    assert data["total_revenue"] > 0


@pytest.mark.asyncio
async def test_get_historical_data(agent):
    """测试获取历史数据"""
    data = await agent._get_historical_data("营收", 30)

    assert len(data) == 30
    assert all(v >= 0 for v in data)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
