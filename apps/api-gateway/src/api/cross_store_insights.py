"""
跨店洞察 API
"""
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.order import Order
from ..models.store import Store
from ..models.user import User
from ..services.cross_store_insights_service import cross_store_insights_service

router = APIRouter(prefix="/api/v1/insights", tags=["cross_store_insights"])


async def _fetch_store_metric(
    db: AsyncSession,
    metric: str,
    target_date: date,
) -> List[dict]:
    """从 Order 表聚合各门店指定日期的指标"""
    if metric == "revenue":
        agg = func.sum(Order.total_amount)
    elif metric == "orders":
        agg = func.count(Order.id)
    else:
        agg = func.sum(Order.total_amount)

    result = await db.execute(
        select(
            Order.store_id,
            agg.label("value"),
        )
        .where(func.date(Order.created_at) == target_date)
        .group_by(Order.store_id)
    )
    rows = result.all()

    # 补充门店名称
    store_ids = [r.store_id for r in rows]
    names = {}
    if store_ids:
        name_result = await db.execute(
            select(Store.id, Store.name).where(Store.id.in_(store_ids))
        )
        names = {r.id: r.name for r in name_result.all()}

    return [
        {
            "store_id": r.store_id,
            "store_name": names.get(r.store_id, r.store_id),
            "value": float(r.value or 0),
        }
        for r in rows
    ]


@router.get("/anomalies")
async def detect_anomalies(
    metric: str = Query("revenue", description="revenue | orders"),
    target_date: Optional[str] = Query(None, description="YYYY-MM-DD，默认今天"),
    threshold: float = Query(2.0, ge=1.0, le=5.0, description="异常阈值（标准差倍数）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """检测今日各门店指标异常"""
    d = date.fromisoformat(target_date) if target_date else date.today()
    store_metrics = await _fetch_store_metric(db, metric, d)
    anomalies = cross_store_insights_service.detect_anomalies(store_metrics, metric, threshold)
    return {
        "date": d.isoformat(),
        "metric": metric,
        "total_stores": len(store_metrics),
        "anomaly_count": len(anomalies),
        "anomalies": anomalies,
    }


@router.get("/best-practices")
async def best_practices(
    metric: str = Query("revenue"),
    target_date: Optional[str] = Query(None),
    top_n: int = Query(3, ge=1, le=10),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """提取各指标 Top/Bottom 门店"""
    d = date.fromisoformat(target_date) if target_date else date.today()
    store_metrics = await _fetch_store_metric(db, metric, d)
    result = cross_store_insights_service.extract_best_practices(store_metrics, metric, top_n)
    return {"date": d.isoformat(), **result}


@router.get("/period-comparison")
async def period_comparison(
    metric: str = Query("revenue"),
    period: str = Query("week", description="week | month"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """本期 vs 上期同期对比"""
    today = date.today()
    if period == "week":
        current_start = today - timedelta(days=today.weekday())
        previous_start = current_start - timedelta(weeks=1)
        previous_end = current_start - timedelta(days=1)
    else:
        current_start = today.replace(day=1)
        previous_start = (current_start - timedelta(days=1)).replace(day=1)
        previous_end = current_start - timedelta(days=1)

    # 聚合本期和上期（按日期范围求和）
    async def fetch_range(start: date, end: date):
        if metric == "revenue":
            agg = func.sum(Order.total_amount)
        else:
            agg = func.count(Order.id)
        result = await db.execute(
            select(Order.store_id, agg.label("value"))
            .where(func.date(Order.created_at).between(start, end))
            .group_by(Order.store_id)
        )
        rows = result.all()
        store_ids = [r.store_id for r in rows]
        names = {}
        if store_ids:
            nr = await db.execute(select(Store.id, Store.name).where(Store.id.in_(store_ids)))
            names = {r.id: r.name for r in nr.all()}
        return [{"store_id": r.store_id, "store_name": names.get(r.store_id, r.store_id), "value": float(r.value or 0)} for r in rows]

    current_data = await fetch_range(current_start, today)
    previous_data = await fetch_range(previous_start, previous_end)

    comparison = cross_store_insights_service.period_comparison(current_data, previous_data, metric)
    return {
        "metric": metric,
        "period": period,
        "current_range": f"{current_start} ~ {today}",
        "previous_range": f"{previous_start} ~ {previous_end}",
        "comparison": comparison,
    }


@router.get("/summary")
async def insight_summary(
    metric: str = Query("revenue"),
    target_date: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """生成跨店 AI 洞察摘要（含异常检测 + 最佳实践 + 同期对比）"""
    d = date.fromisoformat(target_date) if target_date else date.today()
    store_metrics = await _fetch_store_metric(db, metric, d)

    anomalies = cross_store_insights_service.detect_anomalies(store_metrics, metric)
    best = cross_store_insights_service.extract_best_practices(store_metrics, metric)

    # 上周同期
    prev_date = d - timedelta(weeks=1)
    prev_metrics = await _fetch_store_metric(db, metric, prev_date)
    comparison = cross_store_insights_service.period_comparison(store_metrics, prev_metrics, metric)

    summary = await cross_store_insights_service.generate_insight_summary(
        anomalies=anomalies,
        best_practices=best,
        period_comparison=comparison,
        metric=metric,
        target_date=d.isoformat(),
    )

    return {
        "date": d.isoformat(),
        "metric": metric,
        "summary": summary,
        "anomaly_count": len(anomalies),
        "top_store": best["top_stores"][0] if best["top_stores"] else None,
        "spread": best["spread"],
    }
