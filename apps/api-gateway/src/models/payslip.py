"""
Payslip Record Model — 工资条推送记录
记录每次工资条推送的状态、员工确认情况、PDF存储路径
"""
import uuid
from sqlalchemy import (
    Column, String, Boolean, DateTime, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from .base import Base, TimestampMixin


class PayslipRecord(Base, TimestampMixin):
    """工资条推送记录"""
    __tablename__ = "payslip_records"
    __table_args__ = (
        UniqueConstraint("store_id", "employee_id", "pay_month", name="uq_payslip_month"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=False, index=True)
    employee_id = Column(String(50), nullable=False, index=True)
    pay_month = Column(String(7), nullable=False, index=True)  # YYYY-MM

    pushed_at = Column(DateTime, nullable=True)
    push_channel = Column(String(20), nullable=True)  # wechat/dingtalk
    push_status = Column(String(20), default="pending")  # pending/sent/failed
    push_error = Column(String(500), nullable=True)  # 推送失败原因

    confirmed_at = Column(DateTime, nullable=True)  # 员工确认时间
    confirmed = Column(Boolean, default=False)

    pdf_path = Column(String(500), nullable=True)  # PDF存储路径

    def __repr__(self):
        return (
            f"<PayslipRecord(employee='{self.employee_id}', "
            f"month='{self.pay_month}', status='{self.push_status}')>"
        )
