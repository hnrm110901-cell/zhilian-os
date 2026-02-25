"""
Notification Model
"""
from sqlalchemy import Column, String, Boolean, Text, JSON, ForeignKey, Integer, Time
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


class NotificationPreference(Base, TimestampMixin):
    """
    用户通知偏好设置
    控制每种通知类型走哪些渠道，以及免打扰时段
    """

    __tablename__ = "notification_preferences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)

    # 通知类型（info/warning/error/success/alert），NULL 表示全局默认
    notification_type = Column(String(20), nullable=True)

    # 启用的渠道列表，如 ["system", "email", "sms"]
    channels = Column(JSON, nullable=False, default=list)

    # 是否启用该类型通知
    is_enabled = Column(Boolean, default=True, nullable=False)

    # 免打扰时段（HH:MM 格式字符串，存储为 String 以兼容各数据库）
    quiet_hours_start = Column(String(5), nullable=True)  # e.g. "22:00"
    quiet_hours_end = Column(String(5), nullable=True)    # e.g. "08:00"

    # 关系
    user = relationship("User")

    def to_dict(self):
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "notification_type": self.notification_type,
            "channels": self.channels,
            "is_enabled": self.is_enabled,
            "quiet_hours_start": self.quiet_hours_start,
            "quiet_hours_end": self.quiet_hours_end,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class NotificationRule(Base, TimestampMixin):
    """
    通知频率控制规则
    防止同类通知在短时间内刷屏
    """

    __tablename__ = "notification_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 作用范围：user_id 不为空则为用户级规则，否则为全局规则
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)

    # 通知类型（NULL 表示适用所有类型）
    notification_type = Column(String(20), nullable=True)

    # 频率限制：time_window_minutes 分钟内最多发 max_count 条
    max_count = Column(Integer, nullable=False, default=10)
    time_window_minutes = Column(Integer, nullable=False, default=60)

    # 是否启用
    is_active = Column(Boolean, default=True, nullable=False)

    # 描述
    description = Column(String(200), nullable=True)

    # 关系
    user = relationship("User")

    def to_dict(self):
        return {
            "id": str(self.id),
            "user_id": str(self.user_id) if self.user_id else None,
            "notification_type": self.notification_type,
            "max_count": self.max_count,
            "time_window_minutes": self.time_window_minutes,
            "is_active": self.is_active,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
