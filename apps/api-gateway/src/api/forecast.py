"""
Prophet 预测 API
"""
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..models.order import Order
from ..models.kpi import KPIRecord
from ..services.prophet_forecast_service import prophet_forecast_service

router = APIRouter(prefix="/api/v1/forecast", tags=["forecast"])


class HistoryPoint(BaseModel):
    date: str = Field(..., description="日期 YYYY-MM-DD")
    value: float


class ForecastRequest(BaseModel):
    store_id: str
    history: Optional[List[HistoryPoint]] = Field(None, description="手动传入历史数据（不传则从DB自动加载）")
    horizon_days: int = Field(7, ge=1, le=30)
    metric: str = Field("revenue", description="revenue | traffic | orders")
    retrain: bool = Field(False, description="强制重训，忽略缓存")


async def _load_revenue_history(store_id: str, db: AsyncSession, days: int = 90):
    """从 Order 表加载门店近 N 天日营收"""
    since = date.today() - timedelta(days=days)
    result = await db.execute(
        select(
            func.date(Order.created_at).label("date"),
            func.sum(Order.total_amount).label("value"),
        )
        .where(Order.store_id == store_id, func.date(Order.created_at) >= since)
        .group_by(func.date(Order.created_at))
        .order_by(func.date(Order.created_at))
    )
    return [{"date": str(row.date), "value": float(row.value or 0)} for row in result.all()]


async def _load_orders_history(store_id: str, db: AsyncSession, days: int = 90):
    """从 Order 表加载门店近 N 天日订单量"""
    since = date.today() - timedelta(days=days)
    result = await db.execute(
        select(
            func.date(Order.created_at).label("date"),
            func.count(Order.id).label("value"),
        )
        .where(Order.store_id == store_id, func.date(Order.created_at) >= since)
        .group_by(func.date(Order.created_at))
        .order_by(func.date(Order.created_at))
    )
    return [{"date": str(row.date), "value": float(row.value or 0)} for row in result.all()]


@router.post("/prophet")
async def prophet_forecast(
    req: ForecastRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Prophet 时序预测

    - 不传 history 时自动从 DB 加载近 90 天数据
    - metric: revenue（营收）/ orders（订单量）
    - 数据不足 14 天时自动降级为移动平均预测
    """
    history = req.history

    if history is None:
        if req.metric in ("revenue",):
            raw = await _load_revenue_history(req.store_id, db)
        elif req.metric == "orders":
            raw = await _load_orders_history(req.store_id, db)
        else:
            raw = await _load_revenue_history(req.store_id, db)
        history = [HistoryPoint(date=r["date"], value=r["value"]) for r in raw]

    result = await prophet_forecast_service.forecast(
        store_id=req.store_id,
        history=[{"date": h.date, "value": h.value} for h in history],
        horizon_days=req.horizon_days,
        metric=req.metric,
        retrain=req.retrain,
    )
    return result


@router.get("/prophet/{store_id}")
async def prophet_forecast_get(
    store_id: str,
    horizon_days: int = Query(7, ge=1, le=30),
    metric: str = Query("revenue"),
    db: AsyncSession = Depends(get_db),
):
    """GET 版本，自动从 DB 加载历史数据"""
    if metric in ("revenue",):
        raw = await _load_revenue_history(store_id, db)
    elif metric == "orders":
        raw = await _load_orders_history(store_id, db)
    else:
        raw = await _load_revenue_history(store_id, db)

    return await prophet_forecast_service.forecast(
        store_id=store_id,
        history=raw,
        horizon_days=horizon_days,
        metric=metric,
    )


@router.delete("/prophet/{store_id}/cache")
async def invalidate_forecast_cache(
    store_id: str,
    metric: str = Query("revenue"),
):
    """清除门店预测模型缓存（数据更新后调用）"""
    await prophet_forecast_service.invalidate_model(store_id, metric)
    return {"success": True, "store_id": store_id, "metric": metric}


# ==================== FEAT-002: 预测性备料建议 ====================

@router.get("/daily-suggestion")
async def get_daily_forecast_suggestion(
    store_id: str = Query(..., description="门店ID"),
    target_date: Optional[str] = Query(None, description="目标日期 YYYY-MM-DD（不传则默认明日）"),
    db: AsyncSession = Depends(get_db),
):
    """
    获取指定门店指定日期的预测性备料建议

    三档降级策略：
    - < 14天历史 → rule_based（低置信度，附"数据积累中"提示）
    - < 60天历史 → statistical（中置信度，移动加权平均）
    - ≥ 60天历史 → ML Prophet（高置信度）

    Args:
        store_id: 门店ID
        target_date: 目标日期（默认明日）
    """
    from ..services.demand_forecaster import DemandForecaster
    from datetime import date as _date

    if target_date:
        try:
            t_date = _date.fromisoformat(target_date)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail={"message": f"日期格式错误，请使用 YYYY-MM-DD，实际值: {target_date}"}
            )
    else:
        t_date = _date.today() + timedelta(days=1)

    forecaster = DemandForecaster(db_session=db)
    result = await forecaster.predict(store_id=store_id, target_date=t_date)

    return {
        "store_id": result.store_id,
        "target_date": str(result.target_date),
        "estimated_revenue": result.estimated_revenue,
        "confidence": result.confidence,
        "basis": result.basis,
        "note": result.note,
        "items": [
            {
                "sku_id": item.sku_id,
                "name": item.name,
                "unit": item.unit,
                "suggested_quantity": item.suggested_quantity,
                "unit_price": item.unit_price,
                "reason": item.reason,
            }
            for item in result.items
        ],
    }
