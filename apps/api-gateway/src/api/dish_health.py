"""菜品综合健康评分引擎 — REST 端点

Phase 6 Month 8
Prefix: /api/v1/dish-health
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.services.dish_health_service import (
    compute_health_scores,
    get_health_scores,
    get_health_summary,
    get_action_priorities,
    get_dish_health_history,
    BENCHMARK_TIER_SCORES,
    ACTION_IMPACT_RATE,
    PHASE_GROWTH_BASE,
    PERIODS_SCORE_MAP,
)

router = APIRouter(prefix="/api/v1/dish-health", tags=["dish_health"])

_VALID_TIERS     = ['excellent', 'good', 'fair', 'poor']
_VALID_PRIORITIES = ['immediate', 'monitor', 'maintain', 'promote']


# ---------------------------------------------------------------------------
# 计算触发
# ---------------------------------------------------------------------------

@router.post("/compute/{store_id}")
async def compute(
    store_id: str,
    period:   str          = Query(..., description="数据期 YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """
    整合盈利/生命周期/对标/预测 4 路信号，为门店所有菜品计算综合健康评分。
    幂等，全量覆盖。
    """
    return await compute_health_scores(db, store_id, period)


# ---------------------------------------------------------------------------
# 查询
# ---------------------------------------------------------------------------

@router.get("/summary/{store_id}")
async def summary(
    store_id: str,
    period:   str = Query(..., description="数据期 YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """按 health_tier 聚合统计：菜品数、均分、¥改善估算。"""
    return await get_health_summary(db, store_id, period)


@router.get("/priorities/{store_id}")
async def priorities(
    store_id: str,
    period:   str = Query(..., description="数据期 YYYY-MM"),
    priority: str = Query('immediate', description="行动优先级"),
    limit:    int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """返回指定优先级的菜品行动清单，按¥改善空间降序。"""
    if priority not in _VALID_PRIORITIES:
        raise HTTPException(status_code=400,
                            detail=f"priority 必须是 {_VALID_PRIORITIES} 之一")
    items = await get_action_priorities(db, store_id, period,
                                         priority=priority, limit=limit)
    return {
        'store_id': store_id, 'period': period,
        'priority': priority, 'count': len(items), 'items': items,
    }


@router.get("/dish/{store_id}/{dish_id}")
async def dish_health_history(
    store_id: str,
    dish_id:  str,
    periods:  int = Query(6, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
):
    """某道菜近 N 期健康评分历史（追踪评分演进与维度变化）。"""
    history = await get_dish_health_history(db, store_id, dish_id, periods=periods)
    return {'store_id': store_id, 'dish_id': dish_id, 'history': history}


@router.get("/{store_id}")
async def list_scores(
    store_id:    str,
    period:      str          = Query(..., description="数据期 YYYY-MM"),
    health_tier: str | None   = Query(None),
    limit:       int          = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """查询门店某期的菜品健康评分列表，按综合分降序。"""
    if health_tier and health_tier not in _VALID_TIERS:
        raise HTTPException(status_code=400,
                            detail=f"health_tier 必须是 {_VALID_TIERS} 之一")
    recs = await get_health_scores(db, store_id, period,
                                    health_tier=health_tier, limit=limit)
    return {'store_id': store_id, 'period': period,
            'count': len(recs), 'scores': recs}


# ---------------------------------------------------------------------------
# 元数据
# ---------------------------------------------------------------------------

@router.get("/meta/scoring")
async def meta_scoring():
    return {
        'dimensions': {
            'profitability': {
                'max': 25, 'basis': 'GPM + FCR vs 门店同期均值 (各 12.5 分)',
            },
            'growth': {
                'max': 25,
                'basis': '生命周期阶段基础分 + 趋势均值修正 ±3',
                'phase_base': PHASE_GROWTH_BASE,
            },
            'benchmark': {
                'max': 25,
                'basis': '跨店 FCR 基准等级',
                'tier_scores': BENCHMARK_TIER_SCORES,
                'no_data': 12.5,
            },
            'forecast': {
                'max': 25,
                'basis': '历史数据期数（预测成熟度）',
                'periods_map': PERIODS_SCORE_MAP,
                'no_data': 10.0,
            },
        },
        'health_tiers': {
            'excellent': '≥80', 'good': '≥60', 'fair': '≥40', 'poor': '<40',
        },
        'action_priorities': {
            'immediate': '立即介入（poor，或 fair+衰退/退出期）',
            'monitor':   '密切观察（fair，非衰退期）',
            'maintain':  '保持现状（good）',
            'promote':   '重点推广（excellent）',
        },
        'impact_rates': ACTION_IMPACT_RATE,
    }
