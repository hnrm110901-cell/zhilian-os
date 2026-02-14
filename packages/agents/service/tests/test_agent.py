"""
智能服务Agent单元测试
Unit tests for Intelligent Service Agent
"""

import pytest
from datetime import datetime, timedelta
from src.agent import (
    ServiceAgent,
    FeedbackType,
    ComplaintPriority,
    ComplaintStatus,
    ServiceCategory,
    SatisfactionLevel,
    CustomerFeedback,
    Complaint,
    StaffPerformance,
    ServiceQualityMetrics,
    ServiceImprovement
)


@pytest.fixture
def agent():
    """创建测试用的Agent实例"""
    return ServiceAgent(
        store_id="STORE001",
        aoqiwei_adapter=None,  # 使用模拟数据
        quality_thresholds={
            "min_satisfaction_rate": 0.85,
            "max_complaint_rate": 0.05,
            "max_response_time": 30,
            "min_resolution_rate": 0.90,
        }
    )


@pytest.fixture
def sample_feedback():
    """创建示例反馈"""
    feedback: CustomerFeedback = {
        "feedback_id": "FB001",
        "customer_id": "CUST001",
        "customer_name": "张三",
        "store_id": "STORE001",
        "feedback_type": FeedbackType.COMPLAINT,
        "category": ServiceCategory.FOOD_QUALITY,
        "rating": 2,
        "content": "菜品质量差,味道不好,非常失望",
        "staff_id": "STAFF001",
        "order_id": "ORD001",
        "created_at": datetime.now().isoformat(),
        "source": "app"
    }
    return feedback


@pytest.mark.asyncio
async def test_collect_feedback_all(agent):
    """测试收集所有反馈"""
    feedbacks = await agent.collect_feedback()

    assert len(feedbacks) > 0
    assert all("feedback_id" in f for f in feedbacks)
    assert all("customer_id" in f for f in feedbacks)
    assert all("feedback_type" in f for f in feedbacks)


@pytest.mark.asyncio
async def test_collect_feedback_by_type(agent):
    """测试按类型收集反馈"""
    feedbacks = await agent.collect_feedback(feedback_type=FeedbackType.COMPLAINT)

    assert len(feedbacks) > 0
    assert all(f["feedback_type"] == FeedbackType.COMPLAINT for f in feedbacks)


@pytest.mark.asyncio
async def test_collect_feedback_by_date_range(agent):
    """测试按日期范围收集反馈"""
    start_date = (datetime.now() - timedelta(days=7)).isoformat()
    end_date = datetime.now().isoformat()

    feedbacks = await agent.collect_feedback(start_date=start_date, end_date=end_date)

    assert isinstance(feedbacks, list)


@pytest.mark.asyncio
async def test_analyze_feedback(agent, sample_feedback):
    """测试分析反馈"""
    analysis = await agent.analyze_feedback(sample_feedback)

    assert analysis["feedback_id"] == sample_feedback["feedback_id"]
    assert "sentiment" in analysis
    assert analysis["sentiment"] in ["positive", "negative", "neutral"]
    assert "keywords" in analysis
    assert "category" in analysis
    assert "priority" in analysis
    assert "requires_action" in analysis


@pytest.mark.asyncio
async def test_analyze_sentiment_positive(agent):
    """测试正面情感分析"""
    sentiment = agent._analyze_sentiment("服务很好,非常满意!", 5)
    assert sentiment == "positive"


@pytest.mark.asyncio
async def test_analyze_sentiment_negative(agent):
    """测试负面情感分析"""
    sentiment = agent._analyze_sentiment("服务差,很失望", 1)
    assert sentiment == "negative"


@pytest.mark.asyncio
async def test_analyze_sentiment_neutral(agent):
    """测试中性情感分析"""
    sentiment = agent._analyze_sentiment("还可以", 3)
    assert sentiment == "neutral"


