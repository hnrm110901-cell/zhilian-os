"""发券记录 + 核销记录 + ROI日汇总 — P2"""

import uuid
from sqlalchemy import Column, Date, Integer, String, ForeignKey, UniqueConstraint, Index, text
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP

from .base import Base, TimestampMixin


class CouponDistribution(Base, TimestampMixin):
    """统一发券记录（微生活券 + 服务券）"""

    __tablename__ = "coupon_distributions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False)
    brand_id = Column(String(50), nullable=False, index=True)
    consumer_id = Column(UUID(as_uuid=True), ForeignKey("consumer_identities.id"), nullable=False)
    coupon_source = Column(String(20), nullable=False)  # weishenghuo | service_voucher
    coupon_id = Column(String(100), nullable=False)
    coupon_name = Column(String(100), nullable=False)
    coupon_value_fen = Column(Integer, default=0)
    distributed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    distributed_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))
    # marketing_task_id — P3 阶段通过 ALTER TABLE 添加

    __table_args__ = (
        Index("idx_dist_consumer", "consumer_id", "distributed_at"),
        Index("idx_dist_store", "store_id", "distributed_at"),
    )


class CouponRedemption(Base, TimestampMixin):
    """核销记录"""

    __tablename__ = "coupon_redemptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    distribution_id = Column(UUID(as_uuid=True), ForeignKey("coupon_distributions.id"), nullable=False)
    order_id = Column(String(100), nullable=True)
    order_amount_fen = Column(Integer, nullable=True)
    redeemed_at = Column(TIMESTAMP(timezone=True), nullable=False)


class CouponRoiDaily(Base, TimestampMixin):
    """ROI 日汇总"""

    __tablename__ = "coupon_roi_daily"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    date = Column(Date, nullable=False)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False)
    brand_id = Column(String(50), nullable=False)
    staff_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    distributed_count = Column(Integer, default=0)
    distributed_value_fen = Column(Integer, default=0)
    redeemed_count = Column(Integer, default=0)
    redeemed_value_fen = Column(Integer, default=0)
    driven_gmv_fen = Column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint("date", "store_id", "staff_id", name="uq_roi_daily"),
    )
