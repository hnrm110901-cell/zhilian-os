"""菜品智能定价引擎 — REST 端点

Phase 6 Month 5
Prefix: /api/v1/dish-pricing
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.services.dish_pricing_service import (
    REC_ACTIONS,
    STATUSES,
    generate_pricing_recommendations,
    get_pricing_history,
    get_pricing_recommendations,
    get_pricing_summary,
    update_pricing_status,
)

router = APIRouter(prefix="/api/v1/dish-pricing", tags=["dish_pricing"])


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
    为门店当期所有菜品生成/更新定价建议。幂等（已采纳/忽略的记录不被覆盖）。
    """
    return await generate_pricing_recommendations(db, store_id, period)


# ---------------------------------------------------------------------------
# 查询
# ---------------------------------------------------------------------------


@router.get("/{store_id}")
async def list_recommendations(
    store_id: str,
    period: str = Query(..., description="YYYY-MM"),
    rec_action: Optional[str] = Query(None, description="increase/decrease/maintain"),
    status: Optional[str] = Query(None, description="pending/adopted/dismissed"),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """查询定价建议列表，支持 rec_action + status 双重过滤。"""
    if rec_action and rec_action not in REC_ACTIONS:
        raise HTTPException(status_code=400, detail=f"rec_action 必须是 {REC_ACTIONS} 之一")
    if status and status not in STATUSES:
        raise HTTPException(status_code=400, detail=f"status 必须是 {STATUSES} 之一")
    recs = await get_pricing_recommendations(db, store_id, period, rec_action=rec_action, status=status, limit=limit)
    return {"store_id": store_id, "period": period, "count": len(recs), "recommendations": recs}


@router.get("/summary/{store_id}")
async def summary(
    store_id: str,
    period: str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """按 rec_action 聚合定价建议统计及总¥影响。"""
    return await get_pricing_summary(db, store_id, period)


@router.get("/dish/{store_id}/{dish_id}")
async def dish_history(
    store_id: str,
    dish_id: str,
    periods: int = Query(6, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
):
    """某道菜近 N 期定价建议历史（追踪价格调整演进）。"""
    history = await get_pricing_history(db, store_id, dish_id, periods=periods)
    return {"store_id": store_id, "dish_id": dish_id, "history": history}


# ---------------------------------------------------------------------------
# 状态变更
# ---------------------------------------------------------------------------


@router.post("/{rec_id}/adopt")
async def adopt(
    rec_id: int,
    adopted_price: Optional[float] = Query(None, description="实际采纳价格，不传则用建议价"),
    db: AsyncSession = Depends(get_db),
):
    """将定价建议标记为已采纳（可传实际定价）。"""
    result = await update_pricing_status(db, rec_id, "adopt", adopted_price=adopted_price)
    if not result["updated"]:
        raise HTTPException(status_code=404, detail=result.get("reason", "update_failed"))
    return result


@router.post("/{rec_id}/dismiss")
async def dismiss(
    rec_id: int,
    db: AsyncSession = Depends(get_db),
):
    """将定价建议标记为已忽略。"""
    result = await update_pricing_status(db, rec_id, "dismiss")
    if not result["updated"]:
        raise HTTPException(status_code=404, detail=result.get("reason", "update_failed"))
    return result


# ---------------------------------------------------------------------------
# 元数据
# ---------------------------------------------------------------------------


@router.get("/meta/actions")
async def meta_actions():
    return {
        "rec_actions": REC_ACTIONS,
        "statuses": STATUSES,
        "elasticity_classes": ["inelastic", "moderate", "elastic"],
        "price_lift_rules": {
            "star_increase": {"pct": 8.0, "condition": "BCG=star AND GPM≥55%"},
            "cash_cow_increase": {"pct": 5.0, "condition": "BCG=cash_cow AND GPM≥45%"},
            "question_mark_decrease": {"pct": -8.0, "condition": "BCG=question_mark AND orders<30"},
            "high_fcr_increase": {"pct": 6.0, "condition": "FCR≥42%"},
        },
        "demand_retention": {"inelastic": 0.95, "moderate": 0.88, "elastic": 0.80},
        "demand_boost": {"inelastic": 1.08, "moderate": 1.15, "elastic": 1.20},
    }