def test_extract_keywords(agent):
    """测试关键词提取"""
    keywords = agent._extract_keywords("菜品味道不错,服务态度很好,环境也很舒适")
    assert len(keywords) > 0
    assert any(kw in ["菜品", "服务", "环境"] for kw in keywords)


def test_classify_feedback_food_quality(agent):
    """测试菜品质量分类"""
    category = agent._classify_feedback(
        "菜品味道不好,食材不新鲜",
        ServiceCategory.OTHER
    )
    assert category == ServiceCategory.FOOD_QUALITY


def test_classify_feedback_service_attitude(agent):
    """测试服务态度分类"""
    category = agent._classify_feedback(
        "服务员态度不好,不够热情",
        ServiceCategory.OTHER
    )
    assert category == ServiceCategory.SERVICE_ATTITUDE


def test_assess_priority_urgent(agent):
    """测试紧急优先级评估"""
    feedback: CustomerFeedback = {
        "feedback_id": "FB001",
        "customer_id": "CUST001",
        "customer_name": "张三",
        "store_id": "STORE001",
        "feedback_type": FeedbackType.COMPLAINT,
        "category": ServiceCategory.FOOD_QUALITY,
        "rating": 1,
        "content": "食物中毒,立即处理!",
        "staff_id": None,
        "order_id": None,
        "created_at": datetime.now().isoformat(),
        "source": "phone"
    }

    priority = agent._assess_priority(feedback)
    assert priority == ComplaintPriority.URGENT


def test_assess_priority_high(agent):
    """测试高优先级评估"""
    feedback: CustomerFeedback = {
        "feedback_id": "FB002",
        "customer_id": "CUST002",
        "customer_name": "李四",
        "store_id": "STORE001",
        "feedback_type": FeedbackType.COMPLAINT,
        "category": ServiceCategory.SERVICE_ATTITUDE,
        "rating": 2,
        "content": "服务态度很差",
        "staff_id": None,
        "order_id": None,
        "created_at": datetime.now().isoformat(),
        "source": "app"
    }

    priority = agent._assess_priority(feedback)
    assert priority == ComplaintPriority.HIGH


def test_assess_priority_low_for_praise(agent):
    """测试表扬的优先级"""
    feedback: CustomerFeedback = {
        "feedback_id": "FB003",
        "customer_id": "CUST003",
        "customer_name": "王五",
        "store_id": "STORE001",
        "feedback_type": FeedbackType.PRAISE,
        "category": ServiceCategory.SERVICE_ATTITUDE,
        "rating": 5,
        "content": "服务很好!",
        "staff_id": None,
        "order_id": None,
        "created_at": datetime.now().isoformat(),
        "source": "wechat"
    }

    priority = agent._assess_priority(feedback)
    assert priority == ComplaintPriority.LOW


@pytest.mark.asyncio
async def test_handle_complaint(agent, sample_feedback):
    """测试处理投诉"""
    complaint = await agent.handle_complaint(sample_feedback)

    assert complaint["complaint_id"].startswith("COMP_")
    assert complaint["feedback_id"] == sample_feedback["feedback_id"]
    assert complaint["status"] == ComplaintStatus.IN_PROGRESS
    assert complaint["priority"] in [
        ComplaintPriority.LOW,
        ComplaintPriority.MEDIUM,
        ComplaintPriority.HIGH,
        ComplaintPriority.URGENT
    ]
    assert complaint["resolution"] is not None
    assert complaint["compensation"] is not None
    assert complaint["assigned_to"] is not None


def test_generate_resolution_suggestion_food_quality(agent):
    """测试菜品质量解决方案"""
    complaint: Complaint = {
        "complaint_id": "COMP001",
        "feedback_id": "FB001",
        "customer_id": "CUST001",
        "store_id": "STORE001",
        "category": ServiceCategory.FOOD_QUALITY,
        "priority": ComplaintPriority.HIGH,
        "status": ComplaintStatus.PENDING,
        "description": "菜品质量差",
        "staff_id": None,
        "assigned_to": None,
        "resolution": None,
        "compensation": None,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "resolved_at": None
    }

    resolution = agent._generate_resolution_suggestion(complaint)
    assert "道歉" in resolution
    assert "菜品" in resolution


