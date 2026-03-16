"""
菜品渠道定价配置模型

DishChannelConfig — 菜品在特定销售渠道上的定价与上架状态
"""

import uuid

from sqlalchemy import Boolean, Column, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from src.models.base import Base, TimestampMixin


class DishChannelConfig(Base, TimestampMixin):
    """
    菜品渠道定价表 dish_channel_configs

    记录每道菜在各销售渠道的实际售价（分）和上架状态。
    与 SalesChannelConfig 配合计算毛利：
        revenue_fen = price_fen × (1 - platform_commission_pct)
    """

    __tablename__ = "dish_channel_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dish_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dishes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    channel = Column(String(30), nullable=False, index=True)  # SalesChannel.value
    price_fen = Column(Integer, nullable=False)  # 该渠道售价（分）
    is_available = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("dish_id", "channel", name="uq_dish_channel_config_dish_channel"),
        Index("idx_dish_channel_config_dish_id", "dish_id"),
        Index("idx_dish_channel_config_channel", "channel"),
    )

    def __repr__(self):
        return f"<DishChannelConfig(dish_id={self.dish_id}, channel={self.channel}, " f"price_fen={self.price_fen})>"
