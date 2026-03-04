"""
损耗监控 API（Waste Guard）

MVP #3: 损耗Top5排名（含¥归因）
端点：
  GET /api/v1/waste/report   — 综合损耗报告（Top5 + 损耗率 + BOM偏差）
  GET /api/v1/waste/top5     — 单独 Top5 损耗食材
  GET /api/v1/waste/summary  — 单独损耗率汇总（含环比）
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.dependencies import get_current_active_user, get_db
from ..models.user import User
from ..services.waste_guard_service import WasteGuardService

logger = structlog.get_logger()
router = APIRouter()


def _default_dates() -> tuple[date, date]:
    end = date.today()
    start = end - timedelta(days=6)
    return start, end


@router.get("/api/v1/waste/report")
async def get_waste_report(
    store_id: str,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    综合损耗报告：Top5损耗食材 + 损耗率汇总 + BOM偏差排名。
    默认分析过去7天。
    """
    if end_date is None:
        end_date = date.today()
    if start_date is None:
        start_date = end_date - timedelta(days=6)

    report = await WasteGuardService.get_full_waste_report(
        store_id=store_id,
        start_date=start_date,
        end_date=end_date,
        db=db,
    )
    logger.info("waste_report_fetched", store_id=store_id,
                start=start_date.isoformat(), end=end_date.isoformat())
    return report


@router.get("/api/v1/waste/top5")
async def get_waste_top5(
    store_id: str,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Top 5 损耗食材（按¥金额降序，含归因）"""
    if end_date is None:
        end_date = date.today()
    if start_date is None:
        start_date = end_date - timedelta(days=6)

    return await WasteGuardService.get_top5_waste(store_id, start_date, end_date, db)


@router.get("/api/v1/waste/summary")
async def get_waste_summary(
    store_id: str,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """门店损耗率汇总（损耗率 + 环比变化）"""
    if end_date is None:
        end_date = date.today()
    if start_date is None:
        start_date = end_date - timedelta(days=6)

    return await WasteGuardService.get_waste_rate_summary(store_id, start_date, end_date, db)
