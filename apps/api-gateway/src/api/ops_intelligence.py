"""
Ops Intelligence API — Sprint 5

端点：
  CostAgent（成本经营智能）:
    GET  /cost/dashboard       — 成本综合仪表盘
    GET  /cost/categories      — 品类成本结构
    GET  /cost/waste            — 损耗类型分析

  KitchenAgent（后厨效率智能）:
    GET  /kitchen/dashboard     — 后厨综合仪表盘
    GET  /kitchen/dish-speed    — 菜品出品速度排名
    GET  /kitchen/waste-types   — 损耗类型分布

  StoreAgent（门店综合智能）:
    GET  /store/scorecard       — 门店经营记分卡
    GET  /store/ranking         — 跨门店排名
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.core.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/cdp/ops", tags=["CDP-Ops"])


# ── CostAgent ─────────────────────────────────────────────────────


@router.get("/cost/dashboard")
async def get_cost_dashboard(
    store_id: str = Query(...),
    days: int = Query(30, le=365),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """成本综合仪表盘（食材成本率 + 损耗率 + 优化空间¥）"""
    from src.services.cost_agent_service import cost_agent_service

    return await cost_agent_service.get_cost_dashboard(db, store_id, days=days)


@router.get("/cost/categories")
async def get_cost_categories(
    store_id: str = Query(...),
    days: int = Query(30, le=365),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """品类成本结构"""
    from src.services.cost_agent_service import cost_agent_service

    return await cost_agent_service.get_cost_by_category(db, store_id, days=days)


@router.get("/cost/waste")
async def get_cost_waste(
    store_id: str = Query(...),
    days: int = Query(30, le=365),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """损耗类型分析"""
    from src.services.cost_agent_service import cost_agent_service

    return await cost_agent_service.get_waste_analysis(db, store_id, days=days)


# ── KitchenAgent ──────────────────────────────────────────────────


@router.get("/kitchen/dashboard")
async def get_kitchen_dashboard(
    store_id: str = Query(...),
    days: int = Query(7, le=90),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """后厨综合仪表盘（出品速度 + 退菜率 + 效率评级）"""
    from src.services.kitchen_agent_service import kitchen_agent_service

    return await kitchen_agent_service.get_kitchen_dashboard(db, store_id, days=days)


@router.get("/kitchen/dish-speed")
async def get_dish_speed(
    store_id: str = Query(...),
    days: int = Query(7, le=90),
    limit: int = Query(20, le=100),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """菜品出品速度排名"""
    from src.services.kitchen_agent_service import kitchen_agent_service

    return await kitchen_agent_service.get_dish_production_speed(db, store_id, days=days, limit=limit)


@router.get("/kitchen/waste-types")
async def get_waste_types(
    store_id: str = Query(...),
    days: int = Query(7, le=90),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """损耗类型分布"""
    from src.services.kitchen_agent_service import kitchen_agent_service

    return await kitchen_agent_service.get_waste_by_type(db, store_id, days=days)


# ── StoreAgent ────────────────────────────────────────────────────


@router.get("/store/scorecard")
async def get_store_scorecard(
    store_id: str = Query(...),
    days: int = Query(7, le=90),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """门店经营记分卡（5维度评分 + Top3建议）"""
    from src.services.store_agent_service import store_agent_service

    return await store_agent_service.get_store_scorecard(db, store_id, days=days)


@router.get("/store/ranking")
async def get_store_ranking(
    store_ids: Optional[str] = Query(None, description="逗号分隔的门店ID"),
    days: int = Query(7, le=90),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """跨门店排名"""
    from src.services.store_agent_service import store_agent_service

    ids = store_ids.split(",") if store_ids else None
    return await store_agent_service.get_cross_store_ranking(db, store_ids=ids, days=days)
