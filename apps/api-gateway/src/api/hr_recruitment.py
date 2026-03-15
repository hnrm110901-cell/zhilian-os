"""
HR Recruitment API — 招聘管理接口
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime
import uuid
import structlog

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.user import User
from ..models.recruitment import (
    JobPosting, Candidate, Interview, Offer,
    JobStatus, CandidateStage, InterviewResult, OfferStatus,
)
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()
router = APIRouter()


# ── Request Models ─────────────────────────────────────────

class CreateJobRequest(BaseModel):
    store_id: str
    title: str
    position: str
    headcount: int = 1
    salary_min_yuan: Optional[float] = None
    salary_max_yuan: Optional[float] = None
    requirements: Optional[str] = None
    skills_required: Optional[List[str]] = None
    urgent: bool = False
    deadline: Optional[str] = None


class CreateCandidateRequest(BaseModel):
    job_id: str
    store_id: str
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[int] = None
    source: Optional[str] = None
    education: Optional[str] = None
    notes: Optional[str] = None


class UpdateCandidateStageRequest(BaseModel):
    stage: str
    rejection_reason: Optional[str] = None


class CreateInterviewRequest(BaseModel):
    candidate_id: str
    store_id: str
    round: int = 1
    interview_date: datetime
    interviewer_id: Optional[str] = None
    interviewer_name: Optional[str] = None


class SubmitInterviewResultRequest(BaseModel):
    result: str
    skill_score: Optional[int] = None
    attitude_score: Optional[int] = None
    experience_score: Optional[int] = None
    overall_score: Optional[int] = None
    feedback: Optional[str] = None


# ── 职位 ───────────────────────────────────────────────────

@router.get("/hr/jobs")
async def list_jobs(
    store_id: str = Query(...),
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取职位列表"""
    conditions = [JobPosting.store_id == store_id]
    if status:
        conditions.append(JobPosting.status == status)

    result = await db.execute(
        select(JobPosting).where(and_(*conditions))
        .order_by(JobPosting.created_at.desc())
    )
    jobs = result.scalars().all()

    # 每个职位的候选人统计
    items = []
    for job in jobs:
        cand_result = await db.execute(
            select(
                func.count(Candidate.id).label("total"),
                func.count(Candidate.id).filter(Candidate.stage == CandidateStage.HIRED).label("hired"),
            ).where(Candidate.job_id == job.id)
        )
        stats = cand_result.one()
        items.append({
            "id": str(job.id),
            "title": job.title,
            "position": job.position,
            "headcount": job.headcount,
            "hired_count": stats.hired or 0,
            "candidate_count": stats.total or 0,
            "status": job.status.value if job.status else "open",
            "salary_range_yuan": f"{(job.salary_min_fen or 0)/100:.0f}-{(job.salary_max_fen or 0)/100:.0f}",
            "urgent": job.urgent,
            "created_at": job.created_at.isoformat() if job.created_at else None,
        })
    return {"items": items, "total": len(items)}


