"""
HR Dashboard API — HR报表 + 业人一体化仪表盘
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from datetime import date, timedelta
from decimal import Decimal
import structlog

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.user import User
from ..models.employee import Employee
from ..models.payroll import PayrollRecord
from ..models.leave import LeaveRequest, LeaveRequestStatus
from ..models.attendance import AttendanceLog
from ..models.employee_contract import EmployeeContract, ContractStatus
from ..models.employee_lifecycle import EmployeeChange, ChangeType
from ..models.recruitment import JobPosting, Candidate, JobStatus, CandidateStage
from ..models.performance_review import PerformanceReview
from ..models.workforce import LaborCostSnapshot
from sqlalchemy import select, and_, func, case, extract
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()
router = APIRouter()


@router.get("/hr/dashboard/overview")
async def get_hr_overview(
    store_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    HR概览仪表盘 — 一屏看全人力状况
    """
    today = date.today()
    month_start = date(today.year, today.month, 1)

    # 1. 在职人数
    active_count = await db.execute(
        select(func.count(Employee.id)).where(
            and_(Employee.store_id == store_id, Employee.is_active.is_(True))
        )
    )
    total_active = active_count.scalar() or 0

    # 2. 本月入职/离职
    onboard_count = await db.execute(
        select(func.count(EmployeeChange.id)).where(
            and_(
                EmployeeChange.store_id == store_id,
                EmployeeChange.change_type == ChangeType.ONBOARD,
                EmployeeChange.effective_date >= month_start,
            )
        )
    )
    resign_count = await db.execute(
        select(func.count(EmployeeChange.id)).where(
            and_(
                EmployeeChange.store_id == store_id,
                EmployeeChange.change_type.in_([ChangeType.RESIGN, ChangeType.DISMISS]),
                EmployeeChange.effective_date >= month_start,
            )
        )
    )

    # 3. 合同即将到期（30天内）
    expiring = await db.execute(
        select(func.count(EmployeeContract.id)).where(
            and_(
                EmployeeContract.store_id == store_id,
                EmployeeContract.status == ContractStatus.ACTIVE,
                EmployeeContract.end_date.isnot(None),
                EmployeeContract.end_date <= today + timedelta(days=30),
            )
        )
    )

    # 4. 待审批请假
    pending_leaves = await db.execute(
        select(func.count(LeaveRequest.id)).where(
            and_(
                LeaveRequest.store_id == store_id,
                LeaveRequest.status == LeaveRequestStatus.PENDING,
            )
        )
    )

    # 5. 活跃招聘职位
    active_jobs = await db.execute(
        select(func.count(JobPosting.id)).where(
            and_(
                JobPosting.store_id == store_id,
                JobPosting.status == JobStatus.OPEN,
            )
        )
    )

    # 6. 本月出勤率
    attendance_total = await db.execute(
        select(func.count(AttendanceLog.id)).where(
            and_(
                AttendanceLog.store_id == store_id,
                AttendanceLog.work_date >= month_start,
            )
        )
    )
    attendance_normal = await db.execute(
        select(func.count(AttendanceLog.id)).where(
            and_(
                AttendanceLog.store_id == store_id,
                AttendanceLog.work_date >= month_start,
                AttendanceLog.status.in_(["normal", "late"]),
            )
        )
    )
    total_att = attendance_total.scalar() or 0
    normal_att = attendance_normal.scalar() or 0
    attendance_rate = round(normal_att / max(total_att, 1) * 100, 1)

    return {
        "store_id": store_id,
        "total_active_employees": total_active,
        "month_onboard": onboard_count.scalar() or 0,
        "month_resign": resign_count.scalar() or 0,
        "contracts_expiring_30d": expiring.scalar() or 0,
        "pending_leave_requests": pending_leaves.scalar() or 0,
        "active_job_postings": active_jobs.scalar() or 0,
        "attendance_rate_pct": attendance_rate,
    }


