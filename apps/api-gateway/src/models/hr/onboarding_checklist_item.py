"""OnboardingChecklistItem — 入职清单项"""
import uuid
from sqlalchemy import Column, String, Boolean, Integer, ForeignKey, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID
from ..base import Base


class OnboardingChecklistItem(Base):
    __tablename__ = "onboarding_checklist_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    process_id = Column(UUID(as_uuid=True),
                        ForeignKey("onboarding_processes.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    item_type = Column(String(30), nullable=False,
                       comment="document/training/contract_sign/system_setup/equipment")
    title = Column(String(200), nullable=False)
    required = Column(Boolean, nullable=False, default=True, server_default="true")
    completed_at = Column(TIMESTAMP(timezone=True), nullable=True)
    completed_by = Column(String(100), nullable=True)
    file_url = Column(String(500), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                        nullable=False)

    def __repr__(self) -> str:
        return (f"<OnboardingChecklistItem(id={self.id}, "
                f"process_id={self.process_id}, item_type={self.item_type!r})>")
