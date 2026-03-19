"""
Reservation Management API
预约管理API

替代易订PRO核心：
1. 严格7状态机（合法转移守卫）
2. 状态变更自动触发企微通知
3. 订金管理（录入/确认）
4. 桌位冲突检测（同桌同时段不可重复预订）
"""

import uuid
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.reservation import Reservation, ReservationStatus, ReservationType
from ..models.user import User
from ..repositories import ReservationRepository

logger = structlog.get_logger()
router = APIRouter()


# ══════════════════════════════════════════════════════════════════
# 状态机定义 — 严格转移守卫（替代易订核心）
# ══════════════════════════════════════════════════════════════════
VALID_TRANSITIONS: Dict[ReservationStatus, List[ReservationStatus]] = {
    ReservationStatus.PENDING: [
        ReservationStatus.CONFIRMED,
        ReservationStatus.ARRIVED,  # 直接到店（walk-in确认）
        ReservationStatus.CANCELLED,
    ],
    ReservationStatus.CONFIRMED: [
        ReservationStatus.ARRIVED,
        ReservationStatus.CANCELLED,
        ReservationStatus.NO_SHOW,
    ],
    ReservationStatus.ARRIVED: [
        ReservationStatus.SEATED,
        ReservationStatus.CANCELLED,  # 到店后离开
    ],
    ReservationStatus.SEATED: [
        ReservationStatus.COMPLETED,
    ],
    ReservationStatus.COMPLETED: [],  # 终态
    ReservationStatus.CANCELLED: [],  # 终态
    ReservationStatus.NO_SHOW: [],  # 终态
}


def _check_transition(current: ReservationStatus, target: ReservationStatus):
    """校验状态转移合法性"""
    allowed = VALID_TRANSITIONS.get(current, [])
    if target not in allowed:
        allowed_str = ", ".join(s.value for s in allowed) if allowed else "无（终态）"
        raise HTTPException(
            status_code=400,
            detail=f"状态 {current.value} 不可转移到 {target.value}。允许的目标状态: {allowed_str}",
        )


async def _notify_reservation_change(
    reservation: Reservation,
    old_status: str,
    new_status: str,
):
    """状态变更后异步触发企微通知（fire-and-forget，失败不阻塞）"""
    try:
        from ..services.wechat_trigger_service import wechat_trigger_service

        event_map = {
            "confirmed": "reservation.confirmed",
            "cancelled": "reservation.cancelled",
            "arrived": "reservation.arrived",
        }
        event_key = event_map.get(new_status)
        if event_key and hasattr(wechat_trigger_service, "trigger"):
            await wechat_trigger_service.trigger(
                event_key,
                {
                    "store_id": reservation.store_id,
                    "reservation_id": str(reservation.id),
                    "customer_name": reservation.customer_name,
                    "customer_phone": reservation.customer_phone,
                    "party_size": reservation.party_size,
                    "reservation_date": reservation.reservation_date.isoformat() if reservation.reservation_date else "",
                    "reservation_time": reservation.reservation_time.strftime("%H:%M") if reservation.reservation_time else "",
                    "table_number": reservation.table_number or "",
                },
            )
            logger.info("reservation_notification_sent", reservation_id=str(reservation.id), event=event_key)
    except Exception as e:
        logger.warning("reservation_notification_failed", reservation_id=str(reservation.id), error=str(e))


