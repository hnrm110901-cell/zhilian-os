"""
HR Growth API — 员工成长旅程
技能矩阵 · 职业路径 · 里程碑 · 成长计划 · 幸福指数 · 全旅程视图
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel
import uuid as uuid_mod
import structlog

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.user import User
from ..models.employee import Employee
from ..models.employee_growth import (
    SkillDefinition, EmployeeSkill, CareerPath,
    EmployeeMilestone, EmployeeGrowthPlan, EmployeeWellbeing,
    SkillLevel, MilestoneType, GrowthPlanStatus,
)
from ..services.hr_growth_agent_service import (
    analyze_skill_gaps, assess_promotion_readiness,
    generate_growth_plan, check_and_trigger_milestones,
    compute_wellbeing_insights, get_employee_journey,
)
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()
router = APIRouter()


# ── 请求模型 ──────────────────────────────────────────

class SkillDefinitionRequest(BaseModel):
    store_id: Optional[str] = None
    brand_id: Optional[str] = None
    skill_name: str
    skill_category: str
    applicable_positions: Optional[List[str]] = None
    required_level: str = "journeyman"
    description: Optional[str] = None
    promotion_weight: int = 50


class SkillAssessRequest(BaseModel):
    employee_id: str
    skill_id: str
    current_level: str
    score: int = 0
    evidence: Optional[str] = None
    next_target_level: Optional[str] = None


class CareerPathRequest(BaseModel):
    store_id: Optional[str] = None
    brand_id: Optional[str] = None
    path_name: str
    from_position: str
    to_position: str
    sequence: int = 0
    min_tenure_months: int = 6
    required_skills: Optional[list] = None
    min_performance_level: str = "B"
    min_performance_score: int = 70
    salary_increase_pct: float = 15.0
    description: Optional[str] = None


class WellbeingSubmitRequest(BaseModel):
    store_id: str
    employee_id: str
    period: Optional[str] = None
    achievement_score: int       # 1-10
    belonging_score: int
    growth_score: int
    balance_score: int
    culture_score: int
    highlights: Optional[str] = None
    concerns: Optional[str] = None
    suggestions: Optional[str] = None
    is_anonymous: bool = False


# ── 技能矩阵 ──────────────────────────────────────────

@router.get("/hr/growth/skills/definitions")
async def list_skill_definitions(
    store_id: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取技能定义列表"""
    query = select(SkillDefinition).where(SkillDefinition.is_active.is_(True))
    if store_id:
        query = query.where(
            (SkillDefinition.store_id == store_id) | (SkillDefinition.store_id.is_(None))
        )
    if category:
        query = query.where(SkillDefinition.skill_category == category)

    result = await db.execute(query.order_by(SkillDefinition.skill_category))
    skills = result.scalars().all()
    return {
        "items": [
            {
                "id": str(s.id),
                "skill_name": s.skill_name,
                "skill_category": s.skill_category,
                "applicable_positions": s.applicable_positions,
                "required_level": s.required_level.value if hasattr(s.required_level, 'value') else str(s.required_level),
                "promotion_weight": s.promotion_weight,
                "description": s.description,
            }
            for s in skills
        ],
    }


