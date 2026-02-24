"""
AI 模型市场数据模型
"""
from sqlalchemy import Column, String, Integer, Float, DateTime, Text, Enum as SQLEnum, ForeignKey, Numeric
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from .base import Base


class ModelType(str, enum.Enum):
    SCHEDULING = "scheduling"
    INVENTORY = "inventory"
    PRICING = "pricing"
    BOM = "bom"
    CUSTOMER_CHURN = "customer_churn"
    DEMAND_FORECAST = "demand_forecast"


class ModelLevel(str, enum.Enum):
    BASIC = "basic"
    INDUSTRY = "industry"
    CUSTOM = "custom"


class ModelStatus(str, enum.Enum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    TRAINING = "training"


class PurchaseStatus(str, enum.Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class AIModel(Base):
    """AI 模型表"""
    __tablename__ = "ai_models"

    id = Column(String(36), primary_key=True)
    model_name = Column(String(200), nullable=False)
    model_type = Column(SQLEnum(ModelType), nullable=False, index=True)
    model_level = Column(SQLEnum(ModelLevel), nullable=False, index=True)
    industry_category = Column(String(50), index=True)
    description = Column(Text)
    price = Column(Numeric(12, 2), default=0.0, comment="年费（元）")
    training_stores_count = Column(Integer, default=0)
    training_data_points = Column(Integer, default=0)
    accuracy = Column(Float, default=0.0, comment="模型准确率（%）")
    status = Column(SQLEnum(ModelStatus), default=ModelStatus.ACTIVE, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    purchases = relationship("ModelPurchaseRecord", back_populates="model")
    contributions = relationship("DataContributionRecord", back_populates="model")


class ModelPurchaseRecord(Base):
    """模型购买记录表"""
    __tablename__ = "model_purchases"

    id = Column(String(36), primary_key=True)
    store_id = Column(String(36), ForeignKey("stores.id"), nullable=False, index=True)
    model_id = Column(String(36), ForeignKey("ai_models.id"), nullable=False, index=True)
    purchase_date = Column(DateTime, default=datetime.utcnow, nullable=False)
    expiry_date = Column(DateTime, nullable=False)
    price_paid = Column(Numeric(12, 2), default=0.0)
    status = Column(SQLEnum(PurchaseStatus), default=PurchaseStatus.ACTIVE, index=True)

    store = relationship("Store", backref="model_purchases")
    model = relationship("AIModel", back_populates="purchases")


class DataContributionRecord(Base):
    """数据贡献记录表"""
    __tablename__ = "data_contributions"

    id = Column(String(36), primary_key=True)
    store_id = Column(String(36), ForeignKey("stores.id"), nullable=False, index=True)
    model_id = Column(String(36), ForeignKey("ai_models.id"), nullable=False, index=True)
    data_points_contributed = Column(Integer, default=0)
    quality_score = Column(Float, default=0.0, comment="数据质量评分（0-100）")
    contribution_date = Column(DateTime, default=datetime.utcnow, nullable=False)
    revenue_share = Column(Numeric(12, 2), default=0.0, comment="分成金额（元）")

    store = relationship("Store", backref="data_contributions")
    model = relationship("AIModel", back_populates="contributions")
