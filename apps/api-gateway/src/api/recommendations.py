"""
Recommendation Engine API Endpoints
推荐引擎API端点

Phase 4: 智能优化期 (Intelligence Optimization Period)
"""

from fastapi import APIRouter, HTTPException, Depends
import os
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

from ..services.recommendation_engine import (
    IntelligentRecommendationEngine,
    RecommendationType,
    PricingStrategy
)
from ..core.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession


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
async def recommend_dishes(
    request: RecommendDishesRequest,
    db: AsyncSession = Depends(get_db)
):
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
            customer_id=request.customer_id,
            store_id=request.store_id,
            context=request.context,
            top_k=request.top_k
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
                    "confidence": rec.confidence
                }
                for rec in recommendations
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pricing/optimize")
async def optimize_pricing(
    request: OptimizePricingRequest,
    db: AsyncSession = Depends(get_db)
):
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

        pricing = await engine.optimize_pricing(
            store_id=request.store_id,
            dish_id=request.dish_id,
            context=request.context
        )

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
            "reason": pricing.reason
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/marketing/campaign")
async def generate_marketing_campaign(
    request: GenerateCampaignRequest,
    db: AsyncSession = Depends(get_db)
):
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
            target_segment=request.target_segment
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
                "reason": campaign.reason
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/performance")
async def get_recommendation_performance(
    request: PerformanceRequest,
    db: AsyncSession = Depends(get_db)
):
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
            store_id=request.store_id,
            start_date=request.start_date,
            end_date=request.end_date
        )

        return {
            "success": True,
            **performance
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
