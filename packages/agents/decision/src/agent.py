"""
智能决策Agent - Intelligent Decision Agent

核心功能 Core Features:
1. 数据分析洞察 - Data analysis and insights
2. 绩效指标分析 - KPI analysis
3. 业务建议生成 - Business recommendations
4. 趋势预测 - Trend forecasting
5. 资源优化建议 - Resource optimization
6. 战略规划支持 - Strategic planning support
7. 多维度决策支持 - Multi-dimensional decision support
"""

import asyncio
import structlog
from datetime import datetime, timedelta
from enum import Enum
from typing import TypedDict, List, Optional, Dict, Any
from statistics import mean, stdev
from collections import defaultdict
import sys
from pathlib import Path

# Add core module to path
core_path = Path(__file__).parent.parent.parent.parent.parent / "src" / "core"
sys.path.insert(0, str(core_path))

from base_agent import BaseAgent, AgentResponse

logger = structlog.get_logger()


class DecisionType(str, Enum):
    """决策类型 Decision Type"""
    OPERATIONAL = "operational"  # 运营决策
    TACTICAL = "tactical"  # 战术决策
    STRATEGIC = "strategic"  # 战略决策


class RecommendationPriority(str, Enum):
    """建议优先级 Recommendation Priority"""
    LOW = "low"  # 低
    MEDIUM = "medium"  # 中
    HIGH = "high"  # 高
    CRITICAL = "critical"  # 关键


class TrendDirection(str, Enum):
    """趋势方向 Trend Direction"""
    INCREASING = "increasing"  # 上升
    DECREASING = "decreasing"  # 下降
    STABLE = "stable"  # 稳定
    VOLATILE = "volatile"  # 波动


class MetricCategory(str, Enum):
    """指标分类 Metric Category"""
    REVENUE = "revenue"  # 营收
    COST = "cost"  # 成本
    EFFICIENCY = "efficiency"  # 效率
    QUALITY = "quality"  # 质量
    CUSTOMER = "customer"  # 客户


class KPIMetric(TypedDict):
    """KPI指标 KPI Metric"""
    metric_id: str  # 指标ID
    metric_name: str  # 指标名称
    category: MetricCategory  # 分类
    current_value: float  # 当前值
    target_value: float  # 目标值
    previous_value: float  # 上期值
    unit: str  # 单位
    achievement_rate: float  # 达成率
    trend: TrendDirection  # 趋势
    status: str  # 状态(on_track/at_risk/off_track)


class BusinessInsight(TypedDict):
    """业务洞察 Business Insight"""
    insight_id: str  # 洞察ID
    title: str  # 标题
    description: str  # 描述
    category: str  # 分类
    impact_level: str  # 影响程度(low/medium/high)
    data_points: List[Dict[str, Any]]  # 数据点
    discovered_at: str  # 发现时间


class Recommendation(TypedDict):
    """业务建议 Business Recommendation"""
    recommendation_id: str  # 建议ID
    title: str  # 标题
    description: str  # 描述
    decision_type: DecisionType  # 决策类型
    priority: RecommendationPriority  # 优先级
    rationale: str  # 理由
    expected_impact: str  # 预期影响
    action_items: List[str]  # 行动项
    estimated_cost: Optional[int]  # 预估成本(分)
    estimated_roi: Optional[float]  # 预估ROI
    created_at: str  # 创建时间


class TrendForecast(TypedDict):
    """趋势预测 Trend Forecast"""
    forecast_id: str  # 预测ID
    metric_name: str  # 指标名称
    current_value: float  # 当前值
    forecasted_values: List[float]  # 预测值列表
    forecast_period: str  # 预测周期
    confidence_level: float  # 置信度
    trend_direction: TrendDirection  # 趋势方向
    forecasted_at: str  # 预测时间


class ResourceOptimization(TypedDict):
    """资源优化 Resource Optimization"""
    optimization_id: str  # 优化ID
    resource_type: str  # 资源类型(staff/inventory/cost)
    current_allocation: Dict[str, Any]  # 当前配置
    recommended_allocation: Dict[str, Any]  # 建议配置
    expected_savings: int  # 预期节省(分)
    expected_improvement: str  # 预期改进
    implementation_difficulty: str  # 实施难度(easy/medium/hard)
    created_at: str  # 创建时间


class StrategicPlan(TypedDict):
    """战略规划 Strategic Plan"""
    plan_id: str  # 规划ID
    title: str  # 标题
    objectives: List[str]  # 目标
    time_horizon: str  # 时间跨度
    key_initiatives: List[str]  # 关键举措
    success_metrics: List[str]  # 成功指标
    risks: List[str]  # 风险
    created_at: str  # 创建时间


