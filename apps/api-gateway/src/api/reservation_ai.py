"""
预订AI助手 API — Phase P4 (屯象独有)
智能跟进 · 意向预测 · 退订分析 · AI报表
"""

from datetime import date
from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.user import User
from ..services.cancellation_analyzer import cancellation_analyzer
from ..services.follow_up_copilot import follow_up_copilot
from ..services.intent_predictor import intent_predictor

logger = structlog.get_logger()
router = APIRouter()


# ── Request Models ──


class FollowUpRequest(BaseModel):
    store_id: str
    customer_name: str
    customer_phone: str
    current_stage: str
    event_type: str = "wedding"
    target_date: Optional[str] = None
    table_count: Optional[int] = None
    estimated_value_yuan: float = 0
    last_follow_up_days: int = 0
    lost_reason: Optional[str] = None
    competitor_name: Optional[str] = None


class IntentPredictRequest(BaseModel):
    store_id: str
    customer_name: str
    current_stage: str
    event_type: str = "wedding"
    target_date: Optional[str] = None
    table_count: Optional[int] = None
    estimated_value_yuan: float = 0
    follow_up_count: int = 0
    days_since_first_contact: int = 0
    competitor_mentioned: bool = False


class BatchPredictRequest(BaseModel):
    store_id: str
    leads: List[IntentPredictRequest]


# ── 智能跟进 Routes ──


@router.post("/reservation-ai/follow-up")
async def generate_follow_up(
    req: FollowUpRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """AI生成个性化跟进话术"""
    return await follow_up_copilot.generate_follow_up(session=session, **req.model_dump())


# ── 意向预测 Routes ──


@router.post("/reservation-ai/intent-predict")
async def predict_intent(
    req: IntentPredictRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """预测客户成交概率"""
    return await intent_predictor.predict_intent(session=session, **req.model_dump())


@router.post("/reservation-ai/rank-leads")
async def rank_leads(
    req: BatchPredictRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """批量预测并按优先级排序"""
    leads = [lead.model_dump() for lead in req.leads]
    return await intent_predictor.rank_leads(session, req.store_id, leads)


# ── 退订分析 Routes ──


@router.get("/reservation-ai/cancellation-analysis")
async def get_cancellation_analysis(
    store_id: str = Query(...),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """退订/输单原因分析"""
    return await cancellation_analyzer.analyze_cancellations(session, store_id, start_date, end_date)


@router.get("/reservation-ai/cancellation-trend")
async def get_cancellation_trend(
    store_id: str = Query(...),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """最近7天退订趋势"""
    return await cancellation_analyzer.get_weekly_trend(session, store_id)


# ── AI 日报 Routes ──


@router.get("/reservation-ai/daily-report")
async def get_daily_report(
    store_id: str = Query(...),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """生成预订AI日报"""
    from ..services.banquet_sales_service import banquet_sales_service

    # 聚合多维度数据
    funnel_stats = await banquet_sales_service.get_funnel_stats(session, store_id)
    cancellation = await cancellation_analyzer.get_daily_summary(session, store_id)

    # 汇总日报
    stages = funnel_stats.get("stages", [])
    total_leads = sum(s.get("count", 0) for s in stages)
    total_value = sum(s.get("total_value_yuan", 0) for s in stages)
    signed_count = next((s["count"] for s in stages if s["stage"] == "signed"), 0)
    completed_count = next((s["count"] for s in stages if s["stage"] == "completed"), 0)

    return {
        "date": date.today().isoformat(),
        "store_id": store_id,
        "summary": {
            "total_active_leads": total_leads,
            "pipeline_value_yuan": total_value,
            "signed_today": signed_count,
            "completed_today": completed_count,
            "lost_today": cancellation.get("total_lost", 0),
            "lost_value_yuan": cancellation.get("total_lost_value_yuan", 0),
        },
        "funnel_snapshot": stages,
        "cancellation_snapshot": {
            "top_reasons": cancellation.get("categories", [])[:3],
            "insights": cancellation.get("insights", []),
        },
        "ai_message": _compose_daily_message(
            total_leads,
            total_value,
            signed_count,
            completed_count,
            cancellation.get("total_lost", 0),
        ),
    }


def _compose_daily_message(
    leads: int,
    value: float,
    signed: int,
    completed: int,
    lost: int,
) -> str:
    """生成企微推送消息"""
    return (
        f"📊 今日预订快报\n"
        f"活跃线索：{leads}条\n"
        f"管道总额：¥{value:,.0f}\n"
        f"今日签约：{signed}单\n"
        f"今日完成：{completed}单\n"
        f"今日输单：{lost}单\n"
        f"💡 重点跟进高意向客户，关注竞品动态"
    )
