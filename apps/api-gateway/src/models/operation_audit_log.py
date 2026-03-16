"""
操作审计日志 — 记录所有HR模块写操作

合规依据:
  - 《劳动法》《劳动合同法》— 薪酬/考勤/假勤变更可追溯
  - 《个人信息保护法》— 员工信息变更全链路留痕
"""

import uuid

from sqlalchemy import Column, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID

from .base import Base, TimestampMixin


class OperationAuditLog(Base, TimestampMixin):
    """HR操作审计日志 — 自动记录所有写操作（POST/PUT/DELETE）"""

    __tablename__ = "operation_audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 操作人
    operator_id = Column(String(50), nullable=False, index=True, comment="操作人ID")
    operator_name = Column(String(100), nullable=True, comment="操作人姓名")
    operator_role = Column(String(30), nullable=True, comment="角色: admin/store_manager/employee")

    # 操作信息
    action = Column(String(20), nullable=False, index=True, comment="动作: create/update/delete/approve/reject")
    module = Column(String(50), nullable=False, index=True, comment="模块: payroll/attendance/leave/settlement/...")
    resource_type = Column(String(50), nullable=False, comment="资源类型: employee/payroll_record/leave_request/...")
    resource_id = Column(String(100), nullable=True, comment="被操作资源的ID")

    # 请求信息
    method = Column(String(10), nullable=False, comment="HTTP方法: POST/PUT/DELETE")
    path = Column(String(500), nullable=False, comment="请求路径")
    ip_address = Column(String(50), nullable=True, comment="客户端IP")
    user_agent = Column(String(500), nullable=True, comment="客户端User-Agent")

    # 变更详情
    request_body = Column(JSON, nullable=True, comment="请求体（脱敏后）")
    response_status = Column(Integer, nullable=True, comment="HTTP响应状态码")
    changes = Column(JSON, nullable=True, comment="变更记录 {field: {old: x, new: y}}")

    # 结果
    success = Column(String(10), default="true", comment="是否成功: true/false")
    error_message = Column(Text, nullable=True, comment="错误信息")

    # 门店/品牌
    store_id = Column(String(50), nullable=True, index=True, comment="门店ID")
    brand_id = Column(String(50), nullable=True, comment="品牌ID")

    __table_args__ = (
        Index("idx_op_audit_module_time", "module", "created_at"),
        Index("idx_op_audit_operator_time", "operator_id", "created_at"),
        Index("idx_op_audit_resource", "resource_type", "resource_id"),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "operator_id": self.operator_id,
            "operator_name": self.operator_name,
            "operator_role": self.operator_role,
            "action": self.action,
            "module": self.module,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "method": self.method,
            "path": self.path,
            "ip_address": self.ip_address,
            "request_body": self.request_body,
            "response_status": self.response_status,
            "changes": self.changes,
            "success": self.success,
            "error_message": self.error_message,
            "store_id": self.store_id,
            "brand_id": self.brand_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
