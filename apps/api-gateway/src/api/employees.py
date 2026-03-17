"""
Employee Management API
员工管理API
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import date, datetime
import json
import uuid
import structlog

from ..core.database import get_db
from ..core.dependencies import get_current_active_user, require_role
from ..models.employee import Employee
from ..models.schedule import Shift, Schedule
from ..models.store import Store
from ..models.task import Task, TaskStatus, TaskPriority
from ..models.user import User, UserRole
from ..repositories import EmployeeRepository
from ..services.wechat_service import wechat_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()
router = APIRouter()


class CreateEmployeeRequest(BaseModel):
    id: str
    store_id: str
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    position: Optional[str] = None
    skills: Optional[List[str]] = None
    hire_date: Optional[date] = None
    preferences: Optional[dict] = None


class UpdateEmployeeRequest(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    position: Optional[str] = None
    skills: Optional[List[str]] = None
    preferences: Optional[dict] = None
    performance_score: Optional[str] = None
    is_active: Optional[bool] = None


class EmployeeResponse(BaseModel):
    id: str
    store_id: str
    name: str
    phone: Optional[str]
    email: Optional[str]
    position: Optional[str]
    skills: Optional[List[str]]
    hire_date: Optional[date]
    is_active: bool
    performance_score: Optional[str]
    preferences: Optional[dict]


@router.get("/employees", response_model=List[EmployeeResponse])
async def list_employees(
    store_id: str = Query(..., description="门店ID"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取门店员工列表"""
    employees = await EmployeeRepository.get_by_store(session, store_id)
    return [EmployeeResponse(
        id=e.id, store_id=e.store_id, name=e.name, phone=e.phone,
        email=e.email, position=e.position, skills=e.skills or [],
        hire_date=e.hire_date, is_active=e.is_active,
        performance_score=e.performance_score, preferences=e.preferences or {}
    ) for e in employees]


