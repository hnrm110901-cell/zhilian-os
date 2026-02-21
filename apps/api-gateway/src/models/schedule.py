"""
Schedule Models
"""
from sqlalchemy import Column, String, Date, Time, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

from .base import Base, TimestampMixin


class Schedule(Base, TimestampMixin):
    """Schedule model - represents a daily schedule for a store"""

    __tablename__ = "schedules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)
    schedule_date = Column(Date, nullable=False, index=True)

    # Schedule metadata
    total_employees = Column(String(10))
    total_hours = Column(String(10))
    is_published = Column(Boolean, default=False)
    published_by = Column(String(100))

    # Relationships
    shifts = relationship("Shift", back_populates="schedule", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Schedule(store_id='{self.store_id}', date='{self.schedule_date}')>"


class Shift(Base, TimestampMixin):
    """Shift model - represents an employee's shift"""

    __tablename__ = "shifts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    schedule_id = Column(UUID(as_uuid=True), ForeignKey("schedules.id"), nullable=False, index=True)
    employee_id = Column(String(50), ForeignKey("employees.id"), nullable=False, index=True)

    # Shift details
    shift_type = Column(String(20), nullable=False)  # morning, afternoon, evening
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    position = Column(String(50))  # Role for this shift

    # Status
    is_confirmed = Column(Boolean, default=False)
    is_completed = Column(Boolean, default=False)

    # Notes
    notes = Column(String(255))

    # Relationships
    schedule = relationship("Schedule", back_populates="shifts")

    def __repr__(self):
        return f"<Shift(employee_id='{self.employee_id}', type='{self.shift_type}')>"