@router.post("/hr/growth/skills/definitions")
async def create_skill_definition(
    body: SkillDefinitionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """创建技能定义"""
    skill = SkillDefinition(
        id=uuid_mod.uuid4(),
        store_id=body.store_id,
        brand_id=body.brand_id,
        skill_name=body.skill_name,
        skill_category=body.skill_category,
        applicable_positions=body.applicable_positions,
        required_level=body.required_level,
        description=body.description,
        promotion_weight=body.promotion_weight,
    )
    db.add(skill)
    await db.commit()
    return {"id": str(skill.id), "message": f"技能「{body.skill_name}」创建成功"}


@router.post("/hr/growth/skills/assess")
async def assess_employee_skill(
    body: SkillAssessRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """评估员工技能等级"""
    record = EmployeeSkill(
        id=uuid_mod.uuid4(),
        employee_id=body.employee_id,
        skill_id=body.skill_id,
        current_level=body.current_level,
        score=body.score,
        assessed_by=current_user.id if current_user else None,
        assessed_at=date.today(),
        evidence=body.evidence,
        next_target_level=body.next_target_level,
    )
    db.add(record)
    await db.commit()
    return {"id": str(record.id), "message": "技能评估记录已保存"}


@router.get("/hr/growth/skills/gaps/{employee_id}")
async def get_skill_gaps(
    employee_id: str,
    store_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取员工技能差距分析"""
    return await analyze_skill_gaps(db, store_id, employee_id)


# ── 职业路径 ──────────────────────────────────────────

@router.get("/hr/growth/career-paths")
async def list_career_paths(
    store_id: Optional[str] = Query(None),
    from_position: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取职业发展路径"""
    query = select(CareerPath).where(CareerPath.is_active.is_(True))
    if store_id:
        query = query.where(
            (CareerPath.store_id == store_id) | (CareerPath.store_id.is_(None))
        )
    if from_position:
        query = query.where(CareerPath.from_position == from_position)

    result = await db.execute(query.order_by(CareerPath.sequence))
    paths = result.scalars().all()
    return {
        "items": [
            {
                "id": str(p.id),
                "path_name": p.path_name,
                "from_position": p.from_position,
                "to_position": p.to_position,
                "min_tenure_months": p.min_tenure_months,
                "min_performance_score": p.min_performance_score,
                "salary_increase_pct": float(p.salary_increase_pct or 0),
                "description": p.description,
            }
            for p in paths
        ],
    }


@router.post("/hr/growth/career-paths")
async def create_career_path(
    body: CareerPathRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """创建职业发展路径"""
    path = CareerPath(
        id=uuid_mod.uuid4(),
        store_id=body.store_id,
        brand_id=body.brand_id,
        path_name=body.path_name,
        from_position=body.from_position,
        to_position=body.to_position,
        sequence=body.sequence,
        min_tenure_months=body.min_tenure_months,
        required_skills=body.required_skills,
        min_performance_level=body.min_performance_level,
        min_performance_score=body.min_performance_score,
        salary_increase_pct=body.salary_increase_pct,
        description=body.description,
    )
    db.add(path)
    await db.commit()
    return {"id": str(path.id), "message": f"职业路径「{body.path_name}」创建成功"}


@router.get("/hr/growth/promotion-readiness/{employee_id}")
async def get_promotion_readiness(
    employee_id: str,
    store_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取员工晋升就绪度评估"""
    return await assess_promotion_readiness(db, store_id, employee_id)


# ── 成长计划 ──────────────────────────────────────────

@router.get("/hr/growth/plans")
async def list_growth_plans(
    store_id: str = Query(...),
    employee_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取成长计划列表"""
    query = (
        select(EmployeeGrowthPlan, Employee.name.label("employee_name"))
        .join(Employee, EmployeeGrowthPlan.employee_id == Employee.id)
        .where(EmployeeGrowthPlan.store_id == store_id)
    )
    if employee_id:
        query = query.where(EmployeeGrowthPlan.employee_id == employee_id)
    if status:
        query = query.where(EmployeeGrowthPlan.status == status)

    result = await db.execute(query.order_by(EmployeeGrowthPlan.created_at.desc()))
    rows = result.all()
    return {
        "items": [
            {
                "id": str(r.EmployeeGrowthPlan.id),
                "employee_id": r.EmployeeGrowthPlan.employee_id,
                "employee_name": r.employee_name,
                "plan_name": r.EmployeeGrowthPlan.plan_name,
                "status": r.EmployeeGrowthPlan.status.value,
                "target_position": r.EmployeeGrowthPlan.target_position,
                "progress_pct": float(r.EmployeeGrowthPlan.progress_pct or 0),
                "total_tasks": r.EmployeeGrowthPlan.total_tasks,
                "completed_tasks": r.EmployeeGrowthPlan.completed_tasks,
                "mentor_name": r.EmployeeGrowthPlan.mentor_name,
                "ai_generated": r.EmployeeGrowthPlan.ai_generated,
                "target_date": str(r.EmployeeGrowthPlan.target_date) if r.EmployeeGrowthPlan.target_date else None,
            }
            for r in rows
        ],
    }


@router.post("/hr/growth/plans/generate/{employee_id}")
async def generate_ai_growth_plan(
    employee_id: str,
    store_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """AI自动生成成长计划"""
    result = await generate_growth_plan(db, store_id, employee_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    await db.commit()
    return result


# ── 里程碑 ──────────────────────────────────────────

@router.get("/hr/growth/milestones")
async def list_milestones(
    store_id: str = Query(...),
    employee_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取里程碑列表"""
    query = (
        select(EmployeeMilestone, Employee.name.label("employee_name"))
        .join(Employee, EmployeeMilestone.employee_id == Employee.id)
        .where(EmployeeMilestone.store_id == store_id)
    )
    if employee_id:
        query = query.where(EmployeeMilestone.employee_id == employee_id)

    result = await db.execute(
        query.order_by(EmployeeMilestone.achieved_at.desc()).limit(limit)
    )
    rows = result.all()
    return {
        "items": [
            {
                "id": str(r.EmployeeMilestone.id),
                "employee_id": r.EmployeeMilestone.employee_id,
                "employee_name": r.employee_name,
                "milestone_type": r.EmployeeMilestone.milestone_type.value,
                "title": r.EmployeeMilestone.title,
                "description": r.EmployeeMilestone.description,
                "achieved_at": str(r.EmployeeMilestone.achieved_at),
                "badge_icon": r.EmployeeMilestone.badge_icon,
                "reward_yuan": (r.EmployeeMilestone.reward_fen or 0) / 100,
            }
            for r in rows
        ],
    }


@router.post("/hr/growth/milestones/scan")
async def scan_milestones(
    store_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """扫描并自动触发里程碑"""
    triggered = await check_and_trigger_milestones(db, store_id)
    await db.commit()
    return {"triggered_count": len(triggered), "milestones": triggered}


# ── 幸福指数 ──────────────────────────────────────────

@router.post("/hr/growth/wellbeing")
async def submit_wellbeing(
    body: WellbeingSubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """提交幸福指数"""
    today = date.today()
    period = body.period or f"{today.year}-{today.month:02d}"

    # 计算综合分
    scores = [
        body.achievement_score, body.belonging_score,
        body.growth_score, body.balance_score, body.culture_score,
    ]
    overall = round(sum(scores) / len(scores), 1)

    # 检查是否已存在
    existing = await db.execute(
        select(EmployeeWellbeing).where(
            and_(
                EmployeeWellbeing.employee_id == body.employee_id,
                EmployeeWellbeing.period == period,
            )
        )
    )
    record = existing.scalar_one_or_none()
    if record:
        record.achievement_score = body.achievement_score
        record.belonging_score = body.belonging_score
        record.growth_score = body.growth_score
        record.balance_score = body.balance_score
        record.culture_score = body.culture_score
        record.overall_score = Decimal(str(overall))
        record.highlights = body.highlights
        record.concerns = body.concerns
        record.suggestions = body.suggestions
        record.submitted_at = datetime.utcnow()
    else:
        record = EmployeeWellbeing(
            id=uuid_mod.uuid4(),
            store_id=body.store_id,
            employee_id=body.employee_id,
            period=period,
            achievement_score=body.achievement_score,
            belonging_score=body.belonging_score,
            growth_score=body.growth_score,
            balance_score=body.balance_score,
            culture_score=body.culture_score,
            overall_score=Decimal(str(overall)),
            highlights=body.highlights,
            concerns=body.concerns,
            suggestions=body.suggestions,
            is_anonymous=body.is_anonymous,
            submitted_at=datetime.utcnow(),
        )
        db.add(record)

    await db.commit()
    return {"period": period, "overall_score": overall, "message": "幸福指数已提交"}


@router.get("/hr/growth/wellbeing/insights")
async def get_wellbeing_insights(
    store_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取全店幸福指数洞察"""
    return await compute_wellbeing_insights(db, store_id)


# ── 全旅程视图 ────────────────────────────────────────

@router.get("/hr/growth/journey/{employee_id}")
async def get_journey(
    employee_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取员工全旅程视图"""
    result = await get_employee_journey(db, employee_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result
