"""RetentionSignal — 离职风险预测信号（WF-1每日扫描）"""
import uuid
from sqlalchemy import Column, String, Float, ForeignKey, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from ..base import Base


class RetentionSignal(Base):
    __tablename__ = "retention_signals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assignment_id = Column(UUID(as_uuid=True),
                           ForeignKey("employment_assignments.id", ondelete="CASCADE"),
                           nullable=False)
    risk_score = Column(Float, nullable=False, comment="0.0-1.0")
    risk_factors = Column(JSONB, nullable=False, default=dict)
    intervention_status = Column(String(30), nullable=False, default="pending")
    intervention_at = Column(TIMESTAMP(timezone=True), nullable=True)
    computed_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                         nullable=False)

    def __repr__(self) -> str:
        return f"<RetentionSignal(id={self.id}, risk_score={self.risk_score})>"
