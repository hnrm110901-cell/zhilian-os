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


@router.delete("/employees/{employee_id}", status_code=204)
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
