"""
智能服务Agent - Intelligent Service Agent

核心功能 Core Features:
1. 客户反馈管理 - Customer feedback management
2. 服务质量监控 - Service quality monitoring
3. 投诉处理 - Complaint handling
4. 服务改进建议 - Service improvement recommendations
5. 员工表现追踪 - Staff performance tracking
6. 满意度分析 - Customer satisfaction analysis
"""

import os
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


class FeedbackType(str, Enum):
    """反馈类型 Feedback Type"""
    PRAISE = "praise"  # 表扬
    SUGGESTION = "suggestion"  # 建议
    COMPLAINT = "complaint"  # 投诉
    INQUIRY = "inquiry"  # 咨询


class ComplaintPriority(str, Enum):
    """投诉优先级 Complaint Priority"""
    LOW = "low"  # 低
    MEDIUM = "medium"  # 中
    HIGH = "high"  # 高
    URGENT = "urgent"  # 紧急


class ComplaintStatus(str, Enum):
    """投诉状态 Complaint Status"""
    PENDING = "pending"  # 待处理
    IN_PROGRESS = "in_progress"  # 处理中
    RESOLVED = "resolved"  # 已解决
    CLOSED = "closed"  # 已关闭


class ServiceCategory(str, Enum):
    """服务分类 Service Category"""
    FOOD_QUALITY = "food_quality"  # 菜品质量
    SERVICE_ATTITUDE = "service_attitude"  # 服务态度
    ENVIRONMENT = "environment"  # 环境卫生
    WAITING_TIME = "waiting_time"  # 等待时间
    PRICE = "price"  # 价格
    OTHER = "other"  # 其他


class SatisfactionLevel(str, Enum):
    """满意度等级 Satisfaction Level"""
    VERY_SATISFIED = "very_satisfied"  # 非常满意
    SATISFIED = "satisfied"  # 满意
    NEUTRAL = "neutral"  # 一般
    DISSATISFIED = "dissatisfied"  # 不满意
    VERY_DISSATISFIED = "very_dissatisfied"  # 非常不满意


class CustomerFeedback(TypedDict):
    """客户反馈 Customer Feedback"""
    feedback_id: str  # 反馈ID
    customer_id: str  # 客户ID
    customer_name: str  # 客户姓名
    store_id: str  # 门店ID
    feedback_type: FeedbackType  # 反馈类型
    category: ServiceCategory  # 服务分类
    rating: int  # 评分(1-5)
    content: str  # 反馈内容
    staff_id: Optional[str]  # 相关员工ID
    order_id: Optional[str]  # 相关订单ID
    created_at: str  # 创建时间
    source: str  # 来源(app/wechat/phone/onsite)


class Complaint(TypedDict):
    """投诉 Complaint"""
    complaint_id: str  # 投诉ID
    feedback_id: str  # 关联反馈ID
    customer_id: str  # 客户ID
    store_id: str  # 门店ID
    category: ServiceCategory  # 投诉分类
    priority: ComplaintPriority  # 优先级
    status: ComplaintStatus  # 状态
    description: str  # 描述
    staff_id: Optional[str]  # 相关员工ID
    assigned_to: Optional[str]  # 处理人ID
    resolution: Optional[str]  # 解决方案
    compensation: Optional[Dict[str, Any]]  # 补偿方案
    created_at: str  # 创建时间
    updated_at: str  # 更新时间
    resolved_at: Optional[str]  # 解决时间


class StaffPerformance(TypedDict):
    """员工表现 Staff Performance"""
    staff_id: str  # 员工ID
    staff_name: str  # 员工姓名
    store_id: str  # 门店ID
    period_start: str  # 统计开始时间
    period_end: str  # 统计结束时间
    total_feedbacks: int  # 总反馈数
    praise_count: int  # 表扬数
    complaint_count: int  # 投诉数
    average_rating: float  # 平均评分
    service_score: float  # 服务得分(0-100)
    improvement_areas: List[str]  # 改进领域


class ServiceQualityMetrics(TypedDict):
    """服务质量指标 Service Quality Metrics"""
    store_id: str  # 门店ID
    period_start: str  # 统计开始时间
    period_end: str  # 统计结束时间
    total_feedbacks: int  # 总反馈数
    average_rating: float  # 平均评分
    satisfaction_rate: float  # 满意度(%)
    complaint_rate: float  # 投诉率(%)
    response_time_avg: float  # 平均响应时间(分钟)
    resolution_rate: float  # 解决率(%)
    category_breakdown: Dict[str, int]  # 分类统计
    trend: str  # 趋势(improving/stable/declining)


