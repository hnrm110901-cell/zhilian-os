"""LeaveRequest — 请假申请"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Numeric, Text, ForeignKey, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID
from ..base import Base


class LeaveRequest(Base):
    __tablename__ = "leave_requests"
    __table_args__ = {"extend_existing": True}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assignment_id = Column(UUID(as_uuid=True),
                           ForeignKey("employment_assignments.id", ondelete="RESTRICT"),
                           nullable=False, index=True)
    leave_type = Column(String(30), nullable=False,
                        comment="annual/sick/personal/marriage/maternity/paternity/bereavement")
    start_datetime = Column(TIMESTAMP(timezone=True), nullable=False)
    end_datetime = Column(TIMESTAMP(timezone=True), nullable=False)
    days = Column(Numeric(4, 1), nullable=False, comment="支持0.5天")
    reason = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="pending",
                    server_default="'pending'",
                    comment="pending/approved/rejected/cancelled")
    approved_by = Column(String(100), nullable=True)
    created_by = Column(String(100), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                        nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                        onupdate=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return (f"<LeaveRequest(id={self.id}, assignment_id={self.assignment_id}, "
                f"leave_type={self.leave_type!r}, status={self.status!r})>")
