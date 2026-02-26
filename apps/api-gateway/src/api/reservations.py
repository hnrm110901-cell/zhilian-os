"""
Reservation Management API
预约管理API
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import date, time, datetime, timedelta
import structlog

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.reservation import Reservation, ReservationStatus, ReservationType
from ..models.user import User
from ..repositories import ReservationRepository
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
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
    reservation_type: str = "regular"
    table_number: Optional[str] = None
    room_name: Optional[str] = None
    special_requests: Optional[str] = None
    dietary_restrictions: Optional[str] = None
    customer_email: Optional[str] = None
    estimated_budget: Optional[int] = None   # 分
    banquet_details: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None


class UpdateReservationRequest(BaseModel):
    status: Optional[ReservationStatus] = None
    table_number: Optional[str] = None
    room_name: Optional[str] = None
    special_requests: Optional[str] = None
    arrival_time: Optional[datetime] = None
    notes: Optional[str] = None
    banquet_details: Optional[Dict[str, Any]] = None


class AssignTableRequest(BaseModel):
    table_number: str


class ReservationResponse(BaseModel):
    id: str
    store_id: str
    customer_name: str
    customer_phone: str
    customer_email: Optional[str]
    party_size: int
    reservation_date: date
    reservation_time: time
    reservation_type: str
    status: str
    table_number: Optional[str]
    room_name: Optional[str]
    special_requests: Optional[str]
    dietary_restrictions: Optional[str]
    estimated_budget: Optional[int]
    banquet_details: Optional[Dict[str, Any]]
    notes: Optional[str]
    arrival_time: Optional[datetime]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


def _to_response(r: Reservation) -> ReservationResponse:
    return ReservationResponse(
        id=str(r.id),
        store_id=r.store_id,
        customer_name=r.customer_name,
        customer_phone=r.customer_phone,
        customer_email=r.customer_email,
        party_size=r.party_size,
        reservation_date=r.reservation_date,
        reservation_time=r.reservation_time,
        reservation_type=r.reservation_type.value if hasattr(r.reservation_type, "value") else str(r.reservation_type),
        status=r.status.value if hasattr(r.status, "value") else str(r.status),
        table_number=r.table_number,
        room_name=r.room_name,
        special_requests=r.special_requests,
        dietary_restrictions=r.dietary_restrictions,
        estimated_budget=r.estimated_budget,
        banquet_details=r.banquet_details,
        notes=r.notes,
        arrival_time=r.arrival_time,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


@router.get("/reservations", response_model=List[ReservationResponse])
async def list_reservations(
    store_id: str = Query(..., description="门店ID"),
    reservation_date: Optional[date] = Query(None, description="预约日期"),
    status: Optional[str] = Query(None, description="状态筛选"),
    reservation_type: Optional[str] = Query(None, description="类型筛选"),
    upcoming: bool = Query(False, description="仅显示未来预约"),
    limit: int = Query(100, le=500),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取预约列表"""
    query = select(Reservation).where(Reservation.store_id == store_id)

    if upcoming:
        query = query.where(
            and_(
                Reservation.reservation_date >= date.today(),
                Reservation.status.in_([ReservationStatus.PENDING, ReservationStatus.CONFIRMED])
            )
        )
    elif reservation_date:
        query = query.where(Reservation.reservation_date == reservation_date)

    if status:
        query = query.where(Reservation.status == status)
    if reservation_type:
        query = query.where(Reservation.reservation_type == reservation_type)

    query = query.order_by(Reservation.reservation_date.desc(), Reservation.reservation_time).limit(limit)
    result = await session.execute(query)
    return [_to_response(r) for r in result.scalars().all()]


