"""
HR Settlement API — 离职结算接口
计算/创建/审批/打款离职结算单
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date
from uuid import UUID
import structlog

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.user import User
from ..services.settlement_service import SettlementService
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()
router = APIRouter()


# ── Request / Response Models ────────────────────────────

class SettlementCalcRequest(BaseModel):
    store_id: str
    brand_id: str
    employee_id: str
    last_work_date: str  # YYYY-MM-DD
    separation_type: str = "resign"  # resign/dismiss/expire/mutual
    compensation_type: str = "none"  # none/n/n_plus_1/2n
    annual_leave_method: str = "legal"  # legal(3倍)/negotiate(1倍)
    overtime_pay_fen: int = 0
    bonus_fen: int = 0
    deduction_fen: int = 0
    deduction_detail: str = ""


class SettlementCreateRequest(SettlementCalcRequest):
    remark: str = ""


class HandoverUpdateRequest(BaseModel):
    handover_items: List[dict] = Field(
        default_factory=list,
        description='[{"item": "工牌", "returned": true}, {"item": "工服", "returned": false}]',
    )


class ApproveRequest(BaseModel):
    approver_id: str
    approver_name: str = ""


class PayRequest(BaseModel):
    paid_by: str


def _record_to_dict(record) -> dict:
    """将 SettlementRecord 转为响应 dict"""
    return {
        "id": str(record.id),
        "store_id": record.store_id,
        "brand_id": record.brand_id,
        "employee_id": record.employee_id,
        "employee_name": record.employee_name,
        "separation_type": record.separation_type,
        "last_work_date": record.last_work_date.isoformat() if record.last_work_date else None,
        "separation_date": record.separation_date.isoformat() if record.separation_date else None,
        "work_days_last_month": record.work_days_last_month,
        "last_month_salary_fen": record.last_month_salary_fen,
        "last_month_salary_yuan": round((record.last_month_salary_fen or 0) / 100, 2),
        "unused_annual_days": record.unused_annual_days,
        "annual_leave_compensation_fen": record.annual_leave_compensation_fen,
        "annual_leave_compensation_yuan": round((record.annual_leave_compensation_fen or 0) / 100, 2),
        "annual_leave_calc_method": record.annual_leave_calc_method,
        "service_years_x10": record.service_years,
        "compensation_months_x10": record.compensation_months,
        "compensation_base_fen": record.compensation_base_fen,
        "economic_compensation_fen": record.economic_compensation_fen,
        "economic_compensation_yuan": round((record.economic_compensation_fen or 0) / 100, 2),
        "compensation_type": record.compensation_type,
        "overtime_pay_fen": record.overtime_pay_fen,
        "overtime_pay_yuan": round((record.overtime_pay_fen or 0) / 100, 2),
        "bonus_fen": record.bonus_fen,
        "bonus_yuan": round((record.bonus_fen or 0) / 100, 2),
        "deduction_fen": record.deduction_fen,
        "deduction_yuan": round((record.deduction_fen or 0) / 100, 2),
        "deduction_detail": record.deduction_detail,
        "total_payable_fen": record.total_payable_fen,
        "total_payable_yuan": round((record.total_payable_fen or 0) / 100, 2),
        "handover_items": record.handover_items or [],
        "handover_completed": record.handover_completed,
        "status": record.status,
        "paid_at": record.paid_at.isoformat() if record.paid_at else None,
        "paid_by": record.paid_by,
        "remark": record.remark,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


# ── API Endpoints ────────────────────────────────────────

@router.post("/hr/settlement/calculate")
async def calculate_settlement(
    req: SettlementCalcRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    计算离职结算（不入库，预览用）。
    根据员工历史工资、未休年假、工龄等自动计算各项结算金额。
    """
    try:
        svc = SettlementService(req.store_id, req.brand_id)
        result = await svc.calculate_settlement(
            db=db,
            employee_id=req.employee_id,
            last_work_date=date.fromisoformat(req.last_work_date),
            separation_type=req.separation_type,
            compensation_type=req.compensation_type,
            annual_leave_method=req.annual_leave_method,
            overtime_pay_fen=req.overtime_pay_fen,
            bonus_fen=req.bonus_fen,
            deduction_fen=req.deduction_fen,
            deduction_detail=req.deduction_detail,
        )
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("settlement.calculate_failed", error=str(e), employee_id=req.employee_id)
        raise HTTPException(status_code=500, detail=f"结算计算失败: {str(e)}")


@router.post("/hr/settlement/create")
async def create_settlement(
    req: SettlementCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    创建离职结算单（计算并入库）。
    """
    try:
        svc = SettlementService(req.store_id, req.brand_id)
        record = await svc.create_settlement(
            db=db,
            employee_id=req.employee_id,
            last_work_date=date.fromisoformat(req.last_work_date),
            separation_type=req.separation_type,
            compensation_type=req.compensation_type,
            annual_leave_method=req.annual_leave_method,
            overtime_pay_fen=req.overtime_pay_fen,
            bonus_fen=req.bonus_fen,
            deduction_fen=req.deduction_fen,
            deduction_detail=req.deduction_detail,
            remark=req.remark,
        )
        await db.commit()
        return {"success": True, "data": _record_to_dict(record)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("settlement.create_failed", error=str(e), employee_id=req.employee_id)
        raise HTTPException(status_code=500, detail=f"创建结算单失败: {str(e)}")


@router.get("/hr/settlement/list")
async def list_settlements(
    store_id: str = Query(..., description="门店ID"),
    brand_id: str = Query("", description="品牌ID"),
    status: Optional[str] = Query(None, description="状态筛选: draft/pending_approval/approved/paid/disputed"),
    employee_id: Optional[str] = Query(None, description="员工ID筛选"),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """结算单列表"""
    svc = SettlementService(store_id, brand_id)
    result = await svc.list_settlements(
        db, status=status, employee_id=employee_id,
        offset=offset, limit=limit,
    )
    return {
        "success": True,
        "data": {
            "total": result["total"],
            "items": [_record_to_dict(r) for r in result["items"]],
            "offset": result["offset"],
            "limit": result["limit"],
        },
    }


@router.get("/hr/settlement/{settlement_id}")
async def get_settlement(
    settlement_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """查看结算单详情"""
    svc = SettlementService("", "")
    record = await svc.get_settlement(db, settlement_id)
    if not record:
        raise HTTPException(status_code=404, detail="结算单不存在")
    return {"success": True, "data": _record_to_dict(record)}


@router.put("/hr/settlement/{settlement_id}/handover")
async def update_handover(
    settlement_id: UUID,
    req: HandoverUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """更新交接清单"""
    try:
        svc = SettlementService("", "")
        record = await svc.update_handover(db, settlement_id, req.handover_items)
        await db.commit()
        return {"success": True, "data": _record_to_dict(record)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/hr/settlement/{settlement_id}/approve")
async def approve_settlement(
    settlement_id: UUID,
    req: ApproveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """审批结算单"""
    try:
        svc = SettlementService("", "")
        record = await svc.approve_settlement(db, settlement_id, req.approver_id)
        await db.commit()
        return {"success": True, "data": _record_to_dict(record)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/hr/settlement/{settlement_id}/pay")
async def mark_paid(
    settlement_id: UUID,
    req: PayRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """标记已打款"""
    try:
        svc = SettlementService("", "")
        record = await svc.mark_paid(db, settlement_id, req.paid_by)
        await db.commit()
        return {"success": True, "data": _record_to_dict(record)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
