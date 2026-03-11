"""
Workforce API — Phase 8 Step 5
"""

from __future__ import annotations

import calendar
import json
import os
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import get_current_user, require_role
from src.repositories import EmployeeRepository
from src.models.user import User, UserRole
from src.services.labor_cost_service import LaborCostService
from src.services.labor_demand_service import LaborDemandService
from src.services.shift_fairness_service import ShiftFairnessService
from src.services.staffing_pattern_service import StaffingPatternService
from src.services.turnover_prediction_service import TurnoverPredictionService
from src.services.workforce_auto_schedule_service import WorkforceAutoScheduleService

router = APIRouter(prefix="/api/v1/workforce", tags=["workforce"])


class StaffingAdviceConfirmRequest(BaseModel):
    advice_date: str = Field(..., description="建议日期 YYYY-MM-DD")
    meal_period: str = Field("all_day", description="morning/lunch/dinner/all_day")
    action: str = Field(..., description="confirmed/rejected/modified")
    modified_headcount: Optional[int] = Field(None, ge=1)
    rejection_reason_code: Optional[str] = Field(None, description="拒绝原因编码")
    rejection_reason: Optional[str] = None


class StaffingAdviceQueryResponse(BaseModel):
    exists: bool
    store_id: str
    advice_date: str
    meal_period: str
    status: Optional[str] = None
    recommended_headcount: Optional[int] = None
    current_scheduled_headcount: Optional[int] = None
    headcount_delta: Optional[int] = None
    estimated_saving_yuan: Optional[float] = None
    estimated_overspend_yuan: Optional[float] = None
    confidence_score: Optional[float] = None
    position_breakdown: Optional[dict] = None
    reason_1: Optional[str] = None
    reason_2: Optional[str] = None
    reason_3: Optional[str] = None
    confirmed_action: Optional[str] = None
    confirmed_at: Optional[str] = None
    confirmed_by: Optional[str] = None


class StaffingAdviceHistoryItem(BaseModel):
    advice_date: str
    meal_period: str
    status: str
    action: Optional[str] = None
    recommended_headcount: Optional[int] = None
    modified_headcount: Optional[int] = None
    rejection_reason_code: Optional[str] = None
    rejection_reason_text: Optional[str] = None
    rejection_reason: Optional[str] = None
    cost_impact_yuan: Optional[float] = None
    confirmed_at: Optional[str] = None


class StaffingAdviceHistoryResponse(BaseModel):
    store_id: str
    days: int
    total: int
    confirmed_count: int
    modified_count: int
    rejected_count: int
    rejection_reasons_top: list[str]
    items: list[StaffingAdviceHistoryItem]


class LaborBudgetUpsertRequest(BaseModel):
    month: str = Field(..., description="预算月份 YYYY-MM")
    target_labor_cost_rate: float = Field(..., ge=0, le=100)
    max_labor_cost_yuan: float = Field(..., ge=0)
    daily_budget_yuan: Optional[float] = Field(None, ge=0)
    alert_threshold_pct: float = Field(90.0, ge=0, le=100)
    is_active: bool = True


class AutoScheduleRequest(BaseModel):
    schedule_date: Optional[str] = Field(None, description="排班日期 YYYY-MM-DD，默认今天")
    auto_publish: bool = Field(True, description="是否自动发布排班")
    notify_on_anomaly: bool = Field(True, description="发现异常时是否发送企微提醒")
    recipient_user_id: Optional[str] = Field(None, description="企微接收人，默认 store_{store_id}")


class LearnPatternRequest(BaseModel):
    start_date: str = Field(..., description="学习窗口开始日期 YYYY-MM-DD")
    end_date: str = Field(..., description="学习窗口结束日期 YYYY-MM-DD")


def _risk_level(score: float) -> str:
    if score >= 0.7:
        return "critical"
    if score >= 0.5:
        return "high"
    if score >= 0.3:
        return "medium"
    return "low"


def _parse_iso_date(s: str, name: str) -> date:
    try:
        return date.fromisoformat(s)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{name} 格式错误，需为 YYYY-MM-DD，实际值: {s}",
        )


