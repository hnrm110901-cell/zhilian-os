"""
客户资源分配 API — P2 补齐（易订PRO 3.6 客户资源分配）

管理客户-员工归属关系：
- 按区域/楼面分配客户给服务员
- 批量分配/转移
- 新客自动分配（轮询/按能力）
- 复用现有 CustomerOwnership 模型
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.customer_ownership import CustomerOwnership, TransferReason
from ..models.user import User

router = APIRouter()


class AllocateCustomerRequest(BaseModel):
    store_id: str
    customer_phone: str
    customer_name: str
    employee_id: str
    customer_level: Optional[str] = None  # VIP/GOLD/SILVER/NORMAL


class BatchAllocateRequest(BaseModel):
    store_id: str
    allocations: List[AllocateCustomerRequest]


class TransferCustomerRequest(BaseModel):
    from_employee_id: str
    to_employee_id: str
    reason: str = "manual"  # resignation/reorg/manual/auto_balance
    notes: Optional[str] = None


def _to_dict(o: CustomerOwnership) -> Dict[str, Any]:
    return {
        "id": str(o.id),
        "store_id": o.store_id,
        "customer_phone": o.customer_phone[:3] + "****" + o.customer_phone[-4:],
        "customer_name": o.customer_name,
        "owner_employee_id": o.owner_employee_id,
        "customer_level": o.customer_level,
        "total_visits": o.total_visits,
        "total_spent_yuan": round((o.total_spent or 0) / 100, 2),
        "last_visit_at": o.last_visit_at.isoformat() if o.last_visit_at else None,
        "assigned_at": o.assigned_at.isoformat() if o.assigned_at else None,
    }


# ── 查看员工名下客户 ─────────────────────────────────────────────


@router.get("/api/v1/customer-allocation/by-employee")
async def get_employee_customers(
    store_id: str = Query(...),
    employee_id: str = Query(...),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """查看员工名下所有客户"""
    result = await session.execute(
        select(CustomerOwnership)
        .where(
            and_(
                CustomerOwnership.store_id == store_id,
                CustomerOwnership.owner_employee_id == employee_id,
                CustomerOwnership.is_active == True,
            )
        )
        .order_by(CustomerOwnership.total_spent.desc())
    )
    customers = result.scalars().all()
    return {
        "employee_id": employee_id,
        "customers": [_to_dict(c) for c in customers],
        "total": len(customers),
    }


# ── 分配客户 ─────────────────────────────────────────────────────


@router.post("/api/v1/customer-allocation/assign")
async def assign_customer(
    req: AllocateCustomerRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """分配客户给员工"""
    # 检查是否已有归属
    existing = await session.execute(
        select(CustomerOwnership).where(
            and_(
                CustomerOwnership.store_id == req.store_id,
                CustomerOwnership.customer_phone == req.customer_phone,
                CustomerOwnership.is_active == True,
            )
        )
    )
    existing_record = existing.scalar_one_or_none()
    if existing_record:
        if existing_record.owner_employee_id == req.employee_id:
            return {"message": "客户已归属到该员工", "ownership": _to_dict(existing_record)}
        raise HTTPException(
            status_code=409,
            detail=f"客户已归属到员工 {existing_record.owner_employee_id}，请使用转移接口",
        )

    ownership = CustomerOwnership(
        id=uuid.uuid4(),
        store_id=req.store_id,
        customer_phone=req.customer_phone,
        customer_name=req.customer_name,
        owner_employee_id=req.employee_id,
        customer_level=req.customer_level,
        assigned_at=datetime.utcnow(),
        is_active=True,
    )
    session.add(ownership)
    await session.commit()
    await session.refresh(ownership)
    return {"message": "分配成功", "ownership": _to_dict(ownership)}


# ── 批量分配 ─────────────────────────────────────────────────────


@router.post("/api/v1/customer-allocation/batch-assign")
async def batch_assign(
    req: BatchAllocateRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """批量分配客户"""
    results = {"assigned": 0, "skipped": 0, "errors": []}

    for alloc in req.allocations:
        existing = await session.execute(
            select(CustomerOwnership).where(
                and_(
                    CustomerOwnership.store_id == alloc.store_id,
                    CustomerOwnership.customer_phone == alloc.customer_phone,
                    CustomerOwnership.is_active == True,
                )
            )
        )
        if existing.scalar_one_or_none():
            results["skipped"] += 1
            continue

        ownership = CustomerOwnership(
            id=uuid.uuid4(),
            store_id=alloc.store_id,
            customer_phone=alloc.customer_phone,
            customer_name=alloc.customer_name,
            owner_employee_id=alloc.employee_id,
            customer_level=alloc.customer_level,
            assigned_at=datetime.utcnow(),
            is_active=True,
        )
        session.add(ownership)
        results["assigned"] += 1

    await session.commit()
    return results


# ── 转移客户 ─────────────────────────────────────────────────────


@router.post("/api/v1/customer-allocation/{store_id}/transfer")
async def transfer_customers(
    store_id: str,
    req: TransferCustomerRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """批量转移员工名下所有客户（离职交接/组织调整）"""
    result = await session.execute(
        select(CustomerOwnership).where(
            and_(
                CustomerOwnership.store_id == store_id,
                CustomerOwnership.owner_employee_id == req.from_employee_id,
                CustomerOwnership.is_active == True,
            )
        )
    )
    records = result.scalars().all()

    if not records:
        raise HTTPException(status_code=404, detail="该员工名下无客户")

    for r in records:
        r.transferred_from = req.from_employee_id
        r.owner_employee_id = req.to_employee_id
        r.transferred_at = datetime.utcnow()
        r.transfer_reason = TransferReason(req.reason)
        r.transfer_notes = req.notes

    await session.commit()
    return {
        "transferred": len(records),
        "from_employee": req.from_employee_id,
        "to_employee": req.to_employee_id,
        "reason": req.reason,
    }


# ── 分配统计 ─────────────────────────────────────────────────────


@router.get("/api/v1/customer-allocation/{store_id}/overview")
async def get_allocation_overview(
    store_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """客户资源分配概览（各员工客户数/消费分布）"""
    query = (
        select(
            CustomerOwnership.owner_employee_id,
            CustomerOwnership.customer_level,
            func.count().label("count"),
            func.sum(CustomerOwnership.total_spent).label("total_spent"),
        )
        .where(
            and_(
                CustomerOwnership.store_id == store_id,
                CustomerOwnership.is_active == True,
            )
        )
        .group_by(CustomerOwnership.owner_employee_id, CustomerOwnership.customer_level)
    )
    result = await session.execute(query)
    rows = result.all()

    # 按员工聚合
    employees: Dict[str, Dict] = {}
    for r in rows:
        emp_id = r.owner_employee_id
        if emp_id not in employees:
            employees[emp_id] = {
                "employee_id": emp_id,
                "total_customers": 0,
                "total_spent_yuan": 0,
                "by_level": {},
            }
        level = r.customer_level or "NORMAL"
        employees[emp_id]["by_level"][level] = int(r.count)
        employees[emp_id]["total_customers"] += int(r.count)
        employees[emp_id]["total_spent_yuan"] += round(int(r.total_spent or 0) / 100, 2)

    return {
        "store_id": store_id,
        "total_assigned_customers": sum(e["total_customers"] for e in employees.values()),
        "employees": list(employees.values()),
    }
