"""
模型交易市场服务 (Model Marketplace Service)
联邦学习商业化 - 售卖行业最佳实践

核心战略: 打造产业级突触网络
- Level 1: 基础服务（免费） - 使用自己门店数据训练的模型
- Level 2: 行业模型（¥9,999/年） - 全国1000家门店联邦训练的通用模型
- Level 3: 定制模型（¥29,999/年） - 针对特定品类的专属模型
- Level 4: 数据贡献分成 - 门店贡献数据获得模型销售收益分成
"""
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from enum import Enum
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import structlog
import uuid
from src.core.database import get_db_session
from src.models.ai_model import AIModel, ModelPurchaseRecord, DataContributionRecord

logger = structlog.get_logger()


class ModelType(str, Enum):
    """模型类型"""
    SCHEDULING = "scheduling"  # 排班模型
    INVENTORY = "inventory"  # 库存预测模型
    PRICING = "pricing"  # 动态定价模型
    BOM = "bom"  # BOM损耗控制模型
    CUSTOMER_CHURN = "customer_churn"  # 客户流失预测模型
    DEMAND_FORECAST = "demand_forecast"  # 需求预测模型


class ModelLevel(str, Enum):
    """模型级别"""
    BASIC = "basic"  # Level 1: 基础服务（免费）
    INDUSTRY = "industry"  # Level 2: 行业模型（¥9,999/年）
    CUSTOM = "custom"  # Level 3: 定制模型（¥29,999/年）


class IndustryCategory(str, Enum):
    """行业类别"""
    HOTPOT = "hotpot"  # 火锅
    BBQ = "bbq"  # 烧烤
    FAST_FOOD = "fast_food"  # 快餐
    CHINESE_RESTAURANT = "chinese_restaurant"  # 中餐
    SEAFOOD = "seafood"  # 海鲜
    WESTERN_FOOD = "western_food"  # 西餐


class ModelInfo(BaseModel):
    """模型信息"""
    model_id: str
    model_name: str
    model_type: ModelType
    model_level: ModelLevel
    industry_category: Optional[IndustryCategory] = None
    description: str
    price: float  # 年费（元）
    training_stores_count: int  # 参与训练的门店数量
    training_data_points: int  # 训练数据点数量
    accuracy: float  # 模型准确率（%）
    created_at: datetime
    updated_at: datetime


class ModelPurchase(BaseModel):
    """模型购买记录"""
    purchase_id: str
    store_id: str
    model_id: str
    purchase_date: datetime
    expiry_date: datetime
    price_paid: float
    status: str  # active, expired, cancelled


class DataContribution(BaseModel):
    """数据贡献记录"""
    contribution_id: str
    store_id: str
    model_id: str
    data_points_contributed: int
    quality_score: float  # 数据质量评分（0-100）
    contribution_date: datetime
    revenue_share: float  # 分成金额（元）


