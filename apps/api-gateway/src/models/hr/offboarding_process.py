"""OffboardingProcess — 离职流程主记录"""
import uuid
from sqlalchemy import Column, String, Date, Integer, Text, Boolean, ForeignKey, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID
from ..base import Base


class OffboardingProcess(Base):
    __tablename__ = "offboarding_processes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assignment_id = Column(UUID(as_uuid=True),
                           ForeignKey("employment_assignments.id", ondelete="RESTRICT"),
                           nullable=False, index=True)
    reason = Column(String(30), nullable=False,
                    comment="resignation/termination/contract_end/retirement/mutual")
    apply_date = Column(Date, nullable=False)
    planned_last_day = Column(Date, nullable=False)
    actual_last_day = Column(Date, nullable=True)
    status = Column(String(20), nullable=False, default="pending",
                    server_default="'pending'",
                    comment="pending/approved/completed/cancelled")
    knowledge_capture_triggered = Column(Boolean, nullable=False, default=False,
                                         server_default="false")
    settlement_amount_fen = Column(Integer, nullable=False, default=0,
                                   server_default="0",
                                   comment="结算金额（分）")
    notes = Column(Text, nullable=True)
    created_by = Column(String(100), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                        nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                        nullable=False)

    def __repr__(self) -> str:
        return (f"<OffboardingProcess(id={self.id}, "
                f"assignment_id={self.assignment_id}, status={self.status!r})>")
