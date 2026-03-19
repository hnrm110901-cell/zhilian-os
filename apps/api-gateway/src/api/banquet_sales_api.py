"""
宴会销控 API — Phase P2
档期管理 · 销售漏斗 · 竞对分析 · 动态定价
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
from ..services.banquet_sales_service import banquet_sales_service

logger = structlog.get_logger()
router = APIRouter()


# ── Request Models ──


class ConfigureDateRequest(BaseModel):
    store_id: str
    target_date: date
    auspicious_level: str = "normal"  # S/A/B/normal/off_peak
    price_multiplier: float = 1.0
    max_tables: Optional[int] = None
    hall_id: Optional[str] = None
    notes: Optional[str] = None


class LockDateRequest(BaseModel):
    store_id: str
    target_date: date
    reservation_id: str
    lock_days: int = 7


class CreateLeadRequest(BaseModel):
    store_id: str
    customer_name: str
    customer_phone: str
    event_type: Optional[str] = None
    owner_employee_id: Optional[str] = None
    target_date: Optional[date] = None
    table_count: Optional[int] = None
    estimated_value: int = 0  # 分


class AdvanceStageRequest(BaseModel):
    new_stage: str  # lead/intent/room_lock/negotiation/signed/...
    note: Optional[str] = None


class MarkLostRequest(BaseModel):
    lost_reason: str
    lost_to_competitor: Optional[str] = None


# ── 档期管理 Routes ──


@router.post("/banquet-sales/dates/configure", status_code=201)
async def configure_date(
    req: ConfigureDateRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """配置档期（吉日等级+定价系数）"""
    result = await banquet_sales_service.configure_date(session=session, **req.model_dump())
    await session.commit()
    return result


@router.get("/banquet-sales/dates/calendar")
async def get_calendar(
    store_id: str = Query(...),
    start_date: date = Query(...),
    end_date: date = Query(...),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取档期日历"""
    return await banquet_sales_service.get_calendar(session, store_id, start_date, end_date)


@router.post("/banquet-sales/dates/lock")
async def lock_date(
    req: LockDateRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """锁定档期"""
    result = await banquet_sales_service.lock_date(session, req.store_id, req.target_date, req.reservation_id, req.lock_days)
    await session.commit()
    return result


@router.get("/banquet-sales/dates/pricing")
async def get_pricing_suggestion(
    store_id: str = Query(...),
    target_date: date = Query(...),
    base_price_per_table: int = Query(..., description="基准桌价(分)"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """AI动态定价建议"""
    return await banquet_sales_service.get_pricing_suggestion(session, store_id, target_date, base_price_per_table)


# ── 销售漏斗 Routes ──


@router.post("/banquet-sales/leads", status_code=201)
async def create_lead(
    req: CreateLeadRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """创建销售线索"""
    result = await banquet_sales_service.create_lead(session=session, **req.model_dump())
    await session.commit()
    return result


@router.get("/banquet-sales/funnel/stats")
async def get_funnel_stats(
    store_id: str = Query(...),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """漏斗各阶段统计"""
    return await banquet_sales_service.get_funnel_stats(session, store_id)


@router.get("/banquet-sales/funnel")
async def list_funnel(
    store_id: str = Query(...),
    stage: Optional[str] = Query(None),
    employee_id: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """查询漏斗列表"""
    return await banquet_sales_service.list_funnel(session, store_id, stage, employee_id)


@router.patch("/banquet-sales/funnel/{record_id}/advance")
async def advance_stage(
    record_id: str,
    req: AdvanceStageRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """推进漏斗阶段"""
    try:
        result = await banquet_sales_service.advance_stage(session, record_id, req.new_stage, req.note)
        await session.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/banquet-sales/funnel/{record_id}/lost")
async def mark_lost(
    record_id: str,
    req: MarkLostRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """标记输单"""
    try:
        result = await banquet_sales_service.mark_lost(session, record_id, req.lost_reason, req.lost_to_competitor)
        await session.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── 竞对分析 Routes ──


@router.get("/banquet-sales/competitors")
async def list_competitors(
    store_id: str = Query(...),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """竞对列表"""
    return await banquet_sales_service.list_competitors(session, store_id)