class DecisionAgent(BaseAgent):
    """
    智能决策Agent

    工作流程 Workflow:
    1. analyze_kpis() - 分析KPI指标
    2. generate_insights() - 生成业务洞察
    3. generate_recommendations() - 生成业务建议
    4. forecast_trends() - 预测趋势
    5. optimize_resources() - 优化资源配置
    6. create_strategic_plan() - 创建战略规划
    """

    def __init__(
        self,
        store_id: str,
        schedule_agent: Optional[Any] = None,
        order_agent: Optional[Any] = None,
        inventory_agent: Optional[Any] = None,
        service_agent: Optional[Any] = None,
        training_agent: Optional[Any] = None,
        kpi_targets: Optional[Dict[str, float]] = None
    ):
        """
        初始化决策Agent

        Args:
            store_id: 门店ID
            schedule_agent: 排班Agent
            order_agent: 订单Agent
            inventory_agent: 库存Agent
            service_agent: 服务Agent
            training_agent: 培训Agent
            kpi_targets: KPI目标值
        """
        super().__init__()
        self.store_id = store_id
        self.schedule_agent = schedule_agent
        self.order_agent = order_agent
        self.inventory_agent = inventory_agent
        self.service_agent = service_agent
        self.training_agent = training_agent
        self.kpi_targets = kpi_targets or {
            "revenue_growth": 0.15,  # 营收增长15%
            "cost_ratio": 0.35,  # 成本率35%
            "customer_satisfaction": 0.90,  # 客户满意度90%
            "staff_efficiency": 0.85,  # 员工效率85%
            "inventory_turnover": 12,  # 库存周转率12次/年
        }
        self.logger = logger.bind(agent="decision", store_id=store_id)

    def get_supported_actions(self) -> List[str]:
        """获取支持的操作列表"""
        return [
            "analyze_kpis", "generate_insights", "generate_recommendations",
            "forecast_trends", "optimize_resources", "create_strategic_plan",
            "get_decision_report"
        ]

    async def execute(self, action: str, params: Dict[str, Any]) -> AgentResponse:
        """
        执行Agent操作

        Args:
            action: 操作名称
            params: 操作参数

        Returns:
            AgentResponse: 统一的响应格式
        """
        try:
            if action == "analyze_kpis":
                result = await self.analyze_kpis(
                    start_date=params.get("start_date"),
                    end_date=params.get("end_date")
                )
                return AgentResponse(success=True, data=result)
            elif action == "generate_insights":
                result = await self.generate_insights(
                    start_date=params.get("start_date"),
                    end_date=params.get("end_date")
                )
                return AgentResponse(success=True, data=result)
            elif action == "generate_recommendations":
                result = await self.generate_recommendations(
                    decision_type=params.get("decision_type"),
                    start_date=params.get("start_date"),
                    end_date=params.get("end_date")
                )
                return AgentResponse(success=True, data=result)
            elif action == "forecast_trends":
                result = await self.forecast_trends(
                    metric_name=params["metric_name"],
                    forecast_days=params.get("forecast_days", 30),
                    historical_days=params.get("historical_days", 90)
                )
                return AgentResponse(success=True, data=result)
            elif action == "optimize_resources":
                result = await self.optimize_resources(
                    resource_type=params["resource_type"]
                )
                return AgentResponse(success=True, data=result)
            elif action == "create_strategic_plan":
                result = await self.create_strategic_plan(
                    time_horizon=params.get("time_horizon", "1年")
                )
                return AgentResponse(success=True, data=result)
            elif action == "get_decision_report":
                result = await self.get_decision_report(
                    start_date=params.get("start_date"),
                    end_date=params.get("end_date")
                )
                return AgentResponse(success=True, data=result)
            else:
                return AgentResponse(
                    success=False,
                    data=None,
                    error=f"Unsupported action: {action}"
                )
        except Exception as e:
            return AgentResponse(
                success=False,
                data=None,
                error=str(e)
            )

    async def analyze_kpis(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[KPIMetric]:
        """
        分析KPI指标

        Args:
            start_date: 开始日期(ISO格式)
            end_date: 结束日期(ISO格式)

        Returns:
            KPI指标列表
        """
        self.logger.info(
            "analyzing_kpis",
            start_date=start_date,
            end_date=end_date
        )

        try:
            # 收集各维度数据
            revenue_data = await self._collect_revenue_data(start_date, end_date)
            cost_data = await self._collect_cost_data(start_date, end_date)
            efficiency_data = await self._collect_efficiency_data(start_date, end_date)
            quality_data = await self._collect_quality_data(start_date, end_date)
            customer_data = await self._collect_customer_data(start_date, end_date)

            # 计算KPI指标
            kpis = []

            # 营收类指标
            kpis.extend(self._calculate_revenue_kpis(revenue_data))

            # 成本类指标
            kpis.extend(self._calculate_cost_kpis(cost_data, revenue_data))

            # 效率类指标
            kpis.extend(self._calculate_efficiency_kpis(efficiency_data))

            # 质量类指标
            kpis.extend(self._calculate_quality_kpis(quality_data))

            # 客户类指标
            kpis.extend(self._calculate_customer_kpis(customer_data))

            # 评估每个KPI的状态
            for kpi in kpis:
                kpi["status"] = self._evaluate_kpi_status(kpi)

            self.logger.info(
                "kpis_analyzed",
                total_kpis=len(kpis),
                on_track=sum(1 for k in kpis if k["status"] == "on_track"),
                at_risk=sum(1 for k in kpis if k["status"] == "at_risk"),
                off_track=sum(1 for k in kpis if k["status"] == "off_track")
            )

            return kpis

        except Exception as e:
            self.logger.error("analyze_kpis_failed", error=str(e))
            raise

    def _calculate_revenue_kpis(self, revenue_data: Dict[str, Any]) -> List[KPIMetric]:
        """计算营收类KPI"""
        kpis = []

        # 总营收
        total_revenue = revenue_data.get("total_revenue", 0)
        previous_revenue = revenue_data.get("previous_revenue", 0)
        target_revenue = revenue_data.get("target_revenue", total_revenue * 1.15)

        kpi: KPIMetric = {
            "metric_id": "KPI_REVENUE_001",
            "metric_name": "总营收",
            "category": MetricCategory.REVENUE,
            "current_value": total_revenue / 100,  # 转换为元
            "target_value": target_revenue / 100,
            "previous_value": previous_revenue / 100,
            "unit": "元",
            "achievement_rate": total_revenue / target_revenue if target_revenue > 0 else 0,
            "trend": self._calculate_trend(total_revenue, previous_revenue),
            "status": "on_track"
        }
        kpis.append(kpi)

        # 日均营收
        days = revenue_data.get("days", 30)
        daily_avg = total_revenue / days if days > 0 else 0
        previous_daily_avg = previous_revenue / days if days > 0 else 0

        kpi: KPIMetric = {
            "metric_id": "KPI_REVENUE_002",
            "metric_name": "日均营收",
            "category": MetricCategory.REVENUE,
            "current_value": daily_avg / 100,
            "target_value": (target_revenue / days) / 100 if days > 0 else 0,
            "previous_value": previous_daily_avg / 100,
            "unit": "元/天",
            "achievement_rate": daily_avg / (target_revenue / days) if target_revenue > 0 and days > 0 else 0,
            "trend": self._calculate_trend(daily_avg, previous_daily_avg),
            "status": "on_track"
        }
        kpis.append(kpi)

        return kpis

    def _calculate_cost_kpis(
        self,
        cost_data: Dict[str, Any],
        revenue_data: Dict[str, Any]
    ) -> List[KPIMetric]:
        """计算成本类KPI"""
        kpis = []

        total_cost = cost_data.get("total_cost", 0)
        previous_cost = cost_data.get("previous_cost", 0)
        total_revenue = revenue_data.get("total_revenue", 1)

        # 成本率
        cost_ratio = total_cost / total_revenue if total_revenue > 0 else 0
        previous_cost_ratio = previous_cost / revenue_data.get("previous_revenue", 1)
        target_cost_ratio = self.kpi_targets.get("cost_ratio", 0.35)

        kpi: KPIMetric = {
            "metric_id": "KPI_COST_001",
            "metric_name": "成本率",
            "category": MetricCategory.COST,
            "current_value": cost_ratio,
            "target_value": target_cost_ratio,
            "previous_value": previous_cost_ratio,
            "unit": "%",
            "achievement_rate": target_cost_ratio / cost_ratio if cost_ratio > 0 else 0,
            "trend": self._calculate_trend(cost_ratio, previous_cost_ratio, inverse=True),
            "status": "on_track"
        }
        kpis.append(kpi)

        return kpis

    def _calculate_efficiency_kpis(self, efficiency_data: Dict[str, Any]) -> List[KPIMetric]:
        """计算效率类KPI"""
        kpis = []

        # 人效(人均营收)
        revenue_per_staff = efficiency_data.get("revenue_per_staff", 0)
        previous_revenue_per_staff = efficiency_data.get("previous_revenue_per_staff", 0)
        target_revenue_per_staff = revenue_per_staff * 1.1

        kpi: KPIMetric = {
            "metric_id": "KPI_EFFICIENCY_001",
            "metric_name": "人均营收",
            "category": MetricCategory.EFFICIENCY,
            "current_value": revenue_per_staff / 100,
            "target_value": target_revenue_per_staff / 100,
            "previous_value": previous_revenue_per_staff / 100,
            "unit": "元/人",
            "achievement_rate": revenue_per_staff / target_revenue_per_staff if target_revenue_per_staff > 0 else 0,
            "trend": self._calculate_trend(revenue_per_staff, previous_revenue_per_staff),
            "status": "on_track"
        }
        kpis.append(kpi)

        return kpis

    def _calculate_quality_kpis(self, quality_data: Dict[str, Any]) -> List[KPIMetric]:
        """计算质量类KPI"""
        kpis = []

        # 订单准确率
        order_accuracy = quality_data.get("order_accuracy", 0.95)
        previous_accuracy = quality_data.get("previous_accuracy", 0.93)
        target_accuracy = 0.98

        kpi: KPIMetric = {
            "metric_id": "KPI_QUALITY_001",
            "metric_name": "订单准确率",
            "category": MetricCategory.QUALITY,
            "current_value": order_accuracy,
            "target_value": target_accuracy,
            "previous_value": previous_accuracy,
            "unit": "%",
            "achievement_rate": order_accuracy / target_accuracy,
            "trend": self._calculate_trend(order_accuracy, previous_accuracy),
            "status": "on_track"
        }
        kpis.append(kpi)

        return kpis

    def _calculate_customer_kpis(self, customer_data: Dict[str, Any]) -> List[KPIMetric]:
        """计算客户类KPI"""
        kpis = []

        # 客户满意度
        satisfaction_rate = customer_data.get("satisfaction_rate", 0.87)
        previous_satisfaction = customer_data.get("previous_satisfaction", 0.85)
        target_satisfaction = self.kpi_targets.get("customer_satisfaction", 0.90)

        kpi: KPIMetric = {
            "metric_id": "KPI_CUSTOMER_001",
            "metric_name": "客户满意度",
            "category": MetricCategory.CUSTOMER,
            "current_value": satisfaction_rate,
            "target_value": target_satisfaction,
            "previous_value": previous_satisfaction,
            "unit": "%",
            "achievement_rate": satisfaction_rate / target_satisfaction,
            "trend": self._calculate_trend(satisfaction_rate, previous_satisfaction),
            "status": "on_track"
        }
        kpis.append(kpi)

        return kpis

    def _calculate_trend(
        self,
        current: float,
        previous: float,
        inverse: bool = False
    ) -> TrendDirection:
        """计算趋势方向"""
        if previous == 0:
            return TrendDirection.STABLE

        change_rate = (current - previous) / previous

        # 对于成本类指标,下降是好的
        if inverse:
            change_rate = -change_rate

        if abs(change_rate) < 0.05:
            return TrendDirection.STABLE
        elif change_rate > 0.15:
            return TrendDirection.INCREASING
        elif change_rate < -0.15:
            return TrendDirection.DECREASING
        elif abs(change_rate) > 0.10:
            return TrendDirection.VOLATILE
        else:
            return TrendDirection.STABLE

    def _evaluate_kpi_status(self, kpi: KPIMetric) -> str:
        """评估KPI状态"""
        achievement_rate = kpi["achievement_rate"]

        if achievement_rate >= 0.95:
            return "on_track"
        elif achievement_rate >= 0.85:
            return "at_risk"
        else:
            return "off_track"

    async def generate_insights(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[BusinessInsight]:
        """
        生成业务洞察

        Args:
            start_date: 开始日期(ISO格式)
            end_date: 结束日期(ISO格式)

        Returns:
            业务洞察列表
        """
        self.logger.info(
            "generating_insights",
            start_date=start_date,
            end_date=end_date
        )

        try:
            insights = []

            # 分析KPI
            kpis = await self.analyze_kpis(start_date, end_date)

            # 从KPI中发现洞察
            for kpi in kpis:
                if kpi["status"] == "off_track":
                    insight = self._create_kpi_insight(kpi)
                    insights.append(insight)

            # 从各Agent获取数据并分析
            if self.service_agent:
                service_insights = await self._analyze_service_patterns()
                insights.extend(service_insights)

            if self.inventory_agent:
                inventory_insights = await self._analyze_inventory_patterns()
                insights.extend(inventory_insights)

            # 按影响程度排序
            insights.sort(
                key=lambda x: ["low", "medium", "high"].index(x["impact_level"]),
                reverse=True
            )

            self.logger.info(
                "insights_generated",
                total_insights=len(insights),
                high_impact=sum(1 for i in insights if i["impact_level"] == "high")
            )

            return insights

        except Exception as e:
            self.logger.error("generate_insights_failed", error=str(e))
            raise

    def _create_kpi_insight(self, kpi: KPIMetric) -> BusinessInsight:
        """从KPI创建洞察"""
        insight: BusinessInsight = {
            "insight_id": f"INSIGHT_KPI_{kpi['metric_id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "title": f"{kpi['metric_name']}未达标",
            "description": f"{kpi['metric_name']}当前为{kpi['current_value']:.2f}{kpi['unit']},目标为{kpi['target_value']:.2f}{kpi['unit']},达成率仅{kpi['achievement_rate']:.1%}",
            "category": kpi["category"],
            "impact_level": "high" if kpi["achievement_rate"] < 0.80 else "medium",
            "data_points": [
                {"label": "当前值", "value": kpi["current_value"]},
                {"label": "目标值", "value": kpi["target_value"]},
                {"label": "达成率", "value": kpi["achievement_rate"]}
            ],
            "discovered_at": datetime.now().isoformat()
        }
        return insight

    async def _analyze_service_patterns(self) -> List[BusinessInsight]:
        """分析服务模式"""
        insights = []

        # 模拟服务数据分析
        insight: BusinessInsight = {
            "insight_id": f"INSIGHT_SERVICE_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "title": "午餐时段投诉率偏高",
            "description": "数据显示午餐时段(11:00-14:00)的客户投诉率比其他时段高30%,主要原因是等待时间过长",
            "category": "service",
            "impact_level": "high",
            "data_points": [
                {"label": "午餐投诉率", "value": 0.08},
                {"label": "其他时段投诉率", "value": 0.05},
                {"label": "差异", "value": 0.03}
            ],
            "discovered_at": datetime.now().isoformat()
        }
        insights.append(insight)

        return insights

    async def _analyze_inventory_patterns(self) -> List[BusinessInsight]:
        """分析库存模式"""
        insights = []

        # 模拟库存数据分析
        insight: BusinessInsight = {
            "insight_id": f"INSIGHT_INVENTORY_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "title": "周末食材浪费率较高",
            "description": "周末食材浪费率达12%,高于平日的7%,建议优化周末采购计划",
            "category": "inventory",
            "impact_level": "medium",
            "data_points": [
                {"label": "周末浪费率", "value": 0.12},
                {"label": "平日浪费率", "value": 0.07},
                {"label": "潜在节省", "value": 5000}
            ],
            "discovered_at": datetime.now().isoformat()
        }
        insights.append(insight)

        return insights

    async def generate_recommendations(
        self,
        decision_type: Optional[DecisionType] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[Recommendation]:
        """
        生成业务建议

        Args:
            decision_type: 决策类型(可选)
            start_date: 开始日期(ISO格式)
            end_date: 结束日期(ISO格式)

        Returns:
            业务建议列表
        """
        self.logger.info(
            "generating_recommendations",
            decision_type=decision_type,
            start_date=start_date,
            end_date=end_date
        )

        try:
            recommendations = []

            # 获取洞察
            insights = await self.generate_insights(start_date, end_date)

            # 基于洞察生成建议
            for insight in insights:
                if insight["impact_level"] in ["high", "medium"]:
                    recommendation = self._create_recommendation_from_insight(insight)
                    recommendations.append(recommendation)

            # 获取KPI并生成改进建议
            kpis = await self.analyze_kpis(start_date, end_date)
            for kpi in kpis:
                if kpi["status"] == "off_track":
                    recommendation = self._create_recommendation_from_kpi(kpi)
                    recommendations.append(recommendation)

            # 按决策类型筛选
            if decision_type:
                recommendations = [r for r in recommendations if r["decision_type"] == decision_type]

            # 按优先级排序
            recommendations.sort(
                key=lambda x: ["low", "medium", "high", "critical"].index(x["priority"]),
                reverse=True
            )

            self.logger.info(
                "recommendations_generated",
                total_recommendations=len(recommendations),
                critical=sum(1 for r in recommendations if r["priority"] == RecommendationPriority.CRITICAL)
            )

            return recommendations

        except Exception as e:
            self.logger.error("generate_recommendations_failed", error=str(e))
            raise

    def _create_recommendation_from_insight(self, insight: BusinessInsight) -> Recommendation:
        """从洞察创建建议"""
        # 根据洞察类别生成建议
        if "投诉" in insight["title"]:
            recommendation: Recommendation = {
                "recommendation_id": f"REC_{insight['insight_id']}",
                "title": "增加午餐时段人手",
                "description": "在午餐高峰时段(11:00-14:00)增加2-3名服务人员,减少客户等待时间",
                "decision_type": DecisionType.OPERATIONAL,
                "priority": RecommendationPriority.HIGH,
                "rationale": insight["description"],
                "expected_impact": "预计可降低投诉率30%,提升客户满意度5%",
                "action_items": [
                    "调整排班计划,增加午餐时段人手",
                    "培训员工提高服务效率",
                    "优化点餐和上菜流程"
                ],
                "estimated_cost": 500000,  # 5000元/月
                "estimated_roi": 2.5,
                "created_at": datetime.now().isoformat()
            }
        elif "浪费" in insight["title"]:
            recommendation: Recommendation = {
                "recommendation_id": f"REC_{insight['insight_id']}",
                "title": "优化周末采购计划",
                "description": "根据历史数据调整周末食材采购量,减少浪费",
                "decision_type": DecisionType.TACTICAL,
                "priority": RecommendationPriority.MEDIUM,
                "rationale": insight["description"],
                "expected_impact": "预计每月节省成本5000元,降低浪费率至8%",
                "action_items": [
                    "分析周末销售数据",
                    "调整采购计划",
                    "建立动态补货机制"
                ],
                "estimated_cost": 0,
                "estimated_roi": None,
                "created_at": datetime.now().isoformat()
            }
        else:
            recommendation: Recommendation = {
                "recommendation_id": f"REC_{insight['insight_id']}",
                "title": "改进运营流程",
                "description": "基于数据分析优化运营流程",
                "decision_type": DecisionType.OPERATIONAL,
                "priority": RecommendationPriority.MEDIUM,
                "rationale": insight["description"],
                "expected_impact": "提升运营效率",
                "action_items": ["分析问题", "制定方案", "实施改进"],
                "estimated_cost": None,
                "estimated_roi": None,
                "created_at": datetime.now().isoformat()
            }

        return recommendation

    def _create_recommendation_from_kpi(self, kpi: KPIMetric) -> Recommendation:
        """从KPI创建建议"""
        priority = RecommendationPriority.CRITICAL if kpi["achievement_rate"] < 0.80 else RecommendationPriority.HIGH

        recommendation: Recommendation = {
            "recommendation_id": f"REC_KPI_{kpi['metric_id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "title": f"改善{kpi['metric_name']}",
            "description": f"当前{kpi['metric_name']}为{kpi['current_value']:.2f}{kpi['unit']},需要提升至目标值{kpi['target_value']:.2f}{kpi['unit']}",
            "decision_type": DecisionType.TACTICAL,
            "priority": priority,
            "rationale": f"达成率仅{kpi['achievement_rate']:.1%},低于预期",
            "expected_impact": f"提升{kpi['metric_name']}至目标水平",
            "action_items": [
                "分析根本原因",
                "制定改进计划",
                "实施并监控效果"
            ],
            "estimated_cost": None,
            "estimated_roi": None,
            "created_at": datetime.now().isoformat()
        }

        return recommendation

    async def forecast_trends(
        self,
        metric_name: str,
        forecast_days: int = 30,
        historical_days: int = 90
    ) -> TrendForecast:
        """
        预测趋势

        Args:
            metric_name: 指标名称
            forecast_days: 预测天数
            historical_days: 历史数据天数

        Returns:
            趋势预测
        """
        self.logger.info(
            "forecasting_trends",
            metric_name=metric_name,
            forecast_days=forecast_days
        )

        try:
            # 获取历史数据
            historical_data = await self._get_historical_data(metric_name, historical_days)

            # 使用简单移动平均预测
            forecasted_values = self._simple_forecast(historical_data, forecast_days)

            # 计算趋势方向
            current_value = historical_data[-1] if historical_data else 0
            avg_forecast = mean(forecasted_values) if forecasted_values else 0
            trend_direction = self._calculate_trend(avg_forecast, current_value)

            # 计算置信度
            confidence_level = self._calculate_forecast_confidence(historical_data)

            forecast: TrendForecast = {
                "forecast_id": f"FORECAST_{metric_name}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "metric_name": metric_name,
                "current_value": current_value,
                "forecasted_values": forecasted_values,
                "forecast_period": f"{forecast_days}天",
                "confidence_level": confidence_level,
                "trend_direction": trend_direction,
                "forecasted_at": datetime.now().isoformat()
            }

            self.logger.info(
                "trends_forecasted",
                metric_name=metric_name,
                trend_direction=trend_direction,
                confidence_level=confidence_level
            )

            return forecast

        except Exception as e:
            self.logger.error("forecast_trends_failed", error=str(e))
            raise

    def _simple_forecast(self, historical_data: List[float], forecast_days: int) -> List[float]:
        """简单预测"""
        if not historical_data:
            return [0.0] * forecast_days

        # 使用最近7天的平均值
        recent_days = min(7, len(historical_data))
        recent_avg = mean(historical_data[-recent_days:])

        # 计算趋势
        if len(historical_data) >= 2:
            trend = (historical_data[-1] - historical_data[0]) / len(historical_data)
        else:
            trend = 0

        # 预测未来值
        forecasted = []
        for i in range(forecast_days):
            value = recent_avg + trend * i
            forecasted.append(max(0, value))

        return forecasted

    def _calculate_forecast_confidence(self, historical_data: List[float]) -> float:
        """计算预测置信度"""
        if len(historical_data) < 2:
            return 0.5

        # 基于数据稳定性计算置信度
        avg = mean(historical_data)
        if avg == 0:
            return 0.5

        std = stdev(historical_data)
        cv = std / avg  # 变异系数

        # CV越小,置信度越高
        confidence = max(0.0, min(1.0, 1 - cv))

        return round(confidence, 2)

    async def optimize_resources(
        self,
        resource_type: str
    ) -> ResourceOptimization:
        """
        优化资源配置

        Args:
            resource_type: 资源类型(staff/inventory/cost)

        Returns:
            资源优化方案
        """
        self.logger.info("optimizing_resources", resource_type=resource_type)

        try:
            if resource_type == "staff":
                optimization = await self._optimize_staff_allocation()
            elif resource_type == "inventory":
                optimization = await self._optimize_inventory_allocation()
            elif resource_type == "cost":
                optimization = await self._optimize_cost_allocation()
            else:
                raise ValueError(f"Unknown resource type: {resource_type}")

            self.logger.info(
                "resources_optimized",
                resource_type=resource_type,
                expected_savings=optimization["expected_savings"]
            )

            return optimization

        except Exception as e:
            self.logger.error("optimize_resources_failed", error=str(e))
            raise

    async def _optimize_staff_allocation(self) -> ResourceOptimization:
        """优化人员配置"""
        optimization: ResourceOptimization = {
            "optimization_id": f"OPT_STAFF_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "resource_type": "staff",
            "current_allocation": {
                "morning_shift": 5,
                "lunch_shift": 8,
                "dinner_shift": 10,
                "night_shift": 3
            },
            "recommended_allocation": {
                "morning_shift": 4,
                "lunch_shift": 10,
                "dinner_shift": 9,
                "night_shift": 3
            },
            "expected_savings": 200000,  # 2000元/月
            "expected_improvement": "提升午餐时段服务质量,降低晚餐时段人力成本",
            "implementation_difficulty": "easy",
            "created_at": datetime.now().isoformat()
        }
        return optimization

    async def _optimize_inventory_allocation(self) -> ResourceOptimization:
        """优化库存配置"""
        optimization: ResourceOptimization = {
            "optimization_id": f"OPT_INVENTORY_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "resource_type": "inventory",
            "current_allocation": {
                "safety_stock_days": 7,
                "reorder_frequency": "weekly",
                "storage_utilization": 0.75
            },
            "recommended_allocation": {
                "safety_stock_days": 5,
                "reorder_frequency": "twice_weekly",
                "storage_utilization": 0.85
            },
            "expected_savings": 500000,  # 5000元/月
            "expected_improvement": "降低库存成本,提高周转率,减少浪费",
            "implementation_difficulty": "medium",
            "created_at": datetime.now().isoformat()
        }
        return optimization

    async def _optimize_cost_allocation(self) -> ResourceOptimization:
        """优化成本配置"""
        optimization: ResourceOptimization = {
            "optimization_id": f"OPT_COST_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "resource_type": "cost",
            "current_allocation": {
                "food_cost_ratio": 0.35,
                "labor_cost_ratio": 0.25,
                "overhead_ratio": 0.15
            },
            "recommended_allocation": {
                "food_cost_ratio": 0.32,
                "labor_cost_ratio": 0.24,
                "overhead_ratio": 0.14
            },
            "expected_savings": 800000,  # 8000元/月
            "expected_improvement": "优化成本结构,提升利润率",
            "implementation_difficulty": "hard",
            "created_at": datetime.now().isoformat()
        }
        return optimization

    async def create_strategic_plan(
        self,
        time_horizon: str = "1年"
    ) -> StrategicPlan:
        """
        创建战略规划

        Args:
            time_horizon: 时间跨度

        Returns:
            战略规划
        """
        self.logger.info("creating_strategic_plan", time_horizon=time_horizon)

        try:
            # 分析当前状态
            kpis = await self.analyze_kpis()
            insights = await self.generate_insights()
            recommendations = await self.generate_recommendations()

            # 识别关键问题和机会
            key_issues = [i["title"] for i in insights if i["impact_level"] == "high"]
            key_opportunities = [r["title"] for r in recommendations if r["priority"] in [RecommendationPriority.HIGH, RecommendationPriority.CRITICAL]]

            plan: StrategicPlan = {
                "plan_id": f"PLAN_STRATEGIC_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "title": f"{self.store_id}门店{time_horizon}战略规划",
                "objectives": [
                    "提升营收增长率至15%",
                    "降低成本率至32%",
                    "提高客户满意度至92%",
                    "提升员工效率至90%"
                ],
                "time_horizon": time_horizon,
                "key_initiatives": [
                    "优化午餐时段运营,提升服务质量",
                    "实施智能库存管理,降低浪费",
                    "加强员工培训,提升服务水平",
                    "推进数字化转型,提高运营效率"
                ],
                "success_metrics": [
                    "营收增长率",
                    "成本率",
                    "客户满意度",
                    "员工效率",
                    "库存周转率"
                ],
                "risks": [
                    "市场竞争加剧",
                    "人力成本上升",
                    "食材价格波动",
                    "客户需求变化"
                ],
                "created_at": datetime.now().isoformat()
            }

            self.logger.info(
                "strategic_plan_created",
                plan_id=plan["plan_id"],
                objectives_count=len(plan["objectives"])
            )

            return plan

        except Exception as e:
            self.logger.error("create_strategic_plan_failed", error=str(e))
            raise

    async def get_decision_report(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取决策综合报告

        Args:
            start_date: 开始日期(ISO格式)
            end_date: 结束日期(ISO格式)

        Returns:
            决策报告
        """
        self.logger.info(
            "generating_decision_report",
            start_date=start_date,
            end_date=end_date
        )

        try:
            # 并发执行多个任务
            kpis_task = self.analyze_kpis(start_date, end_date)
            insights_task = self.generate_insights(start_date, end_date)
            recommendations_task = self.generate_recommendations(start_date=start_date, end_date=end_date)

            kpis, insights, recommendations = await asyncio.gather(
                kpis_task,
                insights_task,
                recommendations_task
            )

            # 统计KPI状态
            kpi_status_counts = defaultdict(int)
            for kpi in kpis:
                kpi_status_counts[kpi["status"]] += 1

            # 统计建议优先级
            recommendation_priority_counts = defaultdict(int)
            for rec in recommendations:
                recommendation_priority_counts[rec["priority"]] += 1

            report = {
                "store_id": self.store_id,
                "report_date": datetime.now().isoformat(),
                "period_start": start_date or (datetime.now() - timedelta(days=30)).isoformat(),
                "period_end": end_date or datetime.now().isoformat(),
                "kpi_summary": {
                    "total_kpis": len(kpis),
                    "status_distribution": dict(kpi_status_counts),
                    "on_track_rate": kpi_status_counts["on_track"] / len(kpis) if kpis else 0,
                    "key_kpis": kpis[:5]  # 前5个KPI
                },
                "insights_summary": {
                    "total_insights": len(insights),
                    "high_impact": sum(1 for i in insights if i["impact_level"] == "high"),
                    "key_insights": insights[:5]  # 前5个洞察
                },
                "recommendations_summary": {
                    "total_recommendations": len(recommendations),
                    "priority_distribution": dict(recommendation_priority_counts),
                    "critical_recommendations": [
                        r for r in recommendations
                        if r["priority"] == RecommendationPriority.CRITICAL
                    ][:5]
                },
                "overall_health_score": self._calculate_health_score(kpis),
                "action_required": len([r for r in recommendations if r["priority"] in [RecommendationPriority.CRITICAL, RecommendationPriority.HIGH]])
            }

            self.logger.info(
                "decision_report_generated",
                total_kpis=len(kpis),
                total_insights=len(insights),
                total_recommendations=len(recommendations),
                health_score=report["overall_health_score"]
            )

            return report

        except Exception as e:
            self.logger.error("get_decision_report_failed", error=str(e))
            raise

    def _calculate_health_score(self, kpis: List[KPIMetric]) -> float:
        """计算整体健康分数"""
        if not kpis:
            return 0.0

        # 基于KPI达成率计算
        achievement_rates = [kpi["achievement_rate"] for kpi in kpis]
        avg_achievement = mean(achievement_rates)

        # 转换为0-100分
        health_score = min(100, avg_achievement * 100)

        return round(health_score, 1)

    # Helper methods for data collection

    async def _collect_revenue_data(
        self,
        start_date: Optional[str],
        end_date: Optional[str]
    ) -> Dict[str, Any]:
        """收集营收数据"""
        import random
        return {
            "total_revenue": random.randint(80000000, 120000000),  # 80-120万分
            "previous_revenue": random.randint(70000000, 110000000),
            "target_revenue": 100000000,
            "days": 30
        }

    async def _collect_cost_data(
        self,
        start_date: Optional[str],
        end_date: Optional[str]
    ) -> Dict[str, Any]:
        """收集成本数据"""
        import random
        return {
            "total_cost": random.randint(30000000, 45000000),  # 30-45万分
            "previous_cost": random.randint(28000000, 43000000)
        }

    async def _collect_efficiency_data(
        self,
        start_date: Optional[str],
        end_date: Optional[str]
    ) -> Dict[str, Any]:
        """收集效率数据"""
        import random
        return {
            "revenue_per_staff": random.randint(3000000, 5000000),  # 3-5万分/人
            "previous_revenue_per_staff": random.randint(2800000, 4800000)
        }

    async def _collect_quality_data(
        self,
        start_date: Optional[str],
        end_date: Optional[str]
    ) -> Dict[str, Any]:
        """收集质量数据"""
        import random
        return {
            "order_accuracy": random.uniform(0.92, 0.98),
            "previous_accuracy": random.uniform(0.90, 0.96)
        }

    async def _collect_customer_data(
        self,
        start_date: Optional[str],
        end_date: Optional[str]
    ) -> Dict[str, Any]:
        """收集客户数据"""
        import random
        return {
            "satisfaction_rate": random.uniform(0.82, 0.92),
            "previous_satisfaction": random.uniform(0.80, 0.90)
        }

    async def _get_historical_data(
        self,
        metric_name: str,
        days: int
    ) -> List[float]:
        """获取历史数据"""
        import random
        # 生成模拟历史数据
        base_value = 100000.0
        data = []
        for i in range(days):
            value = base_value + random.uniform(-10000, 15000) + i * 100
            data.append(max(0, value))
        return data