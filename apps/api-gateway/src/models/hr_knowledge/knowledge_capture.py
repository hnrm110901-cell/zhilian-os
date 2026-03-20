"""KnowledgeCapture — 对话式知识采集记录（WF-4）"""
import uuid
from sqlalchemy import Column, String, Text, Float, ForeignKey, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from ..base import Base


class KnowledgeCapture(Base):
    __tablename__ = "knowledge_captures"
    __table_args__ = {"extend_existing": True}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    person_id = Column(UUID(as_uuid=True),
                       ForeignKey("persons.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    trigger_type = Column(String(30), nullable=True,
                          comment=("exit/monthly_review/incident/onboarding/"
                                   "growth_review/talent_assessment/legacy_import"))
    raw_dialogue = Column(Text, nullable=True)
    context = Column(Text, nullable=True)
    action = Column(Text, nullable=True)
    result = Column(Text, nullable=True)
    structured_output = Column(JSONB, nullable=True)
    knowledge_node_id = Column(UUID(as_uuid=True), nullable=True)
    quality_score = Column(Float, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                        nullable=False)

    def __repr__(self) -> str:
        return f"<KnowledgeCapture(id={self.id}, trigger={self.trigger_type!r})>"
