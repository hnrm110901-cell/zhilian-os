"""
预订数据分析 API — 8 维度深度分析端点
提供预订经营洞察: 总览/渠道ROI/高峰热力图/客户洞察/No-Show预测/营收影响/取消分析/趋势
"""

from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.auth import get_current_active_user
from src.core.database import get_db
from src.services.reservation_analytics_service import reservation_analytics_service

router = APIRouter(prefix="/api/v1/reservation-analytics", tags=["reservation_analytics"])


def _parse_period(start: Optional[str], end: Optional[str], days: int = 30):
    """解析日期范围参数"""
    if start and end:
        return date.fromisoformat(start), date.fromisoformat(end)
    end_date = date.today()
    start_date = end_date - timedelta(days=days - 1)
    return start_date, end_date


@router.get("/overview")
async def overview(
    store_id: str,
    start: Optional[str] = Query(None, description="起始日期 YYYY-MM-DD"),
    end: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    days: int = Query(30, description="默认天数"),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_active_user),
):
    """预订经营总览 — 预订量/确认率/取消率/No-Show率/平均桌位"""
    start_date, end_date = _parse_period(start, end, days)
    return await reservation_analytics_service.get_overview(db, store_id, start_date, end_date)


@router.get("/channel-roi")
async def channel_roi(
    store_id: str,
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    days: int = Query(30),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_active_user),
):
    """渠道 ROI — 各渠道预订量/转化率/佣金成本/每单获客成本"""
    start_date, end_date = _parse_period(start, end, days)
    return await reservation_analytics_service.get_channel_roi(db, store_id, start_date, end_date)


@router.get("/peak-heatmap")
async def peak_heatmap(
    store_id: str,
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    days: int = Query(30),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_active_user),
):
    """高峰时段热力图 — 星期×时段的预订分布"""
    start_date, end_date = _parse_period(start, end, days)
    return await reservation_analytics_service.get_peak_heatmap(db, store_id, start_date, end_date)


@router.get("/customer-insights")
async def customer_insights(
    store_id: str,
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    days: int = Query(30),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_active_user),
):
    """客户洞察 — 新客/回头客/高频客户/大桌客户"""
    start_date, end_date = _parse_period(start, end, days)
    return await reservation_analytics_service.get_customer_insights(db, store_id, start_date, end_date)


@router.get("/no-show-risk")
async def no_show_risk(
    store_id: str,
    target_date: Optional[str] = Query(None, description="目标日期 YYYY-MM-DD，默认明天"),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_active_user),
):
    """No-Show 风险预测 — 基于客户历史的到店概率评估"""
    td = date.fromisoformat(target_date) if target_date else None
    return await reservation_analytics_service.get_no_show_risk(db, store_id, td)


@router.get("/revenue-impact")
async def revenue_impact(
    store_id: str,
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    days: int = Query(30),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_active_user),
):
    """营收影响 — 取消/No-Show 导致的¥损失量化"""
    start_date, end_date = _parse_period(start, end, days)
    return await reservation_analytics_service.get_revenue_impact(db, store_id, start_date, end_date)


@router.get("/cancellation-deep")
async def cancellation_deep(
    store_id: str,
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    days: int = Query(30),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_active_user),
):
    """取消深度分析 — 取消提前量/时段分布/类型分布/¥损失"""
    start_date, end_date = _parse_period(start, end, days)
    return await reservation_analytics_service.get_cancellation_deep(db, store_id, start_date, end_date)


@router.get("/daily-trend")
async def daily_trend(
    store_id: str,
    days: int = Query(30, description="趋势天数"),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_active_user),
):
    """每日趋势 — 预订量/确认量/取消量/No-Show 折线图数据"""
    return await reservation_analytics_service.get_daily_trend(db, store_id, days)
