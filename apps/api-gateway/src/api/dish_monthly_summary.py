"""菜品经营综合月报 API — Phase 6 Month 12"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.services.dish_monthly_summary_service import build_dish_monthly_summary, get_dish_monthly_summary, get_summary_history

router = APIRouter(prefix="/api/v1/dish-monthly-summary", tags=["dish-monthly-summary"])


@router.post("/build/{store_id}")
async def api_build_summary(
    store_id: str,
    period: str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """
    聚合本期所有菜品分析数据源并生成月度汇总（幂等）。
    需预先运行各引擎的 compute 接口写入基础数据。
    """
    result = await build_dish_monthly_summary(db, store_id, period)
    if "error" in result:
        return {"ok": False, "error": result["error"]}
    return {"ok": True, "data": result}


@router.get("/{store_id}")
async def api_get_summary(
    store_id: str,
    period: str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """查询指定期月度汇总（需已 build）。"""
    result = await get_dish_monthly_summary(db, store_id, period)
    if result is None:
        return {"ok": False, "error": f"找不到 {store_id} {period} 的月度汇总，请先调用 build 接口"}
    return {"ok": True, "data": result}


@router.get("/history/{store_id}")
async def api_get_history(
    store_id: str,
    periods: int = Query(6, ge=1, le=24, description="查询最近几期"),
    db: AsyncSession = Depends(get_db),
):
    """查询近 N 期月度汇总趋势。"""
    rows = await get_summary_history(db, store_id, periods=periods)
    return {"ok": True, "data": rows}
