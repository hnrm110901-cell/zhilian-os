"""
智能培训Agent单元测试
Unit tests for Intelligent Training Agent
"""

import pytest
from datetime import datetime, timedelta
from src.agent import (
    TrainingAgent,
    TrainingType,
    TrainingStatus,
    SkillLevel,
    AssessmentType,
    TrainingPriority,
    TrainingCourse,
    TrainingNeed,
    TrainingPlan,
    TrainingRecord,
    Assessment,
    Certificate,
    SkillGap
)


@pytest.fixture
def agent():
    """创建测试用的Agent实例"""
    return TrainingAgent(
        store_id="STORE001",
        training_config={
            "min_passing_score": 70,
            "max_training_hours_per_month": 40,
            "certificate_validity_months": 12,
            "mandatory_training_types": [
                TrainingType.SAFETY,
                TrainingType.COMPLIANCE
            ]
        }
    )


@pytest.mark.asyncio
async def test_assess_training_needs_all_staff(agent):
    """测试评估所有员工的培训需求"""
    needs = await agent.assess_training_needs()

    assert isinstance(needs, list)
    if len(needs) > 0:
        need = needs[0]
        assert "need_id" in need
        assert "staff_id" in need
        assert "skill_gap" in need
        assert "priority" in need
        assert "recommended_courses" in need


@pytest.mark.asyncio
async def test_assess_training_needs_specific_staff(agent):
    """测试评估特定员工的培训需求"""
    needs = await agent.assess_training_needs(staff_id="STAFF001")

    assert isinstance(needs, list)


@pytest.mark.asyncio
async def test_assess_training_needs_by_position(agent):
    """测试按岗位评估培训需求"""
    needs = await agent.assess_training_needs(position="服务员")

    assert isinstance(needs, list)


@pytest.mark.asyncio
async def test_generate_training_plan(agent):
    """测试生成培训计划"""
    plan = await agent.generate_training_plan(staff_id="STAFF001")

    assert plan["staff_id"] == "STAFF001"
    assert "plan_id" in plan
    assert "courses" in plan
    assert len(plan["courses"]) > 0
    assert plan["total_hours"] > 0
    assert plan["status"] == TrainingStatus.NOT_STARTED
    assert plan["progress_percentage"] == 0.0


@pytest.mark.asyncio
async def test_generate_training_plan_with_needs(agent):
    """测试基于需求生成培训计划"""
    # 先评估需求
    needs = await agent.assess_training_needs(staff_id="STAFF001")

    # 基于需求生成计划
    if needs:
        plan = await agent.generate_training_plan(
            staff_id="STAFF001",
            training_needs=needs
        )

        assert plan["staff_id"] == "STAFF001"
        assert len(plan["courses"]) > 0


@pytest.mark.asyncio
async def test_track_training_progress_all(agent):
    """测试追踪所有培训进度"""
    records = await agent.track_training_progress()

    assert isinstance(records, list)
    if len(records) > 0:
        record = records[0]
        assert "record_id" in record
        assert "staff_id" in record
        assert "course_id" in record
        assert "status" in record
        assert record["status"] in [
            TrainingStatus.NOT_STARTED,
            TrainingStatus.IN_PROGRESS,
            TrainingStatus.COMPLETED,
            TrainingStatus.EXPIRED,
            TrainingStatus.FAILED
        ]


@pytest.mark.asyncio
async def test_track_training_progress_specific_staff(agent):
    """测试追踪特定员工的培训进度"""
    records = await agent.track_training_progress(staff_id="STAFF001")

    assert isinstance(records, list)


def test_update_record_status_completed(agent):
    """测试更新已完成记录状态"""
    record: TrainingRecord = {
        "record_id": "REC001",
        "staff_id": "STAFF001",
        "course_id": "COURSE001",
        "plan_id": None,
        "start_date": (datetime.now() - timedelta(days=10)).isoformat(),
        "completion_date": datetime.now().isoformat(),
        "status": TrainingStatus.IN_PROGRESS,
        "attendance_hours": 8.0,
        "score": 85,
        "passed": True,
        "feedback": "很好",
        "created_at": (datetime.now() - timedelta(days=10)).isoformat()
    }

    status = agent._update_record_status(record)
    assert status == TrainingStatus.COMPLETED


def test_update_record_status_failed(agent):
    """测试更新未通过记录状态"""
    record: TrainingRecord = {
        "record_id": "REC002",
        "staff_id": "STAFF001",
        "course_id": "COURSE001",
        "plan_id": None,
        "start_date": (datetime.now() - timedelta(days=10)).isoformat(),
        "completion_date": datetime.now().isoformat(),
        "status": TrainingStatus.IN_PROGRESS,
        "attendance_hours": 8.0,
        "score": 60,
        "passed": False,
        "feedback": "需要重新学习",
        "created_at": (datetime.now() - timedelta(days=10)).isoformat()
    }

    status = agent._update_record_status(record)
    assert status == TrainingStatus.FAILED


