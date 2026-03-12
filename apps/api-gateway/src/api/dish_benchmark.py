"""跨店菜品对标引擎 — REST 端点

Phase 6 Month 4
Prefix: /api/v1/dish-benchmark
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from src.core.database import get_db
from src.services.dish_benchmark_service import (
    compute_dish_benchmarks,
    get_dish_benchmark,
    get_store_benchmark_summary,
    get_laggard_dishes,
    get_benchmark_trend,
    get_dish_cross_store_detail,
    TIERS,
)

router = APIRouter(prefix="/api/v1/dish-benchmark", tags=["dish_benchmark"])


# ---------------------------------------------------------------------------
# 计算触发
# ---------------------------------------------------------------------------

@router.post("/compute")
async def compute(
    period: str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """
    跨全链对标计算（全量）。
    读取所有门店当期 dish_profitability_records，按菜品名聚合，幂等写入。
    """
    return await compute_dish_benchmarks(db, period)


# ---------------------------------------------------------------------------
# 单店查询
# ---------------------------------------------------------------------------

@router.get("/store/{store_id}")
async def store_benchmark(
    store_id: str,
    period:   str          = Query(..., description="YYYY-MM"),
    fcr_tier: Optional[str] = Query(None, description="top/above_avg/below_avg/laggard"),
    limit:    int          = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """查询某门店对标列表，可按 fcr_tier 过滤，按¥潜力降序。"""
    if fcr_tier and fcr_tier not in TIERS:
        raise HTTPException(status_code=400,
                            detail=f"fcr_tier 必须是 {TIERS} 之一")
    records = await get_dish_benchmark(db, store_id, period, fcr_tier=fcr_tier,
                                       limit=limit)
    return {'store_id': store_id, 'period': period,
            'count': len(records), 'records': records}


@router.get("/store/{store_id}/summary")
async def store_summary(
    store_id: str,
    period:   str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """某门店各档位对标统计及总¥潜力。"""
    return await get_store_benchmark_summary(db, store_id, period)


@router.get("/store/{store_id}/laggards")
async def laggard_dishes(
    store_id: str,
    period:   str = Query(..., description="YYYY-MM"),
    limit:    int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """返回 fcr_tier=laggard 的菜品，按¥潜力降序——改进优先级最高。"""
    dishes = await get_laggard_dishes(db, store_id, period, limit=limit)
    return {'store_id': store_id, 'period': period,
            'count': len(dishes), 'dishes': dishes}


@router.get("/store/{store_id}/trend")
async def benchmark_trend(
    store_id: str,
    period:   str = Query(..., description="基准期 YYYY-MM"),
    periods:  int = Query(6, ge=2, le=12),
    db: AsyncSession = Depends(get_db),
):
    """近 N 期对标趋势：laggard 菜品数、平均 FCR/GPM gap、¥潜力变化。"""
    trend = await get_benchmark_trend(db, store_id, period, periods=periods)
    return {'store_id': store_id, 'periods': periods, 'trend': trend}


# ---------------------------------------------------------------------------
# 跨店横向视图
# ---------------------------------------------------------------------------

@router.get("/dish/{dish_name}")
async def dish_cross_store(
    dish_name: str,
    period:    str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """
    查询某道菜在所有门店的对标详情（横向对比），按 fcr_rank 升序。
    用于推广最佳实践：定位谁的成本控制最好。
    """
    detail = await get_dish_cross_store_detail(db, dish_name, period)
    return {'dish_name': dish_name, 'period': period,
            'store_count': len(detail), 'stores': detail}


# ---------------------------------------------------------------------------
# 元数据
# ---------------------------------------------------------------------------

@router.get("/meta/tiers")
async def meta_tiers():
    return {
        'tiers': TIERS,
        'tier_rules': {
            'top':        'percentile ≥ 75%',
            'above_avg':  '50% ≤ percentile < 75%',
            'below_avg':  '25% ≤ percentile < 50%',
            'laggard':    'percentile < 25%',
        },
        'note': 'FCR lower is better (食材成本率低=好), GPM higher is better (毛利率高=好)',
    }
