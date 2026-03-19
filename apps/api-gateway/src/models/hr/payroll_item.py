"""PayrollItem — 个人薪资条目"""
import uuid

from sqlalchemy import Column, String, Integer, ForeignKey, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID, JSONB

from ..base import Base


class PayrollItem(Base):
    __tablename__ = "payroll_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id = Column(
        UUID(as_uuid=True),
        ForeignKey("payroll_batches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assignment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employment_assignments.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    base_salary_fen = Column(
        Integer, nullable=False, default=0, server_default="0",
        comment="基本工资（分）",
    )
    performance_fen = Column(
        Integer, nullable=False, default=0, server_default="0",
        comment="绩效奖金（分）",
    )
    overtime_fen = Column(
        Integer, nullable=False, default=0, server_default="0",
        comment="加班费（分）",
    )
    deduction_absent_fen = Column(
        Integer, nullable=False, default=0, server_default="0",
        comment="缺勤扣款（分）",
    )
    deduction_late_fen = Column(
        Integer, nullable=False, default=0, server_default="0",
        comment="迟到扣款（分）",
    )
    allowances = Column(JSONB, nullable=True, default=dict, comment="其他津贴")
    gross_fen = Column(
        Integer, nullable=False, default=0, server_default="0",
        comment="税前合计（分）",
    )
    social_insurance_fen = Column(
        Integer, nullable=False, default=0, server_default="0",
        comment="社保个人部分（分）",
    )
    tax_fen = Column(
        Integer, nullable=False, default=0, server_default="0",
        comment="个税（分）",
    )
    net_fen = Column(
        Integer, nullable=False, default=0, server_default="0",
        comment="实发工资（分）",
    )
    viewed_at = Column(
        TIMESTAMP(timezone=True), nullable=True, comment="工资条查看时间",
    )
    view_expires_at = Column(
        TIMESTAMP(timezone=True), nullable=True, comment="查看有效期（阅后即焚）",
    )
    created_at = Column(
        TIMESTAMP(timezone=True), server_default=text("NOW()"), nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<PayrollItem(id={self.id}, "
            f"batch_id={self.batch_id}, "
            f"net_fen={self.net_fen})>"
        )
