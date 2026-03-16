"""
HR Payslip API — 工资条生成、PDF下载、IM推送、员工确认
"""

from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.user import User
from ..services.payslip_service import PayslipService

logger = structlog.get_logger()
router = APIRouter()


# ── 请求模型 ──────────────────────────────────────────


class BatchPushRequest(BaseModel):
    store_id: str
    brand_id: Optional[str] = None
    pay_month: str  # YYYY-MM


class ConfirmRequest(BaseModel):
    store_id: str
    brand_id: Optional[str] = None


# ── 工具函数 ──────────────────────────────────────────


def _get_service(store_id: str, brand_id: Optional[str] = None) -> PayslipService:
    return PayslipService(store_id=store_id, brand_id=brand_id or "")


# ── API 端点 ──────────────────────────────────────────


@router.get("/hr/payslip/{employee_id}/{pay_month}")
async def get_payslip_data(
    employee_id: str,
    pay_month: str,
    store_id: str = Query(..., description="门店ID"),
    brand_id: Optional[str] = Query(None, description="品牌ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取工资条结构化数据"""
    svc = _get_service(store_id, brand_id)
    data = await svc.generate_payslip_data(db, employee_id, pay_month)
    if not data:
        raise HTTPException(status_code=404, detail="工资条数据未找到")
    return {"code": 0, "data": data}


@router.get("/hr/payslip/{employee_id}/{pay_month}/pdf")
async def download_payslip_pdf(
    employee_id: str,
    pay_month: str,
    store_id: str = Query(..., description="门店ID"),
    brand_id: Optional[str] = Query(None, description="品牌ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """下载工资条PDF"""
    svc = _get_service(store_id, brand_id)
    pdf_bytes = await svc.generate_payslip_pdf(db, employee_id, pay_month)
    if not pdf_bytes:
        raise HTTPException(status_code=404, detail="工资条数据未找到，无法生成PDF")

    filename = f"payslip_{employee_id}_{pay_month}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/hr/payslip/{employee_id}/{pay_month}/push")
async def push_payslip(
    employee_id: str,
    pay_month: str,
    store_id: str = Query(..., description="门店ID"),
    brand_id: Optional[str] = Query(None, description="品牌ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """推送工资条到员工IM"""
    svc = _get_service(store_id, brand_id)
    result = await svc.push_payslip_to_employee(db, employee_id, pay_month)
    if not result.get("pushed"):
        raise HTTPException(
            status_code=400,
            detail=result.get("error", "推送失败"),
        )
    return {"code": 0, "data": result}


@router.post("/hr/payslip/batch-push")
async def batch_push_payslips(
    req: BatchPushRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """批量推送工资条到全店员工"""
    svc = _get_service(req.store_id, req.brand_id)
    result = await svc.batch_push_payslips(db, req.pay_month)
    return {"code": 0, "data": result}


@router.post("/hr/payslip/{employee_id}/{pay_month}/confirm")
async def confirm_payslip(
    employee_id: str,
    pay_month: str,
    req: ConfirmRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """员工确认工资条"""
    svc = _get_service(req.store_id, req.brand_id)
    result = await svc.confirm_payslip(db, employee_id, pay_month)
    if not result.get("confirmed"):
        raise HTTPException(
            status_code=400,
            detail=result.get("error", "确认失败"),
        )
    return {"code": 0, "data": result}


@router.get("/hr/payslip/push-status")
async def get_push_status(
    store_id: str = Query(..., description="门店ID"),
    pay_month: str = Query(..., description="薪资月份 YYYY-MM"),
    brand_id: Optional[str] = Query(None, description="品牌ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """查询工资条推送状态"""
    svc = _get_service(store_id, brand_id)
    status_list = await svc.get_push_status(db, pay_month)
    return {"code": 0, "data": status_list}
