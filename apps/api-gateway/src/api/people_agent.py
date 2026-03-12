"""
PeopleAgent API — Phase 12B
人员智能体：排班优化 / 绩效评分 / 人力成本 / 考勤预警 / 人员配置
前缀: /api/v1/people
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.models.people_agent import (
    PeopleShiftRecord,
    PeoplePerformanceScore,
    PeopleLaborCostRecord,
    PeopleAttendanceAlert,
    PeopleStaffingDecision,
    PeopleAgentLog,
)

router = APIRouter(prefix="/api/v1/people")

# ─── 懒加载 Agent ─────────────────────────────────────────────────────────────

def _agents():
    from packages.agents.people_agent.src.agent import (
        ShiftOptimizerAgent,
        PerformanceScoreAgent,
        LaborCostAgent,
        AttendanceWarnAgent,
        StaffingPlanAgent,
    )
    return (
        ShiftOptimizerAgent(),
        PerformanceScoreAgent(),
        LaborCostAgent(),
        AttendanceWarnAgent(),
        StaffingPlanAgent(),
    )


# ─── Pydantic Schemas ─────────────────────────────────────────────────────────

class ShiftOptimizeIn(BaseModel):
    brand_id: str
    store_id: str
    shift_date: date = Field(default_factory=date.today)
    required_headcount: int = Field(..., ge=1)
    scheduled_headcount: int = Field(..., ge=0)
    estimated_labor_cost_yuan: float = Field(..., ge=0)
    revenue_yuan: float = Field(..., ge=0)
    shift_assignments: Optional[List[Dict[str, Any]]] = None
    peak_hours: Optional[List[str]] = None


class PerformanceScoreIn(BaseModel):
    brand_id: str
    store_id: str
    employee_id: str
    employee_name: Optional[str] = None
    role: str = Field(..., example="waiter")
    period: str = Field(..., example="2026-03")
    kpi_values: Dict[str, float] = Field(default_factory=dict)
    base_salary: float = Field(default=5000.0, ge=0)


class LaborCostIn(BaseModel):
    brand_id: str
    store_id: str
    period: str = Field(..., example="2026-03")
    total_labor_cost_yuan: float = Field(..., ge=0)
    revenue_yuan: float = Field(..., ge=0)
    avg_headcount: float = Field(..., ge=0)
    overtime_hours: float = Field(default=0.0, ge=0)
    overtime_cost_yuan: float = Field(default=0.0, ge=0)
    cost_breakdown: Optional[Dict[str, float]] = None
    target_labor_cost_ratio: float = Field(default=28.0, ge=0, le=100)


class AttendanceWarnIn(BaseModel):
    brand_id: str
    store_id: str
    employee_id: Optional[str] = None
    employee_name: Optional[str] = None
    alert_date: date = Field(default_factory=date.today)
    alert_type: str = Field(..., example="late")
    description: Optional[str] = None
    estimated_impact_yuan: float = Field(default=0.0, ge=0)
    count_in_period: int = Field(default=1, ge=1)


class StaffingPlanIn(BaseModel):
    brand_id: str
    store_id: str
    current_headcount: int = Field(..., ge=0)
    revenue_yuan: float = Field(..., ge=0)
    target_revenue_per_person: float = Field(default=50000.0, ge=1)
    role_gaps: Optional[Dict[str, int]] = None


class AlertResolveIn(BaseModel):
    resolution_note: Optional[str] = None


class StaffingAcceptIn(BaseModel):
    accepted_rank: int = Field(default=1, ge=1, le=3)
    note: Optional[str] = None


# ─── 1. 排班优化 Agent ────────────────────────────────────────────────────────

@router.post("/agents/shift-optimize", summary="排班优化 Agent")
async def shift_optimize(body: ShiftOptimizeIn, db: AsyncSession = Depends(get_db)):
    """
    ShiftOptimizerAgent — 根据客流预测生成排班优化方案
    OKR: 人力成本率下降 ≥2个百分点
    """
    shift_agent, *_ = _agents()
    t0 = datetime.utcnow()
    result = await shift_agent.optimize(
        db=db,
        brand_id=body.brand_id,
        store_id=body.store_id,
        shift_date=body.shift_date,
        required_headcount=body.required_headcount,
        scheduled_headcount=body.scheduled_headcount,
        estimated_labor_cost_yuan=body.estimated_labor_cost_yuan,
        revenue_yuan=body.revenue_yuan,
        shift_assignments=body.shift_assignments,
        peak_hours=body.peak_hours,
    )
    await db.commit()
    duration_ms = int((datetime.utcnow() - t0).total_seconds() * 1000)
    _log(db, body.brand_id, "shift_optimizer", body.dict(), result, 0, duration_ms)
    await db.commit()
    return result


# ─── 2. 绩效评分 Agent ────────────────────────────────────────────────────────

@router.post("/agents/performance-score", summary="员工绩效评分 Agent")
async def performance_score(body: PerformanceScoreIn, db: AsyncSession = Depends(get_db)):
    """
    PerformanceScoreAgent — 计算员工月度绩效评分与提成
    OKR: 员工绩效评分覆盖率 ≥95%
    """
    _, perf_agent, *_ = _agents()
    t0 = datetime.utcnow()
    result = await perf_agent.score(
        db=db,
        brand_id=body.brand_id,
        store_id=body.store_id,
        employee_id=body.employee_id,
        employee_name=body.employee_name,
        role=body.role,
        period=body.period,
        kpi_values=body.kpi_values,
        base_salary=body.base_salary,
    )
    await db.commit()
    duration_ms = int((datetime.utcnow() - t0).total_seconds() * 1000)
    impact = result.get("total_commission_yuan", 0)
    _log(db, body.brand_id, "performance_score", body.dict(), result, impact, duration_ms)
    await db.commit()
    return result


# ─── 3. 人力成本分析 Agent ────────────────────────────────────────────────────

@router.post("/agents/labor-cost", summary="人力成本分析 Agent")
async def labor_cost_analyze(body: LaborCostIn, db: AsyncSession = Depends(get_db)):
    """
    LaborCostAgent — 分析人力成本结构，计算优化空间
    OKR: 人力成本核算准确率 ≥98%
    """
    _, _, labor_agent, *_ = _agents()
    t0 = datetime.utcnow()
    result = await labor_agent.analyze(
        db=db,
        brand_id=body.brand_id,
        store_id=body.store_id,
        period=body.period,
        total_labor_cost_yuan=body.total_labor_cost_yuan,
        revenue_yuan=body.revenue_yuan,
        avg_headcount=body.avg_headcount,
        overtime_hours=body.overtime_hours,
        overtime_cost_yuan=body.overtime_cost_yuan,
        cost_breakdown=body.cost_breakdown,
        target_labor_cost_ratio=body.target_labor_cost_ratio,
    )
    await db.commit()
    duration_ms = int((datetime.utcnow() - t0).total_seconds() * 1000)
    impact = result.get("optimization_potential_yuan", 0)
    _log(db, body.brand_id, "labor_cost", body.dict(), result, impact, duration_ms)
    await db.commit()
    return result


# ─── 4. 考勤预警 Agent ────────────────────────────────────────────────────────

@router.post("/agents/attendance-warn", summary="考勤预警 Agent")
async def attendance_warn(body: AttendanceWarnIn, db: AsyncSession = Depends(get_db)):
    """
    AttendanceWarnAgent — 检测考勤异常并给出处置建议
    OKR: 考勤异常发现率 ≥90%
    """
    _, _, _, warn_agent, _ = _agents()
    t0 = datetime.utcnow()
    result = await warn_agent.warn(
        db=db,
        brand_id=body.brand_id,
        store_id=body.store_id,
        employee_id=body.employee_id,
        employee_name=body.employee_name,
        alert_date=body.alert_date,
        alert_type=body.alert_type,
        description=body.description,
        estimated_impact_yuan=body.estimated_impact_yuan,
        count_in_period=body.count_in_period,
    )
    await db.commit()
    duration_ms = int((datetime.utcnow() - t0).total_seconds() * 1000)
    _log(db, body.brand_id, "attendance_warn", body.dict(), result, body.estimated_impact_yuan, duration_ms)
    await db.commit()
    return result


# ─── 5. 人员配置建议 Agent ────────────────────────────────────────────────────

@router.post("/agents/staffing-plan", summary="人员配置建议 Agent")
async def staffing_plan(body: StaffingPlanIn, db: AsyncSession = Depends(get_db)):
    """
    StaffingPlanAgent — 生成综合人员配置建议（招/留/调/降）
    OKR: 配置建议采纳率 ≥65%
    """
    *_, staffing_agent = _agents()
    t0 = datetime.utcnow()
    result = await staffing_agent.plan(
        db=db,
        brand_id=body.brand_id,
        store_id=body.store_id,
        current_headcount=body.current_headcount,
        revenue_yuan=body.revenue_yuan,
        target_revenue_per_person=body.target_revenue_per_person,
        role_gaps=body.role_gaps,
    )
    await db.commit()
    duration_ms = int((datetime.utcnow() - t0).total_seconds() * 1000)
    impact = result.get("total_impact_yuan", 0)
    _log(db, body.brand_id, "staffing_plan", body.dict(), result, impact, duration_ms)
    await db.commit()
    return result


# ─── 查询端点 ─────────────────────────────────────────────────────────────────

@router.get("/shifts", summary="查询排班优化记录")
async def list_shifts(
    brand_id: str,
    store_id: str,
    limit: int = Query(default=10, le=30),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PeopleShiftRecord).where(
            and_(PeopleShiftRecord.brand_id == brand_id, PeopleShiftRecord.store_id == store_id)
        ).order_by(desc(PeopleShiftRecord.shift_date)).limit(limit)
    )
    records = result.scalars().all()
    return {"count": len(records), "shifts": [
        {
            "id": r.id, "shift_date": str(r.shift_date),
            "coverage_rate": r.coverage_rate, "status": r.status,
            "labor_cost_pct": r.labor_cost_per_revenue_pct,
        }
        for r in records
    ]}


@router.get("/performance", summary="查询员工绩效评分")
async def list_performance(
    brand_id: str,
    store_id: str,
    period: Optional[str] = None,
    employee_id: Optional[str] = None,
    limit: int = Query(default=20, le=50),
    db: AsyncSession = Depends(get_db),
):
    conditions = [
        PeoplePerformanceScore.brand_id == brand_id,
        PeoplePerformanceScore.store_id == store_id,
    ]
    if period:
        conditions.append(PeoplePerformanceScore.period == period)
    if employee_id:
        conditions.append(PeoplePerformanceScore.employee_id == employee_id)
    result = await db.execute(
        select(PeoplePerformanceScore).where(and_(*conditions))
        .order_by(desc(PeoplePerformanceScore.created_at)).limit(limit)
    )
    records = result.scalars().all()
    return {"count": len(records), "scores": [
        {
            "id": r.id, "employee_id": r.employee_id,
            "employee_name": r.employee_name, "role": r.role,
            "period": r.period, "overall_score": r.overall_score,
            "rating": r.rating, "total_commission_yuan": float(r.total_commission_yuan or 0),
        }
        for r in records
    ]}


@router.get("/labor-cost", summary="查询人力成本记录")
async def list_labor_cost(
    brand_id: str,
    store_id: str,
    period: Optional[str] = None,
    limit: int = Query(default=12, le=24),
    db: AsyncSession = Depends(get_db),
):
    conditions = [
        PeopleLaborCostRecord.brand_id == brand_id,
        PeopleLaborCostRecord.store_id == store_id,
    ]
    if period:
        conditions.append(PeopleLaborCostRecord.period == period)
    result = await db.execute(
        select(PeopleLaborCostRecord).where(and_(*conditions))
        .order_by(desc(PeopleLaborCostRecord.period)).limit(limit)
    )
    records = result.scalars().all()
    return {"count": len(records), "records": [
        {
            "id": r.id, "period": r.period,
            "labor_cost_ratio": r.labor_cost_ratio,
            "revenue_per_employee_yuan": float(r.revenue_per_employee_yuan or 0),
            "optimization_potential_yuan": float(r.optimization_potential_yuan or 0),
        }
        for r in records
    ]}


@router.get("/attendance-alerts", summary="查询考勤预警")
async def list_attendance_alerts(
    brand_id: str,
    store_id: str,
    include_resolved: bool = False,
    limit: int = Query(default=20, le=50),
    db: AsyncSession = Depends(get_db),
):
    conditions = [
        PeopleAttendanceAlert.brand_id == brand_id,
        PeopleAttendanceAlert.store_id == store_id,
    ]
    if not include_resolved:
        conditions.append(PeopleAttendanceAlert.is_resolved == False)
    result = await db.execute(
        select(PeopleAttendanceAlert).where(and_(*conditions))
        .order_by(desc(PeopleAttendanceAlert.alert_date)).limit(limit)
    )
    records = result.scalars().all()
    return {"count": len(records), "alerts": [
        {
            "id": r.id, "alert_date": str(r.alert_date),
            "alert_type": r.alert_type, "severity": r.severity,
            "employee_name": r.employee_name,
            "estimated_impact_yuan": float(r.estimated_impact_yuan or 0),
            "is_resolved": r.is_resolved,
        }
        for r in records
    ]}


@router.patch("/attendance-alerts/{alert_id}/resolve", summary="标记考勤预警已处理")
async def resolve_alert(
    alert_id: str,
    body: AlertResolveIn,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PeopleAttendanceAlert).where(PeopleAttendanceAlert.id == alert_id)
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(404, "考勤预警不存在")
    alert.is_resolved = True
    alert.resolved_at = datetime.utcnow()
    await db.commit()
    return {"id": alert_id, "status": "resolved"}


@router.get("/staffing-decisions", summary="查询人员配置决策")
async def list_staffing_decisions(
    brand_id: str,
    store_id: str,
    limit: int = Query(default=10, le=20),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PeopleStaffingDecision).where(
            and_(PeopleStaffingDecision.brand_id == brand_id, PeopleStaffingDecision.store_id == store_id)
        ).order_by(desc(PeopleStaffingDecision.decision_date)).limit(limit)
    )
    records = result.scalars().all()
    return {"count": len(records), "decisions": [
        {
            "id": r.id, "decision_date": str(r.decision_date),
            "priority": r.priority, "status": r.status,
            "current_headcount": r.current_headcount,
            "optimal_headcount": r.optimal_headcount,
            "total_impact_yuan": float(r.total_impact_yuan),
            "top_recommendation": r.recommendations[0] if r.recommendations else None,
        }
        for r in records
    ]}


@router.patch("/staffing-decisions/{decision_id}/accept", summary="采纳人员配置建议")
async def accept_staffing_decision(
    decision_id: str,
    body: StaffingAcceptIn,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PeopleStaffingDecision).where(PeopleStaffingDecision.id == decision_id)
    )
    decision = result.scalar_one_or_none()
    if not decision:
        raise HTTPException(404, "人员配置决策不存在")
    decision.status = "accepted"
    decision.accepted_at = datetime.utcnow()
    await db.commit()
    return {"id": decision_id, "status": "accepted", "accepted_rank": body.accepted_rank}


# ─── 驾驶舱 BFF ───────────────────────────────────────────────────────────────

@router.get("/dashboard", summary="人员智能体驾驶舱（首屏BFF）")
async def dashboard(
    brand_id: str,
    store_id: str,
    db: AsyncSession = Depends(get_db),
):
    """首屏一次性加载：排班状态 + 绩效概览 + 人力成本 + 未处理预警"""
    # 最新排班
    shift_result = await db.execute(
        select(PeopleShiftRecord).where(
            and_(PeopleShiftRecord.brand_id == brand_id,
                 PeopleShiftRecord.store_id == store_id)
        ).order_by(desc(PeopleShiftRecord.shift_date)).limit(1)
    )
    latest_shift = shift_result.scalar_one_or_none()

    # 最新人力成本
    cost_result = await db.execute(
        select(PeopleLaborCostRecord).where(
            and_(PeopleLaborCostRecord.brand_id == brand_id,
                 PeopleLaborCostRecord.store_id == store_id)
        ).order_by(desc(PeopleLaborCostRecord.period)).limit(1)
    )
    latest_cost = cost_result.scalar_one_or_none()

    # 未处理考勤预警
    alert_result = await db.execute(
        select(PeopleAttendanceAlert).where(
            and_(PeopleAttendanceAlert.brand_id == brand_id,
                 PeopleAttendanceAlert.store_id == store_id,
                 PeopleAttendanceAlert.is_resolved == False)
        )
    )
    open_alerts = alert_result.scalars().all()

    # 最新待处理配置决策
    decision_result = await db.execute(
        select(PeopleStaffingDecision).where(
            and_(PeopleStaffingDecision.brand_id == brand_id,
                 PeopleStaffingDecision.store_id == store_id,
                 PeopleStaffingDecision.status == "pending")
        ).order_by(desc(PeopleStaffingDecision.created_at)).limit(1)
    )
    pending_decision = decision_result.scalar_one_or_none()

    return {
        "brand_id": brand_id,
        "store_id": store_id,
        "today": str(date.today()),
        "shift_status": {
            "shift_date": str(latest_shift.shift_date) if latest_shift else None,
            "coverage_rate": latest_shift.coverage_rate if latest_shift else None,
            "status": latest_shift.status if latest_shift else None,
            "labor_cost_pct": latest_shift.labor_cost_per_revenue_pct if latest_shift else None,
        },
        "labor_cost": {
            "period": latest_cost.period if latest_cost else None,
            "labor_cost_ratio": latest_cost.labor_cost_ratio if latest_cost else None,
            "revenue_per_employee_yuan": float(latest_cost.revenue_per_employee_yuan or 0) if latest_cost else None,
            "optimization_potential_yuan": float(latest_cost.optimization_potential_yuan or 0) if latest_cost else None,
        },
        "attendance_alerts": {
            "open_count": len(open_alerts),
            "critical_count": sum(1 for a in open_alerts if a.severity == "critical"),
        },
        "pending_staffing": {
            "has_decision": pending_decision is not None,
            "decision_id": pending_decision.id if pending_decision else None,
            "total_impact_yuan": float(pending_decision.total_impact_yuan) if pending_decision else 0,
            "priority": pending_decision.priority if pending_decision else None,
        },
    }


# ─── 内部辅助 ─────────────────────────────────────────────────────────────────

def _log(
    db: AsyncSession,
    brand_id: str,
    agent_type: str,
    params: dict,
    summary: dict,
    impact_yuan: float,
    duration_ms: int,
) -> None:
    """异步写 Agent 调用日志（fire-and-forget，不 await）"""
    import uuid as _uuid
    log = PeopleAgentLog(
        id=str(_uuid.uuid4()),
        brand_id=brand_id,
        agent_type=agent_type,
        input_params=params,
        output_summary={k: v for k, v in summary.items() if k != "kpi_items"},
        impact_yuan=Decimal(str(impact_yuan)) if impact_yuan else None,
        duration_ms=duration_ms,
        success=True,
    )
    db.add(log)
