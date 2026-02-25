"""
异步导出任务模型
跟踪大数据导出任务的状态、进度和结果文件
"""
import uuid
import enum
from sqlalchemy import Column, String, Boolean, Integer, Text, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from .base import Base, TimestampMixin


class ExportStatus(str, enum.Enum):
    PENDING = "pending"       # 等待执行
    RUNNING = "running"       # 执行中
    COMPLETED = "completed"   # 已完成
    FAILED = "failed"         # 失败


class ExportJob(Base, TimestampMixin):
    """
    异步导出任务
    记录大数据导出任务的状态、进度和结果
    """

    __tablename__ = "export_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 提交者
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)

    # 任务类型：transactions / audit_logs / orders / inventory / kpi / custom_report
    job_type = Column(String(50), nullable=False)

    # 导出参数（过滤条件、格式等）
    params = Column(JSON, nullable=False, default=dict)

    # 导出格式：csv / xlsx
    format = Column(String(10), nullable=False, default="csv")

    # 任务状态
    status = Column(String(20), nullable=False, default=ExportStatus.PENDING)

    # Celery 任务 ID
    celery_task_id = Column(String(100), nullable=True)

    # 进度（0-100）
    progress = Column(Integer, default=0, nullable=False)

    # 总行数 / 已处理行数
    total_rows = Column(Integer, nullable=True)
    processed_rows = Column(Integer, default=0, nullable=False)

    # 结果文件路径（临时存储，完成后可下载）
    file_path = Column(String(500), nullable=True)
    file_size_bytes = Column(Integer, nullable=True)

    # 错误信息
    error_message = Column(Text, nullable=True)

    # 完成时间
    completed_at = Column(String(30), nullable=True)

    # 关系
    user = relationship("User")

    def to_dict(self):
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "job_type": self.job_type,
            "params": self.params,
            "format": self.format,
            "status": self.status,
            "celery_task_id": self.celery_task_id,
            "progress": self.progress,
            "total_rows": self.total_rows,
            "processed_rows": self.processed_rows,
            "file_size_bytes": self.file_size_bytes,
            "error_message": self.error_message,
            "completed_at": self.completed_at,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
