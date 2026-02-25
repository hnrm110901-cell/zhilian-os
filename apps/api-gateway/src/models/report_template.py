"""
自定义报表模板模型
支持报表模板管理和定时报表订阅
"""
import uuid
import enum
from sqlalchemy import Column, String, Boolean, Text, JSON, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from .base import Base, TimestampMixin


class ReportFormat(str, enum.Enum):
    CSV = "csv"
    XLSX = "xlsx"
    PDF = "pdf"


class ScheduleFrequency(str, enum.Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class ReportTemplate(Base, TimestampMixin):
    """
    报表模板
    定义报表的数据来源、字段、过滤条件和展示格式
    """

    __tablename__ = "report_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 基本信息
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)

    # 数据来源：transactions / income_statement / cash_flow / kpi / inventory / orders
    data_source = Column(String(50), nullable=False)

    # 字段配置：[{"field": "amount", "label": "金额", "format": "currency"}, ...]
    columns = Column(JSON, nullable=False, default=list)

    # 过滤条件：{"store_id": "STORE001", "transaction_type": "income", ...}
    filters = Column(JSON, nullable=True, default=dict)

    # 排序：[{"field": "created_at", "order": "desc"}]
    sort_by = Column(JSON, nullable=True, default=list)

    # 默认导出格式
    default_format = Column(String(10), nullable=False, default=ReportFormat.XLSX)

    # 是否公开（所有用户可用）
    is_public = Column(Boolean, default=False, nullable=False)

    # 创建者
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    store_id = Column(String(50), nullable=True)

    # 关系
    creator = relationship("User")
    scheduled_reports = relationship("ScheduledReport", back_populates="template", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "data_source": self.data_source,
            "columns": self.columns,
            "filters": self.filters,
            "sort_by": self.sort_by,
            "default_format": self.default_format,
            "is_public": self.is_public,
            "created_by": str(self.created_by),
            "store_id": self.store_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ScheduledReport(Base, TimestampMixin):
    """
    定时报表订阅
    按频率自动生成报表并通过指定渠道推送
    """

    __tablename__ = "scheduled_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 关联模板
    template_id = Column(UUID(as_uuid=True), ForeignKey("report_templates.id"), nullable=False)

    # 订阅者
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    # 调度频率
    frequency = Column(String(20), nullable=False, default=ScheduleFrequency.DAILY)

    # 执行时间（HH:MM，UTC）
    run_at = Column(String(5), nullable=False, default="06:00")

    # 每周几执行（weekly 时有效，0=周一 ... 6=周日）
    day_of_week = Column(Integer, nullable=True)

    # 每月几号执行（monthly 时有效，1-28）
    day_of_month = Column(Integer, nullable=True)

    # 推送渠道：["email", "system"]
    channels = Column(JSON, nullable=False, default=list)

    # 推送目标（邮件地址等）
    recipients = Column(JSON, nullable=True, default=list)

    # 导出格式
    format = Column(String(10), nullable=False, default=ReportFormat.XLSX)

    # 是否启用
    is_active = Column(Boolean, default=True, nullable=False)

    # 最后执行时间
    last_run_at = Column(String(30), nullable=True)

    # 下次执行时间
    next_run_at = Column(String(30), nullable=True)

    # 关系
    template = relationship("ReportTemplate", back_populates="scheduled_reports")
    user = relationship("User")

    def to_dict(self):
        return {
            "id": str(self.id),
            "template_id": str(self.template_id),
            "user_id": str(self.user_id),
            "frequency": self.frequency,
            "run_at": self.run_at,
            "day_of_week": self.day_of_week,
            "day_of_month": self.day_of_month,
            "channels": self.channels,
            "recipients": self.recipients,
            "format": self.format,
            "is_active": self.is_active,
            "last_run_at": self.last_run_at,
            "next_run_at": self.next_run_at,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