@router.post("/hr/jobs")
async def create_job(
    req: CreateJobRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """创建招聘职位"""
    job = JobPosting(
        store_id=req.store_id,
        title=req.title,
        position=req.position,
        headcount=req.headcount,
        salary_min_fen=int(req.salary_min_yuan * 100) if req.salary_min_yuan else None,
        salary_max_fen=int(req.salary_max_yuan * 100) if req.salary_max_yuan else None,
        requirements=req.requirements,
        skills_required=req.skills_required,
        urgent=req.urgent,
        deadline=date.fromisoformat(req.deadline) if req.deadline else None,
        publisher_id=current_user.id if hasattr(current_user, 'id') else None,
    )
    db.add(job)
    await db.commit()
    return {"id": str(job.id), "message": "职位已发布"}


# ── 候选人 ─────────────────────────────────────────────────

@router.get("/hr/candidates")
async def list_candidates(
    job_id: str = Query(...),
    stage: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取候选人列表"""
    conditions = [Candidate.job_id == job_id]
    if stage:
        conditions.append(Candidate.stage == stage)

    result = await db.execute(
        select(Candidate).where(and_(*conditions))
        .order_by(Candidate.created_at.desc())
    )
    candidates = result.scalars().all()
    return {
        "items": [
            {
                "id": str(c.id),
                "name": c.name,
                "phone": c.phone,
                "stage": c.stage.value if c.stage else "new",
                "source": c.source,
                "interview_score": c.interview_score,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in candidates
        ],
        "total": len(candidates),
    }


@router.post("/hr/candidates")
async def create_candidate(
    req: CreateCandidateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """添加候选人"""
    candidate = Candidate(
        job_id=req.job_id,
        store_id=req.store_id,
        name=req.name,
        phone=req.phone,
        email=req.email,
        gender=req.gender,
        age=req.age,
        source=req.source,
        education=req.education,
        notes=req.notes,
    )
    db.add(candidate)
    await db.commit()
    return {"id": str(candidate.id), "message": "候选人已添加"}


@router.put("/hr/candidates/{candidate_id}/stage")
async def update_candidate_stage(
    candidate_id: str,
    req: UpdateCandidateStageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """更新候选人阶段"""
    candidate = await db.get(Candidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="候选人不存在")
    candidate.stage = req.stage
    if req.rejection_reason:
        candidate.rejection_reason = req.rejection_reason
    await db.commit()
    return {"id": str(candidate.id), "stage": req.stage}


# ── 面试 ───────────────────────────────────────────────────

@router.post("/hr/interviews")
async def create_interview(
    req: CreateInterviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """安排面试"""
    interview = Interview(
        candidate_id=req.candidate_id,
        store_id=req.store_id,
        round=req.round,
        interview_date=req.interview_date,
        interviewer_id=req.interviewer_id,
        interviewer_name=req.interviewer_name,
    )
    db.add(interview)

    # 更新候选人阶段
    candidate = await db.get(Candidate, req.candidate_id)
    if candidate and candidate.stage.value in ("new", "screening"):
        candidate.stage = CandidateStage.INTERVIEW

    await db.commit()
    return {"id": str(interview.id), "message": "面试已安排"}


@router.put("/hr/interviews/{interview_id}/result")
async def submit_interview_result(
    interview_id: str,
    req: SubmitInterviewResultRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """提交面试结果"""
    interview = await db.get(Interview, interview_id)
    if not interview:
        raise HTTPException(status_code=404, detail="面试记录不存在")

    interview.result = req.result
    interview.skill_score = req.skill_score
    interview.attitude_score = req.attitude_score
    interview.experience_score = req.experience_score
    interview.overall_score = req.overall_score
    interview.feedback = req.feedback

    # 更新候选人综合面试分
    candidate = await db.get(Candidate, str(interview.candidate_id))
    if candidate and req.overall_score:
        candidate.interview_score = req.overall_score
        if req.result == "fail":
            candidate.stage = CandidateStage.REJECTED

    await db.commit()
    return {"id": str(interview.id), "result": req.result}


# ── 招聘漏斗统计 ───────────────────────────────────────────

@router.get("/hr/recruitment/funnel")
async def get_recruitment_funnel(
    store_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取招聘漏斗数据"""
    stages = ["new", "screening", "interview", "offer", "hired", "rejected"]
    funnel = {}
    for stage in stages:
        result = await db.execute(
            select(func.count(Candidate.id)).where(
                and_(
                    Candidate.store_id == store_id,
                    Candidate.stage == stage,
                )
            )
        )
        funnel[stage] = result.scalar() or 0

    # 活跃职位数
    active_jobs = await db.execute(
        select(func.count(JobPosting.id)).where(
            and_(
                JobPosting.store_id == store_id,
                JobPosting.status == JobStatus.OPEN,
            )
        )
    )

    return {
        "store_id": store_id,
        "active_jobs": active_jobs.scalar() or 0,
        "funnel": funnel,
        "conversion_rate": (
            round(funnel.get("hired", 0) / max(funnel.get("new", 1), 1) * 100, 1)
        ),
    }
