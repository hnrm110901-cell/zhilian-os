"""LeaveBalance — 假期余额账户"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Numeric, ForeignKey, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from ..base import Base


class LeaveBalance(Base):
    __tablename__ = "leave_balances"
    __table_args__ = {"extend_existing": True}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assignment_id = Column(UUID(as_uuid=True),
                           ForeignKey("employment_assignments.id", ondelete="RESTRICT"),
                           nullable=False, index=True)
    leave_type = Column(String(30), nullable=False)
    year = Column(Integer, nullable=False)
    total_days = Column(Numeric(5, 1), nullable=False, default=0, server_default="0")
    used_days = Column(Numeric(5, 1), nullable=False, default=0, server_default="0")
    remaining_days = Column(Numeric(5, 1), nullable=False, default=0, server_default="0")
    accrual_rule = Column(JSONB, nullable=True, default=dict,
                          comment="按工龄/用工性质的配额规则")
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                        nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                        onupdate=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return (f"<LeaveBalance(id={self.id}, assignment_id={self.assignment_id}, "
                f"leave_type={self.leave_type!r}, year={self.year})>")
