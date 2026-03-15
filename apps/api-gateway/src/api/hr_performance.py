"""
HR Performance & Contract API — 绩效考核 + 合同管理接口
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime
from decimal import Decimal
import structlog

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.user import User
from ..models.performance_review import (
    PerformanceTemplate, PerformanceReview, ReviewStatus, ReviewLevel,
)
from ..models.employee_contract import EmployeeContract, ContractStatus, ContractType
from ..models.employee import Employee
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()
router = APIRouter()


# ── Request Models ─────────────────────────────────────────

class CreateReviewRequest(BaseModel):
    store_id: str
    employee_id: str
    review_period: str          # "2026-Q1" / "2026-03"
    template_id: Optional[str] = None


class SubmitSelfReviewRequest(BaseModel):
    self_score: float
    self_comment: str = ""
    dimension_scores: Optional[dict] = None


class SubmitManagerReviewRequest(BaseModel):
    manager_score: float
    manager_comment: str = ""
    dimension_scores: Optional[dict] = None
    reviewer_id: str
    reviewer_name: str = ""
    level: Optional[str] = None
    improvement_plan: Optional[str] = None


class CreateContractRequest(BaseModel):
    store_id: str
    employee_id: str
    contract_type: str = "fixed_term"
    start_date: str
    end_date: Optional[str] = None
    probation_end_date: Optional[str] = None
    agreed_salary_yuan: Optional[float] = None
    position: Optional[str] = None
    contract_no: Optional[str] = None


# ── 绩效 ───────────────────────────────────────────────────

@router.get("/hr/performance/reviews")
async def list_reviews(
    store_id: str = Query(...),
    period: Optional[str] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取绩效考核列表"""
    conditions = [PerformanceReview.store_id == store_id]
    if period:
        conditions.append(PerformanceReview.review_period == period)
    if status:
        conditions.append(PerformanceReview.status == status)

    result = await db.execute(
        select(PerformanceReview, Employee.name, Employee.position).join(
            Employee, PerformanceReview.employee_id == Employee.id
        ).where(and_(*conditions))
        .order_by(PerformanceReview.created_at.desc())
    )
    rows = result.all()
    return {
        "items": [
            {
                "id": str(r.id),
                "employee_id": r.employee_id,
                "employee_name": name,
                "position": position,
                "review_period": r.review_period,
                "status": r.status.value if r.status else "draft",
                "total_score": float(r.total_score or 0),
                "level": r.level.value if r.level else None,
                "performance_coefficient": float(r.performance_coefficient or 1.0),
            }
            for r, name, position in rows
        ],
        "total": len(rows),
    }


