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
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

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
    result = await session.execute(
        select(Schedule).options(selectinload(Schedule.shifts)).where(
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
    result = await session.execute(
        select(Schedule).options(selectinload(Schedule.shifts)).where(Schedule.id == schedule_id)
    )
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
    result2 = await session.execute(
        select(Schedule).options(selectinload(Schedule.shifts)).where(Schedule.id == schedule.id)
    )
    schedule = result2.scalar_one()
    logger.info("schedule_created", schedule_id=str(schedule.id), date=str(req.schedule_date))
    return _to_schedule_response(schedule)


@router.post("/schedules/{schedule_id}/publish", response_model=ScheduleResponse)
async def publish_schedule(
    schedule_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.STORE_MANAGER)),
):
    """发布排班"""
    result = await session.execute(
        select(Schedule).options(selectinload(Schedule.shifts)).where(Schedule.id == schedule_id)
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="排班不存在")
    schedule.is_published = True
    schedule.published_by = str(current_user.id)
    await session.commit()
    return _to_schedule_response(schedule)


class AutoScheduleRequest(BaseModel):
    store_id: str
    schedule_date: date
    shift_rules: Optional[dict] = None  # 可选自定义班次规则


class ConfirmShiftRequest(BaseModel):
    notes: Optional[str] = None


@router.post("/schedules/auto-generate", response_model=ScheduleResponse, status_code=201)
async def auto_generate_schedule(
    req: AutoScheduleRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.STORE_MANAGER)),
):
    """AI智能排班：根据员工技能自动生成当日排班"""
    from ..repositories import EmployeeRepository
    from datetime import time as dtime

    existing = await ScheduleRepository.get_by_date(session, req.store_id, req.schedule_date)
    if existing:
        raise HTTPException(status_code=409, detail="该日期排班已存在，请先删除再重新生成")

    employees = await EmployeeRepository.get_by_store(session, req.store_id)
    active_emps = [e for e in employees if e.is_active]
    if not active_emps:
        raise HTTPException(status_code=400, detail="该门店暂无在职员工")

    # 默认班次规则
    shift_rules = req.shift_rules or {
        "morning":   {"start": "08:00", "end": "14:00", "needs": ["waiter", "cashier", "chef"]},
        "afternoon": {"start": "14:00", "end": "20:00", "needs": ["waiter", "cashier", "chef"]},
        "evening":   {"start": "20:00", "end": "23:00", "needs": ["waiter", "manager"]},
    }

    # 简单贪心分配：按技能匹配，循环分配班次
    shifts_data = []
    emp_idx = 0
    for shift_type, rule in shift_rules.items():
        start_h, start_m = map(int, rule["start"].split(":"))
        end_h, end_m = map(int, rule["end"].split(":"))
        for needed_skill in rule["needs"]:
            # 找有该技能的员工
            candidates = [e for e in active_emps if needed_skill in (e.skills or [])]
            if not candidates:
                candidates = active_emps  # fallback
            emp = candidates[emp_idx % len(candidates)]
            emp_idx += 1
            shifts_data.append(CreateShiftRequest(
                employee_id=emp.id,
                shift_type=shift_type,
                start_time=dtime(start_h, start_m),
                end_time=dtime(end_h, end_m),
                position=needed_skill,
            ))

    schedule = Schedule(
        store_id=req.store_id,
        schedule_date=req.schedule_date,
        total_employees=str(len({s.employee_id for s in shifts_data})),
    )
    session.add(schedule)
    await session.flush()

    for s in shifts_data:
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
    result2 = await session.execute(
        select(Schedule).options(selectinload(Schedule.shifts)).where(Schedule.id == schedule.id)
    )
    schedule = result2.scalar_one()
    logger.info("auto_schedule_generated", schedule_id=str(schedule.id), date=str(req.schedule_date))
    return _to_schedule_response(schedule)


