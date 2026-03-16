"""
Growth Agent API — Sprint 4

端点：
  裂变引擎 (ReferralEngine):
    GET  /referral/metrics        — 裂变效果指标
    GET  /referral/top-referrers  — 高价值推荐人排名

  楼面智能 (FloorAgent):
    GET  /floor/dashboard         — 楼面综合仪表盘
    GET  /floor/heatmap           — 时段效率热力图
    GET  /floor/table-efficiency  — 桌台效率排名

  菜品智能 (MenuAgent):
    GET  /menu/dashboard          — 菜品经营仪表盘
    GET  /menu/cdp-insights       — CDP增强菜品洞察
    GET  /menu/combos             — 菜品组合推荐

  增收月报 (RevenueGrowth):
    GET  /revenue/monthly         — 增收月报
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.core.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/cdp/growth", tags=["CDP-Growth"])


# ── 裂变引擎 ──────────────────────────────────────────────────────


@router.get("/referral/metrics")
async def get_referral_metrics(
    store_id: str = Query(...),
    days: int = Query(30, le=365),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """裂变效果指标（K-Factor + 场景分布 + 新客占比）"""
    from src.services.referral_engine_service import referral_engine_service

    return await referral_engine_service.get_referral_metrics(db, store_id, days=days)


@router.get("/referral/top-referrers")
async def get_top_referrers(
    store_id: str = Query(...),
    limit: int = Query(20, le=100),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """高价值推荐人排名"""
    from src.services.referral_engine_service import referral_engine_service

    return await referral_engine_service.get_top_referrers(db, store_id, limit=limit)


# ── 楼面智能 ──────────────────────────────────────────────────────


@router.get("/floor/dashboard")
async def get_floor_dashboard(
    store_id: str = Query(...),
    days: int = Query(7, le=90),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """楼面综合仪表盘（翻台率 + 等位转化 + 预订到店率）"""
    from src.services.floor_agent_service import floor_agent_service

    return await floor_agent_service.get_floor_dashboard(db, store_id, days=days)


@router.get("/floor/heatmap")
async def get_hourly_heatmap(
    store_id: str = Query(...),
    days: int = Query(7, le=90),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """时段效率热力图（24小时 × 订单数/营收/客单价）"""
    from src.services.floor_agent_service import floor_agent_service

    return await floor_agent_service.get_hourly_heatmap(db, store_id, days=days)


@router.get("/floor/table-efficiency")
async def get_table_efficiency(
    store_id: str = Query(...),
    days: int = Query(7, le=90),
    limit: int = Query(30, le=100),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """桌台效率排名"""
    from src.services.floor_agent_service import floor_agent_service

    return await floor_agent_service.get_table_efficiency(db, store_id, days=days, limit=limit)


# ── 菜品智能 ──────────────────────────────────────────────────────


@router.get("/menu/dashboard")
async def get_menu_dashboard(
    store_id: str = Query(...),
    days: int = Query(30, le=365),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """菜品经营仪表盘（BCG矩阵 + Top10 + 低毛利预警）"""
    from src.services.menu_agent_service import menu_agent_service

    return await menu_agent_service.get_menu_dashboard(db, store_id, days=days)


@router.get("/menu/cdp-insights")
async def get_dish_cdp_insights(
    store_id: str = Query(...),
    days: int = Query(30, le=365),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """CDP增强菜品洞察（哪些菜带来S1/S2高价值客户）"""
    from src.services.menu_agent_service import menu_agent_service

    return await menu_agent_service.get_dish_cdp_insights(db, store_id, days=days)


@router.get("/menu/combos")
async def get_combo_recommendations(
    store_id: str = Query(...),
    days: int = Query(30, le=365),
    limit: int = Query(10, le=50),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """菜品组合推荐（经常一起点的菜对）"""
    from src.services.menu_agent_service import menu_agent_service

    return await menu_agent_service.get_combo_recommendations(db, store_id, days=days, limit=limit)


# ── 增收月报 ──────────────────────────────────────────────────────


@router.get("/revenue/monthly")
async def get_monthly_report(
    store_id: str = Query(...),
    month_offset: int = Query(0, ge=-12, le=0),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """增收月报（各Agent贡献的¥影响汇总）"""
    from src.services.revenue_growth_service import revenue_growth_service

    return await revenue_growth_service.generate_monthly_report(
        db,
        store_id,
        month_offset=month_offset,
    )
