"""三角对账 API — 执行对账/查询记录/手动匹配/争议解决/汇总统计"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.core.dependencies import require_role
from src.models.user import User, UserRole
from src.services.tri_reconcile_service import TriReconcileService

router = APIRouter(prefix="/tri-recon", tags=["tri-reconciliation"])

svc = TriReconcileService()


# ── 请求模型 ──────────────────────────────────────────────────────────────────


class RunReconciliationRequest(BaseModel):
    brand_id: str = "default"
    target_date: date
    store_id: Optional[str] = None


class ManualMatchRequest(BaseModel):
    order_id: Optional[str] = None
    payment_id: Optional[str] = None
    bank_id: Optional[str] = None
    invoice_id: Optional[str] = None


class ResolveDisputeRequest(BaseModel):
    notes: str


# ── 执行对账 ──────────────────────────────────────────────────────────────────


@router.post("/run")
async def run_reconciliation(
    req: RunReconciliationRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """对指定日期执行三角对账（Order ↔ Payment ↔ Bank ↔ Invoice）"""
    result = await svc.run_reconciliation(
        db,
        req.brand_id,
        req.target_date,
        req.store_id,
    )
    return {
        "success": True,
        "message": f"对账完成：共 {result['total']} 条记录",
        "data": result,
    }


# ── 记录列表 ──────────────────────────────────────────────────────────────────


@router.get("/records")
async def list_records(
    brand_id: str = Query("default"),
    target_date: Optional[date] = Query(None),
    match_level: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """查询三角对账记录列表（支持筛选）"""
    data = await svc.get_records(
        db,
        brand_id,
        target_date,
        match_level,
        status,
        page,
        page_size,
    )
    return {"success": True, "data": data}


# ── 记录详情 ──────────────────────────────────────────────────────────────────


@router.get("/records/{record_id}")
async def get_record_detail(
    record_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """获取单条对账记录详情（含四方实体摘要）"""
    data = await svc.get_record_detail(db, record_id)
    if not data:
        raise HTTPException(status_code=404, detail="对账记录不存在")
    return {"success": True, "data": data}


# ── 手动匹配 ──────────────────────────────────────────────────────────────────


@router.post("/records/{record_id}/manual-match")
async def manual_match(
    record_id: str,
    req: ManualMatchRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """手动将订单/支付/银行流水/发票关联到对账记录"""
    data = await svc.manual_match(
        db,
        record_id,
        req.order_id,
        req.payment_id,
        req.bank_id,
        req.invoice_id,
    )
    if not data:
        raise HTTPException(status_code=404, detail="对账记录不存在")
    return {"success": True, "message": "手动匹配成功", "data": data}


# ── 解决争议 ──────────────────────────────────────────────────────────────────


@router.post("/records/{record_id}/resolve")
async def resolve_dispute(
    record_id: str,
    req: ResolveDisputeRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """标记争议记录为已解决"""
    data = await svc.resolve_dispute(db, record_id, req.notes)
    if not data:
        raise HTTPException(status_code=404, detail="对账记录不存在")
    return {"success": True, "message": "争议已解决", "data": data}


# ── 汇总统计 ──────────────────────────────────────────────────────────────────


@router.get("/summary")
async def get_summary(
    brand_id: str = Query("default"),
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """获取指定周期的三角对账汇总统计"""
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="开始日期不能晚于结束日期")
    data = await svc.get_summary(db, brand_id, start_date, end_date)
    return {"success": True, "data": data}
