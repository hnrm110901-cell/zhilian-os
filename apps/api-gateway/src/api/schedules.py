"""
Schedule Management API
排班管理API
"""

import uuid
from datetime import date, datetime, time
from typing import List, Literal, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.database import get_db
from ..core.dependencies import get_current_active_user, require_role
from ..models.audit_log import AuditAction, AuditLog, ResourceType
from ..models.schedule import Schedule, Shift
from ..models.user import User, UserRole
from ..repositories import ScheduleRepository
from ..services.schedule_conflict_service import detect_schedule_conflicts

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


class ScheduleHistoryItem(BaseModel):
    id: str
    action: str
    description: Optional[str]
    user_id: str
    username: Optional[str]
    user_role: Optional[str]
    created_at: Optional[str]
    changes: Optional[dict] = None
    new_value: Optional[dict] = None


def _add_schedule_audit_log(
    *,
    session: AsyncSession,
    action: str,
    schedule_id: str,
    store_id: str,
    current_user: User,
    description: str,
    changes: Optional[dict] = None,
    new_value: Optional[dict] = None,
) -> None:
    session.add(
        AuditLog(
            action=action,
            resource_type=ResourceType.SCHEDULE,
            resource_id=schedule_id,
            user_id=str(current_user.id),
            username=getattr(current_user, "username", None),
            user_role=getattr(current_user, "role", None),
            description=description,
            changes=changes or {},
            new_value=new_value,
            store_id=store_id,
            status="success",
        )
    )


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
        select(Schedule)
        .options(selectinload(Schedule.shifts))
        .where(
            and_(
                Schedule.store_id == store_id,
                Schedule.schedule_date >= start_date,
                Schedule.schedule_date <= end_date,
            )
        )
        .order_by(Schedule.schedule_date)
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
    result = await session.execute(select(Schedule).options(selectinload(Schedule.shifts)).where(Schedule.id == schedule_id))
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

    conflicts = detect_schedule_conflicts(
        [
            {
                "employee_id": s.employee_id,
                "start_time": s.start_time,
                "end_time": s.end_time,
                "shift_type": s.shift_type,
                "position": s.position,
            }
            for s in req.shifts
        ]
    )
    if conflicts:
        raise HTTPException(status_code=400, detail=f"排班冲突: {conflicts[0]['message']}")

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

    _add_schedule_audit_log(
        session=session,
        action=AuditAction.CREATE,
        schedule_id=str(schedule.id),
        store_id=req.store_id,
        current_user=current_user,
        description="创建排班",
        changes={"shift_count": len(req.shifts)},
        new_value={"schedule_date": req.schedule_date.isoformat()},
    )

    await session.commit()
    result2 = await session.execute(select(Schedule).options(selectinload(Schedule.shifts)).where(Schedule.id == schedule.id))
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
    result = await session.execute(select(Schedule).options(selectinload(Schedule.shifts)).where(Schedule.id == schedule_id))
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="排班不存在")
    schedule.is_published = True
    schedule.published_by = str(current_user.id)
    _add_schedule_audit_log(
        session=session,
        action=AuditAction.UPDATE,
        schedule_id=str(schedule.id),
        store_id=schedule.store_id,
        current_user=current_user,
        description="发布排班",
        changes={"is_published": True},
        new_value={"published_by": str(current_user.id)},
    )
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
    from datetime import time as dtime

    from ..repositories import EmployeeRepository

    existing = await ScheduleRepository.get_by_date(session, req.store_id, req.schedule_date)
    if existing:
        raise HTTPException(status_code=409, detail="该日期排班已存在，请先删除再重新生成")

    persons = await EmployeeRepository.get_by_store(session, req.store_id)
    active_emps = [p for p in persons if p.is_active]
    if not active_emps:
        raise HTTPException(status_code=400, detail="该门店暂无在职员工")

    # 默认班次规则
    shift_rules = req.shift_rules or {
        "morning": {"start": "08:00", "end": "14:00", "needs": ["waiter", "cashier", "chef"]},
        "afternoon": {"start": "14:00", "end": "20:00", "needs": ["waiter", "cashier", "chef"]},
        "evening": {"start": "20:00", "end": "23:00", "needs": ["waiter", "manager"]},
    }

    # 简单贪心分配：按技能匹配，循环分配班次
    shifts_data = []
    emp_idx = 0
    for shift_type, rule in shift_rules.items():
        start_h, start_m = map(int, rule["start"].split(":"))
        end_h, end_m = map(int, rule["end"].split(":"))
        for needed_skill in rule["needs"]:
            # 找有该技能的员工（skills 存储在 Person.preferences["skills"]）
            candidates = [e for e in active_emps if needed_skill in ((e.preferences or {}).get("skills", []))]
            if not candidates:
                candidates = active_emps  # fallback
            emp = candidates[emp_idx % len(candidates)]
            emp_idx += 1
            shifts_data.append(
                CreateShiftRequest(
                    employee_id=emp.legacy_employee_id or str(emp.id),
                    shift_type=shift_type,
                    start_time=dtime(start_h, start_m),
                    end_time=dtime(end_h, end_m),
                    position=needed_skill,
                )
            )

    conflicts = detect_schedule_conflicts(
        [
            {
                "employee_id": s.employee_id,
                "start_time": s.start_time,
                "end_time": s.end_time,
                "shift_type": s.shift_type,
                "position": s.position,
            }
            for s in shifts_data
        ]
    )
    if conflicts:
        raise HTTPException(status_code=400, detail=f"自动排班冲突: {conflicts[0]['message']}")

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

    _add_schedule_audit_log(
        session=session,
        action=AuditAction.CREATE,
        schedule_id=str(schedule.id),
        store_id=req.store_id,
        current_user=current_user,
        description="自动生成排班",
        changes={"mode": "auto", "shift_count": len(shifts_data)},
        new_value={"schedule_date": req.schedule_date.isoformat()},
    )

    await session.commit()
    result2 = await session.execute(select(Schedule).options(selectinload(Schedule.shifts)).where(Schedule.id == schedule.id))
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
    result = await session.execute(select(Shift).where(and_(Shift.id == shift_id, Shift.schedule_id == schedule_id)))
    shift = result.scalar_one_or_none()
    if not shift:
        raise HTTPException(status_code=404, detail="班次不存在")
    schedule_store_result = await session.execute(select(Schedule.store_id).where(Schedule.id == schedule_id))
    schedule_store_id = schedule_store_result.scalar_one_or_none() or ""
    shift.is_confirmed = True
    if req.notes:
        shift.notes = req.notes
    _add_schedule_audit_log(
        session=session,
        action=AuditAction.UPDATE,
        schedule_id=schedule_id,
        store_id=schedule_store_id,
        current_user=current_user,
        description="确认班次",
        changes={"shift_id": str(shift.id), "is_confirmed": True},
        new_value={"notes": req.notes} if req.notes else {"is_confirmed": True},
    )
    await session.commit()
    await session.refresh(shift)
    return ShiftResponse(
        id=str(shift.id),
        employee_id=shift.employee_id,
        shift_type=shift.shift_type,
        start_time=shift.start_time,
        end_time=shift.end_time,
        position=shift.position,
        is_confirmed=shift.is_confirmed,
    )


