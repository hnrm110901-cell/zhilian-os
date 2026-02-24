"""
营销活动模型
"""
from sqlalchemy import Column, String, Integer, Float, DateTime, JSON, Date, Text, Numeric
from sqlalchemy.sql import func
import uuid

from .base import Base


class MarketingCampaign(Base):
    """营销活动表"""
    __tablename__ = "marketing_campaigns"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    store_id = Column(String(50), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    campaign_type = Column(String(50), comment="活动类型: coupon/discount/gift/points")
    status = Column(String(20), default="draft", comment="draft/active/completed/cancelled")

    start_date = Column(Date)
    end_date = Column(Date)

    budget = Column(Numeric(12, 2), default=0.0, comment="预算（元）")
    actual_cost = Column(Numeric(12, 2), default=0.0, comment="实际花费（元）")

    # 效果指标
    reach_count = Column(Integer, default=0, comment="触达人数")
    conversion_count = Column(Integer, default=0, comment="转化人数")
    revenue_generated = Column(Numeric(12, 2), default=0.0, comment="带来营收（元）")

    target_audience = Column(JSON, comment="目标受众配置")
    description = Column(Text)

    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
