"""
Recommendation Engine API Endpoints
推荐引擎API端点

Phase 4: 智能优化期 (Intelligence Optimization Period)
"""

import os
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..services.recommendation_engine import IntelligentRecommendationEngine, PricingStrategy, RecommendationType

router = APIRouter(prefix="/api/v1/recommendations", tags=["recommendations"])


# Request/Response Models
class RecommendDishesRequest(BaseModel):
    """Recommend dishes request"""

    customer_id: str
    store_id: str
    context: Optional[Dict[str, Any]] = None
    top_k: int = int(os.getenv("RECOMMEND_TOP_K", "5"))


class OptimizePricingRequest(BaseModel):
    """Optimize pricing request"""

    store_id: str
    dish_id: str
    context: Optional[Dict[str, Any]] = None


class GenerateCampaignRequest(BaseModel):
    """Generate marketing campaign request"""

    store_id: str
    objective: str
    budget: float
    target_segment: Optional[str] = None


class PerformanceRequest(BaseModel):
    """Get performance request"""

    store_id: str
    start_date: datetime
    end_date: datetime


# API Endpoints
@router.post("/dishes")
async def recommend_dishes(request: RecommendDishesRequest, db: AsyncSession = Depends(get_db)):
    """
    Recommend dishes for customer
    为客户推荐菜品

    Uses hybrid recommendation:
    - Collaborative filtering (similar customers)
    - Content-based filtering (dish attributes)
    - Context-aware (time, weather, occasion)
    - Business rules (profit, inventory)
    """
    try:
        engine = IntelligentRecommendationEngine(db)

        recommendations = await engine.recommend_dishes(
            customer_id=request.customer_id, store_id=request.store_id, context=request.context, top_k=request.top_k
        )

        return {
            "success": True,
            "customer_id": request.customer_id,
            "store_id": request.store_id,
            "recommendations": [
                {
                    "dish_id": rec.dish_id,
                    "dish_name": rec.dish_name,
                    "score": rec.score,
                    "reason": rec.reason,
                    "price": rec.price,
                    "estimated_profit": rec.estimated_profit,
                    "confidence": rec.confidence,
                }
                for rec in recommendations
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pricing/optimize")
async def optimize_pricing(request: OptimizePricingRequest, db: AsyncSession = Depends(get_db)):
    """
    Optimize pricing for dish
    优化菜品定价

    Dynamic pricing based on:
    - Demand elasticity
    - Time of day (peak/off-peak)
    - Inventory levels
    - Competitor pricing
    - Historical performance
    """
    try:
        engine = IntelligentRecommendationEngine(db)

        pricing = await engine.optimize_pricing(store_id=request.store_id, dish_id=request.dish_id, context=request.context)

        return {
            "success": True,
            "store_id": request.store_id,
            "dish_id": pricing.dish_id,
            "current_price": pricing.current_price,
            "recommended_price": pricing.recommended_price,
            "price_change_pct": pricing.price_change_pct,
            "strategy": pricing.strategy.value,
            "expected_demand_change": pricing.expected_demand_change,
            "expected_revenue_change": pricing.expected_revenue_change,
            "reason": pricing.reason,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/marketing/campaign")
async def generate_marketing_campaign(request: GenerateCampaignRequest, db: AsyncSession = Depends(get_db)):
    """
    Generate precision marketing campaign
    生成精准营销方案

    Uses customer segmentation and predictive analytics:
    - Identify target segment
    - Select optimal dishes
    - Determine discount rate
    - Estimate conversion and revenue
    """
    try:
        engine = IntelligentRecommendationEngine(db)

        campaign = await engine.generate_marketing_campaign(
            store_id=request.store_id,
            objective=request.objective,
            budget=request.budget,
            target_segment=request.target_segment,
        )

        return {
            "success": True,
            "campaign": {
                "campaign_id": campaign.campaign_id,
                "target_segment": campaign.target_segment,
                "dish_ids": campaign.dish_ids,
                "discount_rate": campaign.discount_rate,
                "expected_conversion": campaign.expected_conversion,
                "expected_revenue": campaign.expected_revenue,
                "duration_days": campaign.duration_days,
                "reason": campaign.reason,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/performance")
async def get_recommendation_performance(request: PerformanceRequest, db: AsyncSession = Depends(get_db)):
    """
    Get recommendation performance metrics
    获取推荐性能指标

    Tracks:
    - Recommendation acceptance rate
    - Revenue impact
    - Customer satisfaction
    - A/B test results
    """
    try:
        engine = IntelligentRecommendationEngine(db)

        performance = await engine.get_recommendation_performance(
            store_id=request.store_id, start_date=request.start_date, end_date=request.end_date
        )

        return {"success": True, **performance}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== P1-3：门店级经营推荐 ====================

import datetime

import structlog
from sqlalchemy import text

from ..core.dependencies import get_current_active_user
from ..models.user import User
from ..services.recommendation_service import generate_store_recommendations

_rec_logger = structlog.get_logger()


async def _fetch_sales_data(store_id: str, db: AsyncSession) -> List[dict]:
    """查询近7天门店销售数据（按菜品汇总）。"""
    since = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
    try:
        rows = (
            await db.execute(
                text("""
                SELECT
                    oi.item_name                          AS dish_name,
                    COALESCE(oi.item_id, oi.item_name)   AS dish_id,
                    SUM(oi.quantity)::int                  AS qty_sold_7d,
                    SUM(oi.subtotal)                      AS revenue_7d,
                    SUM(oi.quantity) / 7.0                AS avg_daily_qty
                FROM order_items oi
                JOIN orders o ON oi.order_id = o.id
                WHERE oi.store_id = :store_id
                  AND o.created_at >= :since
                GROUP BY oi.item_name, oi.item_id
                ORDER BY revenue_7d DESC
                LIMIT 20
            """),
                {"store_id": store_id, "since": since},
            )
        ).fetchall()
    except Exception as exc:
        _rec_logger.warning("recommendations.sales_query_failed", store_id=store_id, error=str(exc))
        return []

    return [
        {
            "dish_id": str(r[1] or r[0]),
            "dish_name": r[0],
            "qty_sold_7d": int(r[2] or 0),
            "revenue_7d": float(r[3] or 0),
            "avg_daily_qty": float(r[4] or 0),
        }
        for r in rows
        if r[0]
    ]


async def _fetch_inventory_data(store_id: str, db: AsyncSession) -> List[dict]:
    """
    查询库存中消耗速度快/数量偏低的食材，并计算预计耗尽天数。
    days_until_expiry = current_quantity / avg_daily_usage（来自近7天 usage 交易）
    """
    since = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
    try:
        rows = (
            await db.execute(
                text("""
                SELECT
                    ii.name                          AS dish_name,
                    ii.name                          AS dish_id,
                    COALESCE(ii.current_quantity, 0) AS stock_qty,
                    COALESCE(ii.unit_price, 0)       AS cost_per_unit,
                    CASE
                        WHEN COALESCE(usage.daily_usage, 0) > 0
                        THEN FLOOR(ii.current_quantity / usage.daily_usage)::int
                        ELSE 99
                    END                              AS days_until_expiry
                FROM inventory_items ii
                LEFT JOIN (
                    SELECT
                        item_id,
                        ABS(SUM(quantity)) / 7.0 AS daily_usage
                    FROM inventory_transactions
                    WHERE store_id = :store_id
                      AND transaction_type = 'usage'
                      AND created_at >= :since
                    GROUP BY item_id
                ) usage ON ii.id = usage.item_id
                WHERE ii.store_id = :store_id
                  AND ii.current_quantity IS NOT NULL
                  AND ii.current_quantity > 0
                ORDER BY days_until_expiry ASC
                LIMIT 20
            """),
                {"store_id": store_id, "since": since},
            )
        ).fetchall()
    except Exception as exc:
        _rec_logger.warning("recommendations.inventory_query_failed", store_id=store_id, error=str(exc))
        return []

    return [
        {
            "dish_id": r[1],
            "dish_name": r[0],
            "stock_qty": float(r[2]),
            "cost_per_unit": float(r[3]),
            "days_until_expiry": int(r[4]),
        }
        for r in rows
        if r[0]
    ]


@router.get("/{store_id}", summary="获取门店经营推荐（推广/下架/限时折扣）")
async def get_store_recommendations(
    store_id: str,
    _current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    基于销售历史 + 库存状态，返回门店级推荐列表。
    每条推荐包含：建议动作、预期¥影响、置信度、优先级。
    """
    try:
        sales_data = await _fetch_sales_data(store_id, db)
        inventory_data = await _fetch_inventory_data(store_id, db)
        recs = generate_store_recommendations(store_id, sales_data, inventory_data)
        return {
            "store_id": store_id,
            "total": len(recs),
            "recommendations": [
                {
                    "dish_id": r.dish_id,
                    "dish_name": r.dish_name,
                    "action": r.action.value,
                    "reason": r.reason,
                    "expected_revenue_impact": round(r.expected_revenue_impact, 2),
                    "confidence": round(r.confidence, 2),
                    "priority": r.priority,
                    "tags": r.tags,
                }
                for r in recs
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