@router.get("/schedules/{schedule_id}/history", response_model=List[ScheduleHistoryItem])
async def get_schedule_history(
    schedule_id: str,
    limit: int = Query(50, ge=1, le=200),
    action: Optional[Literal["create", "update"]] = Query(None, description="按动作筛选"),
    keyword: Optional[str] = Query(None, description="关键词（操作人/描述）"),
    order: Literal["desc", "asc"] = Query("desc", description="时间排序"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取排班历史记录（审计日志）"""
    # FastAPI direct function calls in tests can pass Query() objects as defaults.
    action_value = action if isinstance(action, str) else None
    keyword_value = keyword if isinstance(keyword, str) else None
    order_value = order if order in ("desc", "asc") else "desc"
    limit_value = limit if isinstance(limit, int) else 50

    result = await session.execute(
        select(AuditLog)
        .where(
            and_(
                AuditLog.resource_type == ResourceType.SCHEDULE,
                AuditLog.resource_id == schedule_id,
            )
        )
        .limit(200)
    )
    rows = result.scalars().all()
    if action_value:
        rows = [item for item in rows if item.action == action_value]
    if keyword_value:
        kw = keyword_value.strip().lower()
        rows = [
            item
            for item in rows
            if kw in f"{item.description or ''} {item.username or ''} {item.user_id or ''} {item.action or ''}".lower()
        ]
    rows.sort(
        key=lambda item: item.created_at.timestamp() if item.created_at else float("-inf"),
        reverse=(order_value == "desc"),
    )
    rows = rows[:limit_value]
    return [
        ScheduleHistoryItem(
            id=str(item.id),
            action=item.action,
            description=item.description,
            user_id=item.user_id,
            username=item.username,
            user_role=item.user_role,
            created_at=item.created_at.isoformat() if item.created_at else None,
            changes=item.changes,
            new_value=item.new_value,
        )
        for item in rows
    ]


@router.get("/schedules/my-schedule")
async def get_my_schedule(
    week_start: date = Query(..., description="周一日期"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """员工查看自己本周班次（按 employee_id = current_user.id 过滤）"""
    from datetime import timedelta

    week_end = week_start + timedelta(days=6)
    result = await session.execute(
        select(Schedule)
        .options(selectinload(Schedule.shifts))
        .where(
            and_(
                Schedule.schedule_date >= week_start,
                Schedule.schedule_date <= week_end,
                Schedule.is_published == True,
            )
        )
        .order_by(Schedule.schedule_date)
    )
    schedules = result.scalars().all()

    my_shifts = []
    for sched in schedules:
        for sh in sched.shifts:
            if sh.employee_id == str(current_user.id):
                my_shifts.append(
                    {
                        "date": sched.schedule_date.isoformat(),
                        "store_id": sched.store_id,
                        "shift_id": str(sh.id),
                        "shift_type": sh.shift_type,
                        "start_time": sh.start_time.strftime("%H:%M"),
                        "end_time": sh.end_time.strftime("%H:%M"),
                        "position": sh.position,
                        "is_confirmed": sh.is_confirmed or False,
                    }
                )

    return {
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "employee_id": str(current_user.id),
        "shifts": my_shifts,
        "total_shifts": len(my_shifts),
    }


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
        select(Schedule)
        .options(selectinload(Schedule.shifts))
        .where(
            and_(
                Schedule.store_id == store_id,
                Schedule.schedule_date >= week_start,
                Schedule.schedule_date <= week_end,
            )
        )
        .order_by(Schedule.schedule_date)
    )
    schedules = result.scalars().all()
    persons = await EmployeeRepository.get_by_store(session, store_id)
    emp_map = {(p.legacy_employee_id or str(p.id)): p.name for p in persons}

    days = []
    for i in range(7):
        d = week_start + timedelta(days=i)
        sched = next((s for s in schedules if s.schedule_date == d), None)
        shifts = []
        if sched:
            for sh in sched.shifts:
                shifts.append(
                    {
                        "shift_id": str(sh.id),
                        "employee_id": sh.employee_id,
                        "employee_name": emp_map.get(sh.employee_id, sh.employee_id),
                        "shift_type": sh.shift_type,
                        "start_time": sh.start_time.strftime("%H:%M"),
                        "end_time": sh.end_time.strftime("%H:%M"),
                        "position": sh.position,
                        "is_confirmed": sh.is_confirmed,
                    }
                )
        days.append(
            {
                "date": d.isoformat(),
                "schedule_id": str(sched.id) if sched else None,
                "is_published": sched.is_published if sched else False,
                "shifts": shifts,
            }
        )
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
        select(Schedule)
        .options(selectinload(Schedule.shifts))
        .where(
            and_(
                Schedule.store_id == store_id,
                Schedule.schedule_date >= start_date,
                Schedule.schedule_date <= end_date,
            )
        )
    )
    schedules = result.scalars().all()
    persons = await EmployeeRepository.get_by_store(session, store_id)
    emp_map = {(p.legacy_employee_id or str(p.id)): p.name for p in persons}

    stats: dict = {}
    for sched in schedules:
        for sh in sched.shifts:
            eid = sh.employee_id
            if eid not in stats:
                stats[eid] = {
                    "employee_id": eid,
                    "employee_name": emp_map.get(eid, eid),
                    "total_shifts": 0,
                    "total_hours": 0.0,
                    "shift_breakdown": {},
                }
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
        shifts=[
            ShiftResponse(
                id=str(sh.id),
                employee_id=sh.employee_id,
                shift_type=sh.shift_type,
                start_time=sh.start_time,
                end_time=sh.end_time,
                position=sh.position,
                is_confirmed=sh.is_confirmed or False,
            )
            for sh in (s.shifts or [])
        ],
    )
