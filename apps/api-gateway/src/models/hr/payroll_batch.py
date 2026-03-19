"""PayrollBatch — 薪资核算批次"""
import uuid
from datetime import datetime

from sqlalchemy import Column, String, Integer, ForeignKey, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID

from ..base import Base


class PayrollBatch(Base):
    __tablename__ = "payroll_batches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_node_id = Column(
        String(64),
        ForeignKey("org_nodes.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    period_year = Column(Integer, nullable=False)
    period_month = Column(Integer, nullable=False)
    status = Column(
        String(20),
        nullable=False,
        default="draft",
        server_default="'draft'",
        comment="draft/calculating/review/approved/paid/locked",
    )
    total_gross_fen = Column(
        Integer, nullable=False, default=0, server_default="0",
        comment="税前总额（分）",
    )
    total_net_fen = Column(
        Integer, nullable=False, default=0, server_default="0",
        comment="税后总额（分）",
    )
    created_by = Column(String(100), nullable=False)
    approved_by = Column(String(100), nullable=True)
    paid_at = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(
        TIMESTAMP(timezone=True), server_default=text("NOW()"), nullable=False,
    )
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=text("NOW()"),
        onupdate=datetime.utcnow,
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<PayrollBatch(id={self.id}, "
            f"period={self.period_year}-{self.period_month}, "
            f"status={self.status!r})>"
        )
