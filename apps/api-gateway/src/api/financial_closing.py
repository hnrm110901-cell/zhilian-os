"""
日清日结 API — Financial Closing (Daily Reconciliation)
POST /run               执行日结
GET  /reports           报告列表
GET  /reports/{id}      报告详情
POST /reports/{id}/rerun 重新执行
GET  /monthly           月度汇总
GET  /calendar          日历视图
GET  /anomalies         异常告警
"""

from datetime import date
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from src.core.database import get_db_session
from src.core.dependencies import get_current_active_user, require_role
from src.models.user import User, UserRole
from src.services.financial_closing_service import financial_closing_service

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/financial-closing", tags=["日清日结"])


# ── Request Models ────────────────────────────────────────────────────


class RunClosingRequest(BaseModel):
    brand_id: str = Field(..., description="品牌ID")
    closing_date: date = Field(..., description="日结日期")
    store_id: Optional[str] = Field(None, description="门店ID（空=品牌汇总）")


# ── Endpoints ─────────────────────────────────────────────────────────


@router.post("/run", summary="执行日结")
async def run_daily_closing(
    request: RunClosingRequest,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    """执行指定日期的日清日结"""
    try:
        async with get_db_session() as db:
            result = await financial_closing_service.run_daily_closing(
                db=db,
                brand_id=request.brand_id,
                closing_date=request.closing_date,
                store_id=request.store_id,
            )
        return {"success": True, "data": result}
    except Exception as e:
        logger.error("执行日结失败", error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reports", summary="日结报告列表")
async def list_reports(
    brand_id: str = Query(..., description="品牌ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, description="状态筛选"),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    """分页查询日结报告"""
    try:
        async with get_db_session() as db:
            result = await financial_closing_service.get_reports(
                db=db,
                brand_id=brand_id,
                page=page,
                page_size=page_size,
                status=status,
                start_date=start_date,
                end_date=end_date,
            )
        return {"success": True, "data": result}
    except Exception as e:
        logger.error("查询日结报告失败", error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reports/{report_id}", summary="日结报告详情")
async def get_report_detail(
    report_id: str,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    """获取日结报告详情"""
    try:
        async with get_db_session() as db:
            result = await financial_closing_service.get_report_detail(db, report_id)
        if not result:
            raise HTTPException(status_code=404, detail="报告不存在")
        return {"success": True, "data": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取日结详情失败", error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reports/{report_id}/rerun", summary="重新执行日结")
async def rerun_closing(
    report_id: str,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    """对已有报告重新执行日结"""
    try:
        async with get_db_session() as db:
            result = await financial_closing_service.rerun_closing(db, report_id)
        return {"success": True, "data": result}
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        logger.error("重新执行日结失败", error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/monthly", summary="月度汇总")
async def get_monthly_summary(
    brand_id: str = Query(...),
    year: int = Query(..., ge=2020, le=2030),
    month: int = Query(..., ge=1, le=12),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    """月度P&L汇总"""
    try:
        async with get_db_session() as db:
            result = await financial_closing_service.get_monthly_summary(db, brand_id, year, month)
        return {"success": True, "data": result}
    except Exception as e:
        logger.error("获取月度汇总失败", error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/calendar", summary="日历视图")
async def get_closing_calendar(
    brand_id: str = Query(...),
    year: int = Query(..., ge=2020, le=2030),
    month: int = Query(..., ge=1, le=12),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    """日历状态视图：每日日结状态"""
    try:
        async with get_db_session() as db:
            result = await financial_closing_service.get_closing_calendar(db, brand_id, year, month)
        return {"success": True, "data": result}
    except Exception as e:
        logger.error("获取日历视图失败", error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/anomalies", summary="异常告警")
async def get_anomaly_alerts(
    brand_id: str = Query(...),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    """获取近期异常告警"""
    try:
        async with get_db_session() as db:
            result = await financial_closing_service.get_anomaly_alerts(db, brand_id, limit)
        return {"success": True, "data": result}
    except Exception as e:
        logger.error("获取异常告警失败", error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=str(e))
