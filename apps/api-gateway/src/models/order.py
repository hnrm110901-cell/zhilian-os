"""
Order Models
"""
from sqlalchemy import Column, String, Integer, ForeignKey, Enum, JSON, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
import enum
from datetime import datetime

from .base import Base, TimestampMixin


class OrderStatus(str, enum.Enum):
    """Order status"""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PREPARING = "preparing"
    READY = "ready"
    SERVED = "served"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Order(Base, TimestampMixin):
    """Order model"""

    __tablename__ = "orders"

    id = Column(String(50), primary_key=True)  # e.g., ORD_20240217_001
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)
    table_number = Column(String(20))
    customer_name = Column(String(100))
    customer_phone = Column(String(20))

    # Order details
    status = Column(Enum(OrderStatus), default=OrderStatus.PENDING, nullable=False, index=True)
    total_amount = Column(Integer, nullable=False)  # Amount in cents
    discount_amount = Column(Integer, default=0)
    final_amount = Column(Integer, nullable=False)

    # Timestamps
    order_time = Column(DateTime, default=datetime.utcnow, nullable=False)
    confirmed_at = Column(DateTime)
    completed_at = Column(DateTime)

    # Metadata
    notes = Column(String(500))
    order_metadata = Column(JSON, default=dict)  # Renamed from metadata to avoid SQLAlchemy conflict

    # Relationships
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Order(id='{self.id}', status='{self.status}', total={self.total_amount})>"


class OrderItem(Base, TimestampMixin):
    """Order item model"""

    __tablename__ = "order_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(String(50), ForeignKey("orders.id"), nullable=False, index=True)

    # Item details
    item_id = Column(String(50), nullable=False)
    item_name = Column(String(100), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Integer, nullable=False)  # Price in cents
    subtotal = Column(Integer, nullable=False)  # quantity * unit_price

    # Special requests
    notes = Column(String(255))
    customizations = Column(JSON, default=dict)

    # Relationships
    order = relationship("Order", back_populates="items")

    def __repr__(self):
        return f"<OrderItem(item_name='{self.item_name}', quantity={self.quantity})>"
