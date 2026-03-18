"""ApprovalStepRecord — 审批步骤记录"""
import uuid
from sqlalchemy import Column, String, Integer, Text, ForeignKey, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID
from ..base import Base


class ApprovalStepRecord(Base):
    __tablename__ = "approval_step_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    instance_id = Column(UUID(as_uuid=True),
                         ForeignKey("approval_instances.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    step = Column(Integer, nullable=False)
    approver_id = Column(String(100), nullable=False)
    approver_name = Column(String(100), nullable=False)
    action = Column(String(20), nullable=False, default="pending",
                    server_default="'pending'",
                    comment="pending/approved/rejected/delegated")
    comment = Column(Text, nullable=True)
    acted_at = Column(TIMESTAMP(timezone=True), nullable=True)
    notified_at = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                        nullable=False)

    def __repr__(self) -> str:
        return (f"<ApprovalStepRecord(id={self.id}, instance_id={self.instance_id}, "
                f"step={self.step}, action={self.action!r})>")