@router.get("/employees/{employee_id}", response_model=EmployeeResponse)
async def get_employee(
    employee_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取员工详情"""
    emp = await EmployeeRepository.get_by_id(session, employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="员工不存在")
    return EmployeeResponse(
        id=emp.id, store_id=emp.store_id, name=emp.name, phone=emp.phone,
        email=emp.email, position=emp.position, skills=emp.skills or [],
        hire_date=emp.hire_date, is_active=emp.is_active,
        performance_score=emp.performance_score, preferences=emp.preferences or {}
    )


@router.post("/employees", response_model=EmployeeResponse, status_code=201)
async def create_employee(
    req: CreateEmployeeRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.STORE_MANAGER)),
):
    """创建员工"""
    emp = Employee(
        id=req.id, store_id=req.store_id, name=req.name, phone=req.phone,
        email=req.email, position=req.position, skills=req.skills or [],
        hire_date=req.hire_date, preferences=req.preferences or {},
    )
    session.add(emp)
    await session.commit()
    await session.refresh(emp)
    logger.info("employee_created", employee_id=emp.id, store_id=emp.store_id)
    # --- HR double-write (shadow, non-blocking) ---
    try:
        from src.services.hr.double_write_service import DoubleWriteService
        dw = DoubleWriteService(session=session)
        await dw.on_employee_created(emp)
    except Exception as exc:
        logger.warning("hr_double_write.create_hook_failed", employee_id=emp.id, error=str(exc))
    return EmployeeResponse(
        id=emp.id, store_id=emp.store_id, name=emp.name, phone=emp.phone,
        email=emp.email, position=emp.position, skills=emp.skills or [],
        hire_date=emp.hire_date, is_active=emp.is_active,
        performance_score=emp.performance_score, preferences=emp.preferences or {}
    )


@router.patch("/employees/{employee_id}", response_model=EmployeeResponse)
async def update_employee(
    employee_id: str,
    req: UpdateEmployeeRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.STORE_MANAGER)),
):
    """更新员工信息"""
    emp = await EmployeeRepository.get_by_id(session, employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="员工不存在")
    changed = set(req.model_dump(exclude_none=True).keys())
    for field, value in req.model_dump(exclude_none=True).items():
        setattr(emp, field, value)
    await session.commit()
    await session.refresh(emp)
    # --- HR double-write (shadow, non-blocking) ---
    try:
        from src.services.hr.double_write_service import DoubleWriteService
        dw = DoubleWriteService(session=session)
        await dw.on_employee_updated(emp, changed_fields=changed)
    except Exception as exc:
        logger.warning("hr_double_write.update_hook_failed", employee_id=emp.id, error=str(exc))
    return EmployeeResponse(
        id=emp.id, store_id=emp.store_id, name=emp.name, phone=emp.phone,
        email=emp.email, position=emp.position, skills=emp.skills or [],
        hire_date=emp.hire_date, is_active=emp.is_active,
        performance_score=emp.performance_score, preferences=emp.preferences or {}
    )


class RecordPerformanceRequest(BaseModel):
    period: str  # e.g. "2026-02" or "2026-W08"
    attendance_rate: Optional[float] = None   # 出勤率 0-100
    customer_rating: Optional[float] = None  # 顾客评分 1-5
    efficiency_score: Optional[float] = None # 效率评分 0-100
    sales_amount: Optional[float] = None     # 销售额（元）
    notes: Optional[str] = None


class EmployeePreferenceUpsertRequest(BaseModel):
    preferences: Dict[str, Any]


class EmployeePreferencePatchRequest(BaseModel):
    preferences: Dict[str, Any]


class EmployeePreferenceResponse(BaseModel):
    employee_id: str
    store_id: str
    preferences: Dict[str, Any]


class ShiftSwapRequestCreate(BaseModel):
    shift_id: str
    target_employee_id: str
    reason: Optional[str] = None


class ShiftSwapApprovalRequest(BaseModel):
    approved: bool
    comment: Optional[str] = None


@router.post("/employees/{employee_id}/performance", status_code=201)
async def record_performance(
    employee_id: str,
    req: RecordPerformanceRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.STORE_MANAGER)),
):
    """录入员工绩效数据，并更新 performance_score 综合评分"""
    emp = await EmployeeRepository.get_by_id(session, employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="员工不存在")

    # 综合评分：各维度加权平均
    scores = []
    if req.attendance_rate is not None:
        scores.append(req.attendance_rate)
    if req.customer_rating is not None:
        scores.append(req.customer_rating * 20)  # 1-5 → 20-100
    if req.efficiency_score is not None:
        scores.append(req.efficiency_score)
    composite = round(sum(scores) / len(scores), 1) if scores else None

    if composite is not None:
        emp.performance_score = str(composite)
    await session.commit()

    logger.info("performance_recorded", employee_id=employee_id, period=req.period, score=composite)
    return {
        "employee_id": employee_id,
        "period": req.period,
        "attendance_rate": req.attendance_rate,
        "customer_rating": req.customer_rating,
        "efficiency_score": req.efficiency_score,
        "sales_amount": req.sales_amount,
        "composite_score": composite,
        "notes": req.notes,
    }


@router.post("/employees/{employee_id}/shift-swaps", status_code=201)
async def create_shift_swap_request(
    employee_id: str,
    req: ShiftSwapRequestCreate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """创建换班申请（申请 -> 技能检查 -> 通知店长审批）"""
    requester = await EmployeeRepository.get_by_id(session, employee_id)
    if not requester or not requester.is_active:
        raise HTTPException(status_code=404, detail="申请员工不存在或已停用")

    target = await EmployeeRepository.get_by_id(session, req.target_employee_id)
    if not target or not target.is_active:
        raise HTTPException(status_code=404, detail="目标员工不存在或已停用")
    if requester.store_id != target.store_id:
        raise HTTPException(status_code=400, detail="仅支持同门店员工换班")

    try:
        shift_uuid = uuid.UUID(req.shift_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="shift_id 格式错误") from exc

    shift = await session.get(Shift, shift_uuid)
    if not shift:
        raise HTTPException(status_code=404, detail="班次不存在")
    if shift.employee_id != employee_id:
        raise HTTPException(status_code=400, detail="仅可申请自己的班次换班")

    schedule = await session.get(Schedule, shift.schedule_id)
    if not schedule or schedule.store_id != requester.store_id:
        raise HTTPException(status_code=400, detail="班次与门店不匹配")

    if shift.position and shift.position not in (target.skills or []):
        raise HTTPException(
            status_code=400,
            detail=f"目标员工技能不匹配，缺少岗位技能: {shift.position}",
        )

    store = await session.get(Store, requester.store_id)
    if not store or not store.manager_id:
        raise HTTPException(status_code=400, detail="门店未配置店长，无法发起审批")

    payload = {
        "shift_id": str(shift.id),
        "schedule_id": str(schedule.id),
        "schedule_date": schedule.schedule_date.isoformat() if schedule.schedule_date else None,
        "from_employee_id": employee_id,
        "to_employee_id": req.target_employee_id,
        "position": shift.position,
        "reason": req.reason,
    }

    task = Task(
        title=f"换班申请: {requester.name} -> {target.name}",
        content=json.dumps(payload, ensure_ascii=False),
        category="shift_swap",
        status=TaskStatus.PENDING,
        priority=TaskPriority.NORMAL,
        store_id=requester.store_id,
        creator_id=current_user.id,
        assignee_id=store.manager_id,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)

    message = (
        f"【换班审批】\n"
        f"门店: {requester.store_id}\n"
        f"申请人: {requester.name}({employee_id})\n"
        f"目标员工: {target.name}({req.target_employee_id})\n"
        f"班次日期: {payload['schedule_date']}\n"
        f"岗位: {shift.position or '-'}\n"
        f"原因: {req.reason or '-'}\n"
        f"申请单号: {task.id}"
    )
    try:
        await wechat_service.send_text_message(content=message, touser=str(store.manager_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("shift_swap_notify_manager_failed", task_id=str(task.id), error=str(exc))

    return {"request_id": str(task.id), "status": task.status, "store_id": requester.store_id}


@router.post("/shift-swaps/{request_id}/approve")
async def approve_shift_swap_request(
    request_id: str,
    req: ShiftSwapApprovalRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.STORE_MANAGER)),
):
    """店长审批换班申请（通过后重排班次并通知双方）"""
    try:
        req_uuid = uuid.UUID(request_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="request_id 格式错误") from exc

    task = await session.get(Task, req_uuid)
    if not task or task.category != "shift_swap":
        raise HTTPException(status_code=404, detail="换班申请不存在")
    if task.status != TaskStatus.PENDING:
        raise HTTPException(status_code=400, detail="该换班申请已处理")

    store = await session.get(Store, task.store_id)
    if store and store.manager_id and current_user.id != store.manager_id:
        raise HTTPException(status_code=403, detail="仅店长可审批本门店换班")

    try:
        payload = json.loads(task.content or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="换班申请数据损坏") from exc

    try:
        shift_uuid = uuid.UUID(str(payload.get("shift_id", "")))
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="换班申请班次ID损坏") from exc

    shift = await session.get(Shift, shift_uuid)
    if not shift:
        raise HTTPException(status_code=404, detail="申请对应班次不存在")

    from_employee_id = payload.get("from_employee_id")
    to_employee_id = payload.get("to_employee_id")
    if not from_employee_id or not to_employee_id:
        raise HTTPException(status_code=500, detail="换班申请员工信息缺失")

    if req.approved:
        shift.employee_id = to_employee_id
        task.status = TaskStatus.COMPLETED
        task.result = req.comment or "approved"
    else:
        task.status = TaskStatus.CANCELLED
        task.result = req.comment or "rejected"

    payload["approved"] = req.approved
    payload["approved_by"] = str(current_user.id)
    payload["approval_comment"] = req.comment
    task.content = json.dumps(payload, ensure_ascii=False)
    task.completed_at = datetime.utcnow()

    await session.commit()
    await session.refresh(task)

    decision = "通过" if req.approved else "驳回"
    notify_message = (
        f"【换班审批结果】\n"
        f"申请单号: {task.id}\n"
        f"审批结果: {decision}\n"
        f"备注: {req.comment or '-'}"
    )
    try:
        await wechat_service.send_text_message(content=notify_message, touser=str(from_employee_id))
        await wechat_service.send_text_message(content=notify_message, touser=str(to_employee_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("shift_swap_notify_employee_failed", task_id=str(task.id), error=str(exc))

    return {"request_id": str(task.id), "status": task.status, "approved": req.approved}


@router.get("/shift-swaps")
async def list_shift_swap_requests(
    store_id: str = Query(..., description="门店ID"),
    status: Optional[str] = Query(None, description="审批状态 pending/completed/cancelled"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """查询门店换班申请列表"""
    stmt = select(Task).where(
        Task.category == "shift_swap",
        Task.store_id == store_id,
    )
    if status:
        stmt = stmt.where(Task.status == status)

    result = await session.execute(stmt.order_by(Task.created_at.desc()))
    tasks = result.scalars().all()

    records = []
    for item in tasks:
        try:
            content = json.loads(item.content or "{}")
        except json.JSONDecodeError:
            content = {}
        records.append(
            {
                "request_id": str(item.id),
                "title": item.title,
                "status": item.status,
                "store_id": item.store_id,
                "created_at": item.created_at.isoformat() if item.created_at else None,
                "completed_at": item.completed_at.isoformat() if item.completed_at else None,
                "content": content,
                "result": item.result,
            }
        )

    return {"store_id": store_id, "total": len(records), "items": records}


@router.get("/employees/performance/leaderboard")
async def get_performance_leaderboard(
    store_id: str = Query(..., description="门店ID"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """员工绩效排行榜（按 performance_score 降序）"""
    employees = await EmployeeRepository.get_by_store(session, store_id)
    ranked = sorted(
        [e for e in employees if e.is_active and e.performance_score],
        key=lambda e: float(e.performance_score or 0),
        reverse=True,
    )
    return {
        "store_id": store_id,
        "total": len(ranked),
        "leaderboard": [
            {
                "rank": idx + 1,
                "employee_id": e.id,
                "name": e.name,
                "position": e.position,
                "performance_score": float(e.performance_score),
            }
            for idx, e in enumerate(ranked)
        ],
    }


@router.get("/employees/{employee_id}/preferences", response_model=EmployeePreferenceResponse)
async def get_employee_preferences(
    employee_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取员工排班偏好。"""
    emp = await EmployeeRepository.get_by_id(session, employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="员工不存在")
    return EmployeePreferenceResponse(
        employee_id=emp.id,
        store_id=emp.store_id,
        preferences=emp.preferences or {},
    )


@router.put("/employees/{employee_id}/preferences", response_model=EmployeePreferenceResponse)
async def put_employee_preferences(
    employee_id: str,
    req: EmployeePreferenceUpsertRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.STORE_MANAGER)),
):
    """全量覆盖员工排班偏好。"""
    emp = await EmployeeRepository.get_by_id(session, employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="员工不存在")
    emp.preferences = req.preferences
    await session.commit()
    await session.refresh(emp)
    return EmployeePreferenceResponse(
        employee_id=emp.id,
        store_id=emp.store_id,
        preferences=emp.preferences or {},
    )


