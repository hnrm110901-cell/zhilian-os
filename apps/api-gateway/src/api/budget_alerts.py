"""
预算管理 + 财务预警 API — Phase 5 Month 4

Router prefixes:
  /api/v1/budget      — 预算计划管理（CRUD + FSM）
  /api/v1/fin-alerts  — 预警规则管理 + 事件流水
"""
from __future__ import annotations

from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..services.budget_service import (
    BUDGET_CATEGORIES,
    VALID_BUDGET_TRANSITIONS,
    compute_variance,
    create_or_update_budget_plan,
    get_budget_plan_detail,
    get_budget_plans,
    get_budget_variance,
    transition_budget_status,
)
from ..services.financial_alert_service import (
    SUPPORTED_METRICS,
    VALID_ALERT_TRANSITIONS,
    create_or_update_rule,
    evaluate_store_alerts,
    get_alert_events,
    get_rules,
    set_rule_enabled,
    transition_alert_status,
)

logger = structlog.get_logger()

# ── Budget router ──────────────────────────────────────────────────────────────

budget_router = APIRouter(prefix="/api/v1/budget", tags=["budget"])


class LineItemIn(BaseModel):
    category:     str
    sub_category: Optional[str] = None
    budget_yuan:  float         = 0.0


class BudgetPlanIn(BaseModel):
    store_id:             str
    period:               str             = Field(..., description="YYYY-MM")
    period_type:          str             = "monthly"
    brand_id:             Optional[str]  = None
    total_revenue_budget: float           = 0.0
    total_cost_budget:    float           = 0.0
    profit_budget:        float           = 0.0
    notes:                Optional[str]  = None
    line_items:           List[LineItemIn] = []


@budget_router.post("/plans")
async def create_budget_plan(
    payload: BudgetPlanIn,
    db: AsyncSession = Depends(get_db),
):
    """创建或更新预算计划（仅 draft 状态可更新）。"""
    result = await create_or_update_budget_plan(
        db=db,
        store_id=payload.store_id,
        period=payload.period,
        period_type=payload.period_type,
        brand_id=payload.brand_id,
        total_revenue_budget=payload.total_revenue_budget,
        total_cost_budget=payload.total_cost_budget,
        profit_budget=payload.profit_budget,
        notes=payload.notes,
        line_items=[li.model_dump() for li in payload.line_items],
    )
    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])
    return result


@budget_router.get("/plans")
async def list_budget_plans(
    store_id: str = Query(...),
    limit:    int = Query(20, ge=1, le=100),
    offset:   int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    plans = await get_budget_plans(db, store_id=store_id, limit=limit, offset=offset)
    return {"plans": plans, "total": len(plans)}


@budget_router.get("/plans/{plan_id}")
async def get_plan_detail(plan_id: str, db: AsyncSession = Depends(get_db)):
    plan = await get_budget_plan_detail(db, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


@budget_router.get("/plans/{plan_id}/variance")
async def get_plan_variance(plan_id: str, db: AsyncSession = Depends(get_db)):
    """预算 vs 实际偏差分析（对接 profit_attribution_results）。"""
    result = await get_budget_variance(db, plan_id)
    if not result:
        raise HTTPException(status_code=404, detail="Plan not found")
    return result


@budget_router.post("/plans/{plan_id}/approve")
async def approve_plan(plan_id: str, db: AsyncSession = Depends(get_db)):
    result = await transition_budget_status(db, plan_id, "approved")
    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])
    return result


@budget_router.post("/plans/{plan_id}/activate")
async def activate_plan(plan_id: str, db: AsyncSession = Depends(get_db)):
    result = await transition_budget_status(db, plan_id, "active")
    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])
    return result


@budget_router.post("/plans/{plan_id}/close")
async def close_plan(plan_id: str, db: AsyncSession = Depends(get_db)):
    result = await transition_budget_status(db, plan_id, "closed")
    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])
    return result


@budget_router.get("/meta/categories")
async def list_categories():
    return {"categories": BUDGET_CATEGORIES}


@budget_router.get("/meta/transitions")
async def list_transitions():
    return {k: list(v) for k, v in VALID_BUDGET_TRANSITIONS.items()}


# ── Fin-alerts router ──────────────────────────────────────────────────────────

alerts_router = APIRouter(prefix="/api/v1/fin-alerts", tags=["fin_alerts"])


class RuleIn(BaseModel):
    store_id:         str
    metric:           str
    threshold_type:   str            = Field(..., description="above | below | abs_above")
    threshold_value:  float
    severity:         str            = "warning"
    cooldown_minutes: int            = 60
    brand_id:         Optional[str] = None


@alerts_router.get("/rules")
async def list_rules(
    store_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    rules = await get_rules(db, store_id=store_id)
    return {"rules": rules, "total": len(rules)}


@alerts_router.post("/rules")
async def create_rule(payload: RuleIn, db: AsyncSession = Depends(get_db)):
    result = await create_or_update_rule(
        db=db,
        store_id=payload.store_id,
        metric=payload.metric,
        threshold_type=payload.threshold_type,
        threshold_value=payload.threshold_value,
        severity=payload.severity,
        cooldown_minutes=payload.cooldown_minutes,
        brand_id=payload.brand_id,
    )
    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])
    return result


@alerts_router.put("/rules/{rule_id}")
async def update_rule(
    rule_id: str,
    payload: RuleIn,
    db: AsyncSession = Depends(get_db),
):
    result = await create_or_update_rule(
        db=db,
        store_id=payload.store_id,
        metric=payload.metric,
        threshold_type=payload.threshold_type,
        threshold_value=payload.threshold_value,
        severity=payload.severity,
        cooldown_minutes=payload.cooldown_minutes,
        brand_id=payload.brand_id,
        rule_id=rule_id,
    )
    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])
    return result


@alerts_router.delete("/rules/{rule_id}")
async def disable_rule(
    rule_id:  str,
    store_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """软删除：将规则设为 disabled（保留历史事件）。"""
    result = await set_rule_enabled(db, rule_id=rule_id, store_id=store_id, enabled=False)
    return result


@alerts_router.post("/evaluate")
async def evaluate_alerts(
    store_id: str = Query(...),
    period:   str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """触发门店预警评估，产生新的预警事件（含冷却期去重）。"""
    result = await evaluate_store_alerts(db, store_id=store_id, period=period)
    return result


@alerts_router.get("/events")
async def list_events(
    store_id: str           = Query(...),
    status:   Optional[str] = Query(None, description="open|acknowledged|resolved"),
    limit:    int           = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    events = await get_alert_events(db, store_id=store_id, status_filter=status, limit=limit)
    return {"events": events, "total": len(events)}


@alerts_router.post("/events/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str, db: AsyncSession = Depends(get_db)):
    result = await transition_alert_status(db, alert_id, "acknowledged")
    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])
    return result


@alerts_router.post("/events/{alert_id}/resolve")
async def resolve_alert(alert_id: str, db: AsyncSession = Depends(get_db)):
    result = await transition_alert_status(db, alert_id, "resolved")
    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])
    return result


@alerts_router.get("/meta/metrics")
async def list_supported_metrics():
    return {"metrics": SUPPORTED_METRICS}


@alerts_router.get("/meta/transitions")
async def list_alert_transitions():
    return {k: list(v) for k, v in VALID_ALERT_TRANSITIONS.items()}
