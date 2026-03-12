"""菜品生命周期管理引擎 — REST 端点

Phase 6 Month 6
Prefix: /api/v1/dish-lifecycle
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from src.core.database import get_db
from src.services.dish_lifecycle_service import (
    compute_lifecycle_analysis,
    get_lifecycle_records,
    get_lifecycle_summary,
    get_phase_transition_alerts,
    get_dish_lifecycle_history,
    PHASES,
    PHASE_ACTION,
)

router = APIRouter(prefix="/api/v1/dish-lifecycle", tags=["dish_lifecycle"])


# ---------------------------------------------------------------------------
# 计算触发
# ---------------------------------------------------------------------------

@router.post("/compute/{store_id}")
async def compute(
    store_id: str,
    period:   str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """
    为门店当期所有菜品执行生命周期分析。幂等。
    读取当期与上期 dish_profitability_records 做环比，结合上期生命周期记录判断阶段跃迁。
    """
    return await compute_lifecycle_analysis(db, store_id, period)


# ---------------------------------------------------------------------------
# 查询
# ---------------------------------------------------------------------------

@router.get("/{store_id}")
async def list_records(
    store_id: str,
    period:   str        = Query(..., description="YYYY-MM"),
    phase:    Optional[str] = Query(None, description="launch/growth/peak/decline/exit"),
    limit:    int        = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """查询门店当期生命周期记录，可按阶段过滤，按期望¥影响降序。"""
    if phase and phase not in PHASES:
        raise HTTPException(status_code=400, detail=f"phase 必须是 {PHASES} 之一")
    records = await get_lifecycle_records(db, store_id, period,
                                           phase=phase, limit=limit)
    return {'store_id': store_id, 'period': period,
            'count': len(records), 'records': records}


@router.get("/summary/{store_id}")
async def summary(
    store_id: str,
    period:   str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """按生命周期阶段聚合统计：菜品数、¥影响、平均阶段时长、跃迁数。"""
    return await get_lifecycle_summary(db, store_id, period)


@router.get("/transitions/{store_id}")
async def transition_alerts(
    store_id: str,
    period:   str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """
    返回本期发生阶段跃迁的菜品（phase_changed=true）。
    用于重点预警：衰退跃迁需立即处理，成长跃迁需把握机会。
    """
    alerts = await get_phase_transition_alerts(db, store_id, period)
    return {'store_id': store_id, 'period': period,
            'count': len(alerts), 'transitions': alerts}


@router.get("/dish/{store_id}/{dish_id}")
async def dish_history(
    store_id: str,
    dish_id:  str,
    periods:  int = Query(12, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
):
    """某道菜近 N 期的生命周期演变历史（追踪阶段流转轨迹）。"""
    history = await get_dish_lifecycle_history(db, store_id, dish_id, periods=periods)
    return {'store_id': store_id, 'dish_id': dish_id, 'history': history}


# ---------------------------------------------------------------------------
# 元数据
# ---------------------------------------------------------------------------

@router.get("/meta/phases")
async def meta_phases():
    return {
        'phases': PHASES,
        'phase_definitions': {
            'launch':  '新品（首期或第2期，数据积累期）',
            'growth':  '成长期（需求快速增长≥10%）',
            'peak':    '成熟期（BCG=star/cash_cow且稳定）',
            'decline': '衰退期（营收/销量持续下滑）',
            'exit':    '退出期（营收销量均暴跌≥20%，建议下架）',
        },
        'phase_actions': {
            p: {'label': v['action_label'], 'action': v['recommended_action']}
            for p, v in PHASE_ACTION.items()
        },
        'transition_thresholds': {
            'growth_order_threshold':    10.0,
            'decline_revenue_threshold': -5.0,
            'exit_revenue_threshold':    -20.0,
            'exit_order_threshold':      -20.0,
        },
    }
