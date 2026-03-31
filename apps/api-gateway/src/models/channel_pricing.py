"""
多渠道独立定价模型

DishChannelPrice   — 渠道定价（按门店+菜品+渠道三维定价）
TimePeriodPrice    — 时段定价规则（午市/晚市/早餐/深夜/节假日/周末）
"""

import uuid

from sqlalchemy import (
    Boolean,
    Column,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

from src.models.base import Base, TimestampMixin


class DishChannelPrice(Base, TimestampMixin):
    """
    渠道定价 dish_channel_prices

    同一菜品在不同渠道（堂食/美团/饿了么/抖音/小程序/企业）可设置不同价格。
    UniqueConstraint 确保同一门店+菜品+渠道只有一条定价记录（upsert 场景）。
    """

    __tablename__ = "dish_channel_prices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    dish_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    channel = Column(
        Enum(
            "dine_in",
            "meituan",
            "eleme",
            "douyin",
            "miniprogram",
            "corporate",
            name="dish_channel_enum",
        ),
        nullable=False,
    )
    price_fen = Column(Integer, nullable=False)  # 渠道价格（分）
    is_active = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint(
            "store_id", "dish_id", "channel", name="uq_dish_channel_price"
        ),
        Index("idx_dish_channel_price_store_id", "store_id"),
        Index("idx_dish_channel_price_dish_id", "dish_id"),
        Index("idx_dish_channel_price_channel", "channel"),
    )

    def __repr__(self):
        return (
            f"<DishChannelPrice(store_id={self.store_id}, "
            f"dish_id={self.dish_id}, channel={self.channel}, "
            f"price={self.price_fen})>"
        )


class TimePeriodPrice(Base, TimestampMixin):
    """
    时段定价规则 time_period_prices

    支持按时间段+星期几组合设置折扣率或固定价格映射。
    weekdays 存储适用的星期几列表，1=周一，7=周日。
    apply_to_dishes=NULL 表示规则适用于全部菜品。
    fixed_price_json 格式：{"dish_id_str": price_fen_int, ...}
    """

    __tablename__ = "time_period_prices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    period_type = Column(
        Enum(
            "lunch",
            "dinner",
            "breakfast",
            "late_night",
            "holiday",
            "weekend",
            name="time_period_type_enum",
        ),
        nullable=False,
    )
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    weekdays = Column(ARRAY(Integer), nullable=False)  # [1-7]，1=周一
    apply_to_dishes = Column(ARRAY(UUID(as_uuid=True)), nullable=True)  # NULL=全部菜品
    discount_rate = Column(Float, nullable=True)  # 折扣率，如 0.8=八折
    fixed_price_json = Column(JSONB, nullable=True)  # {dish_id_str: price_fen_int}
    is_active = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        Index("idx_time_period_price_store_id", "store_id"),
        Index("idx_time_period_price_period_type", "period_type"),
        Index("idx_time_period_price_is_active", "is_active"),
    )

    def __repr__(self):
        return (
            f"<TimePeriodPrice(store_id={self.store_id}, "
            f"name={self.name}, period_type={self.period_type})>"
        )
