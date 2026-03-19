"""屯象服务券 — P2 自建体验类券（赠小菜/试吃/生日惊喜）"""

import uuid
from sqlalchemy import Boolean, Column, Integer, String, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP, JSONB

from .base import Base, TimestampMixin


class ServiceVoucherTemplate(Base, TimestampMixin):
    """服务券模板"""

    __tablename__ = "service_voucher_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(String(50), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    voucher_type = Column(String(20), nullable=False)  # complimentary_dish | tasting | birthday_gift
    description = Column(Text, nullable=True)
    valid_days = Column(Integer, nullable=False, default=7)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    is_active = Column(Boolean, default=True, index=True)


class ServiceVoucher(Base, TimestampMixin):
    """服务券实例（状态机：created → sent → used → expired）"""

    __tablename__ = "service_vouchers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id = Column(UUID(as_uuid=True), ForeignKey("service_voucher_templates.id"), nullable=False)
    consumer_id = Column(UUID(as_uuid=True), ForeignKey("consumer_identities.id"), nullable=False)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False)
    brand_id = Column(String(50), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="created")  # created | sent | used | expired
    issued_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    used_at = Column(TIMESTAMP(timezone=True), nullable=True)
    confirmed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    expires_at = Column(TIMESTAMP(timezone=True), nullable=False)
