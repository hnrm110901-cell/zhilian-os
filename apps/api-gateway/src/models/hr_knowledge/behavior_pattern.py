"""BehaviorPattern — 行为模式学习（元数据层，向量存Qdrant hr_behavior_patterns）"""
import uuid
from sqlalchemy import Column, String, Float, Integer, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from ..base import Base


class BehaviorPattern(Base):
    __tablename__ = "behavior_patterns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pattern_type = Column(String(50), nullable=True)
    feature_vector = Column(JSONB, nullable=False, default=dict,
                            comment="特征元数据（字段名+权重），非向量值")
    qdrant_vector_id = Column(String(100), nullable=True,
                              comment="Qdrant hr_behavior_patterns collection的向量ID")
    outcome = Column(String(100), nullable=True)
    confidence = Column(Float, nullable=True)
    sample_size = Column(Integer, nullable=True)
    org_scope = Column(String(30), nullable=True)
    org_node_id = Column(String(64), nullable=True)
    last_trained = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                        nullable=False)
