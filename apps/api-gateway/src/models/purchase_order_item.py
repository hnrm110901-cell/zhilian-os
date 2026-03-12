"""
Purchase Order Items — 采购单明细行
"""
from sqlalchemy import Column, String, Integer, Numeric
from sqlalchemy.dialects.postgresql import UUID
import uuid

from .base import Base, TimestampMixin


class PurchaseOrderItem(Base, TimestampMixin):
    """采购单明细"""
    __tablename__ = "purchase_order_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    po_id = Column(String(50), nullable=False, index=True)
    ingredient_id = Column(String(50), nullable=False)
    ordered_qty = Column(Numeric(12, 4), nullable=False)
    received_qty = Column(Numeric(12, 4))
    rejected_qty = Column(Numeric(12, 4))
    unit = Column(String(10), nullable=False)
    unit_price_fen = Column(Integer, nullable=False)
    line_amount_fen = Column(Integer, nullable=False)
    reject_reason = Column(String(50))
    batch_id = Column(UUID(as_uuid=True))
