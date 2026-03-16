"""
BusinessIntelAgent API — Phase 12
经营智能体：营收异常 / KPI健康度 / 订单预测 / Top3决策 / 场景识别
前缀: /api/v1/business-intel
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.models.business_intel import BizDecision, BizMetricSnapshot, KpiScorecard, OrderForecast, RevenueAlert, ScenarioRecord

router = APIRouter(prefix="/api/v1/business-intel")

# ─── 懒加载 Agent（避免启动时 DB 依赖）───────────────────────────────────────


def _agents():
    from packages.agents.business_intel.src.agent import (
        BizInsightAgent,
        KpiScorecardAgent,
        OrderForecastAgent,
        RevenueAnomalyAgent,
        ScenarioMatchAgent,
    )

    return (
        RevenueAnomalyAgent(),
        KpiScorecardAgent(),
        OrderForecastAgent(),
        BizInsightAgent(),
        ScenarioMatchAgent(),
    )


# ─── Pydantic Schemas ─────────────────────────────────────────────────────────


class SnapshotIn(BaseModel):
    brand_id: str
    store_id: str
    snapshot_date: date
    revenue_yuan: float
    expected_revenue_yuan: Optional[float] = None
    order_count: int = 0
    food_cost_yuan: Optional[float] = None
    food_cost_ratio: Optional[float] = None
    labor_cost_yuan: Optional[float] = None
    labor_cost_ratio: Optional[float] = None
    gross_profit_yuan: Optional[float] = None
    gross_profit_ratio: Optional[float] = None
    customer_count: Optional[int] = None
    complaint_count: Optional[int] = 0
    staff_count: Optional[int] = None
    table_turnover_rate: Optional[float] = None


class AnomalyDetectIn(BaseModel):
    brand_id: str
    store_id: str
    check_date: date = Field(default_factory=date.today)
    actual_yuan: float
    expected_yuan: float


class KpiSnapshotIn(BaseModel):
    brand_id: str
    store_id: str
    period: str = Field(..., example="2026-03")
    kpi_values: dict = Field(default_factory=dict)


class ForecastIn(BaseModel):
    brand_id: str
    store_id: str
    horizon_days: int = Field(default=7, ge=1, le=30)


class InsightIn(BaseModel):
    brand_id: str
    store_id: str
    context: Optional[dict] = None


class ScenarioIn(BaseModel):
    brand_id: str
    store_id: str
    metrics: Optional[dict] = None


class AlertResolveIn(BaseModel):
    resolution_note: Optional[str] = None


class DecisionAcceptIn(BaseModel):
    accepted_rank: int = Field(..., ge=1, le=3)
    note: Optional[str] = None


# ─── 1. 指标快照 ──────────────────────────────────────────────────────────────


@router.post("/snapshots", summary="录入门店日粒度指标快照")
async def create_snapshot(body: SnapshotIn, db: AsyncSession = Depends(get_db)):
    """录入/更新门店日粒度指标快照（L1主数据）"""
    # 计算偏差%
    deviation_pct = None
    if body.expected_revenue_yuan and body.expected_revenue_yuan > 0:
        deviation_pct = round((body.revenue_yuan - body.expected_revenue_yuan) / body.expected_revenue_yuan * 100, 2)

    snap = BizMetricSnapshot(
        brand_id=body.brand_id,
        store_id=body.store_id,
        snapshot_date=body.snapshot_date,
        revenue_yuan=Decimal(str(body.revenue_yuan)),
        expected_revenue_yuan=Decimal(str(body.expected_revenue_yuan)) if body.expected_revenue_yuan else None,
        revenue_deviation_pct=deviation_pct,
        order_count=body.order_count,
        food_cost_yuan=Decimal(str(body.food_cost_yuan)) if body.food_cost_yuan else None,
        food_cost_ratio=body.food_cost_ratio,
        labor_cost_yuan=Decimal(str(body.labor_cost_yuan)) if body.labor_cost_yuan else None,
        labor_cost_ratio=body.labor_cost_ratio,
        gross_profit_yuan=Decimal(str(body.gross_profit_yuan)) if body.gross_profit_yuan else None,
        gross_profit_ratio=body.gross_profit_ratio,
        customer_count=body.customer_count,
        complaint_count=body.complaint_count,
        staff_count=body.staff_count,
        table_turnover_rate=body.table_turnover_rate,
    )
    db.add(snap)
    await db.commit()
    await db.refresh(snap)
    return {
        "id": snap.id,
        "snapshot_date": str(snap.snapshot_date),
        "revenue_yuan": float(snap.revenue_yuan),
        "deviation_pct": deviation_pct,
    }


@router.get("/snapshots", summary="查询指标快照列表")
async def list_snapshots(
    brand_id: str,
    store_id: str,
    days: int = Query(default=30, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
):
    from datetime import timedelta

    cutoff = date.today() - timedelta(days=days)
    result = await db.execute(
        select(BizMetricSnapshot)
        .where(
            and_(
                BizMetricSnapshot.brand_id == brand_id,
                BizMetricSnapshot.store_id == store_id,
                BizMetricSnapshot.snapshot_date >= cutoff,
            )
        )
        .order_by(desc(BizMetricSnapshot.snapshot_date))
    )
    snaps = result.scalars().all()
    return {
        "count": len(snaps),
        "snapshots": [
            {
                "id": s.id,
                "date": str(s.snapshot_date),
                "revenue_yuan": float(s.revenue_yuan),
                "order_count": s.order_count,
                "food_cost_ratio": s.food_cost_ratio,
                "labor_cost_ratio": s.labor_cost_ratio,
            }
            for s in snaps
        ],
    }


# ─── 2. 营收异常检测 ──────────────────────────────────────────────────────────


@router.post("/agents/detect-anomaly", summary="营收异常检测 Agent")
async def detect_anomaly(body: AnomalyDetectIn, db: AsyncSession = Depends(get_db)):
    """
    RevenueAnomalyAgent — 营收异常检测
    OKR: 每日营收异常识别率 >95%
    """
    revenue_agent, *_ = _agents()
    return await revenue_agent.detect(
        brand_id=body.brand_id,
        store_id=body.store_id,
        check_date=body.check_date,
        actual_yuan=body.actual_yuan,
        expected_yuan=body.expected_yuan,
        db=db,
    )


@router.get("/alerts", summary="获取未处理营收预警列表")
async def list_alerts(
    brand_id: str,
    store_id: Optional[str] = None,
    include_resolved: bool = False,
    limit: int = Query(default=20, le=100),
    db: AsyncSession = Depends(get_db),
):
    conditions = [RevenueAlert.brand_id == brand_id]
    if store_id:
        conditions.append(RevenueAlert.store_id == store_id)
    if not include_resolved:
        conditions.append(RevenueAlert.is_resolved == False)

    result = await db.execute(
        select(RevenueAlert).where(and_(*conditions)).order_by(desc(RevenueAlert.created_at)).limit(limit)
    )
    alerts = result.scalars().all()
    return {
        "count": len(alerts),
        "alerts": [
            {
                "id": a.id,
                "store_id": a.store_id,
                "alert_date": str(a.alert_date),
                "anomaly_level": a.anomaly_level,
                "deviation_pct": a.deviation_pct,
                "impact_yuan": float(a.impact_yuan),
                "recommended_action": a.recommended_action,
                "is_resolved": a.is_resolved,
            }
            for a in alerts
        ],
    }


@router.patch("/alerts/{alert_id}/resolve", summary="标记预警为已处理")
async def resolve_alert(
    alert_id: str,
    body: AlertResolveIn,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(RevenueAlert).where(RevenueAlert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="alert not found")
    alert.is_resolved = True
    alert.resolved_at = datetime.utcnow()
    await db.commit()
    return {"id": alert_id, "resolved": True}


# ─── 3. KPI 健康度快照 ────────────────────────────────────────────────────────


@router.post("/agents/kpi-scorecard", summary="KPI健康度评分卡 Agent")
async def kpi_scorecard(body: KpiSnapshotIn, db: AsyncSession = Depends(get_db)):
    """
    KpiScorecardAgent — KPI健康度快照
    输出: overall_health_score(0-100) + improvement_priorities
    """
    _, kpi_agent, *_ = _agents()
    return await kpi_agent.snapshot(
        brand_id=body.brand_id,
        store_id=body.store_id,
        period=body.period,
        db=db,
        kpi_values=body.kpi_values,
    )


@router.get("/scorecards", summary="查询历史KPI评分卡")
async def list_scorecards(
    brand_id: str,
    store_id: str,
    limit: int = Query(default=12, le=36),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(KpiScorecard)
        .where(and_(KpiScorecard.brand_id == brand_id, KpiScorecard.store_id == store_id))
        .order_by(desc(KpiScorecard.period))
        .limit(limit)
    )
    cards = result.scalars().all()
    return {
        "count": len(cards),
        "scorecards": [
            {
                "id": c.id,
                "period": c.period,
                "overall_health_score": c.overall_health_score,
                "at_risk_count": c.at_risk_count,
                "off_track_count": c.off_track_count,
            }
            for c in cards
        ],
    }


# ─── 4. 订单量/营收预测 ───────────────────────────────────────────────────────


@router.post("/agents/order-forecast", summary="订单量/营收预测 Agent")
async def order_forecast(body: ForecastIn, db: AsyncSession = Depends(get_db)):
    """
    OrderForecastAgent — 基于历史快照预测未来N天
    OKR: 预测准确度 ±5%以内
    """
    _, _, forecast_agent, *_ = _agents()
    return await forecast_agent.forecast(
        brand_id=body.brand_id,
        store_id=body.store_id,
        horizon_days=body.horizon_days,
        db=db,
    )


@router.get("/forecasts", summary="查询历史预测记录")
async def list_forecasts(
    brand_id: str,
    store_id: str,
    limit: int = Query(default=10, le=30),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(OrderForecast)
        .where(and_(OrderForecast.brand_id == brand_id, OrderForecast.store_id == store_id))
        .order_by(desc(OrderForecast.forecast_date))
        .limit(limit)
    )
    forecasts = result.scalars().all()
    return {
        "count": len(forecasts),
        "forecasts": [
            {
                "id": f.id,
                "forecast_date": str(f.forecast_date),
                "horizon_days": f.horizon_days,
                "predicted_orders": f.predicted_orders,
                "predicted_revenue_yuan": float(f.predicted_revenue_yuan),
                "confidence": f.confidence,
            }
            for f in forecasts
        ],
    }


# ─── 5. 综合经营洞察（Top3决策）─────────────────────────────────────────────


@router.post("/agents/biz-insight", summary="综合经营洞察 Agent（Top3决策）")
async def biz_insight(body: InsightIn, db: AsyncSession = Depends(get_db)):
    """
    BizInsightAgent — 整合三维数据，生成优先级排序的Top3行动建议
    OKR: 决策建议采纳率 >70%
    """
    _, _, _, insight_agent, _ = _agents()
    return await insight_agent.generate(
        brand_id=body.brand_id,
        store_id=body.store_id,
        db=db,
        context=body.context,
    )


@router.get("/decisions", summary="查询历史经营决策")
async def list_decisions(
    brand_id: str,
    store_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(default=20, le=50),
    db: AsyncSession = Depends(get_db),
):
    conditions = [BizDecision.brand_id == brand_id]
    if store_id:
        conditions.append(BizDecision.store_id == store_id)
    if status:
        conditions.append(BizDecision.status == status)

    result = await db.execute(
        select(BizDecision).where(and_(*conditions)).order_by(desc(BizDecision.decision_date)).limit(limit)
    )
    decisions = result.scalars().all()
    return {
        "count": len(decisions),
        "decisions": [
            {
                "id": d.id,
                "store_id": d.store_id,
                "decision_date": str(d.decision_date),
                "total_saving_yuan": float(d.total_saving_yuan),
                "priority": d.priority,
                "status": d.status,
                "top_recommendation": d.recommendations[0] if d.recommendations else None,
            }
            for d in decisions
        ],
    }


@router.patch("/decisions/{decision_id}/accept", summary="店长采纳决策建议")
async def accept_decision(
    decision_id: str,
    body: DecisionAcceptIn,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(BizDecision).where(BizDecision.id == decision_id))
    decision = result.scalar_one_or_none()
    if not decision:
        raise HTTPException(status_code=404, detail="decision not found")
    decision.status = "accepted"
    decision.accepted_rank = body.accepted_rank
    decision.accepted_at = datetime.utcnow()
    await db.commit()
    return {"id": decision_id, "status": "accepted", "accepted_rank": body.accepted_rank}


@router.get("/decisions/today", summary="今日Top3经营建议（驾驶舱快捷入口）")
async def today_decisions(
    brand_id: str,
    store_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BizDecision)
        .where(
            and_(
                BizDecision.brand_id == brand_id,
                BizDecision.store_id == store_id,
                BizDecision.decision_date == date.today(),
            )
        )
        .order_by(desc(BizDecision.created_at))
        .limit(1)
    )
    decision = result.scalar_one_or_none()
    if not decision:
        return {"has_decision": False, "message": "今日暂无经营建议，请调用 /agents/biz-insight 生成"}
    return {
        "has_decision": True,
        "decision_id": decision.id,
        "total_saving_yuan": float(decision.total_saving_yuan),
        "priority": decision.priority,
        "status": decision.status,
        "top3": decision.recommendations,
        "ai_insight": None,
    }


# ─── 6. 场景识别 ──────────────────────────────────────────────────────────────


@router.post("/agents/scenario-match", summary="经营场景识别 Agent")
async def scenario_match(body: ScenarioIn, db: AsyncSession = Depends(get_db)):
    """
    ScenarioMatchAgent — 识别当前经营场景，匹配历史案例，输出作战手册
    """
    _, _, _, _, scenario_agent = _agents()
    return await scenario_agent.match(
        brand_id=body.brand_id,
        store_id=body.store_id,
        db=db,
        metrics=body.metrics,
    )


@router.get("/scenarios", summary="查询历史场景记录")
async def list_scenarios(
    brand_id: str,
    store_id: str,
    limit: int = Query(default=10, le=30),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ScenarioRecord)
        .where(and_(ScenarioRecord.brand_id == brand_id, ScenarioRecord.store_id == store_id))
        .order_by(desc(ScenarioRecord.record_date))
        .limit(limit)
    )
    records = result.scalars().all()
    return {
        "count": len(records),
        "scenarios": [
            {"id": r.id, "record_date": str(r.record_date), "scenario_type": r.scenario_type, "confidence": r.confidence}
            for r in records
        ],
    }


# ─── 7. 驾驶舱（BFF汇总）────────────────────────────────────────────────────


@router.get("/dashboard", summary="经营智能体驾驶舱（首屏BFF）")
async def dashboard(
    brand_id: str,
    store_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    首屏一次性加载：今日决策 + 未处理预警 + 最新KPI + 最新预测
    """
    from datetime import timedelta

    # 今日决策
    decision_result = await db.execute(
        select(BizDecision)
        .where(
            and_(BizDecision.brand_id == brand_id, BizDecision.store_id == store_id, BizDecision.decision_date == date.today())
        )
        .order_by(desc(BizDecision.created_at))
        .limit(1)
    )
    decision = decision_result.scalar_one_or_none()

    # 未处理预警数
    alert_count_result = await db.execute(
        select(RevenueAlert).where(
            and_(RevenueAlert.brand_id == brand_id, RevenueAlert.store_id == store_id, RevenueAlert.is_resolved == False)
        )
    )
    open_alerts = alert_count_result.scalars().all()

    # 最新KPI评分卡
    kpi_result = await db.execute(
        select(KpiScorecard)
        .where(and_(KpiScorecard.brand_id == brand_id, KpiScorecard.store_id == store_id))
        .order_by(desc(KpiScorecard.period))
        .limit(1)
    )
    kpi = kpi_result.scalar_one_or_none()

    # 最新预测
    forecast_result = await db.execute(
        select(OrderForecast)
        .where(and_(OrderForecast.brand_id == brand_id, OrderForecast.store_id == store_id))
        .order_by(desc(OrderForecast.forecast_date))
        .limit(1)
    )
    forecast = forecast_result.scalar_one_or_none()

    return {
        "brand_id": brand_id,
        "store_id": store_id,
        "today": str(date.today()),
        "today_decision": {
            "id": decision.id if decision else None,
            "total_saving_yuan": float(decision.total_saving_yuan) if decision else 0,
            "priority": decision.priority if decision else None,
            "top3": decision.recommendations[:3] if decision else [],
        },
        "open_alerts": {
            "count": len(open_alerts),
            "critical_count": sum(1 for a in open_alerts if a.anomaly_level in ("critical", "severe")),
            "top_alert": (
                {
                    "level": open_alerts[0].anomaly_level,
                    "impact_yuan": float(open_alerts[0].impact_yuan),
                    "action": open_alerts[0].recommended_action,
                }
                if open_alerts
                else None
            ),
        },
        "kpi_health": {
            "overall_score": kpi.overall_health_score if kpi else None,
            "at_risk_count": kpi.at_risk_count if kpi else 0,
            "period": kpi.period if kpi else None,
        },
        "forecast_7d": {
            "predicted_revenue_yuan": float(forecast.predicted_revenue_yuan) if forecast else None,
            "trend_direction": (
                "up"
                if (forecast and (forecast.trend_slope or 0) > 50)
                else ("down" if (forecast and (forecast.trend_slope or 0) < -50) else "stable")
            ),
            "confidence": forecast.confidence if forecast else None,
        },
    }
