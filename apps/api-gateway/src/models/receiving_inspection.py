"""
收货验收模型
PurchaseReceiving     — 收货主表
PurchaseReceivingItem — 收货明细
ReceivingDispute      — 争议记录
"""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Enum, Float,
    ForeignKey, Integer, String, Text
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from .base import Base


class ReceivingStatus(str, enum.Enum):
    """收货单状态"""
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    DISPUTED = "disputed"
    CANCELLED = "cancelled"


class QualityStatus(str, enum.Enum):
    """质检状态"""
    PASS = "pass"
    CONDITIONAL = "conditional"
    REJECT = "reject"


class DisputeType(str, enum.Enum):
    """争议类型"""
    SHORTAGE = "shortage"
    QUALITY = "quality"
    PRICE = "price"
    WRONG_ITEM = "wrong_item"


class DisputeResolution(str, enum.Enum):
    """争议处理结果"""
    PENDING = "pending"
    ACCEPTED = "accepted"
    PARTIAL_CREDIT = "partial_credit"
    REJECTED = "rejected"
    RESOLVED = "resolved"


class PurchaseReceiving(Base):
    """收货主表"""

    __tablename__ = "purchase_receivings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # 自动生成 REC-YYYYMMDD-NNNN
    receiving_no = Column(String(30), unique=True, nullable=False, index=True)

    store_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    purchase_order_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    supplier_id = Column(UUID(as_uuid=True), nullable=True)
    supplier_name = Column(String(200), nullable=True)

    status = Column(
        Enum(ReceivingStatus, name="receiving_status_enum", create_type=False),
        nullable=False,
        default=ReceivingStatus.IN_PROGRESS,
        server_default="in_progress",
        index=True,
    )

    received_by = Column(UUID(as_uuid=True), nullable=False)
    received_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    invoice_no = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    total_amount_fen = Column(Integer, nullable=False, default=0, server_default="0")

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # 关联明细
    items = relationship(
        "PurchaseReceivingItem",
        back_populates="receiving",
        cascade="all, delete-orphan",
    )
    disputes = relationship(
        "ReceivingDispute",
        back_populates="receiving",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return (
            f"<PurchaseReceiving(id='{self.id}', "
            f"receiving_no='{self.receiving_no}', status='{self.status}')>"
        )


class PurchaseReceivingItem(Base):
    """收货明细"""

    __tablename__ = "purchase_receiving_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    receiving_id = Column(
        UUID(as_uuid=True),
        ForeignKey("purchase_receivings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    ingredient_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    ingredient_name = Column(String(200), nullable=False)
    unit = Column(String(20), nullable=False)

    ordered_qty = Column(Float, nullable=True)   # 订单数量（关联采购单时有值）
    received_qty = Column(Float, nullable=False)
    rejected_qty = Column(Float, nullable=False, default=0, server_default="0")

    unit_price_fen = Column(Integer, nullable=True)  # 单价（分）

    quality_status = Column(
        Enum(QualityStatus, name="quality_status_enum", create_type=False),
        nullable=False,
        default=QualityStatus.PASS,
        server_default="pass",
    )
    quality_notes = Column(String(500), nullable=True)

    temperature = Column(Float, nullable=True)      # 冷链温度（℃）
    expiry_date = Column(Date, nullable=True)
    batch_no = Column(String(100), nullable=True)

    has_shortage = Column(Boolean, nullable=False, default=False, server_default="false")
    has_quality_issue = Column(Boolean, nullable=False, default=False, server_default="false")

    # 关联主表
    receiving = relationship("PurchaseReceiving", back_populates="items")
    disputes = relationship(
        "ReceivingDispute",
        back_populates="item",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return (
            f"<PurchaseReceivingItem(id='{self.id}', "
            f"ingredient_name='{self.ingredient_name}', "
            f"received_qty={self.received_qty})>"
        )


class ReceivingDispute(Base):
    """争议记录"""

    __tablename__ = "receiving_disputes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    receiving_id = Column(
        UUID(as_uuid=True),
        ForeignKey("purchase_receivings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    item_id = Column(
        UUID(as_uuid=True),
        ForeignKey("purchase_receiving_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    dispute_type = Column(
        Enum(DisputeType, name="dispute_type_enum", create_type=False),
        nullable=False,
    )
    claimed_amount_fen = Column(Integer, nullable=True)  # 索赔金额（分）

    resolution = Column(
        Enum(DisputeResolution, name="dispute_resolution_enum", create_type=False),
        nullable=False,
        default=DisputeResolution.PENDING,
        server_default="pending",
    )

    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # 关联
    receiving = relationship("PurchaseReceiving", back_populates="disputes")
    item = relationship("PurchaseReceivingItem", back_populates="disputes")

    def __repr__(self):
        return (
            f"<ReceivingDispute(id='{self.id}', "
            f"dispute_type='{self.dispute_type}', "
            f"resolution='{self.resolution}')>"
        )
