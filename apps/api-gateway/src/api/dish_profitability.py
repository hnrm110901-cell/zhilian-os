"""菜品盈利能力分析引擎 — REST 端点

Phase 6 Month 1
Prefix: /api/v1/dish-profit
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.services.dish_profitability_service import (
    BCG_ACTIONS,
    BCG_COLORS,
    BCG_LABELS,
    BCG_QUADRANTS,
    compute_dish_profitability,
    get_bcg_summary,
    get_category_summary,
    get_dish_profitability,
    get_dish_trend,
    get_top_dishes,
)

router = APIRouter(prefix="/api/v1/dish-profit", tags=["dish_profitability"])


# ---------------------------------------------------------------------------
# 计算触发
# ---------------------------------------------------------------------------


@router.post("/compute/{store_id}")
async def compute(
    store_id: str,
    period: str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """
    从订单数据聚合当期菜品销售，计算 BCG 四象限 + 盈利排名，写入 DB。
    幂等操作，可重复调用。
    """
    result = await compute_dish_profitability(db, store_id, period)
    # 不在响应中返回全量 records，只返回摘要
    return {
        "store_id": result["store_id"],
        "period": result["period"],
        "dish_count": result["dish_count"],
        "bcg_summary": result.get("bcg_summary"),
    }


# ---------------------------------------------------------------------------
# 查询
# ---------------------------------------------------------------------------


@router.get("/{store_id}")
async def list_dishes(
    store_id: str,
    period: str = Query(..., description="YYYY-MM"),
    bcg_quadrant: str = Query(None, description="star/cash_cow/question_mark/dog，不传返回全部"),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """获取菜品盈利能力列表，支持按 BCG 象限过滤。"""
    if bcg_quadrant and bcg_quadrant not in BCG_QUADRANTS:
        raise HTTPException(status_code=400, detail=f"bcg_quadrant 必须是 {BCG_QUADRANTS} 之一")
    dishes = await get_dish_profitability(db, store_id, period, bcg_quadrant=bcg_quadrant, limit=limit)
    return {"store_id": store_id, "period": period, "count": len(dishes), "dishes": dishes}


@router.get("/bcg/{store_id}")
async def bcg_summary(
    store_id: str,
    period: str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """获取 BCG 四象限汇总统计（各象限菜品数/收入/毛利/占比）。"""
    return await get_bcg_summary(db, store_id, period)


@router.get("/top/{store_id}")
async def top_dishes(
    store_id: str,
    period: str = Query(..., description="YYYY-MM"),
    metric: str = Query(
        "gross_profit_yuan", description="gross_profit_yuan/revenue_yuan/order_count/" "gross_profit_margin/food_cost_rate"
    ),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """按指定指标排序返回 Top N 菜品。"""
    dishes = await get_top_dishes(db, store_id, period, metric=metric, limit=limit)
    return {"store_id": store_id, "period": period, "metric": metric, "count": len(dishes), "dishes": dishes}


@router.get("/trend/{store_id}/{dish_id}")
async def dish_trend(
    store_id: str,
    dish_id: str,
    periods: int = Query(6, ge=2, le=12),
    db: AsyncSession = Depends(get_db),
):
    """获取指定菜品近 N 期历史趋势。"""
    trend = await get_dish_trend(db, store_id, dish_id, periods=periods)
    return {"store_id": store_id, "dish_id": dish_id, "periods": periods, "trend": trend}


@router.get("/category/{store_id}")
async def category_summary(
    store_id: str,
    period: str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
):
    """按菜品分类汇总盈利能力。"""
    cats = await get_category_summary(db, store_id, period)
    return {"store_id": store_id, "period": period, "categories": cats}


# ---------------------------------------------------------------------------
# 元数据
# ---------------------------------------------------------------------------


@router.get("/meta/quadrants")
async def meta_quadrants():
    return {
        "quadrants": [
            {"key": q, "label": BCG_LABELS[q], "action": BCG_ACTIONS[q], "color": BCG_COLORS[q]} for q in BCG_QUADRANTS
        ],
        "metrics": [
            "gross_profit_yuan",
            "revenue_yuan",
            "order_count",
            "gross_profit_margin",
            "food_cost_rate",
        ],
    }
