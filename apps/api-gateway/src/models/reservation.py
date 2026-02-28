"""
Reservation Model
"""
from sqlalchemy import Column, String, Integer, Date, Time, DateTime, ForeignKey, Enum, JSON, Index
from sqlalchemy.dialects.postgresql import UUID
import uuid
import enum

from .base import Base, TimestampMixin


class ReservationStatus(str, enum.Enum):
    """Reservation status"""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    ARRIVED = "arrived"
    SEATED = "seated"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class ReservationType(str, enum.Enum):
    """Reservation type"""
    REGULAR = "regular"  # Regular dining
    BANQUET = "banquet"  # Banquet/Event
    PRIVATE_ROOM = "private_room"  # Private room


class Reservation(Base, TimestampMixin):
    """Reservation model"""

    __tablename__ = "reservations"

    id = Column(String(50), primary_key=True)  # e.g., RES_20240217_001
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)

    # Customer information
    customer_name = Column(String(100), nullable=False)
    customer_phone = Column(String(20), nullable=False, index=True)
    customer_email = Column(String(100))

    # Reservation details
    reservation_type = Column(Enum(ReservationType), default=ReservationType.REGULAR, nullable=False)
    reservation_date = Column(Date, nullable=False, index=True)
    reservation_time = Column(Time, nullable=False)
    party_size = Column(Integer, nullable=False)  # Number of guests

    # Table/Room assignment
    table_number = Column(String(20))
    room_name = Column(String(50))

    # Status
    status = Column(Enum(ReservationStatus), default=ReservationStatus.PENDING, nullable=False, index=True)

    # Special requests
    special_requests = Column(String(500))
    dietary_restrictions = Column(String(255))

    # Banquet details (if applicable)
    banquet_details = Column(JSON, default=dict)  # Menu, budget, decorations, etc.
    estimated_budget = Column(Integer)  # Budget in cents

    # Banquet lifecycle stage (r11 migration)
    banquet_stage            = Column(String(20), nullable=True, index=True)
    banquet_stage_updated_at = Column(DateTime(timezone=False), nullable=True)
    room_locked_at           = Column(DateTime(timezone=False), nullable=True)
    signed_at                = Column(DateTime(timezone=False), nullable=True)
    deposit_paid             = Column(Integer, nullable=True)  # cents

    # Notes
    notes = Column(String(500))

    # Timestamps for status transitions
    arrival_time = Column(DateTime(timezone=True))
    cancelled_at = Column(DateTime(timezone=True))

    # Composite indexes for common query patterns
    __table_args__ = (
        Index('idx_reservation_store_date', 'store_id', 'reservation_date'),
        Index('idx_reservation_store_status', 'store_id', 'status'),
        Index('idx_reservation_date_status', 'reservation_date', 'status'),
    )

    def __repr__(self):
        return f"<Reservation(id='{self.id}', customer='{self.customer_name}', date='{self.reservation_date}')>"
