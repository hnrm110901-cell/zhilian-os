"""
培训认证API — 课程/报名/学习/考试/师徒/看板
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, date
import uuid as uuid_mod
import structlog

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.user import User
from ..models.training import TrainingCourse, TrainingEnrollment, TrainingExam, ExamAttempt
from ..models.mentorship import Mentorship
from ..models.employee import Employee
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()
router = APIRouter()


# ── 课程管理 ──

class CourseRequest(BaseModel):
    brand_id: str
    store_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    category: str = "safety"
    course_type: str = "online"
    applicable_positions: Optional[List[str]] = None
    duration_minutes: int = 60
    content_url: Optional[str] = None
    pass_score: int = 60
    credits: int = 1
    is_mandatory: bool = False


@router.get("/hr/training/courses")
async def list_courses(
    brand_id: str = Query(...),
    category: Optional[str] = Query(None),
    store_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """课程列表（按岗位/分类筛选）"""
    query = select(TrainingCourse).where(
        and_(
            TrainingCourse.brand_id == brand_id,
            TrainingCourse.is_active.is_(True),
        )
    )
    if category:
        query = query.where(TrainingCourse.category == category)
    query = query.order_by(TrainingCourse.sort_order, TrainingCourse.created_at.desc())

    result = await db.execute(query)
    courses = result.scalars().all()

    return {
        "items": [
            {
                "id": str(c.id),
                "title": c.title,
                "description": c.description,
                "category": c.category,
                "course_type": c.course_type,
                "applicable_positions": c.applicable_positions,
                "duration_minutes": c.duration_minutes,
                "pass_score": c.pass_score,
                "credits": c.credits,
                "is_mandatory": c.is_mandatory,
                "content_url": c.content_url,
            }
            for c in courses
        ],
        "total": len(courses),
    }


@router.post("/hr/training/courses")
async def create_course(
    req: CourseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """创建培训课程"""
    course = TrainingCourse(
        brand_id=req.brand_id,
        store_id=req.store_id,
        title=req.title,
        description=req.description,
        category=req.category,
        course_type=req.course_type,
        applicable_positions=req.applicable_positions,
        duration_minutes=req.duration_minutes,
        content_url=req.content_url,
        pass_score=req.pass_score,
        credits=req.credits,
        is_mandatory=req.is_mandatory,
    )
    db.add(course)
    await db.commit()
    return {"id": str(course.id), "message": "课程创建成功"}


# ── 报名/学习进度 ──

@router.post("/hr/training/courses/{course_id}/enroll")
async def enroll_course(
    course_id: str,
    employee_ids: List[str] = Query(..., description="员工ID列表"),
    store_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """报名/指派课程"""
    enrolled = 0
    skipped = 0
    course_uuid = uuid_mod.UUID(course_id)
    for emp_id in employee_ids:
        existing = await db.execute(
            select(TrainingEnrollment).where(
                and_(
                    TrainingEnrollment.employee_id == emp_id,
                    TrainingEnrollment.course_id == course_uuid,
                )
            )
        )
        if existing.scalar_one_or_none():
            skipped += 1
            continue

        enrollment = TrainingEnrollment(
            store_id=store_id,
            employee_id=emp_id,
            course_id=course_uuid,
        )
        db.add(enrollment)
        enrolled += 1

    await db.commit()
    return {"enrolled": enrolled, "skipped": skipped}


@router.get("/hr/training/my-courses")
async def my_courses(
    employee_id: str = Query(...),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """我的课程（含进度）"""
    query = select(TrainingEnrollment, TrainingCourse).join(
        TrainingCourse, TrainingEnrollment.course_id == TrainingCourse.id
    ).where(TrainingEnrollment.employee_id == employee_id)
    if status:
        query = query.where(TrainingEnrollment.status == status)

    result = await db.execute(query)
    rows = result.all()

    return {
        "items": [
            {
                "enrollment_id": str(e.id),
                "course_id": str(c.id),
                "course_title": c.title,
                "category": c.category,
                "course_type": c.course_type,
                "status": e.status,
                "progress_pct": e.progress_pct,
                "score": e.score,
                "certificate_no": e.certificate_no,
                "enrolled_at": e.enrolled_at.isoformat() if e.enrolled_at else None,
                "completed_at": e.completed_at.isoformat() if e.completed_at else None,
                "credits": c.credits,
                "is_mandatory": c.is_mandatory,
            }
            for e, c in rows
        ]
    }


@router.put("/hr/training/enrollments/{enrollment_id}/progress")
async def update_progress(
    enrollment_id: str,
    progress_pct: int = Query(..., ge=0, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """更新学习进度"""
    enrollment = await db.get(TrainingEnrollment, uuid_mod.UUID(enrollment_id))
    if not enrollment:
        raise HTTPException(status_code=404, detail="报名记录不存在")

    enrollment.progress_pct = progress_pct
    if enrollment.status == "enrolled" and progress_pct > 0:
        enrollment.status = "in_progress"
        enrollment.started_at = datetime.utcnow()

    await db.commit()
    return {"id": str(enrollment.id), "progress_pct": progress_pct, "status": enrollment.status}


@router.post("/hr/training/enrollments/{enrollment_id}/complete")
async def complete_enrollment(
    enrollment_id: str,
    score: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """完成学习 + 触发里程碑"""
    enrollment = await db.get(TrainingEnrollment, uuid_mod.UUID(enrollment_id))
    if not enrollment:
        raise HTTPException(status_code=404, detail="报名记录不存在")

    # 获取课程信息
    course = await db.get(TrainingCourse, enrollment.course_id)

    enrollment.status = "completed"
    enrollment.progress_pct = 100
    enrollment.completed_at = datetime.utcnow()
    if score is not None:
        enrollment.score = score
        if course and score < course.pass_score:
            enrollment.status = "failed"

    # 生成证书编号
    if enrollment.status == "completed":
        enrollment.certificate_no = f"CERT-{enrollment.employee_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        enrollment.certified_at = date.today()

        # 创建培训完成里程碑
        try:
            from ..models.employee_growth import EmployeeMilestone, MilestoneType
            milestone = EmployeeMilestone(
                store_id=enrollment.store_id,
                employee_id=enrollment.employee_id,
                milestone_type=MilestoneType.TRAINING_COMPLETE,
                title=f"完成培训：{course.title}" if course else "培训完成",
                description=f"考试成绩：{score}分" if score else None,
                achieved_at=datetime.utcnow(),
                badge_icon="📜",
            )
            db.add(milestone)
        except Exception as e:
            logger.warning("training_milestone_create_failed", error=str(e))

    await db.commit()
    return {
        "id": str(enrollment.id),
        "status": enrollment.status,
        "certificate_no": enrollment.certificate_no,
    }


# ── 考试 ──

@router.post("/hr/training/exams/{exam_id}/submit")
async def submit_exam(
    exam_id: str,
    employee_id: str = Query(...),
    store_id: str = Query(...),
    answers: dict = {},
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """提交考试答案"""
    exam = await db.get(TrainingExam, uuid_mod.UUID(exam_id))
    if not exam:
        raise HTTPException(status_code=404, detail="考试不存在")

    # 计算分数
    questions = exam.questions or []
    total_score = 0
    for q in questions:
        q_id = str(q.get("id", ""))
        if answers.get(q_id) == q.get("answer"):
            total_score += q.get("score", 0)

    passed = total_score >= exam.pass_score

    attempt = ExamAttempt(
        exam_id=uuid_mod.UUID(exam_id),
        employee_id=employee_id,
        store_id=store_id,
        answers=answers,
        score=total_score,
        passed=passed,
    )
    db.add(attempt)
    await db.commit()

    return {
        "id": str(attempt.id),
        "score": total_score,
        "total": exam.total_score,
        "passed": passed,
        "pass_score": exam.pass_score,
    }


@router.get("/hr/training/certificates")
async def my_certificates(
    employee_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """我的证书"""
    result = await db.execute(
        select(TrainingEnrollment, TrainingCourse).join(
            TrainingCourse, TrainingEnrollment.course_id == TrainingCourse.id
        ).where(
            and_(
                TrainingEnrollment.employee_id == employee_id,
                TrainingEnrollment.status == "completed",
                TrainingEnrollment.certificate_no.isnot(None),
            )
        )
    )
    rows = result.all()

    return {
        "items": [
            {
                "certificate_no": e.certificate_no,
                "course_title": c.title,
                "category": c.category,
                "credits": c.credits,
                "score": e.score,
                "certified_at": str(e.certified_at) if e.certified_at else None,
            }
            for e, c in rows
        ]
    }


# ── 师徒制 ──

class MentorshipRequest(BaseModel):
    store_id: str
    brand_id: str
    target_position: str
    mentor_id: str
    mentor_name: Optional[str] = None
    apprentice_id: str
    apprentice_name: Optional[str] = None
    enrolled_at: str  # YYYY-MM-DD
    training_start: Optional[str] = None
    training_end: Optional[str] = None
    expected_review_date: Optional[str] = None


@router.get("/hr/training/mentorships")
async def list_mentorships(
    store_id: str = Query(...),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """师徒关系列表"""
    query = select(Mentorship).where(Mentorship.store_id == store_id)
    if status:
        query = query.where(Mentorship.status == status)
    query = query.order_by(Mentorship.enrolled_at.desc())

    result = await db.execute(query)
    mentorships = result.scalars().all()

    return {
        "items": [
            {
                "id": str(m.id),
                "target_position": m.target_position,
                "mentor_id": m.mentor_id,
                "mentor_name": m.mentor_name,
                "apprentice_id": m.apprentice_id,
                "apprentice_name": m.apprentice_name,
                "enrolled_at": str(m.enrolled_at),
                "training_start": str(m.training_start) if m.training_start else None,
                "training_end": str(m.training_end) if m.training_end else None,
                "expected_review_date": str(m.expected_review_date) if m.expected_review_date else None,
                "actual_review_date": str(m.actual_review_date) if m.actual_review_date else None,
                "review_result": m.review_result,
                "reward_yuan": m.reward_fen / 100 if m.reward_fen else 0,
                "status": m.status,
            }
            for m in mentorships
        ],
        "total": len(mentorships),
    }


@router.post("/hr/training/mentorships")
async def create_mentorship(
    req: MentorshipRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """创建师徒关系"""
    from datetime import datetime as dt
    mentorship = Mentorship(
        store_id=req.store_id,
        brand_id=req.brand_id,
        target_position=req.target_position,
        mentor_id=req.mentor_id,
        mentor_name=req.mentor_name,
        apprentice_id=req.apprentice_id,
        apprentice_name=req.apprentice_name,
        enrolled_at=dt.strptime(req.enrolled_at, "%Y-%m-%d").date(),
        training_start=dt.strptime(req.training_start, "%Y-%m-%d").date() if req.training_start else None,
        training_end=dt.strptime(req.training_end, "%Y-%m-%d").date() if req.training_end else None,
        expected_review_date=dt.strptime(req.expected_review_date, "%Y-%m-%d").date() if req.expected_review_date else None,
    )
    db.add(mentorship)
    await db.commit()
    return {"id": str(mentorship.id), "message": "师徒关系创建成功"}


@router.post("/hr/training/mentorships/{mentorship_id}/review")
async def review_mentorship(
    mentorship_id: str,
    result: str = Query(..., description="passed/failed"),
    reward_fen: int = Query(0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """验收师徒培养"""
    mentorship = await db.get(Mentorship, uuid_mod.UUID(mentorship_id))
    if not mentorship:
        raise HTTPException(status_code=404, detail="师徒关系不存在")

    mentorship.actual_review_date = date.today()
    mentorship.review_result = result
    mentorship.reward_fen = reward_fen
    if result == "passed":
        mentorship.status = "completed"

    await db.commit()
    return {
        "id": str(mentorship.id),
        "review_result": result,
        "reward_yuan": reward_fen / 100,
        "status": mentorship.status,
    }


# ── 培训看板 ──

@router.get("/hr/training/dashboard")
async def training_dashboard(
    store_id: str = Query(None),
    brand_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """培训看板（完成率、认证率、学分统计）"""
    # 课程总数
    course_query = select(func.count(TrainingCourse.id)).where(
        and_(
            TrainingCourse.brand_id == brand_id,
            TrainingCourse.is_active.is_(True),
        )
    )
    total_courses = (await db.execute(course_query)).scalar() or 0

    # 报名统计
    enrollment_query = select(
        TrainingEnrollment.status,
        func.count(TrainingEnrollment.id),
    )
    if store_id:
        enrollment_query = enrollment_query.where(TrainingEnrollment.store_id == store_id)
    enrollment_query = enrollment_query.group_by(TrainingEnrollment.status)
    enroll_result = await db.execute(enrollment_query)
    status_dist = {r[0]: r[1] for r in enroll_result.all()}

    total_enrollments = sum(status_dist.values())
    completed = status_dist.get("completed", 0)
    completion_rate = round(completed / max(total_enrollments, 1) * 100, 1)

    # 学分统计（已完成的课程学分总和）
    credits_result = await db.execute(
        select(func.sum(TrainingCourse.credits)).join(
            TrainingEnrollment, TrainingEnrollment.course_id == TrainingCourse.id
        ).where(
            TrainingEnrollment.status == "completed"
        )
    )
    total_credits = credits_result.scalar() or 0

    # 师徒统计
    mentorship_query = select(
        Mentorship.status,
        func.count(Mentorship.id),
    ).where(Mentorship.brand_id == brand_id)
    if store_id:
        mentorship_query = mentorship_query.where(Mentorship.store_id == store_id)
    mentorship_query = mentorship_query.group_by(Mentorship.status)
    ms_result = await db.execute(mentorship_query)
    mentorship_stats = {r[0]: r[1] for r in ms_result.all()}

    return {
        "total_courses": total_courses,
        "total_enrollments": total_enrollments,
        "enrollment_by_status": status_dist,
        "completion_rate_pct": completion_rate,
        "total_credits_earned": total_credits,
        "mentorship_stats": mentorship_stats,
        "active_mentorships": mentorship_stats.get("active", 0),
        "completed_mentorships": mentorship_stats.get("completed", 0),
    }