@router.post("/hr/performance/reviews")
async def create_review(
    req: CreateReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """创建考核记录"""
    review = PerformanceReview(
        store_id=req.store_id,
        employee_id=req.employee_id,
        template_id=req.template_id,
        review_period=req.review_period,
        status=ReviewStatus.SELF_REVIEW,
    )
    db.add(review)
    await db.commit()
    return {"id": str(review.id), "message": "考核已创建"}


@router.put("/hr/performance/reviews/{review_id}/self")
async def submit_self_review(
    review_id: str,
    req: SubmitSelfReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """提交自评"""
    review = await db.get(PerformanceReview, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="考核记录不存在")

    review.self_score = Decimal(str(req.self_score))
    review.self_comment = req.self_comment
    if req.dimension_scores:
        review.dimension_scores = req.dimension_scores
    review.status = ReviewStatus.MANAGER_REVIEW
    await db.commit()
    return {"id": str(review.id), "status": "manager"}


@router.put("/hr/performance/reviews/{review_id}/manager")
async def submit_manager_review(
    review_id: str,
    req: SubmitManagerReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """提交上级评分"""
    review = await db.get(PerformanceReview, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="考核记录不存在")

    review.manager_score = Decimal(str(req.manager_score))
    review.manager_comment = req.manager_comment
    review.reviewer_id = req.reviewer_id
    review.reviewer_name = req.reviewer_name
    review.improvement_plan = req.improvement_plan

    if req.dimension_scores:
        existing = review.dimension_scores or {}
        existing.update(req.dimension_scores)
        review.dimension_scores = existing

    # 综合分 = (自评 × 30% + 上级评 × 70%)
    self_s = float(review.self_score or 0)
    mgr_s = float(req.manager_score)
    total = self_s * 0.3 + mgr_s * 0.7
    review.total_score = Decimal(str(round(total, 1)))

    # 自动定级
    if req.level:
        review.level = req.level
    else:
        if total >= 90:
            review.level = ReviewLevel.S
        elif total >= 80:
            review.level = ReviewLevel.A
        elif total >= 70:
            review.level = ReviewLevel.B
        elif total >= 60:
            review.level = ReviewLevel.C
        else:
            review.level = ReviewLevel.D

    # 绩效系数
    coeff_map = {"S": 1.5, "A": 1.3, "B": 1.1, "C": 1.0, "D": 0.8}
    level_val = review.level.value if review.level else "C"
    review.performance_coefficient = Decimal(str(coeff_map.get(level_val, 1.0)))

    review.status = ReviewStatus.COMPLETED
    review.completed_at = datetime.utcnow()
    await db.commit()

    return {
        "id": str(review.id),
        "total_score": float(review.total_score),
        "level": level_val,
        "coefficient": float(review.performance_coefficient),
    }


# ── 合同 ───────────────────────────────────────────────────

@router.get("/hr/contracts")
async def list_contracts(
    store_id: str = Query(...),
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取合同列表"""
    conditions = [EmployeeContract.store_id == store_id]
    if status:
        conditions.append(EmployeeContract.status == status)

    result = await db.execute(
        select(EmployeeContract, Employee.name).join(
            Employee, EmployeeContract.employee_id == Employee.id
        ).where(and_(*conditions))
        .order_by(EmployeeContract.end_date.asc().nullslast())
    )
    rows = result.all()
    return {
        "items": [
            {
                "id": str(c.id),
                "employee_id": c.employee_id,
                "employee_name": name,
                "contract_no": c.contract_no,
                "contract_type": c.contract_type.value if c.contract_type else "",
                "status": c.status.value if c.status else "",
                "start_date": str(c.start_date),
                "end_date": str(c.end_date) if c.end_date else None,
                "position": c.position,
                "renewal_count": c.renewal_count,
            }
            for c, name in rows
        ],
        "total": len(rows),
    }


@router.post("/hr/contracts")
async def create_contract(
    req: CreateContractRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """创建合同"""
    contract = EmployeeContract(
        store_id=req.store_id,
        employee_id=req.employee_id,
        contract_type=req.contract_type,
        status=ContractStatus.ACTIVE,
        start_date=date.fromisoformat(req.start_date),
        end_date=date.fromisoformat(req.end_date) if req.end_date else None,
        probation_end_date=date.fromisoformat(req.probation_end_date) if req.probation_end_date else None,
        agreed_salary_fen=int(req.agreed_salary_yuan * 100) if req.agreed_salary_yuan else None,
        position=req.position,
        contract_no=req.contract_no,
    )
    db.add(contract)
    await db.commit()
    return {"id": str(contract.id), "message": "合同已创建"}


@router.get("/hr/contracts/expiring")
async def get_expiring_contracts(
    store_id: str = Query(...),
    days: int = Query(default=30, description="到期天数"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取即将到期的合同"""
    from datetime import timedelta
    deadline = date.today() + timedelta(days=days)

    result = await db.execute(
        select(EmployeeContract, Employee.name).join(
            Employee, EmployeeContract.employee_id == Employee.id
        ).where(
            and_(
                EmployeeContract.store_id == store_id,
                EmployeeContract.status == ContractStatus.ACTIVE,
                EmployeeContract.end_date.isnot(None),
                EmployeeContract.end_date <= deadline,
            )
        ).order_by(EmployeeContract.end_date.asc())
    )
    rows = result.all()
    return {
        "items": [
            {
                "id": str(c.id),
                "employee_id": c.employee_id,
                "employee_name": name,
                "end_date": str(c.end_date),
                "days_remaining": (c.end_date - date.today()).days,
                "renewal_count": c.renewal_count,
            }
            for c, name in rows
        ],
        "total": len(rows),
    }
