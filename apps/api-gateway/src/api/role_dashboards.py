"""
角色仪表盘 API — Phase 5 Month 3

Router prefix: /api/v1/dashboards
Endpoints:
  GET /ceo                      — CEO 多门店驾驶舱
  GET /region                   — 区域负责人仪表盘
"""

from __future__ import annotations

from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..services.ceo_dashboard_service import get_ceo_dashboard, get_region_dashboard

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/dashboards", tags=["role_dashboards"])


@router.get("/ceo")
async def ceo_dashboard(
    period: str = Query(..., description="YYYY-MM"),
    brand_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """CEO 多门店驾驶舱（BFF）"""
    return await get_ceo_dashboard(db, brand_id=brand_id, period=period)


@router.get("/region")
async def region_dashboard(
    store_ids: str = Query(..., description="逗号分隔门店 ID"),
    period: str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """区域负责人仪表盘（BFF）"""
    sid_list = [s.strip() for s in store_ids.split(",") if s.strip()]
    return await get_region_dashboard(db, store_ids=sid_list, period=period)