def test_update_record_status_expired(agent):
    """测试更新过期记录状态"""
    record: TrainingRecord = {
        "record_id": "REC003",
        "staff_id": "STAFF001",
        "course_id": "COURSE001",
        "plan_id": None,
        "start_date": (datetime.now() - timedelta(days=100)).isoformat(),
        "completion_date": None,
        "status": TrainingStatus.IN_PROGRESS,
        "attendance_hours": 4.0,
        "score": None,
        "passed": None,
        "feedback": None,
        "created_at": (datetime.now() - timedelta(days=100)).isoformat()
    }

    status = agent._update_record_status(record)
    assert status == TrainingStatus.EXPIRED


@pytest.mark.asyncio
async def test_evaluate_training_effectiveness(agent):
    """测试评估培训效果"""
    evaluation = await agent.evaluate_training_effectiveness()

    assert "total_participants" in evaluation
    assert "completion_rate" in evaluation
    assert "pass_rate" in evaluation
    assert "average_score" in evaluation
    assert "effectiveness_rating" in evaluation
    assert evaluation["effectiveness_rating"] in [
        "excellent", "good", "satisfactory", "needs_improvement", "poor"
    ]


@pytest.mark.asyncio
async def test_evaluate_training_effectiveness_specific_course(agent):
    """测试评估特定课程的培训效果"""
    evaluation = await agent.evaluate_training_effectiveness(
        course_id="COURSE_SERVICE_001"
    )

    assert evaluation["course_id"] == "COURSE_SERVICE_001"


def test_calculate_effectiveness_rating_excellent(agent):
    """测试优秀评级计算"""
    rating = agent._calculate_effectiveness_rating(0.95, 0.95, 95)
    assert rating == "excellent"


def test_calculate_effectiveness_rating_good(agent):
    """测试良好评级计算"""
    rating = agent._calculate_effectiveness_rating(0.85, 0.85, 85)
    assert rating == "good"


def test_calculate_effectiveness_rating_poor(agent):
    """测试差评级计算"""
    rating = agent._calculate_effectiveness_rating(0.5, 0.5, 50)
    assert rating == "poor"


@pytest.mark.asyncio
async def test_analyze_skill_gaps(agent):
    """测试分析技能差距"""
    gaps = await agent.analyze_skill_gaps(staff_id="STAFF001")

    assert isinstance(gaps, list)
    if len(gaps) > 0:
        gap = gaps[0]
        assert "staff_id" in gap
        assert "skill_name" in gap
        assert "current_level" in gap
        assert "required_level" in gap
        assert "gap_score" in gap
        assert "priority" in gap
        assert 0 <= gap["gap_score"] <= 100


def test_get_position_required_skills_waiter(agent):
    """测试获取服务员岗位要求"""
    skills = agent._get_position_required_skills("服务员")

    assert "服务礼仪" in skills
    assert "客户沟通" in skills
    assert skills["服务礼仪"] == SkillLevel.INTERMEDIATE


def test_get_position_required_skills_chef(agent):
    """测试获取厨师岗位要求"""
    skills = agent._get_position_required_skills("厨师")

    assert "菜品制作" in skills
    assert skills["菜品制作"] == SkillLevel.ADVANCED


def test_calculate_gap_score(agent):
    """测试计算差距分数"""
    # 从初级到中级
    score = agent._calculate_gap_score(SkillLevel.BEGINNER, SkillLevel.INTERMEDIATE)
    assert score == 33

    # 从初级到高级
    score = agent._calculate_gap_score(SkillLevel.BEGINNER, SkillLevel.ADVANCED)
    assert score == 66

    # 从中级到高级
    score = agent._calculate_gap_score(SkillLevel.INTERMEDIATE, SkillLevel.ADVANCED)
    assert score == 33

    # 已达标
    score = agent._calculate_gap_score(SkillLevel.ADVANCED, SkillLevel.INTERMEDIATE)
    assert score == 0


def test_determine_gap_priority_critical_skill(agent):
    """测试关键技能差距优先级"""
    # 关键技能大差距
    priority = agent._determine_gap_priority(66, "食品安全")
    assert priority == TrainingPriority.URGENT

    # 关键技能中等差距
    priority = agent._determine_gap_priority(33, "服务礼仪")
    assert priority == TrainingPriority.HIGH


def test_determine_gap_priority_normal_skill(agent):
    """测试普通技能差距优先级"""
    # 普通技能大差距
    priority = agent._determine_gap_priority(66, "其他技能")
    assert priority == TrainingPriority.HIGH

    # 普通技能小差距
    priority = agent._determine_gap_priority(20, "其他技能")
    assert priority == TrainingPriority.LOW


