"""菜品销售预测引擎 — REST 端点

Phase 6 Month 7
Prefix: /api/v1/dish-forecast
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.services.dish_forecast_service import (
    LIFECYCLE_ADJUSTMENT,
    _next_period,
    generate_dish_forecasts,
    get_dish_forecast_history,
    get_dish_forecasts,
    get_forecast_accuracy,
    get_forecast_summary,
)

router = APIRouter(prefix="/api/v1/dish-forecast", tags=["dish_forecast"])

_VALID_PHASES = list(LIFECYCLE_ADJUSTMENT.keys())


# ---------------------------------------------------------------------------
# 计算触发
# ---------------------------------------------------------------------------


@router.post("/generate/{store_id}")
async def generate(
    store_id: str,
    base_period: str = Query(..., description="最近完整期 YYYY-MM"),
    forecast_period: Optional[str] = Query(None, description="目标预测期，默认为 base_period+1"),
    db: AsyncSession = Depends(get_db),
):
    """
    基于 base_period 及之前的历史数据，为门店所有菜品生成下期预测。
    幂等，全量覆盖。
    """
    return await generate_dish_forecasts(db, store_id, base_period, forecast_period=forecast_period)


# ---------------------------------------------------------------------------
# 查询
# ---------------------------------------------------------------------------


@router.get("/{store_id}")
async def list_forecasts(
    store_id: str,
    forecast_period: str = Query(..., description="预测目标期 YYYY-MM"),
    lifecycle_phase: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """查询门店某预测期的菜品预测列表，按预测营收降序。"""
    if lifecycle_phase and lifecycle_phase not in _VALID_PHASES:
        raise HTTPException(status_code=400, detail=f"lifecycle_phase 必须是 {_VALID_PHASES} 之一")
    recs = await get_dish_forecasts(db, store_id, forecast_period, lifecycle_phase=lifecycle_phase, limit=limit)
    return {"store_id": store_id, "forecast_period": forecast_period, "count": len(recs), "forecasts": recs}


@router.get("/summary/{store_id}")
async def summary(
    store_id: str,
    forecast_period: str = Query(..., description="预测目标期 YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """按生命周期阶段聚合预测统计：菜品数、总预测营收、平均趋势。"""
    return await get_forecast_summary(db, store_id, forecast_period)


@router.get("/accuracy/{store_id}")
async def accuracy(
    store_id: str,
    forecast_period: str = Query(..., description="要回测的预测期 YYYY-MM"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """
    预测精度回测：将预测值与实际 dish_profitability_records JOIN 对比。
    仅在 forecast_period 的实际数据已入库后有结果。
    按实际偏差绝对值降序，便于聚焦偏差最大的菜品。
    """
    results = await get_forecast_accuracy(db, store_id, forecast_period, limit=limit)
    return {"store_id": store_id, "forecast_period": forecast_period, "count": len(results), "accuracy": results}


@router.get("/dish/{store_id}/{dish_id}")
async def dish_forecast_history(
    store_id: str,
    dish_id: str,
    periods: int = Query(6, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
):
    """某道菜近 N 期预测历史（含实际值 LEFT JOIN，可追踪预测精度演进）。"""
    history = await get_dish_forecast_history(db, store_id, dish_id, periods=periods)
    return {"store_id": store_id, "dish_id": dish_id, "history": history}


# ---------------------------------------------------------------------------
# 元数据
# ---------------------------------------------------------------------------


@router.get("/meta/model")
async def meta_model():
    return {
        "algorithm": "weighted_moving_average + linear_trend + lifecycle_adjustment",
        "history_periods": 6,
        "weight_scheme": "linear_recency (oldest=1, newest=n)",
        "lifecycle_adjustments": {k: f"{v*100:+.0f}%" for k, v in LIFECYCLE_ADJUSTMENT.items()},
        "confidence_interval": {
            "formula": "max(10%, 30% - periods_used × 4%)",
            "example_6_periods": "±10%",
            "example_1_period": "±26%",
        },
    }
