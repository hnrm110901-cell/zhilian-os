"""多店财务对标排名引擎 — REST 端点

Phase 5 Month 9
Prefix: /api/v1/fin-ranking
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.services.performance_ranking_service import (
    BENCHMARK_TYPES,
    METRIC_LABELS,
    METRICS,
    compute_period_rankings,
    get_benchmark_gaps,
    get_brand_ranking_summary,
    get_leaderboard,
    get_ranking_trend,
    get_store_ranking,
)

router = APIRouter(prefix="/api/v1/fin-ranking", tags=["performance_ranking"])


# ---------------------------------------------------------------------------
# 计算触发
# ---------------------------------------------------------------------------


@router.post("/compute")
async def compute_rankings(
    period: str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """触发指定期全量排名计算（所有门店 × 4 指标）。结果写入 store_performance_rankings + store_benchmark_gaps。"""
    result = await compute_period_rankings(db, period)
    return result


# ---------------------------------------------------------------------------
# 门店维度查询
# ---------------------------------------------------------------------------


@router.get("/store/{store_id}")
async def store_ranking(
    store_id: str,
    period: str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """获取门店当期全量排名快照（4 指标）。"""
    data = await get_store_ranking(db, store_id, period)
    if data is None:
        raise HTTPException(status_code=404, detail=f"门店 {store_id} 在 {period} 暂无排名数据，请先触发计算")
    return data


@router.get("/store/{store_id}/gaps")
async def store_gaps(
    store_id: str,
    period: str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """获取门店当期对标差距（12 条：4指标 × 3基准）。"""
    gaps = await get_benchmark_gaps(db, store_id, period)
    return {"store_id": store_id, "period": period, "count": len(gaps), "gaps": gaps}


@router.get("/store/{store_id}/trend")
async def store_trend(
    store_id: str,
    metric: str = Query(..., description="revenue/food_cost_rate/profit_margin/health_score"),
    periods: int = Query(6, ge=2, le=12),
    db: AsyncSession = Depends(get_db),
):
    """获取门店指定指标近 N 期排名趋势。"""
    if metric not in METRICS:
        raise HTTPException(status_code=400, detail=f"metric 必须是 {METRICS} 之一")
    trend = await get_ranking_trend(db, store_id, metric, periods=periods)
    return {"store_id": store_id, "metric": metric, "trend": trend}


# ---------------------------------------------------------------------------
# 排行榜
# ---------------------------------------------------------------------------


@router.get("/leaderboard")
async def leaderboard(
    period: str = Query(..., description="YYYY-MM"),
    metric: str = Query("health_score"),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """获取指标排行榜（前 N 名）。"""
    if metric not in METRICS:
        raise HTTPException(status_code=400, detail=f"metric 必须是 {METRICS} 之一")
    board = await get_leaderboard(db, period, metric, limit=limit)
    return {
        "period": period,
        "metric": metric,
        "label": METRIC_LABELS.get(metric, metric),
        "count": len(board),
        "board": board,
    }


# ---------------------------------------------------------------------------
# 品牌维度
# ---------------------------------------------------------------------------


@router.get("/brand-summary")
async def brand_summary(
    brand_id: str = Query(...),
    period: str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """品牌级排名汇总：层级分布 + 每指标最优/最差门店。"""
    return await get_brand_ranking_summary(db, brand_id, period)


# ---------------------------------------------------------------------------
# 元数据
# ---------------------------------------------------------------------------


@router.get("/meta")
async def meta():
    """返回支持的指标与基准类型。"""
    return {
        "metrics": list(METRICS),
        "metric_labels": METRIC_LABELS,
        "benchmark_types": list(BENCHMARK_TYPES),
        "tiers": ["top", "above_avg", "below_avg", "laggard"],
        "rank_changes": ["improved", "declined", "stable", "new"],
    }