def test_generate_compensation_urgent(agent):
    """测试紧急投诉补偿方案"""
    complaint: Complaint = {
        "complaint_id": "COMP001",
        "feedback_id": "FB001",
        "customer_id": "CUST001",
        "store_id": "STORE001",
        "category": ServiceCategory.FOOD_QUALITY,
        "priority": ComplaintPriority.URGENT,
        "status": ComplaintStatus.PENDING,
        "description": "食物中毒",
        "staff_id": None,
        "assigned_to": None,
        "resolution": None,
        "compensation": None,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "resolved_at": None
    }

    compensation = agent._generate_compensation_suggestion(complaint)
    assert compensation["amount_fen"] > 0
    assert compensation["type"] in ["refund_and_coupon", "coupon"]


def test_auto_assign_handler_urgent(agent):
    """测试紧急投诉自动分配"""
    complaint: Complaint = {
        "complaint_id": "COMP001",
        "feedback_id": "FB001",
        "customer_id": "CUST001",
        "store_id": "STORE001",
        "category": ServiceCategory.FOOD_QUALITY,
        "priority": ComplaintPriority.URGENT,
        "status": ComplaintStatus.PENDING,
        "description": "紧急问题",
        "staff_id": None,
        "assigned_to": None,
        "resolution": None,
        "compensation": None,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "resolved_at": None
    }

    handler = agent._auto_assign_handler(complaint)
    assert handler == "MANAGER_001"  # 紧急投诉分配给店长


@pytest.mark.asyncio
async def test_monitor_service_quality(agent):
    """测试监控服务质量"""
    metrics = await agent.monitor_service_quality()

    assert metrics["store_id"] == "STORE001"
    assert metrics["total_feedbacks"] > 0
    assert 0 <= metrics["average_rating"] <= 5
    assert 0 <= metrics["satisfaction_rate"] <= 1
    assert 0 <= metrics["complaint_rate"] <= 1
    assert metrics["response_time_avg"] > 0
    assert 0 <= metrics["resolution_rate"] <= 1
    assert "category_breakdown" in metrics
    assert metrics["trend"] in ["improving", "stable", "declining"]


def test_analyze_trend_improving(agent):
    """测试上升趋势分析"""
    # 创建评分逐渐提高的反馈
    feedbacks = []
    for i in range(20):
        rating = 3 if i < 10 else 4  # 后半段评分更高
        feedback: CustomerFeedback = {
            "feedback_id": f"FB{i:03d}",
            "customer_id": f"CUST{i:03d}",
            "customer_name": f"客户{i}",
            "store_id": "STORE001",
            "feedback_type": FeedbackType.PRAISE,
            "category": ServiceCategory.SERVICE_ATTITUDE,
            "rating": rating,
            "content": "测试",
            "staff_id": None,
            "order_id": None,
            "created_at": (datetime.now() - timedelta(days=20-i)).isoformat(),
            "source": "app"
        }
        feedbacks.append(feedback)

    trend = agent._analyze_trend(feedbacks)
    assert trend == "improving"


@pytest.mark.asyncio
async def test_track_staff_performance_all(agent):
    """测试追踪所有员工表现"""
    performances = await agent.track_staff_performance()

    assert isinstance(performances, list)
    if len(performances) > 0:
        perf = performances[0]
        assert "staff_id" in perf
        assert "total_feedbacks" in perf
        assert "praise_count" in perf
        assert "complaint_count" in perf
        assert "average_rating" in perf
        assert "service_score" in perf
        assert 0 <= perf["service_score"] <= 100


