"""CostAllocation — 工资多门店分摊配置"""
import uuid

from sqlalchemy import Column, String, Numeric, ForeignKey, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID

from ..base import Base


class CostAllocation(Base):
    __tablename__ = "cost_allocations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assignment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employment_assignments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    org_node_id = Column(
        String(64),
        ForeignKey("org_nodes.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    ratio = Column(
        Numeric(4, 3), nullable=False, comment="分摊比例0.000-1.000",
    )
    created_at = Column(
        TIMESTAMP(timezone=True), server_default=text("NOW()"), nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<CostAllocation(id={self.id}, "
            f"assignment_id={self.assignment_id}, "
            f"ratio={self.ratio})>"
        )
