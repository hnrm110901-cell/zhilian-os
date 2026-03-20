"""
HR Employee API — 员工花名册 + 入离职流程
"""

from datetime import date
from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.hr.person import Person
from ..models.hr.employment_assignment import EmploymentAssignment
from ..models.employee_contract import EmployeeContract
from ..models.employee_lifecycle import ChangeType, EmployeeChange
from ..models.user import User
from ..services.data_masking_service import DataMaskingService

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
    query = (
        select(Person, EmploymentAssignment)
        .outerjoin(
            EmploymentAssignment,
            and_(
                EmploymentAssignment.person_id == Person.id,
                EmploymentAssignment.status == "active",
            ),
        )
        .where(Person.store_id == store_id)
    )

    if status == "active":
        query = query.where(Person.is_active.is_(True))
    elif status == "inactive":
        query = query.where(Person.is_active.is_(False))

    if position:
        query = query.where(EmploymentAssignment.position == position)

    if keyword:
        like = f"%{keyword}%"
        query = query.where(or_(Person.name.ilike(like), Person.phone.ilike(like)))

    # 总数
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # 分页 — 按 EA.start_date 降序（相当于原 hire_date）
    result = await db.execute(
        query.order_by(EmploymentAssignment.start_date.desc().nullslast())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = result.all()

    # 确定脱敏级别：优先使用 mask_level 参数，其次从 X-User-Role 头获取
    if mask_level is not None:
        role_level = mask_level
    else:
        role = request.headers.get("X-User-Role", "viewer")
        role_level = DataMaskingService.get_role_level(role)

    items = [
        {
            "id": person.legacy_employee_id or str(person.id),
            "name": person.name,
            "phone": person.phone,
            "email": person.email,
            "position": ea.position if ea else None,
            "hire_date": str(ea.start_date) if ea and ea.start_date else None,
            "is_active": person.is_active,
            "performance_score": (person.profile_ext or {}).get("performance_score"),
            "skills": (person.preferences or {}).get("skills", []),
        }
        for person, ea in rows
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
    row = await db.execute(
        select(Person, EmploymentAssignment)
        .outerjoin(
            EmploymentAssignment,
            and_(
                EmploymentAssignment.person_id == Person.id,
                EmploymentAssignment.status == "active",
            ),
        )
        .where(Person.legacy_employee_id == employee_id)
    )
    result_row = row.first()
    if not result_row:
        raise HTTPException(status_code=404, detail="员工不存在")
    person, ea = result_row

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
        "id": person.legacy_employee_id or str(person.id),
        "name": person.name,
        "phone": person.phone,
        "email": person.email,
        "position": ea.position if ea else None,
        "hire_date": str(ea.start_date) if ea and ea.start_date else None,
        "is_active": person.is_active,
        "performance_score": (person.profile_ext or {}).get("performance_score"),
        "skills": (person.preferences or {}).get("skills", []),
        "store_id": person.store_id,
        "id_card_no": person.id_number,
        "bank_account": person.bank_account,
        "bank_name": person.bank_name,
        "emergency_contact": person.emergency_contact_name,
        "emergency_phone": person.emergency_phone,
        "emergency_relation": person.emergency_relation,
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
    """入职登记：创建 Person + EmploymentAssignment + 入职变动记录"""
    import uuid

    # 检查ID是否已存在
    exists = await db.execute(
        select(Person.id).where(Person.legacy_employee_id == body.employee_id)
    )
    if exists.scalars().first():
        raise HTTPException(status_code=409, detail="员工ID已存在")

    hire_date = date.fromisoformat(body.hire_date)

    # 创建 Person
    person = Person(
        legacy_employee_id=body.employee_id,
        store_id=body.store_id,
        name=body.name,
        phone=body.phone,
        email=body.email,
        is_active=True,
    )
    db.add(person)
    await db.flush()  # 获取 person.id 用于 EA FK

    # 创建在岗关系
    ea = EmploymentAssignment(
        person_id=person.id,
        org_node_id=body.store_id,
        position=body.position,
        employment_type="full_time",
        start_date=hire_date,
        status="active",
    )
    db.add(ea)

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
    """离职登记：更新 Person.is_active + 结束 EmploymentAssignment + 离职变动记录"""
    import uuid

    row = await db.execute(
        select(Person, EmploymentAssignment)
        .outerjoin(
            EmploymentAssignment,
            and_(
                EmploymentAssignment.person_id == Person.id,
                EmploymentAssignment.status == "active",
            ),
        )
        .where(Person.legacy_employee_id == body.employee_id)
    )
    result_row = row.first()
    if not result_row:
        raise HTTPException(status_code=404, detail="员工不存在")
    person, ea = result_row
    if not person.is_active:
        raise HTTPException(status_code=400, detail="该员工已离职")

    last_date = date.fromisoformat(body.last_work_date)
    ct = ChangeType.RESIGN if body.change_type == "resign" else ChangeType.DISMISS

    # 更新 Person 状态
    person.is_active = False

    # 结束在岗关系
    if ea:
        ea.status = "ended"
        ea.end_date = last_date

    # 创建离职变动记录
    change = EmployeeChange(
        id=uuid.uuid4(),
        store_id=body.store_id,
        employee_id=body.employee_id,
        change_type=ct,
        effective_date=last_date,
        from_position=ea.position if ea else None,
        from_store_id=person.store_id,
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
        select(EmployeeChange, Person.name.label("employee_name"))
        .join(Person, Person.legacy_employee_id == EmployeeChange.employee_id)
        .where(EmployeeChange.store_id == store_id)
    )

    if change_type:
        query = query.where(EmployeeChange.change_type == change_type)

    result = await db.execute(query.order_by(EmployeeChange.effective_date.desc()).limit(limit))
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
