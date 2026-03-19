"""SkillNode — 知识图谱骨架（技能节点）

prerequisite_skill_ids 使用PostgreSQL ARRAY存储前置技能UUID列表。
无FK约束（图结构不适合FK）。未来可迁移至Neo4j，skill_node.id作为桥接键。
"""
import uuid
from sqlalchemy import Column, String, Text, Numeric, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from ..base import Base


class SkillNode(Base):
    __tablename__ = "skill_nodes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    skill_name = Column(String(100), nullable=False)
    category = Column(String(50), nullable=True,
                      comment="service / kitchen / management / compliance")
    description = Column(Text, nullable=True)
    prerequisite_skill_ids = Column(
        ARRAY(UUID(as_uuid=True)), nullable=True, default=list,
        comment="前置技能UUID列表（无FK约束）",
    )
    related_training_ids = Column(
        ARRAY(UUID(as_uuid=True)), nullable=True, default=list,
    )
    kpi_impact = Column(JSONB, nullable=True)
    estimated_revenue_lift = Column(Numeric(10, 2), nullable=True,
                                    comment="预计¥收入提升（元/月）")
    org_node_id = Column(String(64), nullable=True,
                         comment="NULL = 行业通用技能")
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                        nullable=False)

    def __repr__(self) -> str:
        return f"<SkillNode(id={self.id}, name={self.skill_name!r})>"
