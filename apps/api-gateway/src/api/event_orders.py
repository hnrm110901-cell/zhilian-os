"""
EO执行引擎 API — Phase P3 (宴小猪能力)
EO单管理 · 演职人员 · 履约追踪 · 宴会厅展示
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
from ..services.event_order_service import event_order_service

logger = structlog.get_logger()
router = APIRouter()


# ── Request Models ──


class GenerateEORequest(BaseModel):
    store_id: str
    reservation_id: str
    event_date: date
    event_type: str = "wedding"
    guest_count: int = 100
    table_count: int = 10
    hall_id: Optional[str] = None
    budget_fen: int = 0
    special_requirements: str = ""


class ConfirmEORequest(BaseModel):
    approved_by: str


class UpdateStatusRequest(BaseModel):
    new_status: str


class FulfillmentUpdateRequest(BaseModel):
    node: str  # setup_start/guest_arrival/event_start/event_end/teardown_end
    actual_time: Optional[datetime] = None
    notes: str = ""


class AssignStaffRequest(BaseModel):
    store_id: str
    event_order_id: str
    role: str
    staff_name: str
    staff_phone: Optional[str] = None
    company: Optional[str] = None
    fee_fen: int = 0
    notes: Optional[str] = None


class UpdateStaffStatusRequest(BaseModel):
    status: str  # confirmed/declined/cancelled


class CreateHallRequest(BaseModel):
    store_id: str
    hall_name: str
    description: Optional[str] = None
    capacity_min: Optional[int] = None
    capacity_max: Optional[int] = None
    table_count_max: Optional[int] = None
    area_sqm: Optional[float] = None
    ceiling_height: Optional[float] = None
    has_led_screen: bool = False
    has_stage: bool = False
    has_natural_light: bool = False
    has_independent_entrance: bool = False
    images: Optional[List[str]] = None
    virtual_tour_url: Optional[str] = None
    price_range: Optional[str] = None
    min_price_fen: Optional[int] = None
    max_price_fen: Optional[int] = None
    features: Optional[List[str]] = None


class UpdateHallRequest(BaseModel):
    hall_name: Optional[str] = None
    description: Optional[str] = None
    capacity_min: Optional[int] = None
    capacity_max: Optional[int] = None
    table_count_max: Optional[int] = None
    area_sqm: Optional[float] = None
    ceiling_height: Optional[float] = None
    has_led_screen: Optional[bool] = None
    has_stage: Optional[bool] = None
    has_natural_light: Optional[bool] = None
    has_independent_entrance: Optional[bool] = None
    images: Optional[List[str]] = None
    virtual_tour_url: Optional[str] = None
    price_range: Optional[str] = None
    min_price_fen: Optional[int] = None
    max_price_fen: Optional[int] = None
    features: Optional[List[str]] = None
    is_active: Optional[bool] = None


# ── EO 单 Routes ──


@router.get("/event-orders")
async def list_event_orders(
    store_id: str = Query(...),
    status: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取 EO 单列表"""
    return await event_order_service.list_event_orders(session, store_id, status, start_date, end_date)


@router.get("/event-orders/{eo_id}")
async def get_event_order(
    eo_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取 EO 单详情"""
    result = await event_order_service.get_event_order(session, eo_id)
    if not result:
        raise HTTPException(status_code=404, detail="EO单不存在")
    return result


@router.post("/event-orders/generate", status_code=201)
async def generate_event_order(
    req: GenerateEORequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """AI 自动生成 EO 单"""
    result = await event_order_service.generate_eo(session=session, **req.model_dump())
    await session.commit()
    return result


@router.patch("/event-orders/{eo_id}/confirm")
async def confirm_event_order(
    eo_id: str,
    req: ConfirmEORequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """确认 EO 单"""
    try:
        result = await event_order_service.confirm_eo(session, eo_id, req.approved_by)
        await session.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/event-orders/{eo_id}/status")
async def update_eo_status(
    eo_id: str,
    req: UpdateStatusRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """更新 EO 状态"""
    try:
        result = await event_order_service.update_eo_status(session, eo_id, req.new_status)
        await session.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/event-orders/{eo_id}/fulfillment")
async def update_fulfillment(
    eo_id: str,
    req: FulfillmentUpdateRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """更新履约节点打卡"""
    try:
        result = await event_order_service.update_fulfillment(session, eo_id, req.node, req.actual_time, req.notes)
        await session.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── 演职人员 Routes ──


@router.get("/event-orders/{eo_id}/staff")
async def list_staff(
    eo_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取演职人员列表"""
    return await event_order_service.list_staff(session, eo_id)


@router.post("/event-staff", status_code=201)
async def assign_staff(
    req: AssignStaffRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """分配演职人员"""
    result = await event_order_service.assign_staff(session=session, **req.model_dump())
    await session.commit()
    return result


@router.patch("/event-staff/{staff_id}/status")
async def update_staff_status(
    staff_id: str,
    req: UpdateStaffStatusRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """更新人员确认状态"""
    try:
        result = await event_order_service.update_staff_status(session, staff_id, req.status)
        await session.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── 宴会厅展示 Routes ──


@router.get("/hall-showcase")
async def list_halls(
    store_id: str = Query(...),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取宴会厅展示列表"""
    return await event_order_service.list_halls(session, store_id)


@router.get("/hall-showcase/{hall_id}")
async def get_hall(
    hall_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取厅位详情"""
    result = await event_order_service.get_hall(session, hall_id)
    if not result:
        raise HTTPException(status_code=404, detail="厅位不存在")
    return result


@router.post("/hall-showcase", status_code=201)
async def create_hall(
    req: CreateHallRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """创建宴会厅展示"""
    result = await event_order_service.create_hall(session=session, **req.model_dump())
    await session.commit()
    return result


@router.put("/hall-showcase/{hall_id}")
async def update_hall(
    hall_id: str,
    req: UpdateHallRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """更新宴会厅展示"""
    try:
        data = req.model_dump(exclude_none=True)
        result = await event_order_service.update_hall(session, hall_id, **data)
        await session.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
