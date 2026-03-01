"""
L4 行动层 Action 模型：可执行任务 + 状态机 + 分级升级（Palantir 目标架构）
"""
from sqlalchemy import Column, String, Text, DateTime, Enum, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSON
import uuid
import enum
from datetime import datetime

from .base import Base, TimestampMixin


class ActionStatus(str, enum.Enum):
    CREATED = "created"
    SENT = "sent"       # 已推送企微
    ACKED = "acked"     # 已回执
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CLOSED = "closed"   # 超时关闭或取消


class ActionPriority(str, enum.Enum):
    P0 = "P0"  # 30min 无回执 @督导
    P1 = "P1"  # 2h 升级区域
    P2 = "P2"  # 24h 升级店长
    P3 = "P3"  # 3天 系统关闭


# 升级时限（分钟）
ESCALATION_MINUTES = {
    ActionPriority.P0.value: 30,
    ActionPriority.P1.value: 2 * 60,
    ActionPriority.P2.value: 24 * 60,
    ActionPriority.P3.value: 3 * 24 * 60,
}


class OntologyAction(Base, TimestampMixin):
    """L4 Action 任务：与推理结论绑定，支持企微推送与分级升级。"""

    __tablename__ = "ontology_actions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    tenant_id = Column(String(50), nullable=False, index=True)
    store_id = Column(String(50), nullable=False, index=True)

    action_type = Column(String(80), nullable=False)  # waste_follow_up, inventory_check, ...
    assignee_staff_id = Column(String(50), nullable=False, index=True)
    assignee_wechat_id = Column(String(100))  # 企微 userid，推送时用

    status = Column(
        String(20),
        default=ActionStatus.CREATED.value,
        nullable=False,
        index=True,
    )
    priority = Column(String(10), default=ActionPriority.P1.value, nullable=False)

    deadline_at = Column(DateTime)
    sent_at = Column(DateTime)   # 推送时间
    acked_at = Column(DateTime) # 回执时间
    done_at = Column(DateTime)

    # 溯源：关联推理报告或事件
    traced_reasoning_id = Column(String(100))
    traced_report = Column(JSON)  # 可选：快照根因摘要

    # 升级
    escalation_at = Column(DateTime)
    escalated_to = Column(String(200))  # 升级到的角色/人

    title = Column(String(200))
    body = Column(Text)
    extra = Column(JSON, default=dict)

    __table_args__ = (
        Index("idx_ontology_action_tenant_status", "tenant_id", "status"),
        Index("idx_ontology_action_deadline", "deadline_at"),
    )