@router.patch("/schedules/{schedule_id}/shifts/{shift_id}/confirm", response_model=ShiftResponse)
async def confirm_shift(
    schedule_id: str,
    shift_id: str,
    req: ConfirmShiftRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """确认班次"""
    result = await session.execute(
        select(Shift).where(and_(Shift.id == shift_id, Shift.schedule_id == schedule_id))
    )
    shift = result.scalar_one_or_none()
    if not shift:
        raise HTTPException(status_code=404, detail="班次不存在")
    shift.is_confirmed = True
    if req.notes:
        shift.notes = req.notes
    await session.commit()
    await session.refresh(shift)
    return ShiftResponse(
        id=str(shift.id), employee_id=shift.employee_id, shift_type=shift.shift_type,
        start_time=shift.start_time, end_time=shift.end_time,
        position=shift.position, is_confirmed=shift.is_confirmed,
    )


@router.get("/schedules/week-view")
async def get_week_view(
    store_id: str = Query(...),
    week_start: date = Query(..., description="周一日期"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取一周排班视图"""
    from datetime import timedelta
    from ..repositories import EmployeeRepository

    week_end = week_start + timedelta(days=6)
    result = await session.execute(
        select(Schedule).options(selectinload(Schedule.shifts)).where(
            and_(
                Schedule.store_id == store_id,
                Schedule.schedule_date >= week_start,
                Schedule.schedule_date <= week_end,
            )
        ).order_by(Schedule.schedule_date)
    )
    schedules = result.scalars().all()
    employees = await EmployeeRepository.get_by_store(session, store_id)
    emp_map = {e.id: e.name for e in employees}

    days = []
    for i in range(7):
        d = week_start + timedelta(days=i)
        sched = next((s for s in schedules if s.schedule_date == d), None)
        shifts = []
        if sched:
            for sh in sched.shifts:
                shifts.append({
                    "shift_id": str(sh.id),
                    "employee_id": sh.employee_id,
                    "employee_name": emp_map.get(sh.employee_id, sh.employee_id),
                    "shift_type": sh.shift_type,
                    "start_time": sh.start_time.strftime("%H:%M"),
                    "end_time": sh.end_time.strftime("%H:%M"),
                    "position": sh.position,
                    "is_confirmed": sh.is_confirmed,
                })
        days.append({
            "date": d.isoformat(),
            "schedule_id": str(sched.id) if sched else None,
            "is_published": sched.is_published if sched else False,
            "shifts": shifts,
        })
    return {"week_start": week_start.isoformat(), "week_end": week_end.isoformat(), "days": days}


@router.get("/schedules/stats")
async def get_schedule_stats(
    store_id: str = Query(...),
    start_date: date = Query(...),
    end_date: date = Query(...),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """员工工时统计"""
    from ..repositories import EmployeeRepository

    result = await session.execute(
        select(Schedule).options(selectinload(Schedule.shifts)).where(
            and_(
                Schedule.store_id == store_id,
                Schedule.schedule_date >= start_date,
                Schedule.schedule_date <= end_date,
            )
        )
    )
    schedules = result.scalars().all()
    employees = await EmployeeRepository.get_by_store(session, store_id)
    emp_map = {e.id: e.name for e in employees}

    stats: dict = {}
    for sched in schedules:
        for sh in sched.shifts:
            eid = sh.employee_id
            if eid not in stats:
                stats[eid] = {"employee_id": eid, "employee_name": emp_map.get(eid, eid), "total_shifts": 0, "total_hours": 0.0, "shift_breakdown": {}}
            hours = (sh.end_time.hour * 60 + sh.end_time.minute - sh.start_time.hour * 60 - sh.start_time.minute) / 60
            stats[eid]["total_shifts"] += 1
            stats[eid]["total_hours"] = round(stats[eid]["total_hours"] + hours, 1)
            stats[eid]["shift_breakdown"][sh.shift_type] = stats[eid]["shift_breakdown"].get(sh.shift_type, 0) + 1

    return {"stats": list(stats.values()), "period": {"start": start_date.isoformat(), "end": end_date.isoformat()}}


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
