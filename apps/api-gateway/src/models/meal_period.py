"""
MealPeriod Model — 门店营业时段（早餐/午餐/晚餐/深夜）
"""
from sqlalchemy import Column, String, SmallInteger, Boolean, ForeignKey, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
import uuid

from .base import Base, TimestampMixin


class MealPeriod(Base, TimestampMixin):
    """门店营业时段模型"""

    __tablename__ = "meal_periods"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)
    name = Column(String(50), nullable=False)          # 如"早餐"/"午餐"/"晚餐"/"深夜"
    start_hour = Column(SmallInteger, nullable=False)  # 0-23
    end_hour = Column(SmallInteger, nullable=False)    # 0-23（可 > start_hour 跨午夜）
    is_active = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("store_id", "name", name="uq_meal_period_store_name"),
        Index("idx_meal_period_store_id", "store_id"),
        Index("idx_meal_period_store_active", "store_id", "is_active"),
    )

    def __repr__(self):
        return f"<MealPeriod(store_id='{self.store_id}', name='{self.name}', {self.start_hour}-{self.end_hour})>"
