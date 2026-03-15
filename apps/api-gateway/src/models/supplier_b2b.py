"""
供应商B2B采购单模型
B2BPurchaseOrder（采购单）+ B2BPurchaseItem（采购单明细）
"""
import uuid
from datetime import datetime, date
from sqlalchemy import (
    Column, String, Integer, Text, Date, DateTime,
    ForeignKey, Index, Numeric,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.models.base import Base
from src.models.mixins import TimestampMixin


class B2BPurchaseOrder(Base, TimestampMixin):
    """供应商采购单（B2B）"""

    __tablename__ = "b2b_purchase_orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(String(50), nullable=False, index=True)
    store_id = Column(String(50), nullable=False, index=True)
    supplier_id = Column(String(50), nullable=False, index=True)
    supplier_name = Column(String(100), nullable=False)

    # 采购单号：PO-YYYYMMDD-XXXX（唯一）
    order_number = Column(String(50), unique=True, nullable=False, index=True)

    # 状态：draft / submitted / confirmed / shipping / received / completed / cancelled
    status = Column(String(20), nullable=False, default="draft")

    # 金额（单位：分）
    total_amount_fen = Column(Integer, nullable=False, default=0)

    # 交货日期
    expected_delivery_date = Column(Date, nullable=True)
    actual_delivery_date = Column(Date, nullable=True)

    # 备注
    notes = Column(Text, nullable=True)

    # 关键时间节点
    submitted_at = Column(DateTime, nullable=True)
    confirmed_at = Column(DateTime, nullable=True)
    received_at = Column(DateTime, nullable=True)

    # 关联明细
    items = relationship("B2BPurchaseItem", back_populates="order", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_b2b_po_brand_status", "brand_id", "status"),
        Index("ix_b2b_po_supplier", "brand_id", "supplier_id"),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "brand_id": self.brand_id,
            "store_id": self.store_id,
            "supplier_id": self.supplier_id,
            "supplier_name": self.supplier_name,
            "order_number": self.order_number,
            "status": self.status,
            "total_amount_fen": self.total_amount_fen,
            "expected_delivery_date": self.expected_delivery_date.isoformat() if self.expected_delivery_date else None,
            "actual_delivery_date": self.actual_delivery_date.isoformat() if self.actual_delivery_date else None,
            "notes": self.notes,
            "submitted_at": self.submitted_at.isoformat() if self.submitted_at else None,
            "confirmed_at": self.confirmed_at.isoformat() if self.confirmed_at else None,
            "received_at": self.received_at.isoformat() if self.received_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "items": [item.to_dict() for item in self.items] if self.items else [],
        }


class B2BPurchaseItem(Base, TimestampMixin):
    """采购单明细"""

    __tablename__ = "b2b_purchase_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(UUID(as_uuid=True), ForeignKey("b2b_purchase_orders.id", ondelete="CASCADE"), nullable=False, index=True)

    ingredient_name = Column(String(100), nullable=False)
    ingredient_id = Column(String(50), nullable=True)

    quantity = Column(Numeric(10, 2), nullable=False)
    unit = Column(String(20), nullable=False, default="kg")
    unit_price_fen = Column(Integer, nullable=False, default=0)
    amount_fen = Column(Integer, nullable=False, default=0)

    # 收货信息
    received_quantity = Column(Numeric(10, 2), nullable=True)
    # 质量状态：accepted / rejected / partial
    quality_status = Column(String(20), nullable=True)

    # 关联
    order = relationship("B2BPurchaseOrder", back_populates="items")

    def to_dict(self):
        return {
            "id": str(self.id),
            "order_id": str(self.order_id),
            "ingredient_name": self.ingredient_name,
            "ingredient_id": self.ingredient_id,
            "quantity": float(self.quantity) if self.quantity else 0,
            "unit": self.unit,
            "unit_price_fen": self.unit_price_fen,
            "amount_fen": self.amount_fen,
            "received_quantity": float(self.received_quantity) if self.received_quantity else None,
            "quality_status": self.quality_status,
        }
