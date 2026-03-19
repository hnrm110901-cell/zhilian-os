"""
HR Reward & Penalty API -- 奖惩管理
"""

import uuid as uuid_mod
from datetime import date
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.hr.person import Person
from ..models.reward_penalty import RewardPenaltyRecord, RewardPenaltyStatus, RewardPenaltyType
from ..models.user import User

logger = structlog.get_logger()
router = APIRouter()


class RewardPenaltyRequest(BaseModel):
    store_id: str
    employee_id: str
    rp_type: str  # reward|penalty
    category: str  # RewardPenaltyCategory value
    amount_fen: int
    pay_month: Optional[str] = None  # 计入哪个月（默认当月）
    incident_date: str  # YYYY-MM-DD
    description: str
    evidence: Optional[list] = None
    remark: Optional[str] = None


@router.get("/hr/reward-penalty")
async def list_reward_penalties(
    store_id: str = Query(...),
    pay_month: Optional[str] = Query(None),
    rp_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    employee_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """奖惩记录列表"""
    query = (
        select(RewardPenaltyRecord, Person.name.label("employee_name"))
        .join(Person, Person.legacy_employee_id == RewardPenaltyRecord.employee_id)
        .where(RewardPenaltyRecord.store_id == store_id)
    )
    if pay_month:
        query = query.where(RewardPenaltyRecord.pay_month == pay_month)
    if rp_type:
        query = query.where(RewardPenaltyRecord.rp_type == rp_type)
    if status:
        query = query.where(RewardPenaltyRecord.status == status)
    if employee_id:
        query = query.where(RewardPenaltyRecord.employee_id == employee_id)

    result = await db.execute(
        query.order_by(RewardPenaltyRecord.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    rows = result.all()

    return {
        "items": [
            {
                "id": str(r.RewardPenaltyRecord.id),
                "employee_id": r.RewardPenaltyRecord.employee_id,
                "employee_name": r.employee_name,
                "rp_type": r.RewardPenaltyRecord.rp_type.value,
                "category": r.RewardPenaltyRecord.category.value,
                "status": r.RewardPenaltyRecord.status.value,
                "amount_yuan": r.RewardPenaltyRecord.amount_fen / 100,
                "pay_month": r.RewardPenaltyRecord.pay_month,
                "incident_date": str(r.RewardPenaltyRecord.incident_date),
                "description": r.RewardPenaltyRecord.description,
                "evidence": r.RewardPenaltyRecord.evidence,
                "submitted_by": r.RewardPenaltyRecord.submitted_by,
                "approved_by": r.RewardPenaltyRecord.approved_by,
            }
            for r in rows
        ],
    }


@router.post("/hr/reward-penalty")
async def create_reward_penalty(
    body: RewardPenaltyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """提交奖惩记录（待审批）"""
    today = date.today()
    pay_month = body.pay_month or f"{today.year}-{today.month:02d}"

    record = RewardPenaltyRecord(
        id=uuid_mod.uuid4(),
        store_id=body.store_id,
        employee_id=body.employee_id,
        rp_type=body.rp_type,
        category=body.category,
        status=RewardPenaltyStatus.PENDING,
        amount_fen=body.amount_fen,
        pay_month=pay_month,
        incident_date=date.fromisoformat(body.incident_date),
        description=body.description,
        evidence=body.evidence,
        submitted_by=current_user.id if current_user else None,
        remark=body.remark,
    )
    db.add(record)
    await db.commit()

    rp_label = "奖励" if body.rp_type == "reward" else "罚款"
    return {
        "id": str(record.id),
        "message": f"{rp_label}记录已提交，待审批",
        "amount_yuan": body.amount_fen / 100,
    }


@router.post("/hr/reward-penalty/{record_id}/approve")
async def approve_reward_penalty(
    record_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """审批通过奖惩记录"""
    result = await db.execute(select(RewardPenaltyRecord).where(RewardPenaltyRecord.id == record_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    if record.status != RewardPenaltyStatus.PENDING:
        raise HTTPException(status_code=400, detail=f"记录状态为{record.status.value}，不可审批")

    record.status = RewardPenaltyStatus.APPROVED
    record.approved_by = current_user.id if current_user else "system"
    record.approved_at = date.today()
    await db.commit()

    return {"id": record_id, "status": "approved"}


@router.post("/hr/reward-penalty/{record_id}/reject")
async def reject_reward_penalty(
    record_id: str,
    reason: str = Query(""),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """驳回奖惩记录"""
    result = await db.execute(select(RewardPenaltyRecord).where(RewardPenaltyRecord.id == record_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    if record.status != RewardPenaltyStatus.PENDING:
        raise HTTPException(status_code=400, detail=f"记录状态为{record.status.value}，不可驳回")

    record.status = RewardPenaltyStatus.REJECTED
    record.reject_reason = reason
    await db.commit()

    return {"id": record_id, "status": "rejected"}
