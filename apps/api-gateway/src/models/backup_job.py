"""
增量备份任务模型
跟踪全量/增量备份任务的状态和结果文件
"""
import uuid
import enum
from sqlalchemy import Column, String, Integer, Text, JSON
from sqlalchemy.dialects.postgresql import UUID

from .base import Base, TimestampMixin


class BackupType(str, enum.Enum):
    FULL = "full"               # 全量备份
    INCREMENTAL = "incremental" # 增量备份


class BackupStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class BackupJob(Base, TimestampMixin):
    """
    备份任务
    记录全量/增量备份的状态、文件路径和校验和
    """

    __tablename__ = "backup_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 备份类型：full / incremental
    backup_type = Column(String(20), nullable=False, default=BackupType.FULL)

    # 增量备份的起始时间戳（ISO 8601），全量备份为 None
    since_timestamp = Column(String(30), nullable=True)

    # 要备份的表列表（空列表 = 全部表）
    tables = Column(JSON, nullable=False, default=list)

    # 任务状态
    status = Column(String(20), nullable=False, default=BackupStatus.PENDING)

    # Celery 任务 ID
    celery_task_id = Column(String(100), nullable=True)

    # 进度（0-100）
    progress = Column(Integer, default=0, nullable=False)

    # 结果压缩包路径（tar.gz）
    file_path = Column(String(500), nullable=True)
    file_size_bytes = Column(Integer, nullable=True)

    # SHA256 校验和
    checksum = Column(String(64), nullable=True)

    # 备份的行数统计（按表）
    row_counts = Column(JSON, nullable=True)

    # 错误信息
    error_message = Column(Text, nullable=True)

    # 完成时间
    completed_at = Column(String(30), nullable=True)

    def to_dict(self):
        return {
            "id": str(self.id),
            "backup_type": self.backup_type,
            "since_timestamp": self.since_timestamp,
            "tables": self.tables,
            "status": self.status,
            "celery_task_id": self.celery_task_id,
            "progress": self.progress,
            "file_size_bytes": self.file_size_bytes,
            "checksum": self.checksum,
            "row_counts": self.row_counts,
            "error_message": self.error_message,
            "completed_at": self.completed_at,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
