"""ApprovalInstance — HR审批实例"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, ForeignKey, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from ..base import Base


class ApprovalInstance(Base):
    __tablename__ = "approval_instances"
    __table_args__ = {"extend_existing": True}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id = Column(UUID(as_uuid=True),
                         ForeignKey("approval_templates.id", ondelete="RESTRICT"),
                         nullable=False, index=True)
    resource_type = Column(String(30), nullable=False, index=True,
                           comment="onboarding/offboarding/transfer")
    resource_id = Column(UUID(as_uuid=True), nullable=False, index=True,
                         comment="对应onboarding_process.id / offboarding_process.id等")
    status = Column(String(20), nullable=False, default="pending",
                    server_default="'pending'",
                    comment="pending/approved/rejected/cancelled")
    current_step = Column(Integer, nullable=False, default=1, server_default="1")
    created_by = Column(String(100), nullable=False)
    extra_data = Column(JSONB, nullable=True, default=dict,
                        comment="申请摘要供审批人快速判断")
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                        nullable=False)
    completed_at = Column(TIMESTAMP(timezone=True), nullable=True)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                        onupdate=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return (f"<ApprovalInstance(id={self.id}, resource_type={self.resource_type!r}, "
                f"status={self.status!r})>")
