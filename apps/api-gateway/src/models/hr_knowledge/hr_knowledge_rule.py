"""HrKnowledgeRule — HR专属行业经验库

与现有 knowledge_rules 表共存，互不干扰。
现有表用于通用规则引擎；本表专用于HR领域AGI推理。
"""
import uuid
from sqlalchemy import Column, String, Float, Boolean, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from ..base import Base


class HrKnowledgeRule(Base):
    __tablename__ = "hr_knowledge_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_type = Column(String(30), nullable=False,
                       comment="sop / kpi_baseline / alert / best_practice")
    category = Column(String(50), nullable=True,
                      comment="turnover / scheduling / standards / training")
    condition = Column(JSONB, nullable=False, default=dict)
    action = Column(JSONB, nullable=False, default=dict)
    expected_impact = Column(JSONB, nullable=True)
    confidence = Column(Float, nullable=False, default=0.8)
    industry_source = Column(String(100), nullable=True)
    org_node_id = Column(String(64), nullable=True,
                         comment="NULL = 全行业通用")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                        nullable=False)

    def __repr__(self) -> str:
        return f"<HrKnowledgeRule(id={self.id}, type={self.rule_type!r})>"
