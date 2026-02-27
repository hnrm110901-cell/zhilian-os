"""
KPI Management API
KPI管理API
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import date
import structlog

from ..core.database import get_db
from ..core.dependencies import get_current_active_user, require_role
from ..models.kpi import KPI, KPIRecord
from ..models.user import User, UserRole
from ..repositories import KPIRepository
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid

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
    return [KPIResponse(
        id=k.id, name=k.name, category=k.category, description=k.description,
        unit=k.unit, target_value=k.target_value, warning_threshold=k.warning_threshold,
        critical_threshold=k.critical_threshold, is_active=k.is_active or "true"
    ) for k in kpis]


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
    return [KPIRecordResponse(
        id=str(r.id), kpi_id=r.kpi_id, store_id=r.store_id,
        record_date=r.record_date, value=r.value, notes=getattr(r, "notes", None)
    ) for r in records]


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
        id=kpi.id, name=kpi.name, category=kpi.category, description=kpi.description,
        unit=kpi.unit, target_value=kpi.target_value, warning_threshold=kpi.warning_threshold,
        critical_threshold=kpi.critical_threshold, is_active=kpi.is_active or "true"
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
        id=kpi.id, name=kpi.name, category=kpi.category, description=kpi.description,
        unit=kpi.unit, target_value=kpi.target_value, warning_threshold=kpi.warning_threshold,
        critical_threshold=kpi.critical_threshold, is_active=kpi.is_active or "true"
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
        id=str(record.id), kpi_id=record.kpi_id, store_id=record.store_id,
        record_date=record.record_date, value=record.value, notes=None
    )