@pytest.mark.asyncio
async def test_track_staff_performance_specific(agent):
    """测试追踪特定员工表现"""
    performances = await agent.track_staff_performance(staff_id="STAFF001")

    assert isinstance(performances, list)


def test_identify_improvement_areas(agent):
    """测试识别改进领域"""
    feedbacks = [
        {
            "feedback_id": "FB001",
            "customer_id": "CUST001",
            "customer_name": "客户1",
            "store_id": "STORE001",
            "feedback_type": FeedbackType.COMPLAINT,
            "category": ServiceCategory.FOOD_QUALITY,
            "rating": 2,
            "content": "菜品不好",
            "staff_id": "STAFF001",
            "order_id": None,
            "created_at": datetime.now().isoformat(),
            "source": "app"
        },
        {
            "feedback_id": "FB002",
            "customer_id": "CUST002",
            "customer_name": "客户2",
            "store_id": "STORE001",
            "feedback_type": FeedbackType.COMPLAINT,
            "category": ServiceCategory.FOOD_QUALITY,
            "rating": 2,
            "content": "菜品不好",
            "staff_id": "STAFF001",
            "order_id": None,
            "created_at": datetime.now().isoformat(),
            "source": "app"
        },
        {
            "feedback_id": "FB003",
            "customer_id": "CUST003",
            "customer_name": "客户3",
            "store_id": "STORE001",
            "feedback_type": FeedbackType.COMPLAINT,
            "category": ServiceCategory.SERVICE_ATTITUDE,
            "rating": 2,
            "content": "服务不好",
            "staff_id": "STAFF001",
            "order_id": None,
            "created_at": datetime.now().isoformat(),
            "source": "app"
        }
    ]

    areas = agent._identify_improvement_areas(feedbacks)
    assert len(areas) > 0
    assert ServiceCategory.FOOD_QUALITY in areas


@pytest.mark.asyncio
async def test_generate_improvements(agent):
    """测试生成改进建议"""
    improvements = await agent.generate_improvements()

    assert isinstance(improvements, list)
    if len(improvements) > 0:
        improvement = improvements[0]
        assert "improvement_id" in improvement
        assert "category" in improvement
        assert "issue" in improvement
        assert "root_cause" in improvement
        assert "recommendation" in improvement
        assert "priority" in improvement
        assert "estimated_impact" in improvement


@pytest.mark.asyncio
async def test_get_service_report(agent):
    """测试获取服务综合报告"""
    report = await agent.get_service_report()

    assert report["store_id"] == "STORE001"
    assert "report_date" in report
    assert "quality_metrics" in report
    assert "staff_performances" in report
    assert "top_performers" in report
    assert "improvements" in report
    assert "urgent_improvements" in report
    assert "complaints_summary" in report

    # 检查质量指标
    quality = report["quality_metrics"]
    assert quality["total_feedbacks"] > 0

    # 检查投诉摘要
    complaints = report["complaints_summary"]
    assert "total" in complaints
    assert "urgent" in complaints


@pytest.mark.asyncio
async def test_concurrent_operations(agent):
    """测试并发操作"""
    import asyncio

    # 同时执行多个操作
    tasks = [
        agent.collect_feedback(),
        agent.monitor_service_quality(),
        agent.track_staff_performance()
    ]

    results = await asyncio.gather(*tasks)

    assert len(results) == 3
    assert isinstance(results[0], list)  # feedbacks
    assert isinstance(results[1], dict)  # quality_metrics
    assert isinstance(results[2], list)  # staff_performances


def test_generate_mock_feedbacks(agent):
    """测试生成模拟反馈数据"""
    feedbacks = agent._generate_mock_feedbacks(None, None)

    assert len(feedbacks) > 0
    assert all("feedback_id" in f for f in feedbacks)
    assert all("feedback_type" in f for f in feedbacks)
    assert all(1 <= f["rating"] <= 5 for f in feedbacks)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