@pytest.mark.asyncio
async def test_manage_certificates_all(agent):
    """测试管理所有证书"""
    certificates = await agent.manage_certificates()

    assert isinstance(certificates, list)
    if len(certificates) > 0:
        cert = certificates[0]
        assert "certificate_id" in cert
        assert "staff_id" in cert
        assert "course_id" in cert
        assert "issue_date" in cert
        assert "status" in cert


@pytest.mark.asyncio
async def test_manage_certificates_specific_staff(agent):
    """测试管理特定员工的证书"""
    certificates = await agent.manage_certificates(staff_id="STAFF001")

    assert isinstance(certificates, list)


@pytest.mark.asyncio
async def test_manage_certificates_include_expired(agent):
    """测试包含过期证书"""
    certificates = await agent.manage_certificates(include_expired=True)

    assert isinstance(certificates, list)


def test_check_certificate_status_valid(agent):
    """测试有效证书状态"""
    cert: Certificate = {
        "certificate_id": "CERT001",
        "staff_id": "STAFF001",
        "staff_name": "张三",
        "course_id": "COURSE001",
        "course_name": "课程1",
        "issue_date": datetime.now().isoformat(),
        "expiry_date": (datetime.now() + timedelta(days=365)).isoformat(),
        "certificate_url": "https://example.com/cert001",
        "status": "valid"
    }

    status = agent._check_certificate_status(cert)
    assert status == "valid"


def test_check_certificate_status_expired(agent):
    """测试过期证书状态"""
    cert: Certificate = {
        "certificate_id": "CERT002",
        "staff_id": "STAFF001",
        "staff_name": "张三",
        "course_id": "COURSE001",
        "course_name": "课程1",
        "issue_date": (datetime.now() - timedelta(days=400)).isoformat(),
        "expiry_date": (datetime.now() - timedelta(days=10)).isoformat(),
        "certificate_url": "https://example.com/cert002",
        "status": "valid"
    }

    status = agent._check_certificate_status(cert)
    assert status == "expired"


@pytest.mark.asyncio
async def test_issue_certificate(agent):
    """测试颁发证书"""
    # 先获取一个已完成的培训记录
    records = await agent._get_training_records(staff_id="STAFF001")
    completed_records = [r for r in records if r.get("passed")]

    if completed_records:
        record = completed_records[0]
        certificate = await agent.issue_certificate(
            staff_id=record["staff_id"],
            course_id=record["course_id"],
            record_id=record["record_id"]
        )

        assert certificate["staff_id"] == record["staff_id"]
        assert certificate["course_id"] == record["course_id"]
        assert certificate["status"] == "valid"
        assert certificate["expiry_date"] is not None


@pytest.mark.asyncio
async def test_get_training_report(agent):
    """测试获取培训综合报告"""
    report = await agent.get_training_report()

    assert report["store_id"] == "STORE001"
    assert "report_date" in report
    assert "training_needs" in report
    assert "training_progress" in report
    assert "training_effectiveness" in report
    assert "certificates" in report

    # 检查培训需求
    needs = report["training_needs"]
    assert "total" in needs
    assert "urgent" in needs
    assert "high" in needs

    # 检查培训进度
    progress = report["training_progress"]
    assert "total_records" in progress
    assert "status_distribution" in progress
    assert "completion_rate" in progress

    # 检查证书
    certs = report["certificates"]
    assert "total" in certs
    assert "valid" in certs


@pytest.mark.asyncio
async def test_concurrent_operations(agent):
    """测试并发操作"""
    import asyncio

    # 同时执行多个操作
    tasks = [
        agent.assess_training_needs(),
        agent.track_training_progress(),
        agent.manage_certificates()
    ]

    results = await asyncio.gather(*tasks)

    assert len(results) == 3
    assert isinstance(results[0], list)  # needs
    assert isinstance(results[1], list)  # records
    assert isinstance(results[2], list)  # certificates


def test_recommend_courses_for_skill(agent):
    """测试为技能推荐课程"""
    courses = agent._recommend_courses_for_skill(
        "菜品制作",
        SkillLevel.BEGINNER,
        SkillLevel.INTERMEDIATE
    )

    assert len(courses) > 0
    assert isinstance(courses, list)


@pytest.mark.asyncio
async def test_get_courses_info(agent):
    """测试获取课程信息"""
    courses = await agent._get_courses_info(["COURSE_SERVICE_001", "COURSE_COOKING_001"])

    assert len(courses) == 2
    assert all("course_id" in c for c in courses)
    assert all("course_name" in c for c in courses)
    assert all("duration_hours" in c for c in courses)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
