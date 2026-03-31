"""
门店间调拨模型
InterStoreTransferRequest — 调拨申请主表
InterStoreTransferItem    — 调拨明细
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float, ForeignKey,
    Integer, String, Text
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from .base import Base


class TransferStatus(str, enum.Enum):
    """调拨单状态"""
    DRAFT = "draft"
    PENDING = "pending"
    APPROVED = "approved"
    DISPATCHED = "dispatched"
    RECEIVED = "received"
    PARTIAL = "partial"
    CANCELLED = "cancelled"


class InterStoreTransferRequest(Base):
    """调拨申请主表"""

    __tablename__ = "inter_store_transfer_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # 自动生成 IST-YYYYMMDD-NNNN
    transfer_no = Column(String(30), unique=True, nullable=False, index=True)

    from_store_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    to_store_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    brand_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # 只允许同品牌内调拨

    status = Column(
        Enum(TransferStatus, name="transfer_status_enum", create_type=False),
        nullable=False,
        default=TransferStatus.PENDING,
        server_default="pending",
        index=True,
    )

    requested_by = Column(UUID(as_uuid=True), nullable=False)
    approved_by = Column(UUID(as_uuid=True), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    dispatched_at = Column(DateTime, nullable=True)
    received_at = Column(DateTime, nullable=True)

    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # 关联明细
    items = relationship(
        "InterStoreTransferItem",
        back_populates="transfer",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return (
            f"<InterStoreTransferRequest(id='{self.id}', "
            f"transfer_no='{self.transfer_no}', status='{self.status}')>"
        )


class InterStoreTransferItem(Base):
    """调拨明细"""

    __tablename__ = "inter_store_transfer_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transfer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("inter_store_transfer_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    ingredient_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    ingredient_name = Column(String(200), nullable=False)  # 冗余存储，防止食材被删

    unit = Column(String(20), nullable=False)
    requested_qty = Column(Float, nullable=False)
    dispatched_qty = Column(Float, nullable=True)   # 实际发出量
    received_qty = Column(Float, nullable=True)     # 实际收到量

    unit_cost_fen = Column(Integer, nullable=True)  # 调拨内部成本价（分）

    # received_qty - dispatched_qty，负数表示运输损耗
    qty_variance = Column(Float, nullable=True)
    variance_reason = Column(String(500), nullable=True)

    # 关联主表
    transfer = relationship("InterStoreTransferRequest", back_populates="items")

    def __repr__(self):
        return (
            f"<InterStoreTransferItem(id='{self.id}', "
            f"ingredient_name='{self.ingredient_name}', "
            f"requested_qty={self.requested_qty})>"
        )
