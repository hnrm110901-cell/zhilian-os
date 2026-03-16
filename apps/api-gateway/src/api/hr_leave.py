"""
HR Leave & Approval API — 假勤审批接口
"""

from datetime import date, datetime
from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.user import User
from ..services.hr_approval_service import HRApprovalService
from ..services.leave_service import LeaveService

logger = structlog.get_logger()
router = APIRouter()


# ── Request Models ─────────────────────────────────────────


class LeaveSubmitRequest(BaseModel):
    store_id: str
    employee_id: str
    leave_category: str
    start_date: str
    end_date: str
    leave_days: float
    reason: str
    start_half: str = "am"
    end_half: str = "pm"
    leave_hours: Optional[float] = None
    substitute_employee_id: Optional[str] = None


class OvertimeSubmitRequest(BaseModel):
    store_id: str
    employee_id: str
    overtime_type: str = "weekday"
    work_date: str
    start_time: datetime
    end_time: datetime
    hours: float
    reason: str
    compensatory: bool = False


class ApprovalActionRequest(BaseModel):
    approver_id: str
    approver_name: str = ""
    comment: str = ""
    reason: str = ""


# ── 请假 ───────────────────────────────────────────────────


@router.post("/hr/leave/submit")
async def submit_leave(
    req: LeaveSubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """提交请假申请"""
    svc = LeaveService(store_id=req.store_id)
    try:
        result = await svc.submit_leave(db, req.model_dump())
        await db.commit()
        return {
            "id": str(result.id),
            "status": result.status.value,
            "message": "请假申请已提交",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/hr/leave/{request_id}/approve")
async def approve_leave(
    request_id: str,
    req: ApprovalActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """审批通过请假"""
    svc = LeaveService(store_id=current_user.store_id)
    try:
        result = await svc.approve_leave(db, request_id, req.approver_id, req.approver_name)
        await db.commit()
        return {"id": str(result.id), "status": result.status.value}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/hr/leave/{request_id}/reject")
async def reject_leave(
    request_id: str,
    req: ApprovalActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """驳回请假"""
    svc = LeaveService(store_id=current_user.store_id)
    try:
        result = await svc.reject_leave(db, request_id, req.approver_id, req.reason)
        await db.commit()
        return {"id": str(result.id), "status": result.status.value}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/hr/leave/list")
async def get_leave_list(
    store_id: str = Query(...),
    status: Optional[str] = None,
    month: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取请假列表"""
    svc = LeaveService(store_id=store_id)
    items = await svc.get_leave_list(db, store_id, status=status, month=month)
    return {"items": items, "total": len(items)}


@router.get("/hr/leave/balance/{employee_id}")
async def get_leave_balance(
    employee_id: str,
    year: int = Query(default=2026),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取假期余额"""
    svc = LeaveService(store_id=current_user.store_id)
    balances = await svc.get_leave_balance(db, employee_id, year)
    return {"employee_id": employee_id, "year": year, "balances": balances}


# ── 加班 ───────────────────────────────────────────────────


@router.post("/hr/overtime/submit")
async def submit_overtime(
    req: OvertimeSubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """提交加班申请"""
    svc = LeaveService(store_id=req.store_id)
    try:
        result = await svc.submit_overtime(db, req.model_dump())
        await db.commit()
        return {
            "id": str(result.id),
            "status": result.status.value,
            "pay_rate": float(result.pay_rate),
            "message": "加班申请已提交",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── 审批中心 ───────────────────────────────────────────────


@router.get("/hr/approval/pending")
async def get_pending_approvals(
    store_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取待审批列表"""
    svc = HRApprovalService(store_id=store_id)
    items = await svc.get_pending_list(db, store_id=store_id)
    return {"items": items, "total": len(items)}


@router.get("/hr/approval/mine")
async def get_my_approvals(
    applicant_id: str = Query(...),
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取我发起的审批"""
    svc = HRApprovalService(store_id=current_user.store_id)
    items = await svc.get_my_approvals(db, applicant_id, status=status)
    return {"items": items, "total": len(items)}


@router.post("/hr/approval/{instance_id}/approve")
async def approve_instance(
    instance_id: str,
    req: ApprovalActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """通过审批"""
    svc = HRApprovalService(store_id=current_user.store_id)
    try:
        result = await svc.approve(db, instance_id, req.approver_id, req.approver_name, req.comment)
        await db.commit()
        return {"id": str(result.id), "status": result.status.value}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/hr/approval/{instance_id}/reject")
async def reject_instance(
    instance_id: str,
    req: ApprovalActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """驳回审批"""
    svc = HRApprovalService(store_id=current_user.store_id)
    try:
        result = await svc.reject(db, instance_id, req.approver_id, req.approver_name, req.reason)
        await db.commit()
        return {"id": str(result.id), "status": result.status.value}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
