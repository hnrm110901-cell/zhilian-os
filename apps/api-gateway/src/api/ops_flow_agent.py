"""
OpsFlowAgent API — Phase 13
运营流程体：订单异常 / 库存预警 / 菜品质检 / 出品链联动 / 综合优化
前缀: /api/v1/ops-flow
"""
from __future__ import annotations

import time
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, and_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.models.ops_flow_agent import (
    OpsChainEvent, OpsChainLinkage,
    OpsOrderAnomaly, OpsInventoryAlert, OpsQualityRecord,
    OpsFlowDecision, OpsFlowAgentLog,
)

router = APIRouter(prefix="/api/v1/ops-flow")


# ── 懒加载 Agents ──────────────────────────────────────────────────────────────

def _agents():
    from packages.agents.ops_flow.src.agent import (
        ChainAlertAgent, OrderAnomalyAgent, InventoryIntelAgent,
        QualityInspectionAgent, OpsOptimizeAgent,
    )
    return (
        ChainAlertAgent(),
        OrderAnomalyAgent(),
        InventoryIntelAgent(),
        QualityInspectionAgent(),
        OpsOptimizeAgent(),
    )


# ── Pydantic Schemas ───────────────────────────────────────────────────────────

class OrderAnomalyIn(BaseModel):
    brand_id: str
    store_id: str
    metrics: Dict[str, float] = Field(..., example={
        "refund_rate": 0.08, "complaint_rate": 0.04,
        "revenue_yuan": 8000.0, "avg_order_yuan": 85.0,
    })
    baseline: Dict[str, float] = Field(..., example={
        "refund_rate": 0.02, "complaint_rate": 0.01,
        "revenue_yuan": 10000.0, "avg_order_yuan": 100.0,
    })
    daily_revenue_yuan: float = Field(default=10000.0, ge=0)
    time_period: str = Field(default="today")


class InventoryCheckIn(BaseModel):
    brand_id: str
    store_id: str
    dish_id: str
    dish_name: str
    current_qty: int = Field(..., ge=0)
    safety_qty: int = Field(..., ge=0)
    hourly_consumption: float = Field(..., ge=0)
    unit_price_yuan: float = Field(default=50.0, ge=0)


class InventoryBatchCheckIn(BaseModel):
    brand_id: str
    store_id: str
    items: List[Dict[str, Any]] = Field(..., min_length=1)


class QualityInspectIn(BaseModel):
    brand_id: str
    store_id: str
    dish_id: Optional[str] = None
    dish_name: str
    quality_score: float = Field(..., ge=0, le=100)
    issues: Optional[List[Dict[str, Any]]] = None
    image_url: Optional[str] = None


class ChainResolveIn(BaseModel):
    event_id: str


class DecisionAcceptIn(BaseModel):
    decision_id: str


# ── 1. 出品链联动事件 ──────────────────────────────────────────────────────────