def _parse_yyyymm(month: str) -> tuple[int, int]:
    try:
        y, m = month.split("-")
        year, mon = int(y), int(m)
        if mon < 1 or mon > 12:
            raise ValueError
        return year, mon
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"month 格式错误，需为 YYYY-MM，实际值: {month}",
        )


def _build_rejection_reason_payload(
    code: Optional[str],
    text: Optional[str],
) -> Optional[str]:
    code = (code or "").strip()
    text = (text or "").strip()
    if not code and not text:
        return None
    payload = {"code": code or "other", "text": text}
    return json.dumps(payload, ensure_ascii=False)


def _parse_rejection_reason_payload(raw: Optional[str]) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Parse stored rejection_reason text.
    Returns (code, text, display).
    """
    if not raw:
        return None, None, None
    raw = str(raw).strip()
    if not raw:
        return None, None, None
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            code = str(obj.get("code") or "").strip() or None
            text = str(obj.get("text") or "").strip() or None
            display = text or code
            return code, text, display
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return None, raw, raw


@router.get("/stores/{store_id}/staffing-advice", response_model=StaffingAdviceQueryResponse)
async def get_staffing_advice(
    store_id: str,
    date_str: Optional[str] = Query(None, alias="date", description="建议日期 YYYY-MM-DD，默认明天"),
    meal_period: str = Query("all_day", description="morning/lunch/dinner/all_day"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    advice_date = _parse_iso_date(date_str, "date") if date_str else (date.today() + timedelta(days=1))
    meal_period = meal_period.lower()
    if meal_period not in {"morning", "lunch", "dinner", "all_day"}:
        raise HTTPException(status_code=400, detail="meal_period 必须是 morning/lunch/dinner/all_day")

    result = await db.execute(
        text(
            """
            SELECT
                sa.id, sa.store_id, sa.advice_date, sa.meal_period, sa.status,
                sa.recommended_headcount, sa.current_scheduled_headcount, sa.headcount_delta,
                sa.estimated_saving_yuan, sa.estimated_overspend_yuan, sa.confidence_score,
                sa.position_breakdown, sa.reason_1, sa.reason_2, sa.reason_3,
                sac.action AS confirmed_action, sac.confirmed_at, sac.confirmed_by
            FROM staffing_advice sa
            LEFT JOIN staffing_advice_confirmations sac ON sac.advice_id = sa.id
            WHERE sa.store_id = :sid
              AND sa.advice_date = :advice_date
              AND sa.meal_period = :meal_period
            ORDER BY sa.created_at DESC, sac.confirmed_at DESC NULLS LAST
            LIMIT 1
            """
        ),
        {"sid": store_id, "advice_date": advice_date, "meal_period": meal_period},
    )
    row = result.fetchone()
    if not row:
        return StaffingAdviceQueryResponse(
            exists=False,
            store_id=store_id,
            advice_date=advice_date.isoformat(),
            meal_period=meal_period,
        )

    return StaffingAdviceQueryResponse(
        exists=True,
        store_id=row.store_id,
        advice_date=row.advice_date.isoformat() if hasattr(row.advice_date, "isoformat") else str(row.advice_date),
        meal_period=row.meal_period,
        status=row.status,
        recommended_headcount=int(row.recommended_headcount) if row.recommended_headcount is not None else None,
        current_scheduled_headcount=int(row.current_scheduled_headcount) if row.current_scheduled_headcount is not None else None,
        headcount_delta=int(row.headcount_delta) if row.headcount_delta is not None else None,
        estimated_saving_yuan=float(row.estimated_saving_yuan) if row.estimated_saving_yuan is not None else None,
        estimated_overspend_yuan=float(row.estimated_overspend_yuan) if row.estimated_overspend_yuan is not None else None,
        confidence_score=float(row.confidence_score) if row.confidence_score is not None else None,
        position_breakdown=row.position_breakdown if isinstance(row.position_breakdown, dict) else None,
        reason_1=row.reason_1,
        reason_2=row.reason_2,
        reason_3=row.reason_3,
        confirmed_action=row.confirmed_action,
        confirmed_at=row.confirmed_at.isoformat() if hasattr(row.confirmed_at, "isoformat") and row.confirmed_at else None,
        confirmed_by=row.confirmed_by,
    )


@router.get("/stores/{store_id}/staffing-advice/history", response_model=StaffingAdviceHistoryResponse)
async def get_staffing_advice_history(
    store_id: str,
    days: int = Query(7, ge=1, le=30, description="查询最近 N 天建议处理记录"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    start_date = date.today() - timedelta(days=days - 1)

    result = await db.execute(
        text(
            """
            SELECT
                sa.advice_date,
                sa.meal_period,
                sa.status,
                sa.recommended_headcount,
                sac.action,
                sac.modified_headcount,
                sac.rejection_reason,
                sac.confirmed_at
            FROM staffing_advice sa
            LEFT JOIN LATERAL (
                SELECT action, modified_headcount, rejection_reason, confirmed_at
                FROM staffing_advice_confirmations
                WHERE advice_id = sa.id
                ORDER BY confirmed_at DESC
                LIMIT 1
            ) sac ON TRUE
            WHERE sa.store_id = :sid
              AND sa.advice_date >= :start_date
            ORDER BY sa.advice_date DESC, sa.created_at DESC
            """
        ),
        {"sid": store_id, "start_date": start_date},
    )
    rows = result.fetchall()

    avg_wage_per_day = float(os.getenv("L8_AVG_WAGE_PER_DAY", "200"))
    items: list[StaffingAdviceHistoryItem] = []
    reasons: list[str] = []
    confirmed_count = 0
    modified_count = 0
    rejected_count = 0

    for row in rows:
        action = row.action or None
        recommended = int(row.recommended_headcount) if row.recommended_headcount is not None else None
        modified = int(row.modified_headcount) if row.modified_headcount is not None else None
        if action == "confirmed":
            confirmed_count += 1
        elif action == "modified":
            modified_count += 1
        elif action == "rejected":
            rejected_count += 1
            _, _, display_reason = _parse_rejection_reason_payload(row.rejection_reason)
            if display_reason:
                reasons.append(display_reason)

        effective = modified if action == "modified" and modified is not None else recommended
        cost_impact = None
        if effective is not None and recommended is not None:
            cost_impact = float((effective - recommended) * avg_wage_per_day)
        reason_code, reason_text, reason_display = _parse_rejection_reason_payload(row.rejection_reason)

        items.append(
            StaffingAdviceHistoryItem(
                advice_date=row.advice_date.isoformat() if hasattr(row.advice_date, "isoformat") else str(row.advice_date),
                meal_period=row.meal_period,
                status=row.status,
                action=action,
                recommended_headcount=recommended,
                modified_headcount=modified,
                rejection_reason_code=reason_code,
                rejection_reason_text=reason_text,
                rejection_reason=reason_display,
                cost_impact_yuan=round(cost_impact, 2) if cost_impact is not None else None,
                confirmed_at=row.confirmed_at.isoformat() if hasattr(row.confirmed_at, "isoformat") and row.confirmed_at else None,
            )
        )

    top_reasons: list[str] = []
    if reasons:
        counts: dict[str, int] = {}
        for r in reasons:
            counts[r] = counts.get(r, 0) + 1
        top_reasons = [k for k, _ in sorted(counts.items(), key=lambda x: x[1], reverse=True)[:3]]

    return StaffingAdviceHistoryResponse(
        store_id=store_id,
        days=days,
        total=len(items),
        confirmed_count=confirmed_count,
        modified_count=modified_count,
        rejected_count=rejected_count,
        rejection_reasons_top=top_reasons,
        items=items,
    )


@router.get("/stores/{store_id}/labor-forecast")
async def get_labor_forecast(
    store_id: str,
    date_str: Optional[str] = Query(None, alias="date", description="目标日期 YYYY-MM-DD，默认明天"),
    weather_score: float = Query(1.0, ge=0.5, le=1.5),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    target_date = _parse_iso_date(date_str, "date") if date_str else (date.today() + timedelta(days=1))
    return await LaborDemandService.forecast_all_periods(
        store_id=store_id,
        forecast_date=target_date,
        db=db,
        save=True,
        weather_score=weather_score,
    )


@router.get("/stores/{store_id}/labor-cost")
async def get_labor_cost(
    store_id: str,
    date_str: Optional[str] = Query(None, alias="date", description="目标日期 YYYY-MM-DD，默认今天"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    target_date = _parse_iso_date(date_str, "date") if date_str else date.today()
    return await LaborCostService.compute_and_save_snapshot(
        store_id=store_id,
        snapshot_date=target_date,
        db=db,
    )


@router.get("/stores/{store_id}/labor-efficiency")
async def get_labor_efficiency(
    store_id: str,
    start_date: str = Query(..., description="开始日期 YYYY-MM-DD"),
    end_date: str = Query(..., description="结束日期 YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    sd = _parse_iso_date(start_date, "start_date")
    ed = _parse_iso_date(end_date, "end_date")
    if ed < sd:
        raise HTTPException(status_code=400, detail="end_date 不能早于 start_date")

    result = await db.execute(
        text(
            """
            SELECT
                d.snapshot_date,
                d.actual_revenue_yuan,
                d.headcount_actual
            FROM labor_cost_snapshots d
            WHERE d.store_id = :sid
              AND d.snapshot_date >= :start_date
              AND d.snapshot_date <= :end_date
            ORDER BY d.snapshot_date
            """
        ),
        {"sid": store_id, "start_date": sd, "end_date": ed},
    )
    rows = result.fetchall()
    days = []
    for r in rows:
        revenue = float(r.actual_revenue_yuan or 0)
        headcount = int(r.headcount_actual or 0)
        efficiency = round(revenue / headcount, 2) if headcount > 0 else 0.0
        days.append(
            {
                "date": str(r.snapshot_date),
                "revenue_yuan": revenue,
                "headcount_actual": headcount,
                "labor_efficiency_yuan_per_person": efficiency,
            }
        )

    avg_efficiency = round(
        sum(d["labor_efficiency_yuan_per_person"] for d in days) / len(days), 2
    ) if days else 0.0

    return {
        "store_id": store_id,
        "start_date": sd.isoformat(),
        "end_date": ed.isoformat(),
        "avg_labor_efficiency_yuan_per_person": avg_efficiency,
        "days": days,
    }


@router.get("/stores/{store_id}/employee-health")
async def get_employee_health(
    store_id: str,
    year: Optional[int] = Query(None, ge=2020, le=2100),
    month: Optional[int] = Query(None, ge=1, le=12),
    top_n: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    target = date.today()
    y = year or target.year
    m = month or target.month

    fairness_service = ShiftFairnessService()
    turnover_service = TurnoverPredictionService()

    employees = await EmployeeRepository.get_by_store(db, store_id)
    fairness_data = await fairness_service.get_monthly_shift_fairness(
        store_id=store_id,
        year=y,
        month=m,
        db=db,
    )
    fairness_map = {
        item["employee_id"]: item
        for item in fairness_data.get("employee_stats", [])
    }

    items = []
    for employee in employees:
        pred = await turnover_service.predict_employee_turnover(
            employee_id=employee.id,
            db=db,
            send_alert=False,
        )
        stat = fairness_map.get(employee.id, {})
        risk_score = float(pred["risk_score_90d"])
        items.append(
            {
                "employee_id": employee.id,
                "name": employee.name,
                "position": employee.position,
                "risk_score_90d": risk_score,
                "risk_level": _risk_level(risk_score),
                "replacement_cost_yuan": float(pred["replacement_cost_yuan"]),
                "major_risk_factors": pred["major_risk_factors"],
                "unfavorable_ratio": float(stat.get("unfavorable_ratio", 0.0)),
                "unfavorable_shifts": int(stat.get("unfavorable_shifts", 0)),
                "total_shifts": int(stat.get("total_shifts", 0)),
            }
        )

    items.sort(key=lambda item: item["risk_score_90d"], reverse=True)
    sliced = items[:top_n]

    fairness_distribution = {
        "high_unfairness": sum(1 for item in sliced if item["unfavorable_ratio"] >= 0.5),
        "medium_unfairness": sum(1 for item in sliced if 0.25 <= item["unfavorable_ratio"] < 0.5),
        "low_unfairness": sum(1 for item in sliced if item["unfavorable_ratio"] < 0.25),
    }

    return {
        "store_id": store_id,
        "year": y,
        "month": m,
        "total": len(items),
        "fairness_index": float(fairness_data.get("fairness_index", 100.0)),
        "fairness_distribution": fairness_distribution,
        "items": sliced,
    }


@router.post("/stores/{store_id}/staffing-advice/confirm")
async def confirm_staffing_advice(
    store_id: str,
    body: StaffingAdviceConfirmRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    advice_date = _parse_iso_date(body.advice_date, "advice_date")
    meal_period = body.meal_period.lower()
    action = body.action.lower()
    if meal_period not in {"morning", "lunch", "dinner", "all_day"}:
        raise HTTPException(status_code=400, detail="meal_period 必须是 morning/lunch/dinner/all_day")
    if action not in {"confirmed", "rejected", "modified"}:
        raise HTTPException(status_code=400, detail="action 必须是 confirmed/rejected/modified")
    if action == "modified" and body.modified_headcount is None:
        raise HTTPException(status_code=400, detail="modified 动作必须提供 modified_headcount")
    if action == "rejected" and not ((body.rejection_reason or "").strip() or (body.rejection_reason_code or "").strip()):
        raise HTTPException(status_code=400, detail="rejected 动作必须提供 rejection_reason 或 rejection_reason_code")

    advice_result = await db.execute(
        text(
            """
            SELECT
                id, created_at,
                recommended_headcount, current_scheduled_headcount,
                estimated_saving_yuan, estimated_overspend_yuan
            FROM staffing_advice
            WHERE store_id = :sid
              AND advice_date = :advice_date
              AND meal_period = :meal_period
            ORDER BY created_at DESC
            LIMIT 1
            """
        ),
        {"sid": store_id, "advice_date": advice_date, "meal_period": meal_period},
    )
    advice_row = advice_result.fetchone()
    if not advice_row:
        raise HTTPException(status_code=404, detail="未找到对应排班建议")

    now = datetime.utcnow()
    created_at = advice_row.created_at if hasattr(advice_row.created_at, "timestamp") else now
    response_seconds = max(int((now - created_at).total_seconds()), 0)
    advice_status = "confirmed" if action in {"confirmed", "modified"} else "rejected"
    baseline_recommended = int(getattr(advice_row, "recommended_headcount", 0) or 0)
    baseline_current = int(getattr(advice_row, "current_scheduled_headcount", 0) or 0)
    avg_wage_per_day = float(os.getenv("L8_AVG_WAGE_PER_DAY", "200"))
    effective_headcount = int(body.modified_headcount) if action == "modified" and body.modified_headcount is not None else baseline_recommended
    cost_impact_yuan = float((effective_headcount - baseline_current) * avg_wage_per_day)

    rejection_reason_payload = _build_rejection_reason_payload(
        body.rejection_reason_code if action == "rejected" else None,
        body.rejection_reason if action == "rejected" else None,
    )

    await db.execute(
        text(
            """
            UPDATE staffing_advice
            SET status = :status, updated_at = NOW()
            WHERE id = :advice_id
            """
        ),
        {"status": advice_status, "advice_id": advice_row.id},
    )
    await db.execute(
        text(
            """
            INSERT INTO staffing_advice_confirmations (
                advice_id, store_id, confirmed_by, action, modified_headcount,
                rejection_reason, response_time_seconds, actual_saving_yuan,
                confirmed_at, created_at
            ) VALUES (
                :advice_id, :store_id, :confirmed_by, :action, :modified_headcount,
                :rejection_reason, :response_time_seconds, NULL,
                NOW(), NOW()
            )
            """
        ),
        {
            "advice_id": advice_row.id,
            "store_id": store_id,
            "confirmed_by": str(user.id),
            "action": action,
            "modified_headcount": body.modified_headcount,
            "rejection_reason": rejection_reason_payload,
            "response_time_seconds": response_seconds,
        },
    )
    await db.commit()

    message = (
        "排班建议已确认"
        if action == "confirmed"
        else "排班建议已修改并确认"
        if action == "modified"
        else "排班建议已拒绝"
    )

    return {
        "ok": True,
        "store_id": store_id,
        "advice_date": advice_date.isoformat(),
        "meal_period": meal_period,
        "action": action,
        "status": advice_status,
        "cost_impact_yuan": round(cost_impact_yuan, 2),
        "message": message,
    }


@router.get("/multi-store/labor-ranking")
async def get_multi_store_labor_ranking(
    month: str = Query(..., description="排名月份 YYYY-MM"),
    brand_id: Optional[str] = Query(None, description="可选，默认取当前用户品牌"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    year, mon = _parse_yyyymm(month)
    ranking_day = calendar.monthrange(year, mon)[1]
    ranking_date = date(year, mon, ranking_day)
    effective_brand_id = brand_id or user.brand_id
    if not effective_brand_id:
        raise HTTPException(status_code=400, detail="当前用户无 brand_id，请显式传入 brand_id")

    return await LaborCostService.refresh_store_rankings(
        brand_id=effective_brand_id,
        ranking_date=ranking_date,
        period_type="monthly",
        db=db,
    )


@router.get("/stores/{store_id}/labor-budget")
async def get_labor_budget(
    store_id: str,
    month: Optional[str] = Query(None, description="YYYY-MM，默认当月"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    period = month or date.today().strftime("%Y-%m")
    _parse_yyyymm(period)
    result = await db.execute(
        text(
            """
            SELECT
                store_id, budget_period, budget_type,
                target_labor_cost_rate, max_labor_cost_yuan,
                daily_budget_yuan, alert_threshold_pct, approved_by, is_active
            FROM store_labor_budgets
            WHERE store_id = :sid
              AND budget_period = :period
            ORDER BY updated_at DESC
            LIMIT 1
            """
        ),
        {"sid": store_id, "period": period},
    )
    row = result.fetchone()
    if not row:
        return {"store_id": store_id, "budget_period": period, "exists": False}
    return {
        "store_id": row.store_id,
        "budget_period": row.budget_period,
        "budget_type": row.budget_type,
        "target_labor_cost_rate": float(row.target_labor_cost_rate or 0),
        "max_labor_cost_yuan": float(row.max_labor_cost_yuan or 0),
        "daily_budget_yuan": float(row.daily_budget_yuan) if row.daily_budget_yuan is not None else None,
        "alert_threshold_pct": float(row.alert_threshold_pct or 90),
        "approved_by": row.approved_by,
        "is_active": bool(row.is_active),
        "exists": True,
    }


@router.put("/stores/{store_id}/labor-budget")
async def upsert_labor_budget(
    store_id: str,
    body: LaborBudgetUpsertRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.STORE_MANAGER)),
):
    _parse_yyyymm(body.month)
    await db.execute(
        text(
            """
            INSERT INTO store_labor_budgets (
                store_id, budget_period, budget_type,
                target_labor_cost_rate, max_labor_cost_yuan,
                daily_budget_yuan, alert_threshold_pct, approved_by, is_active,
                created_at, updated_at
            ) VALUES (
                :store_id, :budget_period, 'monthly',
                :target_labor_cost_rate, :max_labor_cost_yuan,
                :daily_budget_yuan, :alert_threshold_pct, :approved_by, :is_active,
                NOW(), NOW()
            )
            ON CONFLICT (store_id, budget_period, budget_type)
            DO UPDATE SET
                target_labor_cost_rate = EXCLUDED.target_labor_cost_rate,
                max_labor_cost_yuan    = EXCLUDED.max_labor_cost_yuan,
                daily_budget_yuan      = EXCLUDED.daily_budget_yuan,
                alert_threshold_pct    = EXCLUDED.alert_threshold_pct,
                approved_by            = EXCLUDED.approved_by,
                is_active              = EXCLUDED.is_active,
                updated_at             = NOW()
            """
        ),
        {
            "store_id": store_id,
            "budget_period": body.month,
            "target_labor_cost_rate": body.target_labor_cost_rate,
            "max_labor_cost_yuan": body.max_labor_cost_yuan,
            "daily_budget_yuan": body.daily_budget_yuan,
            "alert_threshold_pct": body.alert_threshold_pct,
            "approved_by": str(user.id),
            "is_active": body.is_active,
        },
    )
    await db.commit()
    return {"ok": True, "store_id": store_id, "budget_period": body.month}


@router.post("/stores/{store_id}/auto-schedule")
async def auto_generate_schedule_with_constraints(
    store_id: str,
    body: AutoScheduleRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.STORE_MANAGER)),
):
    target_date = _parse_iso_date(body.schedule_date, "schedule_date") if body.schedule_date else date.today()
    try:
        result = await WorkforceAutoScheduleService.generate_schedule_with_constraints(
            store_id=store_id,
            schedule_date=target_date,
            db=db,
            auto_publish=body.auto_publish,
            notify_on_anomaly=body.notify_on_anomaly,
            recipient_user_id=body.recipient_user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not result.get("created"):
        raise HTTPException(status_code=409, detail="该日期排班已存在，请勿重复生成")
    return result


@router.post("/stores/{store_id}/staffing-patterns/learn")
async def learn_staffing_patterns(
    store_id: str,
    body: LearnPatternRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.STORE_MANAGER)),
):
    start_date = _parse_iso_date(body.start_date, "start_date")
    end_date = _parse_iso_date(body.end_date, "end_date")
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="end_date 不能早于 start_date")
    return await StaffingPatternService.learn_from_history(
        store_id=store_id,
        start_date=start_date,
        end_date=end_date,
        db=db,
    )


@router.get("/stores/{store_id}/staffing-patterns/best")
async def get_best_staffing_pattern(
    store_id: str,
    date_str: Optional[str] = Query(None, alias="date", description="目标日期 YYYY-MM-DD，默认今天"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    target_date = _parse_iso_date(date_str, "date") if date_str else date.today()
    pattern = await StaffingPatternService.get_best_pattern(
        store_id=store_id,
        target_date=target_date,
        db=db,
    )
    if not pattern:
        return {"store_id": store_id, "date": target_date.isoformat(), "exists": False}
    return {"store_id": store_id, "date": target_date.isoformat(), "exists": True, **pattern}


@router.get("/stores/{store_id}/shift-fairness-detail")
async def get_shift_fairness_detail(
    store_id: str,
    year: Optional[int] = Query(None, ge=2020, le=2100),
    month: Optional[int] = Query(None, ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """班次公平性详细分布 — 供员工健康Tab的分布柱状图使用"""
    target = date.today()
    y = year or target.year
    m = month or target.month

    fairness_service = ShiftFairnessService()
    data = await fairness_service.get_monthly_shift_fairness(
        store_id=store_id, year=y, month=m, db=db
    )

    # 按 unfavorable_ratio 分三档，供前端柱状图渲染
    stats = data.get("employee_stats", [])
    buckets = {
        "high":   [s for s in stats if s["unfavorable_ratio"] >= 0.5],
        "medium": [s for s in stats if 0.25 <= s["unfavorable_ratio"] < 0.5],
        "low":    [s for s in stats if s["unfavorable_ratio"] < 0.25],
    }

    alerts = await fairness_service.detect_unfair_assignment_alerts(
        store_id=store_id, end_date=date(y, m, 1).replace(day=1), db=db
    )

    return {
        "store_id": store_id,
        "year": y,
        "month": m,
        "fairness_index": data.get("fairness_index", 100.0),
        "total_employees": data.get("total_employees", 0),
        "distribution": {
            "high_unfairness_count":   len(buckets["high"]),
            "medium_unfairness_count": len(buckets["medium"]),
            "low_unfairness_count":    len(buckets["low"]),
        },
        # 所有员工按 unfavorable_ratio 降序，供前端绘制水平条形图
        "employee_stats": stats,
        # 连续被分配差班的预警员工列表
        "consecutive_alerts": alerts.get("at_risk_employees", []),
    }
