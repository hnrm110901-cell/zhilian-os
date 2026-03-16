"""
Inventory Models
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from .base import Base, TimestampMixin


class InventoryStatus(str, enum.Enum):
    """Inventory status"""

    NORMAL = "normal"
    LOW = "low"
    CRITICAL = "critical"
    OUT_OF_STOCK = "out_of_stock"


class TransactionType(str, enum.Enum):
    """Inventory transaction type"""

    PURCHASE = "purchase"  # 采购入库
    USAGE = "usage"  # 使用出库
    WASTE = "waste"  # 损耗
    ADJUSTMENT = "adjustment"  # 盘点调整
    TRANSFER = "transfer"  # 调拨


class InventoryItem(Base, TimestampMixin):
    """Inventory item model"""

    __tablename__ = "inventory_items"

    id = Column(String(50), primary_key=True)  # e.g., INV_001
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)

    # Item details
    name = Column(String(100), nullable=False)
    category = Column(String(50))  # vegetables, meat, seafood, dry_goods, etc.
    unit = Column(String(20))  # kg, piece, bottle, etc.

    # Stock levels
    current_quantity = Column(Float, nullable=False, default=0)
    min_quantity = Column(Float, nullable=False)  # Reorder point
    max_quantity = Column(Float)  # Maximum stock level

    # Pricing
    unit_cost = Column(Integer)  # Cost in cents

    # Status — stored as VARCHAR in DB, not PostgreSQL ENUM
    status = Column(String(20), default=InventoryStatus.NORMAL.value, nullable=False, index=True)

    # Supplier info
    supplier_name = Column(String(100))
    supplier_contact = Column(String(100))

    # Relationships
    transactions = relationship("InventoryTransaction", back_populates="item", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<InventoryItem(id='{self.id}', name='{self.name}', quantity={self.current_quantity})>"


class InventoryTransaction(Base, TimestampMixin):
    """Inventory transaction model"""

    __tablename__ = "inventory_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    item_id = Column(String(50), ForeignKey("inventory_items.id"), nullable=False, index=True)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)

    # Transaction details — stored as VARCHAR in DB
    transaction_type = Column(String(20), nullable=False, index=True)
    quantity = Column(Float, nullable=False)  # Positive for in, negative for out
    unit_cost = Column(Integer)  # Cost in cents
    total_cost = Column(Integer)  # quantity * unit_cost

    # Before/After quantities
    quantity_before = Column(Float, nullable=False)
    quantity_after = Column(Float, nullable=False)

    # Reference
    reference_id = Column(String(100))  # Order ID, Purchase Order ID, etc.
    notes = Column(String(500))

    # User who performed the transaction
    performed_by = Column(String(100))
    transaction_time = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    item = relationship("InventoryItem", back_populates="transactions")

    def __repr__(self):
        return f"<InventoryTransaction(type='{self.transaction_type}', quantity={self.quantity})>"