@router.get("/stores/{store_id}/chain-events")
async def list_chain_events(
    store_id: str,
    severity: Optional[str] = Query(None, regex="^(info|warning|critical)$"),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """获取门店出品链联动事件列表"""
    chain_agent, *_ = _agents()
    events = await chain_agent.get_active_events(
        db=db, store_id=store_id, severity_filter=severity, limit=limit
    )
    return {"store_id": store_id, "events": events, "count": len(events)}


@router.post("/chain-events/resolve")
async def resolve_chain_event(
    payload: ChainResolveIn,
    db: AsyncSession = Depends(get_db),
):
    """标记出品链事件已解决"""
    chain_agent, *_ = _agents()
    result = await chain_agent.resolve_event(db=db, event_id=payload.event_id)
    await db.commit()
    return result


@router.get("/stores/{store_id}/chain-events/{event_id}/linkages")
async def get_event_linkages(
    store_id: str,
    event_id: str,
    db: AsyncSession = Depends(get_db),
):
    """获取某事件的联动触发明细"""
    result = await db.execute(
        select(OpsChainLinkage)
        .where(OpsChainLinkage.trigger_event_id == event_id)
        .order_by(OpsChainLinkage.executed_at)
    )
    linkages = result.scalars().all()
    return {
        "event_id": event_id,
        "linkages": [
            {
                "id": lk.id,
                "trigger_layer": lk.trigger_layer,
                "target_layer": lk.target_layer,
                "target_action": lk.target_action,
                "result_summary": lk.result_summary,
                "impact_yuan": float(lk.impact_yuan or 0),
                "executed_at": str(lk.executed_at),
            }
            for lk in linkages
        ],
    }


# ── 2. 订单异常 ────────────────────────────────────────────────────────────────

@router.post("/order-anomaly/detect")
async def detect_order_anomaly(
    payload: OrderAnomalyIn,
    db: AsyncSession = Depends(get_db),
):
    """检测订单异常，自动触发出品链联动"""
    _, order_agent, *_ = _agents()
    result = await order_agent.detect_anomaly(
        db=db,
        brand_id=payload.brand_id,
        store_id=payload.store_id,
        metrics=payload.metrics,
        baseline=payload.baseline,
        daily_revenue_yuan=payload.daily_revenue_yuan,
        time_period=payload.time_period,
    )
    await db.commit()
    return result


@router.get("/stores/{store_id}/order-anomalies")
async def list_order_anomalies(
    store_id: str,
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """获取门店订单异常历史"""
    _, order_agent, *_ = _agents()
    anomalies = await order_agent.list_anomalies(db=db, store_id=store_id, days=days, limit=limit)
    return {"store_id": store_id, "anomalies": anomalies, "count": len(anomalies)}


# ── 3. 库存预警 ────────────────────────────────────────────────────────────────

@router.post("/inventory/check")
async def check_inventory(
    payload: InventoryCheckIn,
    db: AsyncSession = Depends(get_db),
):
    """检查单品库存，不足时触发出品链联动"""
    _, _, inv_agent, *_ = _agents()
    result = await inv_agent.check_stock(
        db=db,
        brand_id=payload.brand_id,
        store_id=payload.store_id,
        dish_id=payload.dish_id,
        dish_name=payload.dish_name,
        current_qty=payload.current_qty,
        safety_qty=payload.safety_qty,
        hourly_consumption=payload.hourly_consumption,
        unit_price_yuan=payload.unit_price_yuan,
    )
    await db.commit()
    return result


@router.post("/inventory/batch-check")
async def batch_check_inventory(
    payload: InventoryBatchCheckIn,
    db: AsyncSession = Depends(get_db),
):
    """批量检查多品库存状态"""
    _, _, inv_agent, *_ = _agents()
    result = await inv_agent.batch_check(
        db=db,
        brand_id=payload.brand_id,
        store_id=payload.store_id,
        items=payload.items,
    )
    await db.commit()
    return result


@router.get("/stores/{store_id}/inventory-alerts")
async def list_inventory_alerts(
    store_id: str,
    unresolved_only: bool = Query(True),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """获取门店库存预警列表"""
    _, _, inv_agent, *_ = _agents()
    alerts = await inv_agent.list_alerts(db=db, store_id=store_id,
                                          unresolved_only=unresolved_only, limit=limit)
    return {"store_id": store_id, "alerts": alerts, "count": len(alerts)}


@router.patch("/inventory-alerts/{alert_id}/resolve")
async def resolve_inventory_alert(
    alert_id: str,
    db: AsyncSession = Depends(get_db),
):
    """标记库存预警已处理"""
    result = await db.execute(
        select(OpsInventoryAlert).where(OpsInventoryAlert.id == alert_id)
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail=f"预警 {alert_id} 不存在")
    alert.resolved = True
    alert.resolved_at = datetime.now()
    await db.commit()
    return {"success": True, "alert_id": alert_id, "resolved_at": str(alert.resolved_at)}


# ── 4. 菜品质检 ────────────────────────────────────────────────────────────────

@router.post("/quality/inspect")
async def inspect_quality(
    payload: QualityInspectIn,
    db: AsyncSession = Depends(get_db),
):
    """记录质检结果，失败时触发出品链联动"""
    _, _, _, quality_agent, _ = _agents()
    result = await quality_agent.inspect(
        db=db,
        brand_id=payload.brand_id,
        store_id=payload.store_id,
        dish_id=payload.dish_id,
        dish_name=payload.dish_name,
        quality_score=payload.quality_score,
        issues=payload.issues,
        image_url=payload.image_url,
    )
    await db.commit()
    return result


@router.get("/stores/{store_id}/quality-summary")
async def get_quality_summary(
    store_id: str,
    days: int = Query(7, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
):
    """获取门店质检汇总"""
    _, _, _, quality_agent, _ = _agents()
    return await quality_agent.get_store_quality_summary(db=db, store_id=store_id, days=days)


@router.get("/stores/{store_id}/quality-records")
async def list_quality_records(
    store_id: str,
    status: Optional[str] = Query(None, regex="^(pass|warning|fail)$"),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """获取门店质检记录列表"""
    _, _, _, quality_agent, _ = _agents()
    records = await quality_agent.list_records(
        db=db, store_id=store_id, status_filter=status, limit=limit
    )
    return {"store_id": store_id, "records": records, "count": len(records)}


# ── 5. 综合优化决策 ────────────────────────────────────────────────────────────

@router.post("/stores/{store_id}/optimize")
async def generate_optimize_decision(
    store_id: str,
    brand_id: str = Query(...),
    lookback_hours: int = Query(24, ge=1, le=168),
    db: AsyncSession = Depends(get_db),
):
    """基于近期三层数据生成综合优化决策"""
    _, _, _, _, ops_agent = _agents()
    result = await ops_agent.generate_decision(
        db=db, brand_id=brand_id, store_id=store_id,
        lookback_hours=lookback_hours,
    )
    await db.commit()
    return result


@router.post("/decisions/accept")
async def accept_decision(
    payload: DecisionAcceptIn,
    db: AsyncSession = Depends(get_db),
):
    """接受优化决策"""
    _, _, _, _, ops_agent = _agents()
    result = await ops_agent.accept_decision(db=db, decision_id=payload.decision_id)
    await db.commit()
    return result


@router.get("/stores/{store_id}/decisions")
async def list_decisions(
    store_id: str,
    status: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """获取门店优化决策列表"""
    _, _, _, _, ops_agent = _agents()
    decisions = await ops_agent.list_decisions(
        db=db, store_id=store_id, status_filter=status, limit=limit
    )
    return {"store_id": store_id, "decisions": decisions, "count": len(decisions)}


# ── 6. 驾驶舱 BFF ──────────────────────────────────────────────────────────────

@router.get("/stores/{store_id}/dashboard")
async def ops_flow_dashboard(
    store_id: str,
    db: AsyncSession = Depends(get_db),
):
    """OpsFlowAgent 驾驶舱 — 出品链实时状态快览"""
    from datetime import timedelta
    now = datetime.now()
    since_24h = now - timedelta(hours=24)

    # 并行查询三层数据
    chain_result = await db.execute(
        select(func.count(), func.sum(OpsChainEvent.linkage_count))
        .where(and_(OpsChainEvent.store_id == store_id,
                    OpsChainEvent.created_at >= since_24h))
    )
    chain_stats = chain_result.one()

    order_result = await db.execute(
        select(func.count(), func.sum(OpsOrderAnomaly.estimated_revenue_loss_yuan))
        .where(and_(OpsOrderAnomaly.store_id == store_id,
                    OpsOrderAnomaly.created_at >= since_24h))
    )
    order_stats = order_result.one()

    inv_result = await db.execute(
        select(func.count())
        .where(and_(OpsInventoryAlert.store_id == store_id,
                    OpsInventoryAlert.resolved == False))
    )
    inv_unresolved = inv_result.scalar() or 0

    q_result = await db.execute(
        select(
            func.count(),
            func.avg(OpsQualityRecord.quality_score),
        )
        .where(and_(OpsQualityRecord.store_id == store_id,
                    OpsQualityRecord.created_at >= since_24h))
    )
    quality_stats = q_result.one()

    # 最新联动事件（top3）
    recent_events_result = await db.execute(
        select(OpsChainEvent)
        .where(OpsChainEvent.store_id == store_id)
        .order_by(desc(OpsChainEvent.created_at))
        .limit(3)
    )
    recent_events = [
        {
            "event_type": e.event_type,
            "severity": e.severity,
            "title": e.title,
            "linkage_count": e.linkage_count,
            "created_at": str(e.created_at),
        }
        for e in recent_events_result.scalars().all()
    ]

    # 最新优化决策
    latest_decision_result = await db.execute(
        select(OpsFlowDecision)
        .where(and_(OpsFlowDecision.store_id == store_id,
                    OpsFlowDecision.status == "pending"))
        .order_by(desc(OpsFlowDecision.created_at))
        .limit(1)
    )
    latest_decision = latest_decision_result.scalar_one_or_none()

    return {
        "store_id": store_id,
        "as_of": str(now),
        "chain_events_24h": {
            "total": chain_stats[0] or 0,
            "total_linkages": int(chain_stats[1] or 0),
        },
        "order_layer": {
            "anomaly_count_24h": order_stats[0] or 0,
            "total_loss_yuan": float(order_stats[1] or 0),
        },
        "inventory_layer": {
            "unresolved_alerts": inv_unresolved,
        },
        "quality_layer": {
            "inspections_24h": quality_stats[0] or 0,
            "avg_score": round(float(quality_stats[1] or 0), 1),
        },
        "recent_events": recent_events,
        "pending_decision": {
            "id": latest_decision.id if latest_decision else None,
            "title": latest_decision.decision_title if latest_decision else None,
            "priority": latest_decision.priority if latest_decision else None,
            "impact_yuan": float(latest_decision.estimated_revenue_impact_yuan or 0) if latest_decision else 0,
        },
    }