async def _check_table_conflict(
    session: AsyncSession,
    store_id: str,
    table_number: str,
    reservation_date: date,
    reservation_time: time,
    exclude_id: Optional[str] = None,
):
    """桌位冲突检测：同门店同桌号同日期±1小时内不可重复预订"""
    time_start = (datetime.combine(reservation_date, reservation_time) - timedelta(hours=1)).time()
    time_end = (datetime.combine(reservation_date, reservation_time) + timedelta(hours=1)).time()

    query = select(Reservation).where(
        and_(
            Reservation.store_id == store_id,
            Reservation.table_number == table_number,
            Reservation.reservation_date == reservation_date,
            Reservation.reservation_time >= time_start,
            Reservation.reservation_time <= time_end,
            Reservation.status.in_(
                [
                    ReservationStatus.PENDING,
                    ReservationStatus.CONFIRMED,
                    ReservationStatus.ARRIVED,
                    ReservationStatus.SEATED,
                ]
            ),
        )
    )
    if exclude_id:
        query = query.where(Reservation.id != exclude_id)

    result = await session.execute(query)
    conflict = result.scalar_one_or_none()
    if conflict:
        raise HTTPException(
            status_code=409,
            detail=f"桌位冲突：桌号 {table_number} 在 {reservation_date} {reservation_time.strftime('%H:%M')} "
            f"附近已有预订（{conflict.customer_name}，{conflict.reservation_time.strftime('%H:%M')}）",
        )


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
    estimated_budget: Optional[int] = None  # 分
    deposit_amount: Optional[int] = None  # 订金金额（分）
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
    deposit_amount: Optional[int] = None  # 订金金额（分）
    deposit_paid: Optional[int] = None  # 已付订金（分）


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
    deposit_amount: Optional[int] = None
    deposit_paid: Optional[int] = None
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
        deposit_amount=getattr(r, "deposit_amount", None),
        deposit_paid=getattr(r, "deposit_paid", None),
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
                Reservation.status.in_([ReservationStatus.PENDING, ReservationStatus.CONFIRMED]),
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
        select(Reservation).where(and_(Reservation.store_id == store_id, Reservation.reservation_date == today))
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
        _to_response(r)
        for r in reservations
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
    # 桌位冲突检测
    if req.table_number:
        await _check_table_conflict(
            session,
            req.store_id,
            req.table_number,
            req.reservation_date,
            req.reservation_time,
        )

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
    # 订金
    if req.deposit_amount is not None:
        r.deposit_paid = req.deposit_amount
    session.add(r)
    await session.commit()
    await session.refresh(r)

    # CDP 自动关联消费者ID（异步，不阻塞）
    try:
        from ..services.dining_journey_service import link_consumer_to_reservation

        await link_consumer_to_reservation(session, r)
        await session.commit()
    except Exception:
        pass  # fire-and-forget

    # Bridge 4: 检查客户活跃旅程（优惠券/回归礼遇）
    journey_hint = None
    try:
        from ..services.lifecycle_bridge import check_active_journeys_on_reservation

        journey_info = await check_active_journeys_on_reservation(
            session,
            req.customer_phone,
            req.store_id,
        )
        if journey_info.get("has_active_journey"):
            journey_hint = journey_info
            await session.commit()
    except Exception:
        pass  # fire-and-forget

    logger.info("reservation_created", reservation_id=str(r.id), type=req.reservation_type)
    resp = _to_response(r)
    if journey_hint:
        return {**resp.model_dump(), "journey_hint": journey_hint}
    return resp


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

    old_status = r.status

    # 状态转移守卫
    if req.status is not None and req.status != r.status:
        _check_transition(r.status, req.status)

    # 桌位变更时检测冲突
    if req.table_number and req.table_number != r.table_number:
        res_date = r.reservation_date
        res_time = r.reservation_time
        await _check_table_conflict(
            session,
            r.store_id,
            req.table_number,
            res_date,
            res_time,
            exclude_id=str(r.id),
        )

    for field, value in req.model_dump(exclude_none=True).items():
        setattr(r, field, value)
    if req.status == ReservationStatus.CANCELLED:
        r.cancelled_at = datetime.utcnow()
    if req.status == ReservationStatus.ARRIVED:
        r.arrival_time = datetime.utcnow()
    await session.commit()
    await session.refresh(r)

    # 状态变更通知
    if req.status is not None and req.status != old_status:
        new_status_val = req.status.value if hasattr(req.status, "value") else str(req.status)
        await _notify_reservation_change(r, old_status.value, new_status_val)

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
    _check_transition(r.status, ReservationStatus.ARRIVED)
    old_status = r.status.value
    r.status = ReservationStatus.ARRIVED
    r.arrival_time = datetime.utcnow()
    await session.commit()
    await session.refresh(r)
    await _notify_reservation_change(r, old_status, "arrived")

    # Bridge 1: 预订到店→自动准备订单（含预排菜转入）
    try:
        from ..services.lifecycle_bridge import prepare_order_from_reservation

        order_result = await prepare_order_from_reservation(session, reservation_id)
        await session.commit()
        logger.info("reservation_auto_order", reservation_id=reservation_id, order_id=order_result.get("order_id"))
    except Exception as e:
        logger.warning("reservation_auto_order_failed", error=str(e))

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
    _check_transition(r.status, ReservationStatus.SEATED)

    # 桌位冲突检测
    await _check_table_conflict(
        session,
        r.store_id,
        req.table_number,
        r.reservation_date,
        r.reservation_time,
        exclude_id=str(r.id),
    )

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
    _check_transition(r.status, ReservationStatus.NO_SHOW)
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
    _check_transition(r.status, ReservationStatus.COMPLETED)
    r.status = ReservationStatus.COMPLETED
    await session.commit()
    await session.refresh(r)

    # 离店满意度调查（异步，不阻塞）
    try:
        from ..services.dining_journey_service import trigger_satisfaction_survey

        await trigger_satisfaction_survey(session, reservation_id)
    except Exception:
        pass  # fire-and-forget

    return _to_response(r)
