"""
营销 Agent API
暴露 MarketingAgentService 的完整能力：顾客画像、发券策略、营销活动管理、个性化推荐
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.user import User
from ..models.marketing_campaign import MarketingCampaign as MarketingCampaignModel
from ..services.marketing_agent_service import MarketingAgentService

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/marketing", tags=["marketing_agent"])


def _get_service(db: AsyncSession) -> MarketingAgentService:
    return MarketingAgentService(db)


# ── Request / Response schemas ─────────────────────────────────────────────────

class CouponStrategyRequest(BaseModel):
    scenario: str               # traffic_decline / new_product_launch / member_day / default
    store_id: str
    context: Optional[Dict[str, Any]] = None


class CreateCampaignRequest(BaseModel):
    store_id:  str
    objective: str              # acquisition / activation / retention
    budget:    float
    name:      Optional[str] = None
    description: Optional[str] = None


class TriggerMarketingRequest(BaseModel):
    trigger_type: str           # birthday / churn_warning / repurchase_reminder
    store_id:     str


# ── Customer Profile ───────────────────────────────────────────────────────────

@router.get("/stores/{store_id}/customers/{customer_id}/profile")
async def get_customer_profile(
    store_id:    str,
    customer_id: str,
    db:          AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """构建顾客 360° 画像（RFM 价值评分、流失风险、口味偏好向量、分群标签）"""
    try:
        svc = _get_service(db)
        return await svc.build_customer_profile(customer_id, store_id)
    except Exception as e:
        logger.error("get_customer_profile_failed", error=str(e), customer_id=customer_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stores/{store_id}/customers/{customer_id}/recommendations")
async def recommend_dishes(
    store_id:    str,
    customer_id: str,
    top_k:       int = Query(5, ge=1, le=20, description="推荐数量"),
    db:          AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[Dict[str, Any]]:
    """基于顾客口味向量的个性化菜品推荐"""
    try:
        svc = _get_service(db)
        return await svc.recommend_dishes(customer_id, store_id, top_k=top_k)
    except Exception as e:
        logger.error("recommend_dishes_failed", error=str(e), customer_id=customer_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stores/{store_id}/customers/{customer_id}/trigger")
async def trigger_marketing(
    store_id:    str,
    customer_id: str,
    body:        TriggerMarketingRequest,
    db:          AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """手动触发营销动作（生日券 / 流失预警挽回 / 复购提醒）"""
    try:
        svc = _get_service(db)
        await svc.auto_trigger_marketing(body.trigger_type, customer_id, store_id)
        return {"status": "ok", "trigger_type": body.trigger_type, "customer_id": customer_id}
    except Exception as e:
        logger.error("trigger_marketing_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ── Coupon Strategy ────────────────────────────────────────────────────────────

@router.post("/coupon-strategy")
async def generate_coupon_strategy(
    body: CouponStrategyRequest,
    db:   AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """AI 生成发券策略（满减/折扣/代金 + 预期转化率/ROI）"""
    try:
        svc      = _get_service(db)
        strategy = await svc.generate_coupon_strategy(body.scenario, body.store_id, body.context)
        return strategy.dict()
    except Exception as e:
        logger.error("generate_coupon_strategy_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ── Campaigns ─────────────────────────────────────────────────────────────────

@router.get("/stores/{store_id}/campaigns")
async def list_campaigns(
    store_id: str,
    status:   Optional[str] = Query(None, description="过滤状态: draft/active/completed/cancelled"),
    limit:    int = Query(20, ge=1, le=100),
    offset:   int = Query(0, ge=0),
    db:       AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """列出门店所有营销活动"""
    try:
        conditions = [MarketingCampaignModel.store_id == store_id]
        if status:
            conditions.append(MarketingCampaignModel.status == status)

        stmt = (
            select(MarketingCampaignModel)
            .where(and_(*conditions))
            .order_by(MarketingCampaignModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await db.execute(stmt)).scalars().all()

        campaigns = [
            {
                "id":               c.id,
                "name":             c.name,
                "campaign_type":    c.campaign_type,
                "status":           c.status,
                "start_date":       str(c.start_date) if c.start_date else None,
                "end_date":         str(c.end_date)   if c.end_date   else None,
                "budget":           float(c.budget or 0),
                "actual_cost":      float(c.actual_cost or 0),
                "reach_count":      c.reach_count,
                "conversion_count": c.conversion_count,
                "revenue_generated":float(c.revenue_generated or 0),
                "description":      c.description,
                "created_at":       str(c.created_at),
            }
            for c in rows
        ]
        return {"store_id": store_id, "total": len(campaigns), "campaigns": campaigns}
    except Exception as e:
        logger.error("list_campaigns_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stores/{store_id}/campaigns")
async def create_campaign(
    store_id: str,
    body:     CreateCampaignRequest,
    db:       AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """AI 生成营销活动方案并持久化到 marketing_campaigns 表"""
    try:
        svc      = _get_service(db)
        campaign = await svc.create_marketing_campaign(body.objective, store_id, body.budget)

        # 持久化到数据库
        record = MarketingCampaignModel(
            id=campaign.campaign_id,
            store_id=store_id,
            name=body.name or campaign.name,
            campaign_type=campaign.coupon_strategy.coupon_type,
            status="draft",
            start_date=campaign.start_time.date(),
            end_date=campaign.end_time.date(),
            budget=float(campaign.budget),
            target_audience={"segment": campaign.target_segment},
            description=body.description or f"AI 生成营销活动 — 目标：{body.objective}",
        )
        db.add(record)
        await db.flush()
        await db.commit()

        return {
            "campaign_id":     campaign.campaign_id,
            "name":            record.name,
            "objective":       body.objective,
            "target_segment":  campaign.target_segment,
            "channel":         campaign.channel,
            "coupon_strategy": campaign.coupon_strategy.dict(),
            "expected_reach":  campaign.expected_reach,
            "budget":          float(campaign.budget),
            "start_date":      str(campaign.start_time.date()),
            "end_date":        str(campaign.end_time.date()),
        }
    except Exception as e:
        logger.error("create_campaign_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stores/{store_id}/campaigns/{campaign_id}")
async def get_campaign(
    store_id:    str,
    campaign_id: str,
    db:          AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """获取营销活动详情"""
    c = await db.get(MarketingCampaignModel, campaign_id)
    if not c or c.store_id != store_id:
        raise HTTPException(status_code=404, detail="Campaign not found")

    return {
        "id":               c.id,
        "name":             c.name,
        "campaign_type":    c.campaign_type,
        "status":           c.status,
        "start_date":       str(c.start_date) if c.start_date else None,
        "end_date":         str(c.end_date)   if c.end_date   else None,
        "budget":           float(c.budget or 0),
        "actual_cost":      float(c.actual_cost or 0),
        "reach_count":      c.reach_count,
        "conversion_count": c.conversion_count,
        "revenue_generated":float(c.revenue_generated or 0),
        "target_audience":  c.target_audience,
        "description":      c.description,
        "created_at":       str(c.created_at),
    }


@router.patch("/stores/{store_id}/campaigns/{campaign_id}/status")
async def update_campaign_status(
    store_id:    str,
    campaign_id: str,
    status:      str = Query(..., regex="^(active|completed|cancelled)$"),
    db:          AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """更新活动状态（draft→active→completed/cancelled）"""
    c = await db.get(MarketingCampaignModel, campaign_id)
    if not c or c.store_id != store_id:
        raise HTTPException(status_code=404, detail="Campaign not found")

    c.status = status
    await db.commit()
    logger.info("campaign_status_updated", campaign_id=campaign_id, status=status)
    return {"campaign_id": campaign_id, "status": status}
