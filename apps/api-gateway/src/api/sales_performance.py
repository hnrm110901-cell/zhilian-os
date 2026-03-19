"""
销售业绩归属 API — P1 补齐（易订PRO 3.3 销售业绩）

将散客预订归属到销售员/预订员，统计个人预订业绩：
- 按员工聚合预订量、到店量、完成量、预估消费
- 排名和转化率
- 复用已有 CustomerOwnership 模型做员工-客户绑定
"""

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.customer_ownership import CustomerOwnership
from ..models.reservation import Reservation, ReservationStatus
from ..models.user import User

router = APIRouter()


# ── 预订归属 ─────────────────────────────────────────────────────


class AssignReservationRequest(BaseModel):
    reservation_id: str
    employee_id: str  # 销售员/预订员 employee_id


@router.post("/api/v1/sales-performance/assign")
async def assign_reservation_to_employee(
    req: AssignReservationRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """将预订归属到员工（销售员/预订员）"""
    result = await session.execute(select(Reservation).where(Reservation.id == req.reservation_id))
    r = result.scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="预订不存在")

    # 写入 notes 字段记录归属（复用现有模型，不新增字段）
    attribution_tag = f"[sales:{req.employee_id}]"
    if r.notes and attribution_tag in r.notes:
        return {"message": "该预订已归属到此员工", "reservation_id": req.reservation_id}

    r.notes = f"{r.notes or ''} {attribution_tag}".strip()
    await session.commit()

    return {
        "reservation_id": req.reservation_id,
        "employee_id": req.employee_id,
        "message": "预订已归属",
    }


# ── 销售业绩统计 ─────────────────────────────────────────────────


@router.get("/api/v1/sales-performance/ranking")
async def get_sales_ranking(
    store_id: str = Query(..., description="门店ID"),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    员工预订业绩排名。

    按 notes 中的 [sales:employee_id] 标签聚合统计：
    - 总预订量
    - 完成量（seated+completed）
    - 到店率（arrived/total）
    - 预估消费总额
    """
    end_dt = end_date or date.today()
    start_dt = start_date or (end_dt - timedelta(days=30))

    result = await session.execute(
        select(Reservation).where(
            and_(
                Reservation.store_id == store_id,
                Reservation.reservation_date >= start_dt,
                Reservation.reservation_date <= end_dt,
                Reservation.notes.ilike("%[sales:%"),
            )
        )
    )
    reservations = result.scalars().all()

    # 按员工聚合
    employee_stats: Dict[str, Dict[str, Any]] = {}
    for r in reservations:
        # 提取 [sales:xxx] 标签
        import re

        match = re.search(r"\[sales:([^\]]+)\]", r.notes or "")
        if not match:
            continue
        emp_id = match.group(1)

        if emp_id not in employee_stats:
            employee_stats[emp_id] = {
                "employee_id": emp_id,
                "total_reservations": 0,
                "completed": 0,
                "arrived": 0,
                "cancelled": 0,
                "no_show": 0,
                "total_guests": 0,
                "total_budget": 0,
            }
        stats = employee_stats[emp_id]
        stats["total_reservations"] += 1
        stats["total_guests"] += r.party_size
        stats["total_budget"] += r.estimated_budget or 0

        status = r.status.value if hasattr(r.status, "value") else str(r.status)
        if status in ("completed", "seated"):
            stats["completed"] += 1
        if status in ("arrived", "seated", "completed"):
            stats["arrived"] += 1
        if status == "cancelled":
            stats["cancelled"] += 1
        if status == "no_show":
            stats["no_show"] += 1

    # 排名
    rankings = sorted(employee_stats.values(), key=lambda x: x["completed"], reverse=True)
    for rank, emp in enumerate(rankings, 1):
        total = emp["total_reservations"]
        emp["rank"] = rank
        emp["arrival_rate"] = round(emp["arrived"] / total * 100, 1) if total > 0 else 0
        emp["completion_rate"] = round(emp["completed"] / total * 100, 1) if total > 0 else 0
        emp["total_budget_yuan"] = round(emp["total_budget"] / 100, 2)

    return {
        "store_id": store_id,
        "period": f"{start_dt} ~ {end_dt}",
        "total_employees": len(rankings),
        "rankings": rankings,
    }


# ── 客户归属统计（复用 CustomerOwnership） ────────────────────────


@router.get("/api/v1/sales-performance/customer-stats")
async def get_customer_ownership_stats(
    store_id: str = Query(..., description="门店ID"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """员工客户归属统计（各员工名下客户数 + 总消费）"""
    query = (
        select(
            CustomerOwnership.owner_employee_id,
            func.count().label("customer_count"),
            func.sum(CustomerOwnership.total_spent).label("total_spent"),
            func.sum(CustomerOwnership.total_visits).label("total_visits"),
        )
        .where(
            and_(
                CustomerOwnership.store_id == store_id,
                CustomerOwnership.is_active == True,
            )
        )
        .group_by(CustomerOwnership.owner_employee_id)
        .order_by(func.sum(CustomerOwnership.total_spent).desc())
    )
    result = await session.execute(query)
    rows = result.all()

    stats = []
    for r in rows:
        stats.append(
            {
                "employee_id": r.owner_employee_id,
                "customer_count": int(r.customer_count),
                "total_spent_yuan": round(int(r.total_spent or 0) / 100, 2),
                "total_visits": int(r.total_visits or 0),
            }
        )

    return {
        "store_id": store_id,
        "employees": stats,
        "total_customers": sum(s["customer_count"] for s in stats),
    }
