"""财务智能建议引擎 — REST 端点

Phase 5 Month 10
Prefix: /api/v1/fin-rec
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.services.financial_recommendation_service import (
    METRIC_LABELS,
    REC_TYPES,
    generate_store_recommendations,
    get_brand_rec_summary,
    get_recommendation_stats,
    get_recommendations,
    update_recommendation_status,
)

router = APIRouter(prefix="/api/v1/fin-rec", tags=["financial_recommendation"])


# ---------------------------------------------------------------------------
# 生成
# ---------------------------------------------------------------------------


@router.post("/generate/{store_id}")
async def generate_recommendations(
    store_id: str,
    period: str = Query(..., description="YYYY-MM"),
    max_recs: int = Query(10, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    """
    聚合 Phase 5 全部信号（异常/排名/预测），生成并持久化建议列表。
    可重复调用（幂等 upsert）。
    """
    result = await generate_store_recommendations(db, store_id, period, max_recs=max_recs)
    return result


# ---------------------------------------------------------------------------
# 查询
# ---------------------------------------------------------------------------


@router.get("/{store_id}")
async def list_recommendations(
    store_id: str,
    period: str = Query(..., description="YYYY-MM"),
    status: str = Query(None, description="pending/adopted/dismissed，不传返回全部"),
    db: AsyncSession = Depends(get_db),
):
    """获取门店当期建议列表，按优先级降序。"""
    recs = await get_recommendations(db, store_id, period, status=status or None)
    return {"store_id": store_id, "period": period, "count": len(recs), "recommendations": recs}


@router.get("/stats/{store_id}")
async def recommendation_stats(
    store_id: str,
    periods: int = Query(6, ge=2, le=12),
    db: AsyncSession = Depends(get_db),
):
    """获取门店近 N 期建议采纳率统计。"""
    stats = await get_recommendation_stats(db, store_id, periods=periods)
    return {"store_id": store_id, "periods": periods, "stats": stats}


@router.get("/brand-summary")
async def brand_summary(
    brand_id: str = Query(...),
    period: str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """品牌级建议汇总（¥潜力 + 采纳率 + 紧急度分布）。"""
    return await get_brand_rec_summary(db, brand_id, period)


# ---------------------------------------------------------------------------
# 操作
# ---------------------------------------------------------------------------


@router.post("/{rec_id}/adopt")
async def adopt(
    rec_id: int,
    db: AsyncSession = Depends(get_db),
):
    """标记建议为「已采纳」。"""
    result = await update_recommendation_status(db, rec_id, "adopted")
    if not result.get("updated"):
        raise HTTPException(status_code=404, detail="未找到 pending 状态的建议")
    return result


@router.post("/{rec_id}/dismiss")
async def dismiss(
    rec_id: int,
    db: AsyncSession = Depends(get_db),
):
    """标记建议为「已驳回」。"""
    result = await update_recommendation_status(db, rec_id, "dismissed")
    if not result.get("updated"):
        raise HTTPException(status_code=404, detail="未找到 pending 状态的建议")
    return result


# ---------------------------------------------------------------------------
# 元数据
# ---------------------------------------------------------------------------


@router.get("/meta/types")
async def meta_types():
    return {
        "rec_types": list(REC_TYPES),
        "urgency_levels": ["high", "medium", "low"],
        "statuses": ["pending", "adopted", "dismissed"],
        "metric_labels": METRIC_LABELS,
    }
