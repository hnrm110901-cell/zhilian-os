"""
Order Models
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

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

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)  # DB stores UUID
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)
    table_number = Column(String(20))
    customer_name = Column(String(100))
    customer_phone = Column(String(20))

    # CDP 统一消费者ID（Sprint 1 地基层）
    consumer_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    # Order details
    status = Column(String(20), default=OrderStatus.PENDING.value, nullable=False, index=True)
    total_amount = Column(Numeric(10, 2), nullable=False)  # stored as yuan in DB
    discount_amount = Column(Integer, default=0)
    final_amount = Column(Integer)

    # Timestamps
    order_time = Column(DateTime, default=datetime.utcnow, nullable=False)
    confirmed_at = Column(DateTime)
    completed_at = Column(DateTime)

    # Staff tracking
    waiter_id = Column(String(50), index=True)  # 服务员ID（用于员工绩效基线计算）

    # 销售渠道（Task2 P0 字段）
    sales_channel = Column(String(30), nullable=True, index=True)

    # Metadata
    notes = Column(String(500))
    order_metadata = Column(JSON, default=dict)  # Renamed from metadata to avoid SQLAlchemy conflict

    # Relationships
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")

    # Composite indexes for common query patterns
    __table_args__ = (
        Index("idx_order_store_status", "store_id", "status"),
        Index("idx_order_store_time", "store_id", "order_time"),
        Index("idx_order_status_time", "status", "order_time"),
        Index("idx_order_store_waiter", "store_id", "waiter_id"),
    )

    def __repr__(self):
        return f"<Order(id='{self.id}', status='{self.status}', total={self.total_amount})>"


class OrderItem(Base, TimestampMixin):
    """Order item model"""

    __tablename__ = "order_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False, index=True)

    # Item details
    item_id = Column(String(50), nullable=False)
    item_name = Column(String(100), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)  # yuan in DB
    subtotal = Column(Numeric(10, 2), nullable=False)  # yuan in DB

    # 食材实际成本（BOM 理论成本）
    food_cost_actual = Column(Integer, nullable=True)  # 分，BOM 理论成本
    gross_margin = Column(Numeric(6, 4), nullable=True)  # 毛利率 0.0000–1.0000

    # Special requests
    notes = Column(String(255))
    customizations = Column(JSON, default=dict)

    # Relationships
    order = relationship("Order", back_populates="items")

    def __repr__(self):
        return f"<OrderItem(item_name='{self.item_name}', quantity={self.quantity})>"
