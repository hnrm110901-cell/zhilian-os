"""
销售渠道配置模型

SalesChannelConfig — 渠道级成本参数（佣金率、配送费、包材费）
支持品牌级覆盖（brand_id=null 为集团默认）。
"""

import uuid

from sqlalchemy import Boolean, Column, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from src.models.base import Base, TimestampMixin


class SalesChannelConfig(Base, TimestampMixin):
    """
    渠道成本配置表 sales_channel_configs

    channel 字段存 SalesChannel.value 字符串（避免 PostgreSQL ALTER TYPE 迁移复杂性）。
    brand_id=null 表示全集团默认；有 brand_id 时优先使用品牌级配置。
    """

    __tablename__ = "sales_channel_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(String(50), nullable=True, index=True)  # null=全集团默认
    channel = Column(String(30), nullable=False, index=True)  # SalesChannel.value
    platform_commission_pct = Column(Numeric(6, 4), nullable=False, default=0)  # 0.1800 = 18%
    delivery_cost_fen = Column(Integer, nullable=False, default=0)  # 配送费（分）
    packaging_cost_fen = Column(Integer, nullable=False, default=0)  # 包材费（分）
    is_active = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("brand_id", "channel", name="uq_channel_config_brand_channel"),
        Index("idx_channel_config_brand_id", "brand_id"),
        Index("idx_channel_config_channel", "channel"),
    )

    def __repr__(self):
        return (
            f"<SalesChannelConfig(brand_id={self.brand_id}, channel={self.channel}, "
            f"commission={self.platform_commission_pct})>"
        )
