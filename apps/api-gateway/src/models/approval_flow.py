"""
Approval Flow Models — 通用审批引擎
支持请假、加班、薪资确认、招聘Offer等多种审批场景
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, Date, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID

from .base import Base, TimestampMixin


class ApprovalType(str, enum.Enum):
    """审批类型"""

    LEAVE = "leave"  # 请假
    OVERTIME = "overtime"  # 加班
    PAYROLL_CONFIRM = "payroll"  # 薪资确认
    OFFER = "offer"  # 招聘Offer
    CONTRACT = "contract"  # 合同签署
    TRANSFER = "transfer"  # 调岗
    RESIGNATION = "resignation"  # 离职
    GENERAL = "general"  # 通用


class ApprovalStatus(str, enum.Enum):
    """审批状态"""

    PENDING = "pending"  # 待审批
    APPROVED = "approved"  # 已通过
    REJECTED = "rejected"  # 已驳回
    WITHDRAWN = "withdrawn"  # 已撤回
    EXPIRED = "expired"  # 已过期


class ApprovalNodeType(str, enum.Enum):
    """审批节点类型"""

    SINGLE = "single"  # 单人审批
    AND_SIGN = "and_sign"  # 会签（所有人通过）
    OR_SIGN = "or_sign"  # 或签（任一人通过）


# ── 1. 审批流程模板 ────────────────────────────────────────


class ApprovalFlowTemplate(Base, TimestampMixin):
    """
    审批流程定义：定义审批节点链。
    每种审批类型可配置不同的审批流（如请假3天以上需总部审批）。
    """

    __tablename__ = "approval_flow_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=True, index=True)  # NULL = 全局模板
    brand_id = Column(String(50), nullable=True, index=True)

    name = Column(String(100), nullable=False)
    approval_type = Column(
        SAEnum(ApprovalType, name="approval_type_enum"),
        nullable=False,
        index=True,
    )
    description = Column(Text, nullable=True)

    # 审批节点定义（JSON数组）
    # [
    #   {"step": 1, "node_type": "single", "role": "store_manager", "label": "店长审批"},
    #   {"step": 2, "node_type": "single", "role": "area_manager", "label": "区域经理审批",
    #    "condition": {"leave_days_gte": 3}}
    # ]
    nodes = Column(JSON, nullable=False, default=list)

    # 触发条件（当满足条件时使用此模板）
    # {"leave_days_gte": 3, "amount_gte": 50000}
    trigger_conditions = Column(JSON, nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)
    priority = Column(Integer, default=0)  # 多模板匹配时优先级

    def __repr__(self):
        return f"<ApprovalFlowTemplate(name='{self.name}', type='{self.approval_type}')>"


# ── 2. 审批实例 ────────────────────────────────────────────


# ApprovalInstance 已迁移到 models/hr/approval_instance.py，此处 re-export 保持向后兼容
from .hr.approval_instance import ApprovalInstance  # noqa: F401


# ── 3. 审批节点记录 ────────────────────────────────────────


class ApprovalNodeRecord(Base, TimestampMixin):
    """
    审批节点执行记录：每个审批步骤一条。
    记录谁审批了、什么时候、审批意见。
    """

    __tablename__ = "approval_node_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    instance_id = Column(UUID(as_uuid=True), ForeignKey("approval_instances.id"), nullable=False, index=True)

    step = Column(Integer, nullable=False)
    node_type = Column(
        SAEnum(ApprovalNodeType, name="approval_node_type_enum"),
        nullable=False,
        default=ApprovalNodeType.SINGLE,
    )

    # 审批人
    approver_id = Column(String(50), nullable=False)
    approver_name = Column(String(100), nullable=True)
    approver_role = Column(String(50), nullable=True)

    # 审批结果
    action = Column(String(20), nullable=True)  # approved / rejected
    comment = Column(Text, nullable=True)
    acted_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<ApprovalNodeRecord(instance='{self.instance_id}', " f"step={self.step}, action='{self.action}')>"