@router.get("/hr/dashboard/labor-cost-trend")
async def get_labor_cost_trend(
    store_id: str = Query(...),
    days: int = Query(default=30),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """人力成本趋势（日维度）"""
    start = date.today() - timedelta(days=days)
    result = await db.execute(
        select(LaborCostSnapshot).where(
            and_(
                LaborCostSnapshot.store_id == store_id,
                LaborCostSnapshot.snapshot_date >= start,
            )
        ).order_by(LaborCostSnapshot.snapshot_date.asc())
    )
    snapshots = result.scalars().all()
    return {
        "items": [
            {
                "date": str(s.snapshot_date),
                "actual_cost_yuan": float(s.actual_labor_cost_yuan),
                "actual_rate_pct": float(s.actual_labor_cost_rate),
                "budgeted_rate_pct": float(s.budgeted_labor_cost_rate or 0),
                "variance_yuan": float(s.variance_yuan or 0),
                "overtime_cost_yuan": float(s.overtime_cost_yuan or 0),
            }
            for s in snapshots
        ],
    }


@router.get("/hr/dashboard/turnover-trend")
async def get_turnover_trend(
    store_id: str = Query(...),
    months: int = Query(default=6),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """离职率趋势（月维度）"""
    today = date.today()
    trends = []
    for i in range(months - 1, -1, -1):
        m = today.month - i
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        month_start = date(y, m, 1)
        if m == 12:
            month_end = date(y + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(y, m + 1, 1) - timedelta(days=1)

        # 月初在职人数
        active_start = await db.execute(
            select(func.count(Employee.id)).where(
                and_(
                    Employee.store_id == store_id,
                    Employee.is_active.is_(True),
                )
            )
        )
        # 本月离职人数
        resign_count = await db.execute(
            select(func.count(EmployeeChange.id)).where(
                and_(
                    EmployeeChange.store_id == store_id,
                    EmployeeChange.change_type.in_([ChangeType.RESIGN, ChangeType.DISMISS]),
                    EmployeeChange.effective_date >= month_start,
                    EmployeeChange.effective_date <= month_end,
                )
            )
        )
        active = active_start.scalar() or 1
        resigned = resign_count.scalar() or 0
        rate = round(resigned / max(active, 1) * 100, 1)

        trends.append({
            "month": f"{y}-{m:02d}",
            "active_employees": active,
            "resignations": resigned,
            "turnover_rate_pct": rate,
        })

    return {"items": trends}


@router.get("/hr/dashboard/hr-efficiency")
async def get_hr_efficiency(
    store_id: str = Query(...),
    pay_month: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    业人一体化核心指标 — 人效比
    人效 = 营收 / 人力成本
    """
    if not pay_month:
        today = date.today()
        pay_month = f"{today.year}-{today.month:02d}"

    # 人力成本
    payroll_result = await db.execute(
        select(
            func.sum(PayrollRecord.net_salary_fen).label("total_salary"),
            func.count(PayrollRecord.id).label("headcount"),
        ).where(
            and_(
                PayrollRecord.store_id == store_id,
                PayrollRecord.pay_month == pay_month,
            )
        )
    )
    payroll = payroll_result.one()
    total_salary_yuan = (payroll.total_salary or 0) / 100
    headcount = payroll.headcount or 0

    # 营收（从 LaborCostSnapshot 获取）
    month_start = date(int(pay_month[:4]), int(pay_month[5:7]), 1)
    revenue_result = await db.execute(
        select(func.sum(LaborCostSnapshot.actual_revenue_yuan)).where(
            and_(
                LaborCostSnapshot.store_id == store_id,
                LaborCostSnapshot.snapshot_date >= month_start,
            )
        )
    )
    revenue_yuan = float(revenue_result.scalar() or 0)

    # 人效比
    efficiency = round(revenue_yuan / max(total_salary_yuan, 1), 2)
    # 人均产值
    per_capita = round(revenue_yuan / max(headcount, 1), 2)

    return {
        "store_id": store_id,
        "pay_month": pay_month,
        "headcount": headcount,
        "total_salary_yuan": total_salary_yuan,
        "revenue_yuan": revenue_yuan,
        "hr_efficiency_ratio": efficiency,
        "per_capita_revenue_yuan": per_capita,
        "labor_cost_rate_pct": round(total_salary_yuan / max(revenue_yuan, 1) * 100, 1),
    }


@router.get("/hr/dashboard/position-distribution")
async def get_position_distribution(
    store_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """岗位分布"""
    result = await db.execute(
        select(
            Employee.position,
            func.count(Employee.id).label("count"),
        ).where(
            and_(
                Employee.store_id == store_id,
                Employee.is_active.is_(True),
            )
        ).group_by(Employee.position)
    )
    rows = result.all()
    return {
        "items": [
            {"position": r.position or "未分配", "count": r.count}
            for r in rows
        ],
    }


@router.get("/hr/agent/insights")
async def get_agent_insights(
    store_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    HR AI Agent 洞察：
    - 薪资异常分析 + 优化建议
    - 离职风险预测 + 留人建议
    - 招聘策略推荐 + 渠道效果
    """
    from ..services.hr_agent_service import get_hr_agent_insights
    return await get_hr_agent_insights(store_id, db)
