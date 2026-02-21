"""
Notification Model
"""
from sqlalchemy import Column, String, Boolean, Text, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
import enum

from .base import Base, TimestampMixin


class NotificationType(str, enum.Enum):
    """通知类型"""
    INFO = "info"  # 信息通知
    WARNING = "warning"  # 警告
    ERROR = "error"  # 错误
    SUCCESS = "success"  # 成功
    ALERT = "alert"  # 紧急提醒


class NotificationPriority(str, enum.Enum):
    """通知优先级"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class Notification(Base, TimestampMixin):
    """通知模型"""

    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 通知内容
    title = Column(String(200), nullable=False)  # 通知标题
    message = Column(Text, nullable=False)  # 通知内容
    type = Column(String(20), nullable=False, default=NotificationType.INFO)  # 通知类型
    priority = Column(String(20), nullable=False, default=NotificationPriority.NORMAL)  # 优先级

    # 接收者信息
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)  # 特定用户
    role = Column(String(50), nullable=True)  # 特定角色(如果为空则发给所有人)
    store_id = Column(String(50), nullable=True, index=True)  # 特定门店

    # 状态
    is_read = Column(Boolean, default=False, nullable=False)  # 是否已读
    read_at = Column(String(50), nullable=True)  # 阅读时间

    # 元数据
    extra_data = Column(JSON, nullable=True)  # 额外数据(如链接、操作等)
    source = Column(String(50), nullable=True)  # 来源(哪个Agent或服务)

    def __repr__(self):
        return f"<Notification(title='{self.title}', type='{self.type}', user_id='{self.user_id}')>"

    def to_dict(self):
        """转换为字典"""
        return {
            "id": str(self.id),
            "title": self.title,
            "message": self.message,
            "type": self.type,
            "priority": self.priority,
            "user_id": str(self.user_id) if self.user_id else None,
            "role": self.role,
            "store_id": self.store_id,
            "is_read": self.is_read,
            "read_at": self.read_at,
            "extra_data": self.extra_data,
            "source": self.source,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
