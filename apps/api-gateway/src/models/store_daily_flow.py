"""
门店全天业务流程节点管理 — 数据模型

覆盖从开店准备(07:00)到日清日结(24:00)的 11 个标准节点。
支持多品牌差异化模板 + 门店实例化 + 任务级追踪 + 异常升级。
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Date,
    ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from .base import Base, TimestampMixin


# ══════════════════════════════════════════════════════════════
#  枚举
# ══════════════════════════════════════════════════════════════

class NodeStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    OVERDUE = "overdue"
    SKIPPED = "skipped"


class TaskStatus(str, enum.Enum):
    TODO = "todo"
    DOING = "doing"
    DONE = "done"
    OVERTIME = "overtime"
    PENDING_REVIEW = "pending_review"
    SKIPPED = "skipped"


class IncidentSeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentStatus(str, enum.Enum):
    NEW = "new"
    ACCEPTED = "accepted"
    IN_PROCESS = "in_process"
    PENDING_REVIEW = "pending_review"
    CLOSED = "closed"
    ESCALATED = "escalated"


class ProofType(str, enum.Enum):
    NONE = "none"
    PHOTO = "photo"
    NUMBER = "number"
    TEXT = "text"
    SIGNATURE = "signature"
    CHECKLIST = "checklist"


# ══════════════════════════════════════════════════════════════
#  模板层（品牌级配置，由总部管理）
# ══════════════════════════════════════════════════════════════

class FlowTemplate(Base, TimestampMixin):
    """流程模板：一个品牌的全天标准流程"""
    __tablename__ = "flow_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    brand_id = Column(String(64), nullable=False, index=True)
    store_type = Column(String(32), default="standard")
    business_mode = Column(String(32), default="lunch_dinner")
    is_active = Column(Boolean, default=True)
    description = Column(Text)


class NodeTemplate(Base, TimestampMixin):
    """节点模板：流程中的一个标准节点"""
    __tablename__ = "node_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    flow_template_id = Column(UUID(as_uuid=True), ForeignKey("flow_templates.id"), nullable=False, index=True)
    node_code = Column(String(50), nullable=False)
    node_name = Column(String(100), nullable=False)
    node_order = Column(Integer, nullable=False)
    default_start_time = Column(String(5), nullable=False)
    default_end_time = Column(String(5), nullable=False)
    owner_role = Column(String(32), default="store_manager")
    is_optional = Column(Boolean, default=False)
    pass_condition = Column(JSON)
    description = Column(Text)

    __table_args__ = (
        UniqueConstraint("flow_template_id", "node_code", name="uq_node_tpl_flow_code"),
    )


class TaskTemplate(Base, TimestampMixin):
    """任务模板：节点下的标准任务"""
    __tablename__ = "task_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    node_template_id = Column(UUID(as_uuid=True), ForeignKey("node_templates.id"), nullable=False, index=True)
    task_code = Column(String(50), nullable=False)
    task_name = Column(String(100), nullable=False)
    task_order = Column(Integer, nullable=False)
    is_required = Column(Boolean, default=True)
    assignee_role = Column(String(32), default="store_staff")
    proof_type = Column(String(20), default="none")
    timeout_minutes = Column(Integer, default=0)
    description = Column(Text)

    __table_args__ = (
        UniqueConstraint("node_template_id", "task_code", name="uq_task_tpl_node_code"),
    )


# ══════════════════════════════════════════════════════════════
#  实例层（门店每日自动生成）
# ══════════════════════════════════════════════════════════════

class FlowInstance(Base, TimestampMixin):
    """流程实例：某门店某天的全天流程"""
    __tablename__ = "flow_instances"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(64), nullable=False, index=True)
    brand_id = Column(String(64), nullable=False, index=True)
    biz_date = Column(Date, nullable=False, index=True)
    flow_template_id = Column(UUID(as_uuid=True), ForeignKey("flow_templates.id"))
    status = Column(String(20), default="pending")
    total_nodes = Column(Integer, default=0)
    completed_nodes = Column(Integer, default=0)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    __table_args__ = (
        UniqueConstraint("store_id", "biz_date", name="uq_flow_inst_store_date"),
        Index("ix_flow_inst_brand_date", "brand_id", "biz_date"),
    )


class NodeInstance(Base, TimestampMixin):
    """节点实例：某门店某天某个节点的执行状态"""
    __tablename__ = "node_instances"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    flow_instance_id = Column(UUID(as_uuid=True), ForeignKey("flow_instances.id"), nullable=False, index=True)
    store_id = Column(String(64), nullable=False, index=True)
    biz_date = Column(Date, nullable=False, index=True)
    node_code = Column(String(50), nullable=False)
    node_name = Column(String(100), nullable=False)
    node_order = Column(Integer, nullable=False)
    scheduled_start = Column(DateTime, nullable=False)
    scheduled_end = Column(DateTime, nullable=False)
    actual_start = Column(DateTime)
    actual_end = Column(DateTime)
    status = Column(String(20), default="pending", index=True)
    owner_role = Column(String(32))
    owner_user_id = Column(String(64))
    total_tasks = Column(Integer, default=0)
    completed_tasks = Column(Integer, default=0)
    is_optional = Column(Boolean, default=False)
    pass_condition = Column(JSON)
    metrics_snapshot = Column(JSON)

    __table_args__ = (
        UniqueConstraint("flow_instance_id", "node_code", name="uq_node_inst_flow_code"),
        Index("ix_node_inst_store_date_status", "store_id", "biz_date", "status"),
    )


class TaskInstance(Base, TimestampMixin):
    """任务实例：某节点下某个任务的执行状态"""
    __tablename__ = "task_instances"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    node_instance_id = Column(UUID(as_uuid=True), ForeignKey("node_instances.id"), nullable=False, index=True)
    store_id = Column(String(64), nullable=False, index=True)
    biz_date = Column(Date, nullable=False)
    task_code = Column(String(50), nullable=False)
    task_name = Column(String(100), nullable=False)
    task_order = Column(Integer, nullable=False)
    is_required = Column(Boolean, default=True)
    assignee_role = Column(String(32))
    assignee_user_id = Column(String(64))
    status = Column(String(20), default="todo", index=True)
    proof_type = Column(String(20), default="none")
    proof_value = Column(JSON)
    submitted_at = Column(DateTime)
    submitted_by = Column(String(64))
    reviewed_by = Column(String(64))
    reviewed_at = Column(DateTime)
    timeout_minutes = Column(Integer, default=0)
    remark = Column(Text)

    __table_args__ = (
        UniqueConstraint("node_instance_id", "task_code", name="uq_task_inst_node_code"),
    )


# ══════════════════════════════════════════════════════════════
#  异常管理
# ══════════════════════════════════════════════════════════════

class Incident(Base, TimestampMixin):
    """异常事件：任何节点/任务中发现的问题"""
    __tablename__ = "store_incidents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(64), nullable=False, index=True)
    brand_id = Column(String(64), nullable=False, index=True)
    biz_date = Column(Date, nullable=False, index=True)
    source_type = Column(String(20))
    source_id = Column(UUID(as_uuid=True))
    incident_type = Column(String(50), nullable=False)
    severity = Column(String(20), default="medium", index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text)
    status = Column(String(20), default="new", index=True)
    reporter_id = Column(String(64))
    reporter_role = Column(String(32))
    assignee_id = Column(String(64))
    assignee_role = Column(String(32))
    escalation_level = Column(Integer, default=0)
    resolution_note = Column(Text)
    resolved_at = Column(DateTime)
    attachments = Column(JSON)

    __table_args__ = (
        Index("ix_incident_store_date", "store_id", "biz_date"),
        Index("ix_incident_severity_status", "severity", "status"),
    )


# ══════════════════════════════════════════════════════════════
#  操作日志
# ══════════════════════════════════════════════════════════════

class NodeLog(Base):
    """节点/任务操作日志"""
    __tablename__ = "node_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(64), nullable=False, index=True)
    biz_date = Column(Date, nullable=False)
    node_instance_id = Column(UUID(as_uuid=True), index=True)
    task_instance_id = Column(UUID(as_uuid=True))
    action_type = Column(String(30), nullable=False)
    action_by = Column(String(64), nullable=False)
    action_role = Column(String(32))
    action_time = Column(DateTime, default=datetime.utcnow)
    action_note = Column(Text)
    extra_data = Column(JSON)


# ══════════════════════════════════════════════════════════════
#  11 个标准节点常量（PRD V1）
# ══════════════════════════════════════════════════════════════

STANDARD_NODES = [
    {"code": "opening_prep",    "name": "开店准备",  "order": 1,  "start": "07:00", "end": "08:30", "role": "store_manager"},
    {"code": "ready_check",     "name": "营业就绪",  "order": 2,  "start": "08:30", "end": "10:00", "role": "store_manager"},
    {"code": "lunch_warmup",    "name": "午市预热",  "order": 3,  "start": "10:00", "end": "11:30", "role": "store_manager"},
    {"code": "lunch_peak",      "name": "午市高峰",  "order": 4,  "start": "11:30", "end": "14:00", "role": "store_manager"},
    {"code": "lunch_wrapup",    "name": "午市收尾",  "order": 5,  "start": "14:00", "end": "16:30", "role": "store_manager"},
    {"code": "dinner_prep",     "name": "晚市准备",  "order": 6,  "start": "16:30", "end": "17:30", "role": "store_manager"},
    {"code": "dinner_peak",     "name": "晚市高峰",  "order": 7,  "start": "17:30", "end": "21:30", "role": "store_manager"},
    {"code": "late_night_prep", "name": "夜宵准备",  "order": 8,  "start": "21:00", "end": "22:00", "role": "store_manager", "optional": True},
    {"code": "late_night_ops",  "name": "夜宵经营",  "order": 9,  "start": "22:00", "end": "02:00", "role": "store_manager", "optional": True},
    {"code": "closing",         "name": "闭店收尾",  "order": 10, "start": "21:30", "end": "23:00", "role": "store_manager"},
    {"code": "settlement",      "name": "日清日结",  "order": 11, "start": "22:00", "end": "24:00", "role": "store_manager"},
]