@router.patch("/employees/{employee_id}/preferences", response_model=EmployeePreferenceResponse)
async def patch_employee_preferences(
    employee_id: str,
    req: EmployeePreferencePatchRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.STORE_MANAGER)),
):
    """局部更新员工排班偏好（merge）。"""
    emp = await EmployeeRepository.get_by_id(session, employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="员工不存在")
    merged = dict(emp.preferences or {})
    merged.update(req.preferences)
    emp.preferences = merged
    await session.commit()
    await session.refresh(emp)
    return EmployeePreferenceResponse(
        employee_id=emp.id,
        store_id=emp.store_id,
        preferences=emp.preferences or {},
    )


@router.delete("/employees/{employee_id}/preferences")
async def delete_employee_preferences(
    employee_id: str,
    key: Optional[str] = Query(None, description="可选，删除指定偏好键"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.STORE_MANAGER)),
):
    """
    删除员工偏好。
    - 未提供 key：清空全部偏好
    - 提供 key：仅删除指定字段
    """
    emp = await EmployeeRepository.get_by_id(session, employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="员工不存在")

    current = dict(emp.preferences or {})
    if key:
        current.pop(key, None)
        emp.preferences = current
    else:
        emp.preferences = {}

    await session.commit()
    await session.refresh(emp)
    return {
        "ok": True,
        "employee_id": emp.id,
        "preferences": emp.preferences or {},
    }



async def deactivate_employee(
    employee_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.STORE_MANAGER)),
):
    """停用员工（软删除）"""
    emp = await EmployeeRepository.get_by_id(session, employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="员工不存在")
    emp.is_active = False
    await session.commit()
    logger.info("employee_deactivated", employee_id=employee_id)
