"""EmploymentContract — 用工合同（薪酬方案 + 考勤规则）"""
import uuid
from sqlalchemy import Column, String, Date, ForeignKey, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from ..base import Base


class EmploymentContract(Base):
    __tablename__ = "employment_contracts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assignment_id = Column(UUID(as_uuid=True),
                           ForeignKey("employment_assignments.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    contract_type = Column(String(30), nullable=False,
                           comment="labor/hourly/outsource/dispatch/partnership")
    pay_scheme = Column(JSONB, nullable=False, default=dict,
                        comment="薪酬方案：月薪/时薪/提成比例等")
    attendance_rule_id = Column(UUID(as_uuid=True),
                                ForeignKey("attendance_rules.id", ondelete="SET NULL"),
                                nullable=True)
    kpi_template_id = Column(UUID(as_uuid=True),
                             ForeignKey("kpi_templates.id", ondelete="SET NULL"),
                             nullable=True)
    valid_from = Column(Date, nullable=False)
    valid_to = Column(Date, nullable=True)
    signed_at = Column(TIMESTAMP(timezone=True), nullable=True)
    file_url = Column(String(500), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                        nullable=False)

    # ── ORM relationships ──────────────────────────────────────
    assignment = relationship("EmploymentAssignment", back_populates="contracts")

    def __repr__(self) -> str:
        return (f"<EmploymentContract(id={self.id}, "
                f"type={self.contract_type!r})>")
