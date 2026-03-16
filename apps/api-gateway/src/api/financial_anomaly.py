"""财务异常检测引擎 — REST 端点

Phase 5 Month 8
Prefix: /api/v1/fin-anomaly
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.services.financial_anomaly_service import (
    METRICS,
    detect_store_anomalies,
    get_anomaly_records,
    get_anomaly_trend,
    get_brand_anomaly_summary,
    resolve_anomaly,
)

router = APIRouter(prefix="/api/v1/fin-anomaly", tags=["financial_anomaly"])


# ---------------------------------------------------------------------------
# 检测
# ---------------------------------------------------------------------------


@router.post("/detect/{store_id}")
async def detect_anomalies(
    store_id: str,
    period: str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """触发门店全量财务异常检测（4 指标）。结果写入 financial_anomaly_records。"""
    result = await detect_store_anomalies(db, store_id, period)
    return result


# ---------------------------------------------------------------------------
# 查询
# ---------------------------------------------------------------------------


@router.get("/{store_id}")
async def list_anomalies(
    store_id: str,
    only_anomalies: bool = Query(True, description="true=只返回异常记录"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """获取门店异常记录列表。"""
    records = await get_anomaly_records(db, store_id, only_anomalies=only_anomalies, limit=limit)
    return {"store_id": store_id, "count": len(records), "records": records}


@router.get("/trend/{store_id}")
async def anomaly_trend(
    store_id: str,
    periods: int = Query(6, ge=2, le=12),
    db: AsyncSession = Depends(get_db),
):
    """按月汇总异常计数趋势（近 N 个月）。"""
    trend = await get_anomaly_trend(db, store_id, periods=periods)
    return {"store_id": store_id, "periods": periods, "trend": trend}


@router.get("/brand-summary")
async def brand_summary(
    brand_id: str = Query(...),
    period: str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """品牌级多店异常汇总。"""
    summary = await get_brand_anomaly_summary(db, brand_id, period)
    return summary


# ---------------------------------------------------------------------------
# 操作
# ---------------------------------------------------------------------------


@router.post("/resolve/{store_id}")
async def resolve(
    store_id: str,
    period: str = Query(..., description="YYYY-MM"),
    metric: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """标记指定异常为已解决。"""
    if metric not in METRICS:
        raise HTTPException(status_code=400, detail=f"metric 必须是 {METRICS} 之一")
    result = await resolve_anomaly(db, store_id, period, metric)
    if not result.get("updated"):
        raise HTTPException(status_code=404, detail="未找到对应异常记录")
    return result


# ---------------------------------------------------------------------------
# 元数据
# ---------------------------------------------------------------------------


@router.get("/meta/metrics")
async def meta_metrics():
    """返回支持检测的指标列表。"""
    return {
        "metrics": list(METRICS),
        "severity_levels": ["normal", "mild", "moderate", "severe"],
        "detection_methods": ["z_score", "forecast_deviation", "iqr"],
    }