@router.get("/reservations/today-overview")
async def today_overview(
    store_id: str = Query(...),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """今日预约概览（统计看板数据）"""
    today = date.today()
    result = await session.execute(
        select(Reservation).where(
            and_(Reservation.store_id == store_id, Reservation.reservation_date == today)
        )
    )
    reservations = result.scalars().all()

    by_status: Dict[str, int] = {}
    by_type: Dict[str, int] = {}
    total_guests = 0
    for r in reservations:
        s = r.status.value if hasattr(r.status, "value") else str(r.status)
        t = r.reservation_type.value if hasattr(r.reservation_type, "value") else str(r.reservation_type)
        by_status[s] = by_status.get(s, 0) + 1
        by_type[t] = by_type.get(t, 0) + 1
        total_guests += r.party_size

    # 即将到来（2小时内）
    now = datetime.now().time()
    upcoming_soon = [
        _to_response(r) for r in reservations
        if r.status.value in ("pending", "confirmed")
        and r.reservation_time >= now
        and (datetime.combine(today, r.reservation_time) - datetime.now()).seconds <= 7200
    ]

    return {
        "date": today.isoformat(),
        "total": len(reservations),
        "total_guests": total_guests,
        "by_status": by_status,
        "by_type": by_type,
        "upcoming_soon": upcoming_soon,
        "pending_count": by_status.get("pending", 0),
        "confirmed_count": by_status.get("confirmed", 0),
        "seated_count": by_status.get("seated", 0),
        "no_show_count": by_status.get("no_show", 0),
    }


@router.get("/reservations/statistics")
async def get_statistics(
    store_id: str = Query(...),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """预约统计（近30天默认）"""
    end_dt = end_date or date.today()
    start_dt = start_date or (end_dt - timedelta(days=30))

    result = await session.execute(
        select(Reservation).where(
            and_(
                Reservation.store_id == store_id,
                Reservation.reservation_date >= start_dt,
                Reservation.reservation_date <= end_dt,
            )
        )
    )
    reservations = result.scalars().all()
    total = len(reservations)
    by_status: Dict[str, int] = {}
    by_type: Dict[str, int] = {}
    total_guests = 0
    for r in reservations:
        s = r.status.value if hasattr(r.status, "value") else str(r.status)
        t = r.reservation_type.value if hasattr(r.reservation_type, "value") else str(r.reservation_type)
        by_status[s] = by_status.get(s, 0) + 1
        by_type[t] = by_type.get(t, 0) + 1
        total_guests += r.party_size

    return {
        "period_start": start_dt.isoformat(),
        "period_end": end_dt.isoformat(),
        "total": total,
        "total_guests": total_guests,
        "avg_party_size": round(total_guests / total, 1) if total else 0,
        "by_status": by_status,
        "by_type": by_type,
        "confirmed_rate": round(by_status.get("confirmed", 0) / total, 3) if total else 0,
        "cancellation_rate": round(by_status.get("cancelled", 0) / total, 3) if total else 0,
        "no_show_rate": round(by_status.get("no_show", 0) / total, 3) if total else 0,
    }


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
    reservation_id = f"RES_{req.reservation_date.strftime('%Y%m%d')}_{str(uuid.uuid4())[:8].upper()}"
    r = Reservation(
        id=reservation_id,
        store_id=req.store_id,
        customer_name=req.customer_name,
        customer_phone=req.customer_phone,
        customer_email=req.customer_email,
        party_size=req.party_size,
        reservation_date=req.reservation_date,
        reservation_time=req.reservation_time,
        reservation_type=ReservationType(req.reservation_type),
        table_number=req.table_number,
        room_name=req.room_name,
        special_requests=req.special_requests,
        dietary_restrictions=req.dietary_restrictions,
        estimated_budget=req.estimated_budget,
        banquet_details=req.banquet_details or {},
        notes=req.notes,
        status=ReservationStatus.PENDING,
    )
    session.add(r)
    await session.commit()
    await session.refresh(r)
    logger.info("reservation_created", reservation_id=str(r.id), type=req.reservation_type)
    return _to_response(r)


@router.patch("/reservations/{reservation_id}", response_model=ReservationResponse)
async def update_reservation(
    reservation_id: str,
    req: UpdateReservationRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """更新预约"""
    result = await session.execute(select(Reservation).where(Reservation.id == reservation_id))
    r = result.scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="预约不存在")
    for field, value in req.model_dump(exclude_none=True).items():
        setattr(r, field, value)
    if req.status == ReservationStatus.CANCELLED:
        r.cancelled_at = datetime.utcnow()
    if req.status == ReservationStatus.ARRIVED:
        r.arrival_time = datetime.utcnow()
    await session.commit()
    await session.refresh(r)
    logger.info("reservation_updated", reservation_id=reservation_id, status=req.status)
    return _to_response(r)


@router.post("/reservations/{reservation_id}/checkin", response_model=ReservationResponse)
async def checkin_reservation(
    reservation_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """顾客到店签到"""
    result = await session.execute(select(Reservation).where(Reservation.id == reservation_id))
    r = result.scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="预约不存在")
    if r.status not in (ReservationStatus.PENDING, ReservationStatus.CONFIRMED):
        raise HTTPException(status_code=400, detail=f"当前状态 {r.status.value} 不可签到")
    r.status = ReservationStatus.ARRIVED
    r.arrival_time = datetime.utcnow()
    await session.commit()
    await session.refresh(r)
    logger.info("reservation_checkin", reservation_id=reservation_id)
    return _to_response(r)


@router.post("/reservations/{reservation_id}/seat", response_model=ReservationResponse)
async def seat_reservation(
    reservation_id: str,
    req: AssignTableRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """分配桌位并入座"""
    result = await session.execute(select(Reservation).where(Reservation.id == reservation_id))
    r = result.scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="预约不存在")
    r.table_number = req.table_number
    r.status = ReservationStatus.SEATED
    await session.commit()
    await session.refresh(r)
    logger.info("reservation_seated", reservation_id=reservation_id, table=req.table_number)
    return _to_response(r)


@router.post("/reservations/{reservation_id}/no-show", response_model=ReservationResponse)
async def mark_no_show(
    reservation_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """标记未到店"""
    result = await session.execute(select(Reservation).where(Reservation.id == reservation_id))
    r = result.scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="预约不存在")
    r.status = ReservationStatus.NO_SHOW
    await session.commit()
    await session.refresh(r)
    return _to_response(r)


@router.post("/reservations/{reservation_id}/complete", response_model=ReservationResponse)
async def complete_reservation(
    reservation_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """完成预约"""
    result = await session.execute(select(Reservation).where(Reservation.id == reservation_id))
    r = result.scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="预约不存在")
    r.status = ReservationStatus.COMPLETED
    await session.commit()
    await session.refresh(r)
    return _to_response(r)
