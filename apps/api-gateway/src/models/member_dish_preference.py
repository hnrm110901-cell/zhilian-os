"""菜品偏好聚合 — 由 POS 订单数据定期聚合而来"""

import uuid
from sqlalchemy import Boolean, Column, Integer, String, UniqueConstraint, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP

from .base import Base, TimestampMixin


class MemberDishPreference(Base, TimestampMixin):
    """顾客菜品偏好（聚合表）"""

    __tablename__ = "member_dish_preferences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    consumer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("consumer_identities.id"),
        nullable=False,
    )
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False)
    brand_id = Column(String(50), nullable=False, index=True)
    dish_name = Column(String(100), nullable=False)
    order_count = Column(Integer, nullable=False, default=0)
    last_ordered_at = Column(TIMESTAMP(timezone=True), nullable=True)
    is_favorite = Column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint("consumer_id", "store_id", "dish_name", name="uq_consumer_store_dish"),
    )