class ServiceImprovement(TypedDict):
    """服务改进建议 Service Improvement"""
    improvement_id: str  # 改进ID
    store_id: str  # 门店ID
    category: ServiceCategory  # 分类
    issue: str  # 问题描述
    root_cause: str  # 根本原因
    recommendation: str  # 改进建议
    priority: ComplaintPriority  # 优先级
    estimated_impact: str  # 预期影响
    created_at: str  # 创建时间


class ServiceAgent(BaseAgent):
    """
    智能服务Agent

    工作流程 Workflow:
    1. collect_feedback() - 收集客户反馈
    2. analyze_feedback() - 分析反馈内容
    3. handle_complaint() - 处理投诉
    4. monitor_service_quality() - 监控服务质量
    5. track_staff_performance() - 追踪员工表现
    6. generate_improvements() - 生成改进建议
    """

    def __init__(
        self,
        store_id: str,
        aoqiwei_adapter: Optional[Any] = None,
        quality_thresholds: Optional[Dict[str, float]] = None
    ):
        """
        初始化服务Agent

        Args:
            store_id: 门店ID
            aoqiwei_adapter: 奥琦韦会员系统适配器
            quality_thresholds: 质量阈值配置
        """
        super().__init__()
        self.store_id = store_id
        self.aoqiwei_adapter = aoqiwei_adapter
        self.quality_thresholds = quality_thresholds or {
            "min_satisfaction_rate": float(os.getenv("SERVICE_MIN_SATISFACTION_RATE", "0.85")),
            "max_complaint_rate": float(os.getenv("SERVICE_MAX_COMPLAINT_RATE", "0.05")),
            "max_response_time": int(os.getenv("SERVICE_MAX_RESPONSE_TIME_MINUTES", "30")),
            "min_resolution_rate": float(os.getenv("SERVICE_MIN_RESOLUTION_RATE", "0.90")),
        }
        self.logger = logger.bind(agent="service", store_id=store_id)

    def get_supported_actions(self) -> List[str]:
        """获取支持的操作列表"""
        return [
            "collect_feedback", "analyze_feedback", "handle_complaint",
            "monitor_service_quality", "track_staff_performance",
            "generate_improvements", "get_service_report"
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
            if action == "collect_feedback":
                result = await self.collect_feedback(
                    start_date=params.get("start_date"),
                    end_date=params.get("end_date"),
                    feedback_type=params.get("feedback_type")
                )
                return AgentResponse(success=True, data=result)
            elif action == "analyze_feedback":
                result = await self.analyze_feedback(
                    feedback=params["feedback"]
                )
                return AgentResponse(success=True, data=result)
            elif action == "handle_complaint":
                result = await self.handle_complaint(
                    feedback=params["feedback"],
                    assigned_to=params.get("assigned_to")
                )
                return AgentResponse(success=True, data=result)
            elif action == "monitor_service_quality":
                result = await self.monitor_service_quality(
                    start_date=params.get("start_date"),
                    end_date=params.get("end_date")
                )
                return AgentResponse(success=True, data=result)
            elif action == "track_staff_performance":
                result = await self.track_staff_performance(
                    staff_id=params.get("staff_id"),
                    start_date=params.get("start_date"),
                    end_date=params.get("end_date")
                )
                return AgentResponse(success=True, data=result)
            elif action == "generate_improvements":
                result = await self.generate_improvements(
                    start_date=params.get("start_date"),
                    end_date=params.get("end_date")
                )
                return AgentResponse(success=True, data=result)
            elif action == "get_service_report":
                result = await self.get_service_report(
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

    async def collect_feedback(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        feedback_type: Optional[FeedbackType] = None
    ) -> List[CustomerFeedback]:
        """
        收集客户反馈

        Args:
            start_date: 开始日期(ISO格式)
            end_date: 结束日期(ISO格式)
            feedback_type: 反馈类型(可选)

        Returns:
            客户反馈列表
        """
        self.logger.info(
            "collecting_feedback",
            start_date=start_date,
            end_date=end_date,
            feedback_type=feedback_type
        )

        try:
            # 从奥琦韦系统获取客户反馈
            if self.aoqiwei_adapter:
                feedbacks = await self.aoqiwei_adapter.get_customer_feedbacks(
                    store_id=self.store_id,
                    start_date=start_date,
                    end_date=end_date
                )
            else:
                # 使用模拟数据
                feedbacks = self._generate_mock_feedbacks(start_date, end_date)

            # 按类型筛选
            if feedback_type:
                feedbacks = [f for f in feedbacks if f["feedback_type"] == feedback_type]

            self.logger.info(
                "feedback_collected",
                total_feedbacks=len(feedbacks),
                feedback_type=feedback_type
            )

            return feedbacks

        except Exception as e:
            self.logger.error("collect_feedback_failed", error=str(e))
            raise

    async def analyze_feedback(
        self,
        feedback: CustomerFeedback
    ) -> Dict[str, Any]:
        """
        分析反馈内容

        Args:
            feedback: 客户反馈

        Returns:
            分析结果
        """
        self.logger.info("analyzing_feedback", feedback_id=feedback["feedback_id"])

        try:
            # 情感分析
            sentiment = self._analyze_sentiment(feedback["content"], feedback["rating"])

            # 关键词提取
            keywords = self._extract_keywords(feedback["content"])

            # 分类确认
            category = self._classify_feedback(feedback["content"], feedback["category"])

            # 优先级评估
            priority = self._assess_priority(feedback)

            analysis = {
                "feedback_id": feedback["feedback_id"],
                "sentiment": sentiment,
                "keywords": keywords,
                "category": category,
                "priority": priority,
                "requires_action": feedback["feedback_type"] == FeedbackType.COMPLAINT,
                "analyzed_at": datetime.now().isoformat()
            }

            self.logger.info(
                "feedback_analyzed",
                feedback_id=feedback["feedback_id"],
                sentiment=sentiment,
                priority=priority
            )

            return analysis

        except Exception as e:
            self.logger.error("analyze_feedback_failed", error=str(e))
            raise

    def _analyze_sentiment(self, content: str, rating: int) -> str:
        """分析情感倾向"""
        # 简化的情感分析(基于评分和关键词)
        negative_keywords = ["差", "糟糕", "失望", "不满", "投诉", "问题"]
        positive_keywords = ["好", "满意", "优秀", "赞", "棒", "喜欢"]

        content_lower = content.lower()
        negative_count = sum(1 for kw in negative_keywords if kw in content_lower)
        positive_count = sum(1 for kw in positive_keywords if kw in content_lower)

        if rating >= int(os.getenv("SERVICE_POSITIVE_RATING_THRESHOLD", "4")) and positive_count > negative_count:
            return "positive"
        elif rating <= int(os.getenv("SERVICE_NEGATIVE_RATING_THRESHOLD", "2")) or negative_count > positive_count:
            return "negative"
        else:
            return "neutral"

    def _extract_keywords(self, content: str) -> List[str]:
        """提取关键词"""
        # 简化的关键词提取
        keywords_map = {
            "菜品": ServiceCategory.FOOD_QUALITY,
            "服务": ServiceCategory.SERVICE_ATTITUDE,
            "环境": ServiceCategory.ENVIRONMENT,
            "等待": ServiceCategory.WAITING_TIME,
            "价格": ServiceCategory.PRICE,
        }

        keywords = []
        for keyword in keywords_map.keys():
            if keyword in content:
                keywords.append(keyword)

        return keywords if keywords else ["其他"]

    def _classify_feedback(self, content: str, current_category: ServiceCategory) -> ServiceCategory:
        """分类反馈"""
        # 基于内容重新分类
        category_keywords = {
            ServiceCategory.FOOD_QUALITY: ["菜品", "味道", "食材", "口感", "新鲜"],
            ServiceCategory.SERVICE_ATTITUDE: ["服务", "态度", "员工", "服务员", "礼貌"],
            ServiceCategory.ENVIRONMENT: ["环境", "卫生", "干净", "装修", "氛围"],
            ServiceCategory.WAITING_TIME: ["等待", "慢", "时间", "排队", "上菜"],
            ServiceCategory.PRICE: ["价格", "贵", "便宜", "性价比", "收费"],
        }

        content_lower = content.lower()
        for category, keywords in category_keywords.items():
            if any(kw in content_lower for kw in keywords):
                return category

        return current_category

    def _assess_priority(self, feedback: CustomerFeedback) -> ComplaintPriority:
        """评估优先级"""
        if feedback["feedback_type"] != FeedbackType.COMPLAINT:
            return ComplaintPriority.LOW

        rating = feedback["rating"]
        urgent_keywords = ["立即", "马上", "严重", "食物中毒", "投诉"]

        content_lower = feedback["content"].lower()
        has_urgent_keyword = any(kw in content_lower for kw in urgent_keywords)

        if rating == 1 or has_urgent_keyword:
            return ComplaintPriority.URGENT
        elif rating == 2:
            return ComplaintPriority.HIGH
        elif rating == 3:
            return ComplaintPriority.MEDIUM
        else:
            return ComplaintPriority.LOW

    async def handle_complaint(
        self,
        feedback: CustomerFeedback,
        assigned_to: Optional[str] = None
    ) -> Complaint:
        """
        处理投诉

        Args:
            feedback: 客户反馈
            assigned_to: 指派处理人ID

        Returns:
            投诉记录
        """
        self.logger.info(
            "handling_complaint",
            feedback_id=feedback["feedback_id"],
            assigned_to=assigned_to
        )

        try:
            # 分析反馈
            analysis = await self.analyze_feedback(feedback)

            # 创建投诉记录
            complaint: Complaint = {
                "complaint_id": f"COMP_{feedback['feedback_id']}",
                "feedback_id": feedback["feedback_id"],
                "customer_id": feedback["customer_id"],
                "store_id": feedback["store_id"],
                "category": analysis["category"],
                "priority": analysis["priority"],
                "status": ComplaintStatus.PENDING,
                "description": feedback["content"],
                "staff_id": feedback.get("staff_id"),
                "assigned_to": assigned_to,
                "resolution": None,
                "compensation": None,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "resolved_at": None
            }

            # 生成处理建议
            resolution_suggestion = self._generate_resolution_suggestion(complaint)
            compensation_suggestion = self._generate_compensation_suggestion(complaint)

            complaint["resolution"] = resolution_suggestion
            complaint["compensation"] = compensation_suggestion

            # 自动分配处理人
            if not assigned_to:
                complaint["assigned_to"] = self._auto_assign_handler(complaint)

            # 更新状态为处理中
            complaint["status"] = ComplaintStatus.IN_PROGRESS

            self.logger.info(
                "complaint_handled",
                complaint_id=complaint["complaint_id"],
                priority=complaint["priority"],
                assigned_to=complaint["assigned_to"]
            )

            return complaint

        except Exception as e:
            self.logger.error("handle_complaint_failed", error=str(e))
            raise

    def _generate_resolution_suggestion(self, complaint: Complaint) -> str:
        """生成解决方案建议"""
        category = complaint["category"]
        priority = complaint["priority"]

        suggestions = {
            ServiceCategory.FOOD_QUALITY: "1. 向客户道歉 2. 重新制作菜品或更换菜品 3. 检查食材和制作流程 4. 培训厨师",
            ServiceCategory.SERVICE_ATTITUDE: "1. 向客户诚恳道歉 2. 对相关员工进行培训 3. 加强服务规范管理",
            ServiceCategory.ENVIRONMENT: "1. 立即清洁相关区域 2. 加强日常卫生检查 3. 改善环境设施",
            ServiceCategory.WAITING_TIME: "1. 向客户解释原因并道歉 2. 提供小食或饮料 3. 优化流程提高效率",
            ServiceCategory.PRICE: "1. 解释定价依据 2. 介绍优惠活动 3. 提供会员折扣",
            ServiceCategory.OTHER: "1. 详细了解问题 2. 提供针对性解决方案 3. 跟进处理结果"
        }

        base_suggestion = suggestions.get(category, suggestions[ServiceCategory.OTHER])

        if priority == ComplaintPriority.URGENT:
            return f"【紧急处理】{base_suggestion} 5. 店长亲自跟进并在1小时内回复客户"
        elif priority == ComplaintPriority.HIGH:
            return f"【优先处理】{base_suggestion} 5. 在2小时内回复客户"
        else:
            return base_suggestion

    def _generate_compensation_suggestion(self, complaint: Complaint) -> Dict[str, Any]:
        """生成补偿方案建议"""
        priority = complaint["priority"]
        category = complaint["category"]

        compensation = {
            "type": "none",
            "amount_fen": 0,
            "description": "无需补偿"
        }

        if priority == ComplaintPriority.URGENT:
            if category == ServiceCategory.FOOD_QUALITY:
                compensation = {
                    "type": "refund_and_coupon",
                    "amount_fen": 10000,  # 100元
                    "description": "全额退款 + 100元代金券"
                }
            else:
                compensation = {
                    "type": "coupon",
                    "amount_fen": 5000,  # 50元
                    "description": "50元代金券 + 诚挚道歉"
                }
        elif priority == ComplaintPriority.HIGH:
            compensation = {
                "type": "coupon",
                "amount_fen": 3000,  # 30元
                "description": "30元代金券"
            }
        elif priority == ComplaintPriority.MEDIUM:
            compensation = {
                "type": "discount",
                "amount_fen": 1000,  # 10元
                "description": "10元代金券或下次消费折扣"
            }

        return compensation

    def _auto_assign_handler(self, complaint: Complaint) -> str:
        """自动分配处理人"""
        priority = complaint["priority"]
        category = complaint["category"]

        # 根据优先级和分类分配
        if priority == ComplaintPriority.URGENT:
            return "MANAGER_001"  # 店长
        elif category == ServiceCategory.FOOD_QUALITY:
            return "CHEF_MANAGER_001"  # 厨师长
        elif category == ServiceCategory.SERVICE_ATTITUDE:
            return "SERVICE_MANAGER_001"  # 服务经理
        else:
            return "CUSTOMER_SERVICE_001"  # 客服专员

    async def monitor_service_quality(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> ServiceQualityMetrics:
        """
        监控服务质量

        Args:
            start_date: 开始日期(ISO格式)
            end_date: 结束日期(ISO格式)

        Returns:
            服务质量指标
        """
        self.logger.info(
            "monitoring_service_quality",
            start_date=start_date,
            end_date=end_date
        )

        try:
            # 收集反馈数据
            feedbacks = await self.collect_feedback(start_date, end_date)

            if not feedbacks:
                raise ValueError("No feedback data available for the period")

            # 计算指标
            total_feedbacks = len(feedbacks)
            ratings = [f["rating"] for f in feedbacks]
            average_rating = mean(ratings)

            # 满意度(评分>=4的比例)
            satisfied_count = sum(1 for r in ratings if r >= int(os.getenv("SERVICE_SATISFIED_RATING_MIN", "4")))
            satisfaction_rate = satisfied_count / total_feedbacks

            # 投诉率
            complaint_count = sum(1 for f in feedbacks if f["feedback_type"] == FeedbackType.COMPLAINT)
            complaint_rate = complaint_count / total_feedbacks

            # 分类统计
            category_breakdown = defaultdict(int)
            for feedback in feedbacks:
                category_breakdown[feedback["category"]] += 1

            # 响应时间(模拟)
            response_time_avg = float(os.getenv("SERVICE_MOCK_RESPONSE_TIME_MINUTES", "25.0"))

            # 解决率(模拟)
            resolution_rate = float(os.getenv("SERVICE_MOCK_RESOLUTION_RATE", "0.92"))

            # 趋势分析
            trend = self._analyze_trend(feedbacks)

            metrics: ServiceQualityMetrics = {
                "store_id": self.store_id,
                "period_start": start_date or (datetime.now() - timedelta(days=int(os.getenv("AGENT_STATS_DAYS", "30")))).isoformat(),
                "period_end": end_date or datetime.now().isoformat(),
                "total_feedbacks": total_feedbacks,
                "average_rating": round(average_rating, 2),
                "satisfaction_rate": round(satisfaction_rate, 2),
                "complaint_rate": round(complaint_rate, 2),
                "response_time_avg": response_time_avg,
                "resolution_rate": resolution_rate,
                "category_breakdown": dict(category_breakdown),
                "trend": trend
            }

            # 检查是否达标
            self._check_quality_thresholds(metrics)

            self.logger.info(
                "service_quality_monitored",
                average_rating=metrics["average_rating"],
                satisfaction_rate=metrics["satisfaction_rate"],
                trend=trend
            )

            return metrics

        except Exception as e:
            self.logger.error("monitor_service_quality_failed", error=str(e))
            raise

    def _analyze_trend(self, feedbacks: List[CustomerFeedback]) -> str:
        """分析趋势"""
        if len(feedbacks) < int(os.getenv("SERVICE_TREND_MIN_FEEDBACKS", "10")):
            return "stable"

        # 按时间排序
        sorted_feedbacks = sorted(feedbacks, key=lambda x: x["created_at"])

        # 分成前后两半
        mid = len(sorted_feedbacks) // 2
        first_half = sorted_feedbacks[:mid]
        second_half = sorted_feedbacks[mid:]

        # 计算平均评分
        first_avg = mean([f["rating"] for f in first_half])
        second_avg = mean([f["rating"] for f in second_half])

        # 判断趋势
        diff = second_avg - first_avg
        if diff > float(os.getenv("SERVICE_TREND_IMPROVING_THRESHOLD", "0.3")):
            return "improving"
        elif diff < -float(os.getenv("SERVICE_TREND_DECLINING_THRESHOLD", "0.3")):
            return "declining"
        else:
            return "stable"

    def _check_quality_thresholds(self, metrics: ServiceQualityMetrics):
        """检查质量阈值"""
        warnings = []

        if metrics["satisfaction_rate"] < self.quality_thresholds["min_satisfaction_rate"]:
            warnings.append(f"满意度低于阈值: {metrics['satisfaction_rate']:.2%}")

        if metrics["complaint_rate"] > self.quality_thresholds["max_complaint_rate"]:
            warnings.append(f"投诉率超过阈值: {metrics['complaint_rate']:.2%}")

        if metrics["response_time_avg"] > self.quality_thresholds["max_response_time"]:
            warnings.append(f"响应时间超过阈值: {metrics['response_time_avg']}分钟")

        if metrics["resolution_rate"] < self.quality_thresholds["min_resolution_rate"]:
            warnings.append(f"解决率低于阈值: {metrics['resolution_rate']:.2%}")

        if warnings:
            self.logger.warning("quality_thresholds_not_met", warnings=warnings)

    async def track_staff_performance(
        self,
        staff_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[StaffPerformance]:
        """
        追踪员工表现

        Args:
            staff_id: 员工ID(可选,不指定则返回所有员工)
            start_date: 开始日期(ISO格式)
            end_date: 结束日期(ISO格式)

        Returns:
            员工表现列表
        """
        self.logger.info(
            "tracking_staff_performance",
            staff_id=staff_id,
            start_date=start_date,
            end_date=end_date
        )

        try:
            # 收集反馈数据
            feedbacks = await self.collect_feedback(start_date, end_date)

            # 按员工分组
            staff_feedbacks = defaultdict(list)
            for feedback in feedbacks:
                if feedback.get("staff_id"):
                    staff_feedbacks[feedback["staff_id"]].append(feedback)

            # 如果指定了员工ID,只返回该员工
            if staff_id:
                staff_feedbacks = {staff_id: staff_feedbacks.get(staff_id, [])}

            # 计算每个员工的表现
            performances = []
            for sid, staff_feedback_list in staff_feedbacks.items():
                if not staff_feedback_list:
                    continue

                performance = self._calculate_staff_performance(
                    sid,
                    staff_feedback_list,
                    start_date,
                    end_date
                )
                performances.append(performance)

            # 按服务得分排序
            performances.sort(key=lambda x: x["service_score"], reverse=True)

            self.logger.info(
                "staff_performance_tracked",
                total_staff=len(performances),
                staff_id=staff_id
            )

            return performances

        except Exception as e:
            self.logger.error("track_staff_performance_failed", error=str(e))
            raise

    def _calculate_staff_performance(
        self,
        staff_id: str,
        feedbacks: List[CustomerFeedback],
        start_date: Optional[str],
        end_date: Optional[str]
    ) -> StaffPerformance:
        """计算员工表现"""
        total_feedbacks = len(feedbacks)
        praise_count = sum(1 for f in feedbacks if f["feedback_type"] == FeedbackType.PRAISE)
        complaint_count = sum(1 for f in feedbacks if f["feedback_type"] == FeedbackType.COMPLAINT)

        ratings = [f["rating"] for f in feedbacks]
        average_rating = mean(ratings)

        # 计算服务得分(0-100)
        # 基础分60 + 平均评分*8 - 投诉数*2 + 表扬数*1
        service_score = float(os.getenv("SERVICE_SCORE_BASE", "60")) + (average_rating * float(os.getenv("SERVICE_SCORE_RATING_WEIGHT", "8"))) - (complaint_count * float(os.getenv("SERVICE_SCORE_COMPLAINT_DEDUCT", "2"))) + (praise_count * float(os.getenv("SERVICE_SCORE_PRAISE_ADD", "1")))
        service_score = max(0, min(100, service_score))

        # 识别改进领域
        improvement_areas = self._identify_improvement_areas(feedbacks)

        performance: StaffPerformance = {
            "staff_id": staff_id,
            "staff_name": f"员工{staff_id[-3:]}",  # 模拟员工姓名
            "store_id": self.store_id,
            "period_start": start_date or (datetime.now() - timedelta(days=int(os.getenv("AGENT_STATS_DAYS", "30")))).isoformat(),
            "period_end": end_date or datetime.now().isoformat(),
            "total_feedbacks": total_feedbacks,
            "praise_count": praise_count,
            "complaint_count": complaint_count,
            "average_rating": round(average_rating, 2),
            "service_score": round(service_score, 2),"improvement_areas": improvement_areas
        }

        return performance

    def _identify_improvement_areas(self, feedbacks: List[CustomerFeedback]) -> List[str]:
        """识别改进领域"""
        # 统计负面反馈的分类
        negative_feedbacks = [
            f for f in feedbacks
            if f["rating"] <= 3 or f["feedback_type"] == FeedbackType.COMPLAINT
        ]

        if not negative_feedbacks:
            return []

        category_counts = defaultdict(int)
        for feedback in negative_feedbacks:
            category_counts[feedback["category"]] += 1

        # 返回出现次数最多的前3个分类
        sorted_categories = sorted(
            category_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )

        improvement_areas = [cat for cat, _ in sorted_categories[:3]]
        return improvement_areas

    async def generate_improvements(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[ServiceImprovement]:
        """
        生成服务改进建议

        Args:
            start_date: 开始日期(ISO格式)
            end_date: 结束日期(ISO格式)

        Returns:
            改进建议列表
        """
        self.logger.info(
            "generating_improvements",
            start_date=start_date,
            end_date=end_date
        )

        try:
            # 获取服务质量指标
            metrics = await self.monitor_service_quality(start_date, end_date)

            # 收集反馈
            feedbacks = await self.collect_feedback(start_date, end_date)

            improvements = []

            # 基于分类统计生成改进建议
            for category, count in metrics["category_breakdown"].items():
                if count >= int(os.getenv("SERVICE_MIN_FEEDBACK_COUNT", "5")):  # 至少5条反馈才生成建议
                    # 分析该分类的负面反馈
                    category_feedbacks = [
                        f for f in feedbacks
                        if f["category"] == category and f["rating"] <= 3
                    ]

                    if category_feedbacks:
                        improvement = self._create_improvement_suggestion(
                            category,
                            category_feedbacks,
                            metrics
                        )
                        improvements.append(improvement)

            # 基于整体趋势生成建议
            if metrics["trend"] == "declining":
                improvement = self._create_trend_improvement(metrics)
                improvements.append(improvement)

            # 按优先级排序
            improvements.sort(
                key=lambda x: ["low", "medium", "high", "urgent"].index(x["priority"]),
                reverse=True
            )

            self.logger.info(
                "improvements_generated",
                total_improvements=len(improvements)
            )

            return improvements

        except Exception as e:
            self.logger.error("generate_improvements_failed", error=str(e))
            raise

    def _create_improvement_suggestion(
        self,
        category: str,
        feedbacks: List[CustomerFeedback],
        metrics: ServiceQualityMetrics
    ) -> ServiceImprovement:
        """创建改进建议"""
        # 分析根本原因
        common_keywords = defaultdict(int)
        for feedback in feedbacks:
            keywords = self._extract_keywords(feedback["content"])
            for keyword in keywords:
                common_keywords[keyword] += 1

        root_cause = f"该分类收到{len(feedbacks)}条负面反馈,主要关键词: {', '.join(list(common_keywords.keys())[:3])}"

        # 生成建议
        recommendations = {
            ServiceCategory.FOOD_QUALITY: "1. 加强食材质量检查 2. 优化菜品制作流程 3. 定期培训厨师 4. 收集客户口味偏好",
            ServiceCategory.SERVICE_ATTITUDE: "1. 加强服务礼仪培训 2. 建立服务标准流程 3. 设立服务质量奖励机制 4. 定期服务技能考核",
            ServiceCategory.ENVIRONMENT: "1. 增加清洁频次 2. 改善通风和照明 3. 更新老旧设施 4. 加强卫生检查",
            ServiceCategory.WAITING_TIME: "1. 优化点餐流程 2. 增加高峰期人手 3. 改进厨房效率 4. 提供等待时的服务",
            ServiceCategory.PRICE: "1. 优化菜品定价策略 2. 推出更多优惠活动 3. 提升菜品性价比 4. 加强价值传播",
            ServiceCategory.OTHER: "1. 详细分析具体问题 2. 制定针对性改进方案 3. 持续跟进改进效果"
        }

        recommendation = recommendations.get(category, recommendations[ServiceCategory.OTHER])

        # 评估优先级
        negative_rate = len(feedbacks) / metrics["total_feedbacks"]
        if negative_rate > float(os.getenv("SERVICE_NEGATIVE_RATE_URGENT", "0.2")):
            priority = ComplaintPriority.URGENT
        elif negative_rate > float(os.getenv("SERVICE_NEGATIVE_RATE_HIGH", "0.1")):
            priority = ComplaintPriority.HIGH
        elif negative_rate > float(os.getenv("SERVICE_NEGATIVE_RATE_MEDIUM", "0.05")):
            priority = ComplaintPriority.MEDIUM
        else:
            priority = ComplaintPriority.LOW

        # 预估影响
        estimated_impact = f"预计可提升{category}分类满意度10-20%,整体满意度提升3-5%"

        improvement: ServiceImprovement = {
            "improvement_id": f"IMP_{category}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "store_id": self.store_id,
            "category": category,
            "issue": f"{category}分类存在{len(feedbacks)}条负面反馈",
            "root_cause": root_cause,
            "recommendation": recommendation,
            "priority": priority,
            "estimated_impact": estimated_impact,
            "created_at": datetime.now().isoformat()
        }

        return improvement

    def _create_trend_improvement(self, metrics: ServiceQualityMetrics) -> ServiceImprovement:
        """创建趋势改进建议"""
        improvement: ServiceImprovement = {
            "improvement_id": f"IMP_TREND_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "store_id": self.store_id,
            "category": ServiceCategory.OTHER,
            "issue": "整体服务质量呈下降趋势",
            "root_cause": f"满意度{metrics['satisfaction_rate']:.2%},投诉率{metrics['complaint_rate']:.2%},趋势为{metrics['trend']}",
            "recommendation": "1. 召开服务质量分析会议 2. 全面检查各项服务流程 3. 加强员工培训 4. 建立服务质量监控机制 5. 定期收集客户反馈",
            "priority": ComplaintPriority.URGENT,
            "estimated_impact": "扭转下降趋势,恢复服务质量到正常水平",
            "created_at": datetime.now().isoformat()
        }

        return improvement

    async def get_service_report(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取服务综合报告

        Args:
            start_date: 开始日期(ISO格式)
            end_date: 结束日期(ISO格式)

        Returns:
            服务报告
        """
        self.logger.info(
            "generating_service_report",
            start_date=start_date,
            end_date=end_date
        )

        try:
            # 并发执行多个任务
            quality_task = self.monitor_service_quality(start_date, end_date)
            staff_task = self.track_staff_performance(start_date=start_date, end_date=end_date)
            improvements_task = self.generate_improvements(start_date, end_date)

            quality_metrics, staff_performances, improvements = await asyncio.gather(
                quality_task,
                staff_task,
                improvements_task
            )

            # 收集投诉数据
            feedbacks = await self.collect_feedback(start_date, end_date)
            complaints = [
                f for f in feedbacks
                if f["feedback_type"] == FeedbackType.COMPLAINT
            ]

            report = {
                "store_id": self.store_id,
                "report_date": datetime.now().isoformat(),
                "period_start": start_date or (datetime.now() - timedelta(days=int(os.getenv("AGENT_STATS_DAYS", "30")))).isoformat(),
                "period_end": end_date or datetime.now().isoformat(),
                "quality_metrics": quality_metrics,
                "staff_performances": staff_performances,
                "top_performers": staff_performances[:5] if staff_performances else [],
                "improvements": improvements,
                "urgent_improvements": [
                    i for i in improvements
                    if i["priority"] == ComplaintPriority.URGENT
                ],
                "complaints_summary": {
                    "total": len(complaints),
                    "urgent": sum(1 for c in complaints if c["rating"] == 1),
                    "categories": dict(defaultdict(int, {
                        c["category"]: sum(1 for f in complaints if f["category"] == c["category"])
                        for c in complaints
                    }))
                }
            }

            self.logger.info(
                "service_report_generated",
                satisfaction_rate=quality_metrics["satisfaction_rate"],
                total_staff=len(staff_performances),
                total_improvements=len(improvements)
            )

            return report

        except Exception as e:
            self.logger.error("get_service_report_failed", error=str(e))
            raise

    def _generate_mock_feedbacks(
        self,
        start_date: Optional[str],
        end_date: Optional[str]
    ) -> List[CustomerFeedback]:
        """生成模拟反馈数据"""
        import random

        mock_feedbacks = []
        base_date = datetime.now() - timedelta(days=int(os.getenv("SERVICE_TREND_DAYS", "7")))

        feedback_templates = [
            {
                "type": FeedbackType.PRAISE,
                "category": ServiceCategory.FOOD_QUALITY,
                "rating": 5,
                "content": "菜品非常美味,食材新鲜,味道很棒!"
            },
            {
                "type": FeedbackType.PRAISE,
                "category": ServiceCategory.SERVICE_ATTITUDE,
                "rating": 5,
                "content": "服务员态度很好,服务周到,非常满意!"
            },
            {
                "type": FeedbackType.COMPLAINT,
                "category": ServiceCategory.WAITING_TIME,
                "rating": 2,
                "content": "等待时间太长了,上菜很慢,希望改进"
            },
            {
                "type": FeedbackType.COMPLAINT,
                "category": ServiceCategory.FOOD_QUALITY,
                "rating": 1,
                "content": "菜品质量差,味道不好,非常失望"
            },
            {
                "type": FeedbackType.SUGGESTION,
                "category": ServiceCategory.ENVIRONMENT,
                "rating": 3,
                "content": "环境还可以,但是卫生需要加强"
            },
            {
                "type": FeedbackType.COMPLAINT,
                "category": ServiceCategory.SERVICE_ATTITUDE,
                "rating": 2,
                "content": "服务员态度不好,不够热情"
            },
            {
                "type": FeedbackType.PRAISE,
                "category": ServiceCategory.ENVIRONMENT,
                "rating": 5,
                "content": "环境很好,装修漂亮,氛围舒适"
            },
            {
                "type": FeedbackType.SUGGESTION,
                "category": ServiceCategory.PRICE,
                "rating": 3,
                "content": "价格有点贵,希望能有更多优惠活动"
            },
        ]

        for i in range(50):
            template = random.choice(feedback_templates)
            feedback_date = base_date + timedelta(days=random.randint(0, 7))

            feedback: CustomerFeedback = {
                "feedback_id": f"FB{datetime.now().strftime('%Y%m%d')}{i:04d}",
                "customer_id": f"CUST{random.randint(1000, 9999)}",
                "customer_name": f"客户{random.randint(100, 999)}",
                "store_id": self.store_id,
                "feedback_type": template["type"],
                "category": template["category"],
                "rating": template["rating"],
                "content": template["content"],
                "staff_id": f"STAFF{random.randint(1, 10):03d}" if random.random() > 0.3 else None,
                "order_id": f"ORD{random.randint(10000, 99999)}" if random.random() > 0.2 else None,
                "created_at": feedback_date.isoformat(),
                "source": random.choice(["app", "wechat", "phone", "onsite"])
            }

            mock_feedbacks.append(feedback)

        return mock_feedbacks