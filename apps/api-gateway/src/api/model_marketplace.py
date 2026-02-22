"""
Model Marketplace API - 模型交易市场API
联邦学习商业化 - 售卖行业最佳实践
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List

from src.core.dependencies import get_db, get_current_user
from src.services.model_marketplace_service import (
    get_model_marketplace_service,
    ModelMarketplaceService,
    ModelType,
    ModelLevel,
    IndustryCategory,
    ModelInfo,
    ModelPurchase,
    DataContribution
)
from src.models.user import User

router = APIRouter(prefix="/api/v1/model-marketplace")


@router.get("/models")
async def list_models(
    model_type: Optional[ModelType] = None,
    model_level: Optional[ModelLevel] = None,
    industry_category: Optional[IndustryCategory] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    列出可用的模型

    - **Level 1 (Basic)**: 基础服务（免费） - 使用自己门店数据训练的模型
    - **Level 2 (Industry)**: 行业模型（¥9,999/年） - 全国1000家门店联邦训练的通用模型
    - **Level 3 (Custom)**: 定制模型（¥29,999/年） - 针对特定品类的专属模型
    """
    service = get_model_marketplace_service(db)
    models = await service.list_available_models(
        model_type=model_type,
        model_level=model_level,
        industry_category=industry_category
    )

    return {
        "total": len(models),
        "models": [m.dict() for m in models]
    }


@router.post("/purchase")
async def purchase_model(
    store_id: str,
    model_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    购买模型

    购买行业模型或定制模型，立即获得成熟的AI能力
    """
    service = get_model_marketplace_service(db)
    purchase = await service.purchase_model(store_id, model_id)

    return {
        "success": True,
        "purchase": purchase.dict(),
        "message": "模型购买成功，已激活"
    }


@router.post("/contribute-data")
async def contribute_data(
    store_id: str,
    model_id: str,
    data_points: int,
    quality_score: float,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    贡献数据参与联邦学习

    门店贡献数据后，可以获得模型销售收益的分成
    数据越优质，分成越高
    """
    service = get_model_marketplace_service(db)
    contribution = await service.contribute_data(
        store_id=store_id,
        model_id=model_id,
        data_points=data_points,
        quality_score=quality_score
    )

    return {
        "success": True,
        "contribution": contribution.dict(),
        "message": f"数据贡献成功，预计分成 ¥{contribution.revenue_share:,.2f}"
    }


@router.get("/my-models/{store_id}")
async def get_my_models(
    store_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取门店已购买的模型
    """
    service = get_model_marketplace_service(db)
    purchases = await service.get_store_purchased_models(store_id)

    return {
        "store_id": store_id,
        "total": len(purchases),
        "purchases": [p.dict() for p in purchases]
    }


@router.get("/my-contributions/{store_id}")
async def get_my_contributions(
    store_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取门店的数据贡献记录
    """
    service = get_model_marketplace_service(db)
    contributions = await service.get_store_data_contributions(store_id)

    total_revenue_share = sum(c.revenue_share for c in contributions)

    return {
        "store_id": store_id,
        "total_contributions": len(contributions),
        "total_revenue_share": total_revenue_share,
        "contributions": [c.dict() for c in contributions]
    }


@router.get("/network-effect")
async def get_network_effect(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取网络效应指标

    展示智链OS的网络效应和护城河强度

    网络效应飞轮:
    更多门店接入 → 更多数据训练 → AI模型更聪明 → 效果更好 → 更多门店愿意接入
    """
    service = get_model_marketplace_service(db)
    network_effect = await service.calculate_network_effect()

    return {
        "network_effect": network_effect,
        "vision": {
            "title": "智链OS = 餐饮行业的\"集体大脑\"",
            "description": [
                f"{network_effect['total_stores']:,}家门店的运营经验",
                f"{network_effect['total_data_points']:,}条交易数据",
                "持续进化的AI模型",
                "不可复制的网络效应"
            ],
            "moat": {
                "strength": network_effect['moat_strength'],
                "explanation": "大厂可以复制代码，但无法复制网络效应。用的店越多，壁垒越高。"
            }
        }
    }
