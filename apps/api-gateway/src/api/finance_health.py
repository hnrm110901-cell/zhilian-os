"""
财务健康评分 API — Phase 5 Month 5

Router prefix: /api/v1/finance-health

Endpoints:
  POST /compute/{store_id}           — 触发评分计算（写入 DB）
  GET  /score/{store_id}             — 获取已计算的评分
  GET  /trend/{store_id}             — 历史健康评分趋势（多期）
  GET  /insights/{store_id}          — 获取文字洞察列表
  GET  /profit-trend/{store_id}      — 原始利润指标多期趋势
  GET  /dashboard/{store_id}         — BFF：一次请求返回全部数据
  GET  /brand-summary                — 多门店健康排行（CEO 视角）
"""
from __future__ import annotations

from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..services.finance_health_service import (
    GRADE_THRESHOLDS,
    MAX_SCORES,
    compute_health_score,
    get_brand_health_summary,
    get_finance_dashboard,
    get_finance_insights,
    get_health_score,
    get_health_trend,
    get_profit_trend,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/finance-health", tags=["finance_health"])


@router.post("/compute/{store_id}")
async def trigger_compute(
    store_id: str,
    period:   str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """触发健康评分计算（实时聚合所有维度数据，结果写入 DB）。"""
    result = await compute_health_score(db, store_id=store_id, period=period)
    return result


@router.get("/score/{store_id}")
async def get_score(
    store_id: str,
    period:   str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """获取已缓存的评分（未计算则 404；可先调用 /compute）。"""
    score = await get_health_score(db, store_id=store_id, period=period)
    if not score:
        raise HTTPException(
            status_code=404,
            detail=f"No health score for store={store_id} period={period}. Call POST /compute first.",
        )
    return score


@router.get("/trend/{store_id}")
async def get_trend(
    store_id: str,
    periods:  int = Query(6, ge=1, le=24, description="最多查询几个历史期间"),
    db: AsyncSession = Depends(get_db),
):
    """返回历史健康评分趋势（升序，最旧→最新，用于折线图）。"""
    trend = await get_health_trend(db, store_id=store_id, periods=periods)
    return {"store_id": store_id, "trend": trend}


@router.get("/insights/{store_id}")
async def list_insights(
    store_id: str,
    period:   str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    insights = await get_finance_insights(db, store_id=store_id, period=period)
    return {"store_id": store_id, "period": period, "insights": insights, "total": len(insights)}


@router.get("/profit-trend/{store_id}")
async def get_raw_profit_trend(
    store_id: str,
    periods:  int = Query(6, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
):
    """原始利润指标多期趋势（升序）。"""
    trend = await get_profit_trend(db, store_id=store_id, periods=periods)
    return {"store_id": store_id, "trend": trend}


@router.get("/dashboard/{store_id}")
async def get_dashboard(
    store_id: str,
    period:   str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """BFF：一次请求返回评分 + 洞察 + 利润趋势 + 健康评分趋势（子查询失败降级为空）。"""
    return await get_finance_dashboard(db, store_id=store_id, period=period)


@router.get("/brand-summary")
async def get_brand_summary(
    period:   str           = Query(..., description="YYYY-MM"),
    brand_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """多门店健康评分排行（CEO 视角）。"""
    return await get_brand_health_summary(db, brand_id=brand_id, period=period)


@router.get("/meta/grades")
async def list_grades():
    return {
        "thresholds": GRADE_THRESHOLDS,
        "max_scores":  MAX_SCORES,
        "dimensions":  list(MAX_SCORES.keys()),
    }
