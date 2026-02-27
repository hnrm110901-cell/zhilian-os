"""
Employee Management API
员工管理API
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import date
import structlog

from ..core.database import get_db
from ..core.dependencies import get_current_active_user, require_role
from ..models.employee import Employee
from ..models.user import User, UserRole
from ..repositories import EmployeeRepository
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
    for field, value in req.model_dump(exclude_none=True).items():
        setattr(emp, field, value)
    await session.commit()
    await session.refresh(emp)
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
