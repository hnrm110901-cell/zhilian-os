"""
全渠道营收分析 API — OmniChannel Revenue Dashboard

GET /api/v1/omni-channel/revenue    — 渠道营收分解
GET /api/v1/omni-channel/trend      — 每日趋势
GET /api/v1/omni-channel/comparison — 渠道对比
GET /api/v1/omni-channel/profit     — 利润瀑布
GET /api/v1/omni-channel/mix        — 渠道占比（饼图）
GET /api/v1/omni-channel/peak-hours — 峰时热力图
"""

from datetime import date
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, Query
from src.core.database import get_db_session
from src.core.dependencies import require_role
from src.models.user import UserRole
from src.services.omni_channel_service import omni_channel_service

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/omni-channel", tags=["omni-channel"])


@router.get("/revenue")
async def get_channel_revenue(
    brand_id: str = Query(..., description="品牌ID"),
    store_id: Optional[str] = Query(None, description="门店ID（空=全品牌）"),
    start_date: date = Query(..., description="开始日期"),
    end_date: date = Query(..., description="结束日期"),
    db=Depends(get_db_session),
    _user=Depends(require_role(UserRole.ADMIN)),
):
    """各渠道营收分解：订单量、毛收入、佣金、配送费、净收入"""
    return await omni_channel_service.get_channel_revenue(
        db=db,
        brand_id=brand_id,
        store_id=store_id,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/trend")
async def get_revenue_trend(
    brand_id: str = Query(..., description="品牌ID"),
    store_id: Optional[str] = Query(None, description="门店ID"),
    days: int = Query(30, ge=1, le=365, description="天数"),
    db=Depends(get_db_session),
    _user=Depends(require_role(UserRole.ADMIN)),
):
    """每日各渠道营收趋势（堆叠柱状图数据）"""
    return await omni_channel_service.get_revenue_trend(
        db=db,
        brand_id=brand_id,
        store_id=store_id,
        days=days,
    )


@router.get("/comparison")
async def get_channel_comparison(
    brand_id: str = Query(..., description="品牌ID"),
    start_date: date = Query(..., description="开始日期"),
    end_date: date = Query(..., description="结束日期"),
    db=Depends(get_db_session),
    _user=Depends(require_role(UserRole.ADMIN)),
):
    """渠道对比：客单价、订单频率、峰值时段"""
    return await omni_channel_service.get_channel_comparison(
        db=db,
        brand_id=brand_id,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/profit")
async def get_profit_by_channel(
    brand_id: str = Query(..., description="品牌ID"),
    store_id: Optional[str] = Query(None, description="门店ID"),
    start_date: date = Query(..., description="开始日期"),
    end_date: date = Query(..., description="结束日期"),
    db=Depends(get_db_session),
    _user=Depends(require_role(UserRole.ADMIN)),
):
    """利润瀑布：毛收入 → 佣金 → 配送 → 包材 → 净利润"""
    return await omni_channel_service.get_profit_by_channel(
        db=db,
        brand_id=brand_id,
        store_id=store_id,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/mix")
async def get_channel_mix(
    brand_id: str = Query(..., description="品牌ID"),
    db=Depends(get_db_session),
    _user=Depends(require_role(UserRole.ADMIN)),
):
    """渠道营收占比（饼图，最近30天）"""
    return await omni_channel_service.get_channel_mix(
        db=db,
        brand_id=brand_id,
    )


@router.get("/peak-hours")
async def get_peak_hours(
    brand_id: str = Query(..., description="品牌ID"),
    store_id: Optional[str] = Query(None, description="门店ID"),
    db=Depends(get_db_session),
    _user=Depends(require_role(UserRole.ADMIN)),
):
    """峰时热力图：每小时各渠道订单分布（最近7天）"""
    return await omni_channel_service.get_peak_analysis(
        db=db,
        brand_id=brand_id,
        store_id=store_id,
    )
