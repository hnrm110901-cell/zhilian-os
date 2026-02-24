"""
RaaS API - Result-as-a-Service API
按效果付费的商业模式API

核心理念: 不卖软件，卖结果
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from datetime import datetime

from src.core.dependencies import get_db, get_current_user
from src.services.raas_pricing_service import (
    get_raas_pricing_service,
    RaaSPricingService,
    PricingTier,
    EffectMetrics,
    BaselineMetrics
)
from src.models.user import User

router = APIRouter(prefix="/api/v1/raas")


@router.get("/pricing-tier/{store_id}")
async def get_pricing_tier(
    store_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取门店当前的定价层级

    - **FREE_TRIAL**: 基础版（免费试用3个月）
    - **COST_SAVING**: 效果版（按省下的成本分成20%）
    - **REVENUE_GROWTH**: 增长版（按增加的营收分成15%）
    - **MODEL_MARKETPLACE**: 模型版（一次性购买）
    """
    service = get_raas_pricing_service(db)
    tier = await service.get_pricing_tier(store_id, datetime.now())

    return {
        "store_id": store_id,
        "pricing_tier": tier,
        "description": {
            PricingTier.FREE_TRIAL: "基础版 - 免费试用3个月",
            PricingTier.COST_SAVING: "效果版 - 省下成本的20%作为服务费",
            PricingTier.REVENUE_GROWTH: "增长版 - 增加营收的15%作为分成",
            PricingTier.MODEL_MARKETPLACE: "模型版 - 一次性购买行业模型"
        }.get(tier, "未知")
    }


@router.get("/baseline/{store_id}")
async def get_baseline_metrics(
    store_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取门店的基线指标

    基线指标是在免费试用期开始前，收集门店过去3个月的运营数据
    """
    service = get_raas_pricing_service(db)

    # 计算过去3个月的基线
    end_date = datetime.now()
    start_date = end_date.replace(month=end_date.month - 3)

    baseline = await service.calculate_baseline(store_id, start_date, end_date)

    return {
        "store_id": store_id,
        "baseline": baseline.dict()
    }


@router.get("/effect-metrics/{store_id}")
async def get_effect_metrics(
    store_id: str,
    year: Optional[int] = None,
    month: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取门店的效果指标

    对比基线和当前期间的数据，计算实际产生的效果
    """
    service = get_raas_pricing_service(db)

    # 如果没有指定年月，使用当前月
    if not year or not month:
        now = datetime.now()
        year = now.year
        month = now.month

    # 计算基线
    baseline_end = datetime(year, month, 1)
    baseline_start = baseline_end.replace(month=baseline_end.month - 3)
    baseline = await service.calculate_baseline(store_id, baseline_start, baseline_end)

    # 计算当月效果
    period_start = datetime(year, month, 1)
    if month == 12:
        period_end = datetime(year + 1, 1, 1)
    else:
        period_end = datetime(year, month + 1, 1)

    effect_metrics = await service.calculate_effect_metrics(
        store_id,
        baseline,
        period_start,
        period_end
    )

    return {
        "store_id": store_id,
        "year": year,
        "month": month,
        "effect_metrics": effect_metrics.dict()
    }


@router.get("/monthly-bill/{store_id}")
async def get_monthly_bill(
    store_id: str,
    year: int,
    month: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    生成月度账单

    根据效果指标计算当月应付费用
    """
    service = get_raas_pricing_service(db)
    bill = await service.generate_monthly_bill(store_id, year, month)

    return bill


@router.get("/value-proposition/{store_id}")
async def get_value_proposition(
    store_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取价值主张

    用商业话术展示智链OS的价值，而不是技术话术
    """
    service = get_raas_pricing_service(db)

    # 获取当月效果
    now = datetime.now()
    bill = await service.generate_monthly_bill(store_id, now.year, now.month)

    effect_metrics = bill.get("effect_metrics", {})

    # 商业话术
    value_proposition = {
        "headline": "智链OS = 年薪只要几万块的数字总经理",
        "features": [
            "拥有行业Top10%管理经验",
            "24小时不休息",
            "永不离职",
            "持续学习进化"
        ],
        "benefits": [
            f"在这个冬天，帮你每个月砍掉一个人工成本（省 ¥{effect_metrics.get('labor_cost_saved', 0):,.0f}）",
            f"省下 ¥{effect_metrics.get('food_waste_saved', 0):,.0f} 的烂菜叶",
            "让你的加盟店拥有和海底捞一样的管理大脑",
            "一个戴在耳朵上的AI总经理"
        ],
        "results": {
            "cost_saved": effect_metrics.get('total_cost_saved', 0),
            "revenue_growth": effect_metrics.get('total_revenue_growth', 0),
            "total_value": effect_metrics.get('total_cost_saved', 0) + effect_metrics.get('total_revenue_growth', 0)
        },
        "pricing": {
            "model": "按效果付费",
            "free_trial": "3个月免费试用",
            "cost_saving_rate": "省下成本的20%",
            "revenue_growth_rate": "增加营收的15%"
        }
    }

    return value_proposition
