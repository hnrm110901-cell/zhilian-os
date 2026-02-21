"""
供应链相关数据模型
"""
from sqlalchemy import Column, String, Float, Integer, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from .base import Base


class Supplier(Base):
    """供应商模型"""

    __tablename__ = "suppliers"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(200), nullable=False, index=True)
    code = Column(String(50), unique=True, index=True)
    category = Column(String(50), nullable=False, default="food")  # food, beverage, equipment, other
    contact_person = Column(String(100))
    phone = Column(String(20))
    email = Column(String(100))
    address = Column(Text)
    status = Column(String(20), nullable=False, default="active")  # active, inactive, suspended
    rating = Column(Float, default=5.0)  # 1-5 rating
    payment_terms = Column(String(50), default="net30")  # net30, net60, cod, etc.
    delivery_time = Column(Integer, default=3)  # 平均交货时间（天）
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关系
    purchase_orders = relationship("PurchaseOrder", back_populates="supplier")


class PurchaseOrder(Base):
    """采购订单模型"""

    __tablename__ = "purchase_orders"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    order_number = Column(String(50), unique=True, nullable=False, index=True)
    supplier_id = Column(String, ForeignKey("suppliers.id"), nullable=False)
    store_id = Column(String, ForeignKey("stores.id"), nullable=False)
    status = Column(
        String(20),
        nullable=False,
        default="pending",
    )  # pending, approved, ordered, shipped, delivered, completed, cancelled
    total_amount = Column(Integer, default=0)  # 总金额（分）
    items = Column(JSON, default=list)  # 订单项列表
    expected_delivery = Column(DateTime)
    actual_delivery = Column(DateTime)
    notes = Column(Text)
    created_by = Column(String)
    approved_by = Column(String)
    approved_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关系
    supplier = relationship("Supplier", back_populates="purchase_orders")
    store = relationship("Store")
