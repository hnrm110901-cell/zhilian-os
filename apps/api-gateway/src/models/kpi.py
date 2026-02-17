"""
KPI Models
"""
from sqlalchemy import Column, String, Float, Date, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

from .base import Base, TimestampMixin


class KPI(Base, TimestampMixin):
    """KPI definition model"""

    __tablename__ = "kpis"

    id = Column(String(50), primary_key=True)  # e.g., KPI_REVENUE_001
    name = Column(String(100), nullable=False)
    category = Column(String(50), nullable=False)  # revenue, cost, efficiency, quality, customer
    description = Column(String(255))
    unit = Column(String(20))  # %, yuan, count, etc.

    # Target values
    target_value = Column(Float)
    warning_threshold = Column(Float)  # Yellow alert threshold
    critical_threshold = Column(Float)  # Red alert threshold

    # Calculation
    calculation_method = Column(String(50))  # sum, average, ratio, etc.
    is_active = Column(String(10), default="true")

    # Relationships
    records = relationship("KPIRecord", back_populates="kpi", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<KPI(id='{self.id}', name='{self.name}', category='{self.category}')>"


class KPIRecord(Base, TimestampMixin):
    """KPI record model - stores historical KPI values"""

    __tablename__ = "kpi_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kpi_id = Column(String(50), ForeignKey("kpis.id"), nullable=False, index=True)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)

    # Record details
    record_date = Column(Date, nullable=False, index=True)
    value = Column(Float, nullable=False)
    target_value = Column(Float)
    achievement_rate = Column(Float)  # value / target_value

    # Comparison
    previous_value = Column(Float)
    change_rate = Column(Float)  # (value - previous_value) / previous_value

    # Status
    status = Column(String(20))  # on_track, at_risk, off_track
    trend = Column(String(20))  # increasing, decreasing, stable, volatile

    # Metadata
    kpi_metadata = Column(JSON, default=dict)  # Renamed from metadata to avoid SQLAlchemy conflict

    # Relationships
    kpi = relationship("KPI", back_populates="records")

    def __repr__(self):
        return f"<KPIRecord(kpi_id='{self.kpi_id}', date='{self.record_date}', value={self.value})>"
