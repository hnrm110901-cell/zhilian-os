"""
KPI Management API
KPI管理API
"""

import uuid
from datetime import date
from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user, require_role
from ..models.kpi import KPI, KPIRecord
from ..models.user import User, UserRole
from ..repositories import KPIRepository

logger = structlog.get_logger()
router = APIRouter()


class KPIResponse(BaseModel):
    id: str
    name: str
    category: str
    description: Optional[str]
    unit: Optional[str]
    target_value: Optional[float]
    warning_threshold: Optional[float]
    critical_threshold: Optional[float]
    is_active: str


class KPIRecordResponse(BaseModel):
    id: str
    kpi_id: str
    store_id: str
    record_date: date
    value: float
    notes: Optional[str]


class CreateKPIRecordRequest(BaseModel):
    kpi_id: str
    store_id: str
    record_date: date
    value: float
    notes: Optional[str] = None


@router.get("/kpis", response_model=List[KPIResponse])
async def list_kpis(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取所有KPI定义"""
    kpis = await KPIRepository.get_all_active(session)
    return [
        KPIResponse(
            id=k.id,
            name=k.name,
            category=k.category,
            description=k.description,
            unit=k.unit,
            target_value=k.target_value,
            warning_threshold=k.warning_threshold,
            critical_threshold=k.critical_threshold,
            is_active=k.is_active or "true",
        )
        for k in kpis
    ]


@router.get("/kpis/records/store", response_model=List[KPIRecordResponse])
async def get_kpi_records(
    store_id: str = Query(..., description="门店ID"),
    start_date: date = Query(..., description="开始日期"),
    end_date: date = Query(..., description="结束日期"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取门店KPI历史记录"""
    records = await KPIRepository.get_records_by_date_range(session, store_id, start_date, end_date)
    return [
        KPIRecordResponse(
            id=str(r.id),
            kpi_id=r.kpi_id,
            store_id=r.store_id,
            record_date=r.record_date,
            value=r.value,
            notes=getattr(r, "notes", None),
        )
        for r in records
    ]


@router.get("/kpis/{kpi_id}", response_model=KPIResponse)
async def get_kpi(
    kpi_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取KPI详情"""
    result = await session.execute(select(KPI).where(KPI.id == kpi_id))
    kpi = result.scalar_one_or_none()
    if not kpi:
        raise HTTPException(status_code=404, detail="KPI不存在")
    return KPIResponse(
        id=kpi.id,
        name=kpi.name,
        category=kpi.category,
        description=kpi.description,
        unit=kpi.unit,
        target_value=kpi.target_value,
        warning_threshold=kpi.warning_threshold,
        critical_threshold=kpi.critical_threshold,
        is_active=kpi.is_active or "true",
    )


class UpdateKPIThresholdsRequest(BaseModel):
    target_value: Optional[float] = None
    warning_threshold: Optional[float] = None
    critical_threshold: Optional[float] = None


@router.patch("/kpis/{kpi_id}/thresholds", response_model=KPIResponse)
async def update_kpi_thresholds(
    kpi_id: str,
    req: UpdateKPIThresholdsRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.STORE_MANAGER)),
):
    """更新 KPI 预警阈值（店长及以上可操作）"""
    result = await session.execute(select(KPI).where(KPI.id == kpi_id))
    kpi = result.scalar_one_or_none()
    if not kpi:
        raise HTTPException(status_code=404, detail="KPI不存在")
    for field, value in req.model_dump(exclude_none=True).items():
        setattr(kpi, field, value)
    await session.commit()
    await session.refresh(kpi)
    logger.info("kpi_thresholds_updated", kpi_id=kpi_id, user_id=str(current_user.id))
    return KPIResponse(
        id=kpi.id,
        name=kpi.name,
        category=kpi.category,
        description=kpi.description,
        unit=kpi.unit,
        target_value=kpi.target_value,
        warning_threshold=kpi.warning_threshold,
        critical_threshold=kpi.critical_threshold,
        is_active=kpi.is_active or "true",
    )


async def create_kpi_record(
    req: CreateKPIRecordRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.STORE_MANAGER)),
):
    """录入KPI数据"""
    record = KPIRecord(
        kpi_id=req.kpi_id,
        store_id=req.store_id,
        record_date=req.record_date,
        value=req.value,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    logger.info("kpi_record_created", kpi_id=req.kpi_id, store_id=req.store_id, date=str(req.record_date))
    return KPIRecordResponse(
        id=str(record.id),
        kpi_id=record.kpi_id,
        store_id=record.store_id,
        record_date=record.record_date,
        value=record.value,
        notes=None,
    )


@router.get("/kpis/alerts/trend")
async def run_trend_alerts(
    store_id: Optional[str] = Query(None, description="指定门店，不传则扫描所有门店"),
    lookback_days: int = Query(14, ge=3, le=90, description="趋势回望天数"),
    forecast_days: int = Query(7, ge=1, le=30, description="向前预测天数"),
    dry_run: bool = Query(False, description="仅计算趋势，不发送企微告警"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    成本率趋势预测告警。

    基于近 lookback_days 天的成本率数据，通过线性回归预测 forecast_days
    天后是否会突破阈值，提前发出趋势预警。

    - trend_status: ok | warning_trend | critical_trend
    - slope_per_day: 每天成本率增速（正数表示上涨）
    - forecasted_pct: 预测期末成本率
    """
    from src.services.kpi_alert_service import KPIAlertService

    thresholds = await KPIAlertService._get_food_cost_thresholds(session)

    if store_id:
        result = await KPIAlertService.check_store_trend(
            store_id=store_id,
            db=session,
            thresholds=thresholds,
            lookback_days=lookback_days,
            forecast_days=forecast_days,
        )
        return result

    if dry_run:
        store_ids = await KPIAlertService._get_active_store_ids(session)
        results = []
        for sid in store_ids:
            try:
                r = await KPIAlertService.check_store_trend(
                    store_id=sid,
                    db=session,
                    thresholds=thresholds,
                    lookback_days=lookback_days,
                    forecast_days=forecast_days,
                )
                results.append(r)
            except Exception as exc:
                logger.warning("trend_alert_dry_run_failed", store_id=sid, error=str(exc))
        alert_count = sum(1 for r in results if r.get("needs_trend_alert"))
        return {"dry_run": True, "total": len(results), "alert_count": alert_count, "results": results}

    return await KPIAlertService.run_trend_alerts(db=session, lookback_days=lookback_days, forecast_days=forecast_days)
