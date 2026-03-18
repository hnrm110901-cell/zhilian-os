"""TransferProcess — 调岗/晋升/外派流程"""
import uuid
from sqlalchemy import Column, String, Date, Float, ForeignKey, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from ..base import Base


class TransferProcess(Base):
    __tablename__ = "transfer_processes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    person_id = Column(UUID(as_uuid=True),
                       ForeignKey("persons.id", ondelete="RESTRICT"),
                       nullable=False, index=True)
    from_assignment_id = Column(UUID(as_uuid=True),
                                ForeignKey("employment_assignments.id", ondelete="RESTRICT"),
                                nullable=False, index=True)
    to_org_node_id = Column(String(64),
                            ForeignKey("org_nodes.id", ondelete="RESTRICT"),
                            nullable=False)
    to_employment_type = Column(String(30), nullable=False,
                                comment="full_time/hourly/outsourced/dispatched/partner")
    new_pay_scheme = Column(JSONB, nullable=True, default=dict)
    transfer_type = Column(String(30), nullable=False,
                           comment="internal_transfer/promotion/demotion/secondment")
    effective_date = Column(Date, nullable=False)
    status = Column(String(20), nullable=False, default="pending",
                    server_default="'pending'",
                    comment="pending/approved/active/rejected")
    reason = Column(String(500), nullable=False)
    revenue_impact_yuan = Column(Float(precision=2), nullable=True,
                                 comment="AI预测¥影响（元）")
    created_by = Column(String(100), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                        nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                        nullable=False)

    def __repr__(self) -> str:
        return (f"<TransferProcess(id={self.id}, "
                f"person_id={self.person_id}, transfer_type={self.transfer_type!r})>")
