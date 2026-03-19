"""
MealPeriod Model — 门店营业时段（早餐/午餐/晚餐/深夜）
含预订容量管理：每餐段可接待桌数、最大客数、预订间隔
"""

import uuid

from sqlalchemy import Boolean, Column, ForeignKey, Index, Integer, SmallInteger, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from .base import Base, TimestampMixin


class MealPeriod(Base, TimestampMixin):
    """门店营业时段模型（含预订容量配置）"""

    __tablename__ = "meal_periods"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)
    name = Column(String(50), nullable=False)  # 如"早餐"/"午餐"/"晚餐"/"深夜"
    start_hour = Column(SmallInteger, nullable=False)  # 0-23
    end_hour = Column(SmallInteger, nullable=False)  # 0-23（可 > start_hour 跨午夜）
    is_active = Column(Boolean, nullable=False, default=True)

    # ── 预订容量配置（P0 餐段配置补齐） ──
    max_tables = Column(Integer, nullable=True)  # 该餐段最大可预订桌数
    max_guests = Column(Integer, nullable=True)  # 该餐段最大接待客数
    reservation_interval = Column(SmallInteger, default=30)  # 预订时间间隔（分钟），如每30分钟一个时段
    last_reservation_offset = Column(SmallInteger, default=60)  # 最晚预订时间距结束前N分钟（如结束前1小时停止预订）
    overbooking_ratio = Column(SmallInteger, default=0)  # 超订比例（%），如10表示允许超订10%

    __table_args__ = (
        UniqueConstraint("store_id", "name", name="uq_meal_period_store_name"),
        Index("idx_meal_period_store_id", "store_id"),
        Index("idx_meal_period_store_active", "store_id", "is_active"),
    )

    def __repr__(self):
        return f"<MealPeriod(store_id='{self.store_id}', name='{self.name}', {self.start_hour}-{self.end_hour})>"
