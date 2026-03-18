"""OnboardingProcess — 入职流程主记录"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Date, ForeignKey, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from ..base import Base


class OnboardingProcess(Base):
    __tablename__ = "onboarding_processes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    person_id = Column(UUID(as_uuid=True),
                       ForeignKey("persons.id", ondelete="RESTRICT"),
                       nullable=False, index=True)
    org_node_id = Column(String(64),
                         ForeignKey("org_nodes.id", ondelete="RESTRICT"),
                         nullable=False, index=True)
    status = Column(String(20), nullable=False, default="draft",
                    server_default="'draft'",
                    comment="draft/pending_review/approved/active/rejected")
    offer_date = Column(Date, nullable=True)
    planned_start_date = Column(Date, nullable=False)
    actual_start_date = Column(Date, nullable=True)
    created_by = Column(String(100), nullable=False)
    extra_data = Column(JSONB, nullable=True, default=dict,
                        comment="扩展元数据，映射DB列名 extra_data")
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                        nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                        onupdate=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return (f"<OnboardingProcess(id={self.id}, "
                f"person_id={self.person_id}, status={self.status!r})>")
