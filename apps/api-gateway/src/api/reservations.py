"""
Reservation Management API
预约管理API
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, time, datetime
import structlog

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.reservation import Reservation, ReservationStatus
from ..models.user import User
from ..repositories import ReservationRepository
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid

logger = structlog.get_logger()
router = APIRouter()


class CreateReservationRequest(BaseModel):
    store_id: str
    customer_name: str
    customer_phone: str
    party_size: int
    reservation_date: date
    reservation_time: time
    table_number: Optional[str] = None
    special_requests: Optional[str] = None


class UpdateReservationRequest(BaseModel):
    status: Optional[ReservationStatus] = None
    table_number: Optional[str] = None
    special_requests: Optional[str] = None
    arrival_time: Optional[datetime] = None


class ReservationResponse(BaseModel):
    id: str
    store_id: str
    customer_name: str
    customer_phone: str
    party_size: int
    reservation_date: date
    reservation_time: time
    status: str
    table_number: Optional[str]
    special_requests: Optional[str]
    arrival_time: Optional[datetime]


@router.get("/reservations", response_model=List[ReservationResponse])
async def list_reservations(
    store_id: str = Query(..., description="门店ID"),
    reservation_date: Optional[date] = Query(None, description="预约日期"),
    upcoming: bool = Query(False, description="仅显示未来预约"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取预约列表"""
    if upcoming:
        reservations = await ReservationRepository.get_upcoming(session, store_id)
    elif reservation_date:
        reservations = await ReservationRepository.get_by_date(session, store_id, reservation_date)
    else:
        result = await session.execute(
            select(Reservation).where(Reservation.store_id == store_id)
            .order_by(Reservation.reservation_date.desc(), Reservation.reservation_time)
        )
        reservations = result.scalars().all()
    return [_to_response(r) for r in reservations]


@router.get("/reservations/{reservation_id}", response_model=ReservationResponse)
async def get_reservation(
    reservation_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取预约详情"""
    result = await session.execute(select(Reservation).where(Reservation.id == reservation_id))
    r = result.scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="预约不存在")
    return _to_response(r)


@router.post("/reservations", response_model=ReservationResponse, status_code=201)
async def create_reservation(
    req: CreateReservationRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """创建预约"""
    r = Reservation(
        store_id=req.store_id,
        customer_name=req.customer_name,
        customer_phone=req.customer_phone,
        party_size=req.party_size,
        reservation_date=req.reservation_date,
        reservation_time=req.reservation_time,
        table_number=req.table_number,
        special_requests=req.special_requests,
        status=ReservationStatus.PENDING,
    )
    session.add(r)
    await session.commit()
    await session.refresh(r)
    logger.info("reservation_created", reservation_id=str(r.id))
    return _to_response(r)


@router.patch("/reservations/{reservation_id}", response_model=ReservationResponse)
async def update_reservation(
    reservation_id: str,
    req: UpdateReservationRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """更新预约状态"""
    result = await session.execute(select(Reservation).where(Reservation.id == reservation_id))
    r = result.scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="预约不存在")
    for field, value in req.model_dump(exclude_none=True).items():
        setattr(r, field, value)
    if req.status == ReservationStatus.CANCELLED:
        r.cancelled_at = datetime.utcnow()
    await session.commit()
    await session.refresh(r)
    return _to_response(r)


def _to_response(r: Reservation) -> ReservationResponse:
    return ReservationResponse(
        id=str(r.id),
        store_id=r.store_id,
        customer_name=r.customer_name,
        customer_phone=r.customer_phone,
        party_size=r.party_size,
        reservation_date=r.reservation_date,
        reservation_time=r.reservation_time,
        status=r.status.value if hasattr(r.status, "value") else str(r.status),
        table_number=r.table_number,
        special_requests=r.special_requests,
        arrival_time=r.arrival_time,
    )
