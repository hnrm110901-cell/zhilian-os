"""
通用审批流引擎 — 多级路由/委托/催办/超期升级
支持请假、薪资调整、入离调转、奖惩、合同续签等多业务审批场景
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID

from .base import Base, TimestampMixin


class ApprovalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    ESCALATED = "escalated"  # 超期自动升级


# ApprovalTemplate 已迁移到 models/hr/approval_template.py，此处 re-export 保持向后兼容
from .hr.approval_template import ApprovalTemplate  # noqa: F401


class ApprovalInstance(Base, TimestampMixin):
    """审批实例 — 一次具体的审批流程"""

    __tablename__ = "hr_approval_instances"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(String(50), nullable=False, index=True)
    store_id = Column(String(50), nullable=False, index=True)

    template_code = Column(String(50), nullable=False, index=True)

    # 关联业务
    business_type = Column(String(50), nullable=False)
    business_id = Column(String(100), nullable=False, index=True)

    # 发起人
    applicant_id = Column(String(50), nullable=False, index=True)
    applicant_name = Column(String(100))

    # 当前状态
    status = Column(String(20), nullable=False, default="pending", index=True)
    current_level = Column(Integer, default=1)

    # 金额（用于阈梯触发判断），单位：分
    amount_fen = Column(Integer, nullable=True)

    # 业务摘要（用于审批页面展示）
    summary = Column(Text, nullable=True)

    # 最终结果
    final_result = Column(String(20), nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # 超期截止
    deadline = Column(DateTime, nullable=True)


class ApprovalRecord(Base, TimestampMixin):
    """审批记录 — 每一步的审批动作"""

    __tablename__ = "hr_approval_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    instance_id = Column(
        UUID(as_uuid=True),
        ForeignKey("hr_approval_instances.id"),
        nullable=False,
        index=True,
    )

    level = Column(Integer, nullable=False)
    approver_id = Column(String(50), nullable=False)
    approver_name = Column(String(100))
    approver_role = Column(String(50))

    action = Column(String(20), nullable=False)  # approve/reject/delegate/escalate
    comment = Column(Text, nullable=True)
    acted_at = Column(DateTime, default=datetime.utcnow)

    # 委托
    delegated_to_id = Column(String(50), nullable=True)
    delegated_to_name = Column(String(100), nullable=True)


class ApprovalDelegation(Base, TimestampMixin):
    """审批委托 — 休假时指定代理人"""

    __tablename__ = "hr_approval_delegations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(String(50), nullable=False)

    delegator_id = Column(String(50), nullable=False, index=True)
    delegator_name = Column(String(100))
    delegate_id = Column(String(50), nullable=False)
    delegate_name = Column(String(100))

    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)

    template_codes = Column(JSON, default=list)  # 委托的审批类型，空=全部
    is_active = Column(Boolean, default=True)
