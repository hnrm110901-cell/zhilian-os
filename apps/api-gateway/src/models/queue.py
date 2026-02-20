"""
等位/排队数据模型
Queue/Waiting List Models
"""
from sqlalchemy import Column, String, Integer, DateTime, Boolean, Text, Enum as SQLEnum
from sqlalchemy.sql import func
from datetime import datetime
import enum

from ..core.database import Base


class QueueStatus(str, enum.Enum):
    """排队状态"""
    WAITING = "waiting"  # 等待中
    CALLED = "called"  # 已叫号
    SEATED = "seated"  # 已入座
    CANCELLED = "cancelled"  # 已取消
    NO_SHOW = "no_show"  # 未到场


class Queue(Base):
    """排队记录"""
    __tablename__ = "queues"

    # 基础信息
    queue_id = Column(String(50), primary_key=True, comment="排队ID")
    queue_number = Column(Integer, nullable=False, comment="排队号码")
    store_id = Column(String(50), nullable=False, index=True, comment="门店ID")

    # 客户信息
    customer_name = Column(String(100), nullable=False, comment="客户姓名")
    customer_phone = Column(String(20), nullable=False, index=True, comment="客户电话")
    party_size = Column(Integer, nullable=False, comment="就餐人数")

    # 状态信息
    status = Column(
        SQLEnum(QueueStatus),
        nullable=False,
        default=QueueStatus.WAITING,
        index=True,
        comment="排队状态"
    )

    # 时间信息
    created_at = Column(DateTime, nullable=False, default=func.now(), comment="创建时间")
    called_at = Column(DateTime, nullable=True, comment="叫号时间")
    seated_at = Column(DateTime, nullable=True, comment="入座时间")
    cancelled_at = Column(DateTime, nullable=True, comment="取消时间")

    # 预估信息
    estimated_wait_time = Column(Integer, nullable=True, comment="预估等待时间（分钟）")
    actual_wait_time = Column(Integer, nullable=True, comment="实际等待时间（分钟）")

    # 桌台信息
    table_number = Column(String(20), nullable=True, comment="分配的桌号")
    table_type = Column(String(50), nullable=True, comment="桌台类型（小桌、中桌、大桌）")

    # 备注信息
    special_requests = Column(Text, nullable=True, comment="特殊要求")
    notes = Column(Text, nullable=True, comment="备注")

    # 通知信息
    notification_sent = Column(Boolean, default=False, comment="是否已发送通知")
    notification_method = Column(String(20), nullable=True, comment="通知方式（短信、微信）")

    # 元数据
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment="更新时间")

    def __repr__(self):
        return f"<Queue {self.queue_number} - {self.customer_name} ({self.status})>"

    def to_dict(self):
        """转换为字典"""
        return {
            "queue_id": self.queue_id,
            "queue_number": self.queue_number,
            "store_id": self.store_id,
            "customer_name": self.customer_name,
            "customer_phone": self.customer_phone,
            "party_size": self.party_size,
            "status": self.status.value if self.status else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "called_at": self.called_at.isoformat() if self.called_at else None,
            "seated_at": self.seated_at.isoformat() if self.seated_at else None,
            "cancelled_at": self.cancelled_at.isoformat() if self.cancelled_at else None,
            "estimated_wait_time": self.estimated_wait_time,
            "actual_wait_time": self.actual_wait_time,
            "table_number": self.table_number,
            "table_type": self.table_type,
            "special_requests": self.special_requests,
            "notes": self.notes,
            "notification_sent": self.notification_sent,
            "notification_method": self.notification_method,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
