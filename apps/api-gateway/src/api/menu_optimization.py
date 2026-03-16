"""菜单优化建议引擎 — REST 端点

Phase 6 Month 2
Prefix: /api/v1/menu-opt
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.services.menu_optimization_service import (
    REC_ACTIONS,
    REC_LABELS,
    REC_TITLES,
    REC_TYPES,
    generate_menu_recommendations,
    get_dish_recommendations,
    get_menu_recommendations,
    get_recommendation_summary,
    update_recommendation_status,
)

router = APIRouter(prefix="/api/v1/menu-opt", tags=["menu_optimization"])


# ---------------------------------------------------------------------------
# 计算触发
# ---------------------------------------------------------------------------


@router.post("/generate/{store_id}")
async def generate(
    store_id: str,
    period: str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """
    读取当期 BCG 数据，为每道菜生成优化建议，写入 DB。幂等。
    """
    result = await generate_menu_recommendations(db, store_id, period)
    return result


# ---------------------------------------------------------------------------
# 查询
# ---------------------------------------------------------------------------


@router.get("/{store_id}")
async def list_recommendations(
    store_id: str,
    period: str = Query(..., description="YYYY-MM"),
    rec_type: Optional[str] = Query(None, description="|".join(REC_TYPES)),
    status: Optional[str] = Query(None, description="pending/adopted/dismissed"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """查询菜单优化建议列表，支持按类型和状态过滤。"""
    if rec_type and rec_type not in REC_TYPES:
        raise HTTPException(status_code=400, detail=f"rec_type 必须是 {REC_TYPES} 之一")
    if status and status not in ("pending", "adopted", "dismissed"):
        raise HTTPException(status_code=400, detail="status 必须是 pending/adopted/dismissed")
    recs = await get_menu_recommendations(db, store_id, period, rec_type=rec_type, status=status, limit=limit)
    return {"store_id": store_id, "period": period, "count": len(recs), "recommendations": recs}


@router.get("/summary/{store_id}")
async def summary(
    store_id: str,
    period: str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """按建议类型聚合¥预期影响与采纳情况。"""
    return await get_recommendation_summary(db, store_id, period)


@router.get("/dish/{store_id}/{dish_id}")
async def dish_history(
    store_id: str,
    dish_id: str,
    periods: int = Query(6, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
):
    """查询某道菜近 N 期的历史优化建议。"""
    recs = await get_dish_recommendations(db, store_id, dish_id, periods=periods)
    return {"store_id": store_id, "dish_id": dish_id, "history": recs}


# ---------------------------------------------------------------------------
# 状态变更
# ---------------------------------------------------------------------------


@router.post("/{rec_id}/adopt")
async def adopt(
    rec_id: int,
    db: AsyncSession = Depends(get_db),
):
    """将建议标记为已采纳。"""
    result = await update_recommendation_status(db, rec_id, "adopted")
    if not result["updated"]:
        raise HTTPException(status_code=404, detail=result.get("reason", "update_failed"))
    return result


@router.post("/{rec_id}/dismiss")
async def dismiss(
    rec_id: int,
    db: AsyncSession = Depends(get_db),
):
    """将建议标记为已忽略。"""
    result = await update_recommendation_status(db, rec_id, "dismissed")
    if not result["updated"]:
        raise HTTPException(status_code=404, detail=result.get("reason", "update_failed"))
    return result


# ---------------------------------------------------------------------------
# 元数据
# ---------------------------------------------------------------------------


@router.get("/meta/types")
async def meta_types():
    return {
        "rec_types": [
            {"key": rt, "label": REC_LABELS[rt], "title": REC_TITLES[rt], "action": REC_ACTIONS[rt]} for rt in REC_TYPES
        ]
    }
