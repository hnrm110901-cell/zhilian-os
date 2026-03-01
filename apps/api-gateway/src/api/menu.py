"""
FEAT-004: 动态菜单推荐 API

GET /api/v1/menu/recommendations?store_id=&limit=10
目标响应时间：< 200ms（Redis 缓存，TTL 5分钟）
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, status
import structlog

from src.services.menu_ranker import MenuRanker

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/menu", tags=["menu-recommendations"])


@router.get("/recommendations")
async def get_menu_recommendations(
    store_id: str,
    limit: int = 10,
):
    """
    获取动态菜单推荐

    基于5因子评分（趋势30%、毛利25%、库存20%、时段匹配15%、低退单10%）。
    Redis 缓存，TTL 5分钟，目标响应时间 < 200ms。

    Args:
        store_id: 门店ID
        limit: 返回推荐数量（默认10）
    """
    if limit < 1 or limit > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "limit 必须在 1-50 之间"},
        )

    try:
        ranker = MenuRanker()
        ranked = await ranker.rank(store_id=store_id, limit=limit)

        return {
            "store_id": store_id,
            "total": len(ranked),
            "recommendations": [
                {
                    "rank": dish.rank,
                    "dish_id": dish.dish_id,
                    "dish_name": dish.dish_name,
                    "category": dish.category,
                    "price": float(dish.price) if dish.price else None,
                    "highlight": dish.highlight,
                    "scores": {
                        "total": dish.score.total_score,
                        "trend": dish.score.trend_score,
                        "margin": dish.score.margin_score,
                        "stock": dish.score.stock_score,
                        "time_slot": dish.score.time_slot_score,
                        "low_refund": dish.score.low_refund_score,
                    },
                }
                for dish in ranked
            ],
        }

    except Exception as e:
        logger.error("menu_recommendations.failed", store_id=store_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "获取菜单推荐失败，请稍后重试"},
        )
