"""
Schedule Management API
排班管理API
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, time
import uuid
import structlog

from ..core.database import get_db
from ..core.dependencies import get_current_active_user, require_role
from ..models.schedule import Schedule, Shift
from ..models.user import User, UserRole
from ..repositories import ScheduleRepository
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

logger = structlog.get_logger()
router = APIRouter()


class CreateShiftRequest(BaseModel):
    employee_id: str
    shift_type: str  # morning / afternoon / evening
    start_time: time
    end_time: time
    position: Optional[str] = None


class CreateScheduleRequest(BaseModel):
    store_id: str
    schedule_date: date
    shifts: List[CreateShiftRequest] = []


class ShiftResponse(BaseModel):
    id: str
    employee_id: str
    shift_type: str
    start_time: time
    end_time: time
    position: Optional[str]
    is_confirmed: bool


class ScheduleResponse(BaseModel):
    id: str
    store_id: str
    schedule_date: date
    total_employees: Optional[str]
    total_hours: Optional[str]
    is_published: bool
    shifts: List[ShiftResponse]


@router.get("/schedules", response_model=List[ScheduleResponse])
async def list_schedules(
    store_id: str = Query(..., description="门店ID"),
    start_date: date = Query(..., description="开始日期"),
    end_date: date = Query(..., description="结束日期"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取排班列表"""
    from sqlalchemy import and_
    result = await session.execute(
        select(Schedule).where(
            and_(
                Schedule.store_id == store_id,
                Schedule.schedule_date >= start_date,
                Schedule.schedule_date <= end_date,
            )
        ).order_by(Schedule.schedule_date)
    )
    schedules = result.scalars().all()
    return [_to_schedule_response(s) for s in schedules]


@router.get("/schedules/{schedule_id}", response_model=ScheduleResponse)
async def get_schedule(
    schedule_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取排班详情"""
    result = await session.execute(select(Schedule).where(Schedule.id == schedule_id))
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="排班不存在")
    return _to_schedule_response(schedule)


@router.post("/schedules", response_model=ScheduleResponse, status_code=201)
async def create_schedule(
    req: CreateScheduleRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.STORE_MANAGER)),
):
    """创建排班"""
    existing = await ScheduleRepository.get_by_date(session, req.store_id, req.schedule_date)
    if existing:
        raise HTTPException(status_code=409, detail="该日期排班已存在")

    schedule = Schedule(
        store_id=req.store_id,
        schedule_date=req.schedule_date,
        total_employees=str(len(req.shifts)),
    )
    session.add(schedule)
    await session.flush()

    for s in req.shifts:
        shift = Shift(
            schedule_id=schedule.id,
            employee_id=s.employee_id,
            shift_type=s.shift_type,
            start_time=s.start_time,
            end_time=s.end_time,
            position=s.position,
        )
        session.add(shift)

    await session.commit()
    await session.refresh(schedule)
    logger.info("schedule_created", schedule_id=str(schedule.id), date=str(req.schedule_date))
    return _to_schedule_response(schedule)


@router.post("/schedules/{schedule_id}/publish", response_model=ScheduleResponse)
async def publish_schedule(
    schedule_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.STORE_MANAGER)),
):
    """发布排班"""
    result = await session.execute(select(Schedule).where(Schedule.id == schedule_id))
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="排班不存在")
    schedule.is_published = True
    schedule.published_by = str(current_user.id)
    await session.commit()
    await session.refresh(schedule)
    return _to_schedule_response(schedule)


def _to_schedule_response(s: Schedule) -> ScheduleResponse:
    return ScheduleResponse(
        id=str(s.id),
        store_id=s.store_id,
        schedule_date=s.schedule_date,
        total_employees=s.total_employees,
        total_hours=s.total_hours,
        is_published=s.is_published or False,
        shifts=[ShiftResponse(
            id=str(sh.id),
            employee_id=sh.employee_id,
            shift_type=sh.shift_type,
            start_time=sh.start_time,
            end_time=sh.end_time,
            position=sh.position,
            is_confirmed=sh.is_confirmed or False,
        ) for sh in (s.shifts or [])],
    )
