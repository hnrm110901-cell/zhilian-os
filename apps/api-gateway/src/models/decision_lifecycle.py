"""
Decision Lifecycle — 决策全生命周期追踪
"""

import uuid

from sqlalchemy import Column, Date, DateTime, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID

from .base import Base, TimestampMixin


class DecisionLifecycle(Base, TimestampMixin):
    """决策生命周期: generated → pushed → viewed → accepted/rejected → executed → measured"""

    __tablename__ = "decision_lifecycle"

    decision_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=False, index=True)
    decision_date = Column(Date, nullable=False)
    source = Column(String(30), nullable=False)  # cost_truth/unified_brain/waste_guard/labor/inventory
    title = Column(String(100), nullable=False)
    action = Column(Text, nullable=False)
    expected_saving_yuan = Column(Numeric(10, 2), nullable=False)
    confidence_pct = Column(Integer, nullable=False)
    severity = Column(String(10), nullable=False)  # critical/warning/watch/ok
    executor = Column(String(50))  # 厨师长/店长/...
    deadline_hours = Column(Integer)
    category = Column(String(20), nullable=False)  # cost/labor/inventory/waste/revenue
    status = Column(String(20), nullable=False, default="generated")
    # Lifecycle timestamps
    pushed_at = Column(DateTime(timezone=True))
    push_channel = Column(String(20))  # wechat/app/sms
    viewed_at = Column(DateTime(timezone=True))
    accepted_at = Column(DateTime(timezone=True))
    rejected_at = Column(DateTime(timezone=True))
    reject_reason = Column(String(100))
    executed_at = Column(DateTime(timezone=True))
    measured_at = Column(DateTime(timezone=True))
    # Outcome
    actual_saving_yuan = Column(Numeric(10, 2))
    measurement_method = Column(Text)
