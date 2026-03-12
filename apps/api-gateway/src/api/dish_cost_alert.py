"""菜品成本预警引擎 — REST 端点

Phase 6 Month 3
Prefix: /api/v1/dish-alert
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from src.core.database import get_db
from src.services.dish_cost_alert_service import (
    generate_dish_cost_alerts,
    get_dish_cost_alerts,
    get_alert_summary,
    resolve_alert,
    get_store_cost_trend,
    get_dish_alert_history,
    ALERT_TYPES,
    ALERT_LABELS,
    SEVERITIES,
)

router = APIRouter(prefix="/api/v1/dish-alert", tags=["dish_cost_alert"])


# ---------------------------------------------------------------------------
# 计算触发
# ---------------------------------------------------------------------------

@router.post("/detect/{store_id}")
async def detect(
    store_id: str,
    period: str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """
    比对当期与上期 dish_profitability_records，生成成本预警。幂等。
    """
    return await generate_dish_cost_alerts(db, store_id, period)


# ---------------------------------------------------------------------------
# 查询
# ---------------------------------------------------------------------------

@router.get("/{store_id}")
async def list_alerts(
    store_id: str,
    period:   str          = Query(..., description="YYYY-MM"),
    severity: Optional[str] = Query(None, description="critical/warning/info"),
    status:   Optional[str] = Query(None, description="open/resolved/suppressed"),
    limit:    int          = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """查询菜品成本预警列表，支持按严重度和状态过滤。"""
    if severity and severity not in SEVERITIES:
        raise HTTPException(status_code=400,
                            detail=f"severity 必须是 {SEVERITIES} 之一")
    if status and status not in ('open', 'resolved', 'suppressed'):
        raise HTTPException(status_code=400,
                            detail="status 必须是 open/resolved/suppressed")
    alerts = await get_dish_cost_alerts(db, store_id, period,
                                        severity=severity, status=status, limit=limit)
    return {
        'store_id': store_id, 'period': period,
        'count': len(alerts), 'alerts': alerts,
    }


@router.get("/summary/{store_id}")
async def summary(
    store_id: str,
    period:   str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """按告警类型和严重度聚合预警统计。"""
    return await get_alert_summary(db, store_id, period)


@router.get("/trend/{store_id}")
async def cost_trend(
    store_id: str,
    period:   str = Query(..., description="基准期 YYYY-MM"),
    periods:  int = Query(6, ge=2, le=12),
    db: AsyncSession = Depends(get_db),
):
    """门店近 N 期食材成本率/毛利率趋势。"""
    trend = await get_store_cost_trend(db, store_id, period, periods=periods)
    return {'store_id': store_id, 'periods': periods, 'trend': trend}


@router.get("/dish/{store_id}/{dish_id}")
async def dish_alert_history(
    store_id: str,
    dish_id:  str,
    periods:  int = Query(6, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
):
    """某道菜近 N 期的历史预警记录。"""
    history = await get_dish_alert_history(db, store_id, dish_id, periods=periods)
    return {'store_id': store_id, 'dish_id': dish_id, 'history': history}


# ---------------------------------------------------------------------------
# 状态变更
# ---------------------------------------------------------------------------

@router.post("/{alert_id}/resolve")
async def resolve(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
):
    """将告警标记为已解决。"""
    result = await resolve_alert(db, alert_id)
    if not result['updated']:
        raise HTTPException(status_code=404, detail=result.get('reason', 'update_failed'))
    return result


# ---------------------------------------------------------------------------
# 元数据
# ---------------------------------------------------------------------------

@router.get("/meta/types")
async def meta_types():
    return {
        'alert_types': [
            {'key': at, 'label': ALERT_LABELS[at]}
            for at in ALERT_TYPES
        ],
        'severities': SEVERITIES,
        'thresholds': {
            'fcr_spike':   {'info': 3.0, 'warning': 5.0, 'critical': 10.0},
            'margin_drop': {'info': 5.0, 'warning': 10.0, 'critical': 15.0},
        },
    }
