"""
Store Model
"""
from sqlalchemy import Column, String, Boolean, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

from .base import Base, TimestampMixin


class Store(Base, TimestampMixin):
    """Store/Restaurant model"""

    __tablename__ = "stores"

    id = Column(String(50), primary_key=True)  # e.g., STORE001
    name = Column(String(100), nullable=False)
    address = Column(String(255))
    phone = Column(String(20))
    manager_id = Column(UUID(as_uuid=True))
    is_active = Column(Boolean, default=True, nullable=False)

    # Store configuration
    config = Column(JSON, default=dict)  # Opening hours, capacity, etc.

    # Business metrics
    monthly_revenue_target = Column(String(20))  # Stored as string to avoid precision issues
    cost_ratio_target = Column(String(10))

    def __repr__(self):
        return f"<Store(id='{self.id}', name='{self.name}')>"
