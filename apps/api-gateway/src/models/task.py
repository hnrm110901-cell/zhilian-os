"""
Task Model
任务管理模型
"""
from sqlalchemy import Column, String, Text, DateTime, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
import uuid
import enum
from datetime import datetime

from .base import Base, TimestampMixin


class TaskStatus(str, enum.Enum):
    """任务状态"""
    PENDING = "pending"  # 待处理
    IN_PROGRESS = "in_progress"  # 进行中
    COMPLETED = "completed"  # 已完成
    CANCELLED = "cancelled"  # 已取消
    OVERDUE = "overdue"  # 已逾期


class TaskPriority(str, enum.Enum):
    """任务优先级"""
    LOW = "low"  # 低
    NORMAL = "normal"  # 普通
    HIGH = "high"  # 高
    URGENT = "urgent"  # 紧急


class Task(Base, TimestampMixin):
    """任务模型"""

    __tablename__ = "tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 任务基本信息
    title = Column(String(200), nullable=False, index=True)
    content = Column(Text)  # 任务详细内容

    # 任务分类
    category = Column(String(50))  # 任务类别：开店流程、关店流程、卫生检查、设备巡检等

    # 任务状态和优先级
    status = Column(
        Enum(TaskStatus, values_callable=lambda x: [e.value for e in x]),
        default=TaskStatus.PENDING,
        nullable=False,
        index=True
    )
    priority = Column(
        Enum(TaskPriority, values_callable=lambda x: [e.value for e in x]),
        default=TaskPriority.NORMAL,
        nullable=False
    )

    # 任务关联
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)  # 创建人
    assignee_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))  # 指派给谁

    # 时间管理
    due_at = Column(DateTime(timezone=True))  # 截止时间
    started_at = Column(DateTime(timezone=True))  # 开始时间
    completed_at = Column(DateTime(timezone=True))  # 完成时间

    # 任务结果
    result = Column(Text)  # 任务完成结果/备注
    attachments = Column(Text)  # 附件URL列表（JSON格式）

    # 软删除
    is_deleted = Column(String(10), default="false", nullable=False)
    deleted_at = Column(DateTime(timezone=True))

    def __repr__(self):
        return f"<Task(id='{self.id}', title='{self.title}', status='{self.status}')>"
