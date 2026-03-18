"""识客事件记录 — 每次顾客被识别（搜索/预订/POS触发）生成一条"""

import uuid
from sqlalchemy import Column, String, Index, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMP

from .base import Base, TimestampMixin


class MemberCheckIn(Base, TimestampMixin):
    """到店识客事件"""

    __tablename__ = "member_check_ins"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False)
    brand_id = Column(String(50), nullable=False, index=True)
    consumer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("consumer_identities.id"),
        nullable=False,
    )
    trigger_type = Column(String(20), nullable=False)  # manual_search | reservation | pos_webhook
    staff_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    checked_in_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
    profile_snapshot = Column(JSONB, nullable=True)

    __table_args__ = (
        Index("idx_check_ins_consumer", "consumer_id", "checked_in_at"),
        Index("idx_check_ins_store", "store_id", "checked_in_at"),
    )
