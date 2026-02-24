"""
神经事件日志模型
记录每个Neural System事件的完整处理链路，支持事件溯源审计
"""
from sqlalchemy import Column, String, Integer, Float, DateTime, Text, JSON, Boolean, Enum as SQLEnum
from datetime import datetime
import enum
from .base import Base


class EventProcessingStatus(str, enum.Enum):
    """事件处理状态"""
    QUEUED = "queued"          # 已入队，等待处理
    PROCESSING = "processing"  # 处理中
    COMPLETED = "completed"    # 处理完成
    FAILED = "failed"          # 处理失败
    RETRYING = "retrying"      # 重试中


class NeuralEventLog(Base):
    """神经事件日志表 — 事件溯源核心表"""
    __tablename__ = "neural_event_logs"

    # 主键 / 事件标识
    event_id = Column(String(36), primary_key=True, comment="事件ID（与Celery任务参数一致）")
    celery_task_id = Column(String(255), index=True, comment="Celery任务ID")

    # 事件基本信息
    event_type = Column(String(100), nullable=False, index=True, comment="事件类型 (order.created, revenue_anomaly, ...)")
    event_source = Column(String(100), nullable=False, index=True, comment="事件来源 (pos_webhook, agent, scheduler, ...)")
    store_id = Column(String(36), nullable=False, index=True, comment="门店ID")
    priority = Column(Integer, default=0, comment="优先级")

    # 原始事件数据
    data = Column(JSON, comment="原始事件数据")

    # 处理状态
    processing_status = Column(
        SQLEnum(EventProcessingStatus),
        default=EventProcessingStatus.QUEUED,
        nullable=False,
        index=True,
        comment="处理状态",
    )

    # 处理结果
    vector_indexed = Column(Boolean, default=False, comment="是否已写入向量DB")
    wechat_sent = Column(Boolean, default=False, comment="是否已触发企微推送")
    downstream_tasks = Column(JSON, comment="触发的下游任务列表 [{task_name, task_id}]")
    actions_taken = Column(JSON, comment="处理过程中执行的动作列表")

    # 时间戳
    queued_at = Column(DateTime, default=datetime.utcnow, nullable=False, comment="入队时间")
    started_at = Column(DateTime, comment="开始处理时间")
    processed_at = Column(DateTime, comment="处理完成时间")

    # 错误信息
    error_message = Column(Text, comment="失败时的错误信息")
    retry_count = Column(Integer, default=0, comment="重试次数")

    def __repr__(self):
        return f"<NeuralEventLog(event_id={self.event_id}, type={self.event_type}, status={self.processing_status})>"

    def to_dict(self):
        return {
            "event_id": self.event_id,
            "celery_task_id": self.celery_task_id,
            "event_type": self.event_type,
            "event_source": self.event_source,
            "store_id": self.store_id,
            "priority": self.priority,
            "data": self.data,
            "processing_status": self.processing_status.value if self.processing_status else None,
            "vector_indexed": self.vector_indexed,
            "wechat_sent": self.wechat_sent,
            "downstream_tasks": self.downstream_tasks,
            "actions_taken": self.actions_taken,
            "queued_at": self.queued_at.isoformat() if self.queued_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
        }
