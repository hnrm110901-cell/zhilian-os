"""
Integration Hub Status Model
集成中心状态模型 — 跟踪所有外部集成的健康状况和同步状态
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from .base import Base, TimestampMixin


class IntegrationHubStatus(Base, TimestampMixin):
    """集成状态追踪 — 每个外部集成对应一行"""

    __tablename__ = "integration_hub_statuses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    integration_key = Column(
        String(30),
        unique=True,
        nullable=False,
        index=True,
        comment="集成标识，如 eleme / pinzhi / wechat_work",
    )
    display_name = Column(String(50), nullable=False, comment="显示名称")
    category = Column(
        String(30),
        nullable=False,
        comment="分类: pos / channel / financial / compliance / review / procurement / im",
    )
    status = Column(
        String(20),
        nullable=False,
        default="not_configured",
        comment="健康状态: healthy / degraded / error / disconnected / not_configured",
    )
    last_sync_at = Column(DateTime, nullable=True, comment="最后成功同步时间")
    last_error_at = Column(DateTime, nullable=True, comment="最后出错时间")
    last_error_message = Column(Text, nullable=True, comment="最后错误信息")
    sync_count_today = Column(Integer, default=0, comment="今日同步次数")
    error_count_today = Column(Integer, default=0, comment="今日错误次数")
    config_complete = Column(Boolean, default=False, comment="配置是否完整")
    metadata_ = Column("metadata", JSON, nullable=True, comment="适配器专属信息（版本、限流等）")

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "integration_key": self.integration_key,
            "display_name": self.display_name,
            "category": self.category,
            "status": self.status,
            "last_sync_at": self.last_sync_at.isoformat() if self.last_sync_at else None,
            "last_error_at": self.last_error_at.isoformat() if self.last_error_at else None,
            "last_error_message": self.last_error_message,
            "sync_count_today": self.sync_count_today,
            "error_count_today": self.error_count_today,
            "config_complete": self.config_complete,
            "metadata": self.metadata_,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
