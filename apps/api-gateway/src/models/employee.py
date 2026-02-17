"""
Employee Model
"""
from sqlalchemy import Column, String, Boolean, JSON, ForeignKey, Date
from sqlalchemy.dialects.postgresql import UUID, ARRAY
import uuid

from .base import Base, TimestampMixin


class Employee(Base, TimestampMixin):
    """Employee model"""

    __tablename__ = "employees"

    id = Column(String(50), primary_key=True)  # e.g., EMP001
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    phone = Column(String(20))
    email = Column(String(100))

    # Employment details
    position = Column(String(50))  # waiter, chef, cashier, manager
    skills = Column(ARRAY(String), default=list)  # List of skills
    hire_date = Column(Date)
    is_active = Column(Boolean, default=True, nullable=False)

    # Work preferences
    preferences = Column(JSON, default=dict)  # Preferred shifts, days off, etc.

    # Performance metrics
    performance_score = Column(String(10))  # Stored as string
    training_completed = Column(ARRAY(String), default=list)

    def __repr__(self):
        return f"<Employee(id='{self.id}', name='{self.name}', position='{self.position}')>"
