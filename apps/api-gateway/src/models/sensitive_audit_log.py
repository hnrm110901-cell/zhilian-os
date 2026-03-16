"""
敏感数据访问审计日志
记录所有对 PII 字段（身份证号、银行卡号等）的读写操作

合规依据:
  - 《个人信息保护法》第五十四条 — 定期审计
  - PCI-DSS Requirement 10 — 跟踪和监视访问
"""

import uuid

from sqlalchemy import Column, DateTime, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from .base import Base, TimestampMixin


class SensitiveDataAuditLog(Base, TimestampMixin):
    """敏感数据访问审计日志"""

    __tablename__ = "sensitive_data_audit_logs"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="主键",
    )
    operator_id = Column(
        String(50),
        nullable=False,
        index=True,
        comment="操作人ID",
    )
    employee_id = Column(
        String(50),
        nullable=False,
        index=True,
        comment="被访问员工ID",
    )
    field_name = Column(
        String(50),
        nullable=False,
        comment="字段名: id_card_no / bank_account / phone",
    )
    action = Column(
        String(20),
        nullable=False,
        comment="操作类型: read / write / export / batch_encrypt",
    )
    ip_address = Column(
        String(50),
        nullable=True,
        comment="客户端IP",
    )
    user_agent = Column(
        String(500),
        nullable=True,
        comment="客户端User-Agent",
    )
    store_id = Column(
        String(50),
        nullable=True,
        index=True,
        comment="门店ID（便于按店审计）",
    )
    detail = Column(
        String(500),
        nullable=True,
        comment="附加说明（如批量加密数量）",
    )

    __table_args__ = (
        Index("idx_sensitive_audit_operator_time", "operator_id", "created_at"),
        Index("idx_sensitive_audit_employee_time", "employee_id", "created_at"),
        Index("idx_sensitive_audit_action", "action"),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "operator_id": self.operator_id,
            "employee_id": self.employee_id,
            "field_name": self.field_name,
            "action": self.action,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "store_id": self.store_id,
            "detail": self.detail,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
