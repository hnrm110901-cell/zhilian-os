"""
HR Employee API — 员工花名册 + 入离职流程
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from typing import Optional, List
from datetime import date
from pydantic import BaseModel
import structlog

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.user import User
from ..models.employee import Employee
from ..models.employee_lifecycle import EmployeeChange, ChangeType
from ..models.employee_contract import EmployeeContract
from ..services.data_masking_service import DataMaskingService
from sqlalchemy import select, and_, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()
router = APIRouter()


# ── 花名册 ──────────────────────────────────────────────────

@router.get("/hr/employees")
async def list_employees(
    request: Request,
    store_id: str = Query(...),
    status: Optional[str] = Query(None, description="active|inactive|all"),
    position: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None, description="姓名/电话模糊搜索"),
    mask_level: Optional[int] = Query(None, ge=0, le=3, description="脱敏级别覆盖（测试用）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """员工花名册：分页、筛选、搜索（敏感字段按角色自动脱敏）"""
    query = select(Employee).where(Employee.store_id == store_id)

    if status == "active":
        query = query.where(Employee.is_active.is_(True))
    elif status == "inactive":
        query = query.where(Employee.is_active.is_(False))

    if position:
        query = query.where(Employee.position == position)

    if keyword:
        like = f"%{keyword}%"
        query = query.where(or_(Employee.name.ilike(like), Employee.phone.ilike(like)))

    # 总数
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # 分页
    result = await db.execute(
        query.order_by(Employee.hire_date.desc().nullslast())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    employees = result.scalars().all()

    # 确定脱敏级别：优先使用 mask_level 参数，其次从 X-User-Role 头获取
    if mask_level is not None:
        role_level = mask_level
    else:
        role = request.headers.get("X-User-Role", "viewer")
        role_level = DataMaskingService.get_role_level(role)

    items = [
        {
            "id": e.id,
            "name": e.name,
            "phone": e.phone,
            "email": e.email,
            "position": e.position,
            "hire_date": str(e.hire_date) if e.hire_date else None,
            "is_active": e.is_active,
            "performance_score": e.performance_score,
            "skills": e.skills or [],
        }
        for e in employees
    ]

    # 按角色级别脱敏敏感字段
    masked_items = DataMaskingService.mask_employee_list(items, role_level)

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": masked_items,
    }


@router.get("/hr/employees/{employee_id}")
async def get_employee_detail(
    request: Request,
    employee_id: str,
    mask_level: Optional[int] = Query(None, ge=0, le=3, description="脱敏级别覆盖（测试用）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """员工详情：基本信息 + 合同 + 变动记录（敏感字段按角色自动脱敏）"""
    emp = await db.execute(
        select(Employee).where(Employee.id == employee_id)
    )
    employee = emp.scalars().first()
    if not employee:
        raise HTTPException(status_code=404, detail="员工不存在")

    # 合同
    contract_result = await db.execute(
        select(EmployeeContract)
        .where(EmployeeContract.employee_id == employee_id)
        .order_by(EmployeeContract.start_date.desc())
        .limit(5)
    )
    contracts = contract_result.scalars().all()

    # 变动记录
    change_result = await db.execute(
        select(EmployeeChange)
        .where(EmployeeChange.employee_id == employee_id)
        .order_by(EmployeeChange.effective_date.desc())
        .limit(20)
    )
    changes = change_result.scalars().all()

    # 确定脱敏级别
    if mask_level is not None:
        role_level = mask_level
    else:
        role = request.headers.get("X-User-Role", "viewer")
        role_level = DataMaskingService.get_role_level(role)

    # 员工详情包含更多敏感字段
    employee_data = {
        "id": employee.id,
        "name": employee.name,
        "phone": employee.phone,
        "email": employee.email,
        "position": employee.position,
        "hire_date": str(employee.hire_date) if employee.hire_date else None,
        "is_active": employee.is_active,
        "performance_score": employee.performance_score,
        "skills": employee.skills or [],
        "store_id": employee.store_id,
        "id_card_no": employee.id_card_no,
        "bank_account": employee.bank_account,
        "bank_name": employee.bank_name,
        "emergency_contact": employee.emergency_contact,
        "emergency_phone": employee.emergency_phone,
        "emergency_relation": employee.emergency_relation,
    }

    # 按角色级别脱敏敏感字段
    masked_employee = DataMaskingService.mask_employee_data(employee_data, role_level)

    return {
        "employee": masked_employee,
        "contracts": [
            {
                "id": str(c.id),
                "contract_no": c.contract_no,
                "contract_type": c.contract_type.value if c.contract_type else None,
                "status": c.status.value if c.status else None,
                "start_date": str(c.start_date),
                "end_date": str(c.end_date) if c.end_date else None,
                "renewal_count": c.renewal_count,
            }
            for c in contracts
        ],
        "changes": [
            {
                "id": str(ch.id),
                "change_type": ch.change_type.value,
                "effective_date": str(ch.effective_date),
                "from_position": ch.from_position,
                "to_position": ch.to_position,
                "from_store_id": ch.from_store_id,
                "to_store_id": ch.to_store_id,
                "remark": ch.remark,
            }
            for ch in changes
        ],
    }


# ── 入职 ──────────────────────────────────────────────────

class OnboardRequest(BaseModel):
    store_id: str
    employee_id: str
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    position: str
    hire_date: str
    remark: Optional[str] = None


@router.post("/hr/onboard")
async def onboard_employee(
    body: OnboardRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """入职登记：创建员工 + 入职变动记录"""
    import uuid

    # 检查ID是否已存在
    exists = await db.execute(
        select(Employee.id).where(Employee.id == body.employee_id)
    )
    if exists.scalars().first():
        raise HTTPException(status_code=409, detail="员工ID已存在")

    hire_date = date.fromisoformat(body.hire_date)

    # 创建员工
    employee = Employee(
        id=body.employee_id,
        store_id=body.store_id,
        name=body.name,
        phone=body.phone,
        email=body.email,
        position=body.position,
        hire_date=hire_date,
        is_active=True,
    )
    db.add(employee)

    # 创建入职变动记录
    change = EmployeeChange(
        id=uuid.uuid4(),
        store_id=body.store_id,
        employee_id=body.employee_id,
        change_type=ChangeType.ONBOARD,
        effective_date=hire_date,
        to_position=body.position,
        to_store_id=body.store_id,
        remark=body.remark or f"入职 - {body.position}",
    )
    db.add(change)

    await db.commit()
    logger.info("employee_onboarded", employee_id=body.employee_id, store_id=body.store_id)

    return {"message": "入职成功", "employee_id": body.employee_id}


# ── 离职 ──────────────────────────────────────────────────

class ResignRequest(BaseModel):
    store_id: str
    employee_id: str
    resign_reason: str
    last_work_date: str
    handover_to: Optional[str] = None
    change_type: str = "resign"  # resign | dismiss


@router.post("/hr/resign")
async def resign_employee(
    body: ResignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """离职登记：更新员工状态 + 离职变动记录"""
    import uuid

    emp = await db.execute(
        select(Employee).where(Employee.id == body.employee_id)
    )
    employee = emp.scalars().first()
    if not employee:
        raise HTTPException(status_code=404, detail="员工不存在")
    if not employee.is_active:
        raise HTTPException(status_code=400, detail="该员工已离职")

    last_date = date.fromisoformat(body.last_work_date)
    ct = ChangeType.RESIGN if body.change_type == "resign" else ChangeType.DISMISS

    # 更新员工状态
    employee.is_active = False

    # 创建离职变动记录
    change = EmployeeChange(
        id=uuid.uuid4(),
        store_id=body.store_id,
        employee_id=body.employee_id,
        change_type=ct,
        effective_date=last_date,
        from_position=employee.position,
        from_store_id=employee.store_id,
        resign_reason=body.resign_reason,
        last_work_date=last_date,
        handover_to=body.handover_to,
        remark=body.resign_reason,
    )
    db.add(change)

    await db.commit()
    logger.info("employee_resigned", employee_id=body.employee_id, type=body.change_type)

    return {"message": "离职登记成功", "employee_id": body.employee_id}


# ── 员工变动记录 ──────────────────────────────────────────

@router.get("/hr/employee-changes")
async def list_employee_changes(
    store_id: str = Query(...),
    change_type: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """员工变动记录列表"""
    query = (
        select(EmployeeChange, Employee.name.label("employee_name"))
        .join(Employee, Employee.id == EmployeeChange.employee_id)
        .where(EmployeeChange.store_id == store_id)
    )

    if change_type:
        query = query.where(EmployeeChange.change_type == change_type)

    result = await db.execute(
        query.order_by(EmployeeChange.effective_date.desc()).limit(limit)
    )
    rows = result.all()

    return {
        "items": [
            {
                "id": str(row.EmployeeChange.id),
                "employee_id": row.EmployeeChange.employee_id,
                "employee_name": row.employee_name,
                "change_type": row.EmployeeChange.change_type.value,
                "effective_date": str(row.EmployeeChange.effective_date),
                "from_position": row.EmployeeChange.from_position,
                "to_position": row.EmployeeChange.to_position,
                "from_store_id": row.EmployeeChange.from_store_id,
                "to_store_id": row.EmployeeChange.to_store_id,
                "resign_reason": row.EmployeeChange.resign_reason,
                "remark": row.EmployeeChange.remark,
            }
            for row in rows
        ],
    }