class ModelMarketplaceService:
    """模型交易市场服务"""

    # 模型定价（支持环境变量覆盖）
    INDUSTRY_MODEL_PRICE = float(os.getenv("MARKETPLACE_INDUSTRY_PRICE", "9999.0"))
    CUSTOM_MODEL_PRICE = float(os.getenv("MARKETPLACE_CUSTOM_PRICE", "29999.0"))

    # 数据贡献分成比例（支持环境变量覆盖）
    DATA_CONTRIBUTION_SHARE = float(os.getenv("MARKETPLACE_DATA_CONTRIBUTION_SHARE", "0.30"))

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_available_models(
        self,
        model_type: Optional[ModelType] = None,
        model_level: Optional[ModelLevel] = None,
        industry_category: Optional[IndustryCategory] = None
    ) -> List[ModelInfo]:
        """
        列出可用的模型
        """
        logger.info(
            "列出可用模型",
            model_type=model_type,
            model_level=model_level,
            industry_category=industry_category
        )

        async with get_db_session() as session:
            stmt = select(AIModel).where(AIModel.status == "active")
            if model_type:
                stmt = stmt.where(AIModel.model_type == model_type.value)
            if model_level:
                stmt = stmt.where(AIModel.model_level == model_level.value)
            if industry_category:
                stmt = stmt.where(AIModel.industry_category == industry_category.value)
            result = await session.execute(stmt)
            rows = result.scalars().all()

        models = [
            ModelInfo(
                model_id=r.id,
                model_name=r.model_name,
                model_type=ModelType(r.model_type),
                model_level=ModelLevel(r.model_level),
                industry_category=IndustryCategory(r.industry_category) if r.industry_category else None,
                description=r.description or "",
                price=r.price or 0.0,
                training_stores_count=r.training_stores_count or 0,
                training_data_points=r.training_data_points or 0,
                accuracy=r.accuracy or 0.0,
                created_at=r.created_at,
                updated_at=r.updated_at or r.created_at,
            )
            for r in rows
        ]

        return models

    async def purchase_model(
        self,
        store_id: str,
        model_id: str
    ) -> ModelPurchase:
        """
        购买模型
        """
        logger.info("购买模型", store_id=store_id, model_id=model_id)

        async with get_db_session() as session:
            model_result = await session.execute(
                select(AIModel).where(AIModel.id == model_id)
            )
            model = model_result.scalar_one_or_none()
            if not model:
                raise ValueError(f"模型不存在: {model_id}")

            price_paid = model.price or self.INDUSTRY_MODEL_PRICE
            record = ModelPurchaseRecord(
                id=str(uuid.uuid4()),
                store_id=store_id,
                model_id=model_id,
                purchase_date=datetime.now(),
                expiry_date=datetime.now() + timedelta(days=int(os.getenv("MODEL_LICENSE_EXPIRY_DAYS", "365"))),
                price_paid=price_paid,
                status="active",
            )
            session.add(record)
            await session.commit()
            purchase_id = record.id

        purchase = ModelPurchase(
            purchase_id=purchase_id,
            store_id=store_id,
            model_id=model_id,
            purchase_date=datetime.now(),
            expiry_date=datetime.now() + timedelta(days=int(os.getenv("MODEL_LICENSE_EXPIRY_DAYS", "365"))),
            price_paid=price_paid,
            status="active",
        )

        logger.info("模型购买成功", purchase_id=purchase.purchase_id)
        return purchase

    async def contribute_data(
        self,
        store_id: str,
        model_id: str,
        data_points: int,
        quality_score: float
    ) -> DataContribution:
        """
        贡献数据参与联邦学习

        门店贡献数据后，可以获得模型销售收益的分成
        """
        logger.info(
            "贡献数据",
            store_id=store_id,
            model_id=model_id,
            data_points=data_points,
            quality_score=quality_score
        )

        base_revenue_share = float(os.getenv("MARKETPLACE_BASE_REVENUE_SHARE", "100.0"))
        quality_multiplier = quality_score / 100.0
        data_volume_multiplier = min(data_points / int(os.getenv("MARKETPLACE_DATA_VOLUME_BASE", "10000")), float(os.getenv("MARKETPLACE_DATA_VOLUME_MAX_MULTIPLIER", "10.0")))
        revenue_share = base_revenue_share * quality_multiplier * data_volume_multiplier

        async with get_db_session() as session:
            record = DataContributionRecord(
                id=str(uuid.uuid4()),
                store_id=store_id,
                model_id=model_id,
                data_points_contributed=data_points,
                quality_score=quality_score,
                contribution_date=datetime.now(),
                revenue_share=revenue_share,
            )
            session.add(record)
            await session.commit()
            contribution_id = record.id

        contribution = DataContribution(
            contribution_id=contribution_id,
            store_id=store_id,
            model_id=model_id,
            data_points_contributed=data_points,
            quality_score=quality_score,
            contribution_date=datetime.now(),
            revenue_share=revenue_share,
        )

        logger.info(
            "数据贡献成功",
            contribution_id=contribution.contribution_id,
            revenue_share=revenue_share
        )
        return contribution

    async def get_store_purchased_models(
        self,
        store_id: str
    ) -> List[ModelPurchase]:
        """
        获取门店已购买的模型
        """
        logger.info("获取门店已购买模型", store_id=store_id)

        async with get_db_session() as session:
            result = await session.execute(
                select(ModelPurchaseRecord).where(
                    ModelPurchaseRecord.store_id == store_id,
                    ModelPurchaseRecord.status == "active",
                )
            )
            rows = result.scalars().all()

        return [
            ModelPurchase(
                purchase_id=r.id,
                store_id=r.store_id,
                model_id=r.model_id,
                purchase_date=r.purchase_date,
                expiry_date=r.expiry_date,
                price_paid=r.price_paid or 0.0,
                status=r.status,
            )
            for r in rows
        ]

    async def get_data_contributions(
        self,
        store_id: str
    ) -> List[DataContribution]:
        """
        获取门店的数据贡献记录
        """
        logger.info("获取门店数据贡献记录", store_id=store_id)

        async with get_db_session() as session:
            result = await session.execute(
                select(DataContributionRecord).where(
                    DataContributionRecord.store_id == store_id
                ).order_by(DataContributionRecord.contribution_date.desc())
            )
            rows = result.scalars().all()

        return [
            DataContribution(
                contribution_id=r.id,
                store_id=r.store_id,
                model_id=r.model_id,
                data_points_contributed=r.data_points_contributed or 0,
                quality_score=r.quality_score or 0.0,
                contribution_date=r.contribution_date,
                revenue_share=r.revenue_share or 0.0,
            )
            for r in rows
        ]
        """
        计算网络效应指标

        更多门店接入 → 更多数据训练 → AI模型更聪明 → 效果更好 → 更多门店愿意接入
        """
        logger.info("计算网络效应指标")

        async with get_db_session() as session:
            total_stores_result = await session.execute(
                select(func.count(func.distinct(ModelPurchaseRecord.store_id)))
            )
            total_stores = int(total_stores_result.scalar() or 0)

            total_models_result = await session.execute(
                select(func.count(AIModel.id)).where(AIModel.status == "active")
            )
            total_models = int(total_models_result.scalar() or 0)

            total_data_result = await session.execute(
                select(func.coalesce(func.sum(DataContributionRecord.data_points_contributed), 0))
            )
            total_data_points = int(total_data_result.scalar() or 0)

            avg_accuracy_result = await session.execute(
                select(func.avg(AIModel.accuracy)).where(AIModel.status == "active")
            )
            avg_accuracy = round(float(avg_accuracy_result.scalar() or 0), 1)

        network_value = total_stores * total_stores * float(os.getenv("MARKETPLACE_NETWORK_VALUE_COEF", "0.5"))
        moat_strength = "high" if total_stores >= int(os.getenv("MARKETPLACE_MOAT_HIGH_STORES", "500")) else ("medium" if total_stores >= int(os.getenv("MARKETPLACE_MOAT_MED_STORES", "100")) else "low")

        network_effect = {
            "total_stores": total_stores,
            "total_models": total_models,
            "total_data_points": total_data_points,
            "avg_model_accuracy": avg_accuracy,
            "monthly_new_stores": 0,
            "network_value": network_value,
            "moat_strength": moat_strength,
        }

        return network_effect


# 全局服务实例
model_marketplace_service: Optional[ModelMarketplaceService] = None


def get_model_marketplace_service(db: AsyncSession) -> ModelMarketplaceService:
    """获取模型交易市场服务实例"""
    return ModelMarketplaceService(db)
