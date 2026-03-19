"""
餐段配置 API — P0 补齐（易订PRO 1.8 餐段设置）

管理门店营业时段（午市/晚市/宵夜等）的容量和预订规则：
- 每餐段最大桌数/客数
- 预订时间间隔
- 超订比例
- 可用时段查询
"""

import uuid
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.meal_period import MealPeriod
from ..models.reservation import Reservation, ReservationStatus
from ..models.user import User

router = APIRouter()


# ── Request / Response Models ─────────────────────────────────────


class MealPeriodRequest(BaseModel):
    store_id: str
    name: str  # 午市/晚市/宵夜
    start_hour: int  # 0-23
    end_hour: int  # 0-23
    is_active: bool = True
    max_tables: Optional[int] = None  # 最大可预订桌数
    max_guests: Optional[int] = None  # 最大接待客数
    reservation_interval: int = 30  # 预订间隔（分钟）
    last_reservation_offset: int = 60  # 结束前N分钟停止预订
    overbooking_ratio: int = 0  # 超订比例%


class MealPeriodUpdateRequest(BaseModel):
    name: Optional[str] = None
    start_hour: Optional[int] = None
    end_hour: Optional[int] = None
    is_active: Optional[bool] = None
    max_tables: Optional[int] = None
    max_guests: Optional[int] = None
    reservation_interval: Optional[int] = None
    last_reservation_offset: Optional[int] = None
    overbooking_ratio: Optional[int] = None


def _to_dict(mp: MealPeriod) -> Dict[str, Any]:
    return {
        "id": str(mp.id),
        "store_id": mp.store_id,
        "name": mp.name,
        "start_hour": mp.start_hour,
        "end_hour": mp.end_hour,
        "is_active": mp.is_active,
        "max_tables": mp.max_tables,
        "max_guests": mp.max_guests,
        "reservation_interval": mp.reservation_interval,
        "last_reservation_offset": mp.last_reservation_offset,
        "overbooking_ratio": mp.overbooking_ratio,
    }


# ── CRUD Endpoints ───────────────────────────────────────────────


