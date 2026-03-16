"""财务预测 API — Phase 5 Month 7

端点：
  POST /api/v1/fin-forecast/compute/{store_id}      — 触发计算（四维）
  GET  /api/v1/fin-forecast/{store_id}              — 获取缓存预测
  GET  /api/v1/fin-forecast/accuracy/{store_id}     — 历史预测精度
  POST /api/v1/fin-forecast/backfill/{store_id}     — 回填实际值
  GET  /api/v1/fin-forecast/brand-summary           — 品牌汇总
  GET  /api/v1/fin-forecast/meta/types              — 预测类型说明
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.services import financial_forecast_service as svc

router = APIRouter(prefix="/api/v1/fin-forecast", tags=["financial_forecast"])


def _default_next_period() -> str:
    """默认预测下一个月。"""
    now = datetime.now(timezone.utc)
    m = now.month + 1
    y = now.year
    if m > 12:
        m = 1
        y += 1
    return f"{y:04d}-{m:02d}"


# ── 计算 ──────────────────────────────────────────────────────────────────────


@router.post("/compute/{store_id}")
async def compute_forecast(
    store_id: str,
    target_period: Optional[str] = Query(None, description="预测目标月份 YYYY-MM，默认下月"),
    db: AsyncSession = Depends(get_db),
):
    tp = target_period or _default_next_period()
    return await svc.compute_all_forecasts(db, store_id, tp)


# ── 查询 ──────────────────────────────────────────────────────────────────────


@router.get("/accuracy/{store_id}")
async def get_forecast_accuracy(
    store_id: str,
    periods: int = Query(6, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
):
    return await svc.get_forecast_accuracy_history(db, store_id, periods)


@router.get("/brand-summary")
async def get_brand_summary(
    brand_id: str = Query(...),
    target_period: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    tp = target_period or _default_next_period()
    return await svc.get_brand_forecast_summary(db, brand_id, tp)


@router.get("/{store_id}")
async def get_store_forecast(
    store_id: str,
    target_period: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    tp = target_period or _default_next_period()
    result = await svc.get_forecast(db, store_id, tp)
    if result is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"No forecast found for {store_id} / {tp}. POST /compute first.")
    return result


# ── 回填 ──────────────────────────────────────────────────────────────────────


@router.post("/backfill/{store_id}")
async def backfill_actuals(
    store_id: str,
    period: str = Query(..., description="已有实际数据的月份 YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """月末结算后调用，将实际值填入历史预测记录并计算精度。"""
    return await svc.backfill_actual_values(db, store_id, period)


# ── Meta ──────────────────────────────────────────────────────────────────────


@router.get("/meta/types")
async def get_forecast_types():
    return {
        "types": list(svc.FORECAST_TYPES),
        "labels": svc.FORECAST_TYPE_LABELS,
        "method": "weighted_moving_avg + linear_trend CI",
        "confidence": "95%",
        "history_periods": svc.HISTORY_PERIODS,
        "min_periods": svc.MIN_PERIODS,
    }
