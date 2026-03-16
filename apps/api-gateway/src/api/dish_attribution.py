"""菜品营收归因 API — Phase 6 Month 9"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.services.dish_attribution_service import (
    compute_revenue_attribution,
    get_attribution_summary,
    get_dish_attribution_history,
    get_revenue_attribution,
    get_top_movers,
)

router = APIRouter(prefix="/api/v1/dish-attribution", tags=["dish-attribution"])

_VALID_DRIVERS = {"price", "volume", "interaction", "mixed", "stable"}
_VALID_DIRECTIONS = {"gain", "loss"}


@router.post("/compute/{store_id}")
async def api_compute_attribution(
    store_id: str,
    period: str = Query(..., description="YYYY-MM"),
    prev_period: Optional[str] = Query(None, description="YYYY-MM，默认取上月"),
    db: AsyncSession = Depends(get_db),
):
    """触发 PVM 归因计算并写入数据库（幂等）。"""
    result = await compute_revenue_attribution(db, store_id, period, prev_period)
    return {"ok": True, "data": result}


@router.get("/{store_id}")
async def api_get_attribution(
    store_id: str,
    period: str = Query(..., description="YYYY-MM"),
    driver: Optional[str] = Query(None, description="price/volume/interaction/mixed/stable"),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """查询归因明细列表，可按主要驱动因子过滤。"""
    if driver and driver not in _VALID_DRIVERS:
        return {"ok": False, "error": f"driver 必须是 {_VALID_DRIVERS} 之一"}
    rows = await get_revenue_attribution(db, store_id, period, driver=driver, limit=limit)
    return {"ok": True, "data": rows}


@router.get("/summary/{store_id}")
async def api_get_summary(
    store_id: str,
    period: str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """按主要驱动因子聚合统计。"""
    result = await get_attribution_summary(db, store_id, period)
    return {"ok": True, "data": result}


@router.get("/movers/{store_id}")
async def api_get_top_movers(
    store_id: str,
    period: str = Query(..., description="YYYY-MM"),
    direction: str = Query("gain", description="gain=增幅最大；loss=降幅最大"),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """营收变化最大的菜品 Top-N。"""
    if direction not in _VALID_DIRECTIONS:
        return {"ok": False, "error": "direction 必须是 'gain' 或 'loss'"}
    rows = await get_top_movers(db, store_id, period, direction=direction, limit=limit)
    return {"ok": True, "data": rows}


@router.get("/dish/{store_id}/{dish_id}")
async def api_get_dish_history(
    store_id: str,
    dish_id: str,
    periods: int = Query(6, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
):
    """某道菜近 N 期的 PVM 归因历史。"""
    rows = await get_dish_attribution_history(db, store_id, dish_id, periods=periods)
    return {"ok": True, "data": rows}


@router.get("/meta/drivers")
async def api_meta_drivers():
    """返回驱动因子枚举值说明。"""
    return {
        "ok": True,
        "data": [
            {"value": "price", "label": "价格驱动", "description": "均价变化贡献 ≥60% 的营收变化"},
            {"value": "volume", "label": "销量驱动", "description": "销量变化贡献 ≥60% 的营收变化"},
            {"value": "interaction", "label": "交互效应", "description": "价格×销量联合变化贡献 ≥60%"},
            {"value": "mixed", "label": "混合因素", "description": "无单一主导效应"},
            {"value": "stable", "label": "稳定", "description": "营收变化绝对值 < ¥1"},
        ],
    }