@router.get("/api/v1/meal-periods")
async def list_meal_periods(
    store_id: str = Query(..., description="门店ID"),
    active_only: bool = Query(True, description="仅显示启用的"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取门店所有餐段配置"""
    query = select(MealPeriod).where(MealPeriod.store_id == store_id)
    if active_only:
        query = query.where(MealPeriod.is_active == True)
    query = query.order_by(MealPeriod.start_hour)
    result = await session.execute(query)
    return [_to_dict(mp) for mp in result.scalars().all()]


@router.post("/api/v1/meal-periods", status_code=201)
async def create_meal_period(
    req: MealPeriodRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """创建餐段配置"""
    if req.start_hour < 0 or req.start_hour > 23 or req.end_hour < 0 or req.end_hour > 23:
        raise HTTPException(status_code=400, detail="时段小时数必须在0-23之间")

    mp = MealPeriod(
        id=uuid.uuid4(),
        store_id=req.store_id,
        name=req.name,
        start_hour=req.start_hour,
        end_hour=req.end_hour,
        is_active=req.is_active,
        max_tables=req.max_tables,
        max_guests=req.max_guests,
        reservation_interval=req.reservation_interval,
        last_reservation_offset=req.last_reservation_offset,
        overbooking_ratio=req.overbooking_ratio,
    )
    session.add(mp)
    await session.commit()
    await session.refresh(mp)
    return _to_dict(mp)


@router.patch("/api/v1/meal-periods/{period_id}")
async def update_meal_period(
    period_id: str,
    req: MealPeriodUpdateRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """更新餐段配置"""
    result = await session.execute(select(MealPeriod).where(MealPeriod.id == period_id))
    mp = result.scalar_one_or_none()
    if not mp:
        raise HTTPException(status_code=404, detail="餐段不存在")

    for field, value in req.model_dump(exclude_none=True).items():
        setattr(mp, field, value)

    await session.commit()
    await session.refresh(mp)
    return _to_dict(mp)


@router.delete("/api/v1/meal-periods/{period_id}")
async def delete_meal_period(
    period_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """删除餐段配置"""
    result = await session.execute(select(MealPeriod).where(MealPeriod.id == period_id))
    mp = result.scalar_one_or_none()
    if not mp:
        raise HTTPException(status_code=404, detail="餐段不存在")

    await session.delete(mp)
    await session.commit()
    return {"message": f"餐段【{mp.name}】已删除"}


# ── 可用时段查询（核心功能） ──────────────────────────────────────


@router.get("/api/v1/meal-periods/availability")
async def get_availability(
    store_id: str = Query(..., description="门店ID"),
    query_date: date = Query(..., description="查询日期"),
    party_size: int = Query(2, description="用餐人数"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    查询指定日期各餐段的可用时段和剩余容量。

    返回每个餐段的：
    - 可选时间点列表（按 reservation_interval 生成）
    - 每个时间点的已预订桌数/客数 vs 最大容量
    - 是否可预订（考虑超订比例）
    """
    # 获取门店所有启用餐段
    result = await session.execute(
        select(MealPeriod)
        .where(and_(MealPeriod.store_id == store_id, MealPeriod.is_active == True))
        .order_by(MealPeriod.start_hour)
    )
    periods = result.scalars().all()

    if not periods:
        return {"store_id": store_id, "date": query_date.isoformat(), "periods": []}

    # 获取当日所有有效预订
    res_result = await session.execute(
        select(Reservation).where(
            and_(
                Reservation.store_id == store_id,
                Reservation.reservation_date == query_date,
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
    )
    reservations = res_result.scalars().all()

    output_periods = []
    for mp in periods:
        interval = mp.reservation_interval or 30
        last_offset = mp.last_reservation_offset or 60
        max_tables = mp.max_tables
        max_guests = mp.max_guests
        overbook = mp.overbooking_ratio or 0

        # 生成时间槽
        slots = []
        current_minutes = mp.start_hour * 60
        end_minutes = mp.end_hour * 60
        if end_minutes <= current_minutes:
            end_minutes += 24 * 60  # 跨午夜

        last_slot_minutes = end_minutes - last_offset

        while current_minutes <= last_slot_minutes:
            hour = (current_minutes // 60) % 24
            minute = current_minutes % 60
            slot_time = time(hour, minute)

            # 统计该时段±interval窗口内的预订
            window_start = (datetime.combine(query_date, slot_time) - timedelta(minutes=interval)).time()
            window_end = (datetime.combine(query_date, slot_time) + timedelta(minutes=interval)).time()

            booked_tables = 0
            booked_guests = 0
            for r in reservations:
                if window_start <= r.reservation_time <= window_end:
                    booked_tables += 1
                    booked_guests += r.party_size

            effective_max_tables = int(max_tables * (1 + overbook / 100)) if max_tables else None
            effective_max_guests = int(max_guests * (1 + overbook / 100)) if max_guests else None

            available = True
            if effective_max_tables and booked_tables >= effective_max_tables:
                available = False
            if effective_max_guests and booked_guests + party_size > effective_max_guests:
                available = False

            # 过去的时间不可预订
            if query_date == date.today():
                now = datetime.now().time()
                if slot_time <= now:
                    available = False

            slots.append(
                {
                    "time": slot_time.strftime("%H:%M"),
                    "booked_tables": booked_tables,
                    "booked_guests": booked_guests,
                    "max_tables": max_tables,
                    "max_guests": max_guests,
                    "available": available,
                }
            )

            current_minutes += interval

        output_periods.append(
            {
                "id": str(mp.id),
                "name": mp.name,
                "start_hour": mp.start_hour,
                "end_hour": mp.end_hour,
                "max_tables": max_tables,
                "max_guests": max_guests,
                "overbooking_ratio": overbook,
                "slots": slots,
                "total_booked": sum(1 for s in slots if s["booked_tables"] > 0),
                "total_available": sum(1 for s in slots if s["available"]),
            }
        )

    return {
        "store_id": store_id,
        "date": query_date.isoformat(),
        "party_size": party_size,
        "periods": output_periods,
    }
