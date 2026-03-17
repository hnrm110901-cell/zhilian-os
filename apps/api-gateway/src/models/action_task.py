"""
ActionTask — 异常整改任务表
跟踪异常处理与闭环状态。
"""
from sqlalchemy import Column, String, Integer, Boolean, Text, DateTime, JSON
from sqlalchemy.dialects.postgresql import UUID
import uuid
from .base import Base, TimestampMixin


class ActionTask(Base, TimestampMixin):
    """异常整改任务表"""
    __tablename__ = "action_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_no = Column(String(64), unique=True, nullable=False, index=True)
    store_id = Column(String(64), nullable=False, index=True)
    biz_date = Column(String(10), nullable=False, index=True)
    source_type = Column(String(32), nullable=False)      # warning/weekly_review/manual
    source_id = Column(UUID(as_uuid=True), nullable=False) # 来源ID

    task_type = Column(String(64), nullable=False)         # 任务类型
    task_title = Column(String(256), nullable=False)
    task_description = Column(Text)
    severity_level = Column(String(16), nullable=False)    # yellow/red

    assignee_id = Column(String(64))                       # 责任人
    assignee_role = Column(String(32))                     # store_manager/chef/area_manager
    reviewer_id = Column(String(64))                       # 审核人
    due_at = Column(DateTime)                              # 截止时间

    # 任务状态：generated/pending_handle/submitted/pending_review/rectifying/closed/returned/repeated/canceled
    status = Column(String(32), default="generated", nullable=False, index=True)

    submit_comment = Column(Text)                          # 提交说明
    submit_attachments = Column(JSON)                      # 附件列表
    review_comment = Column(Text)                          # 审核意见
    closed_at = Column(DateTime)
    is_repeated_issue = Column(Boolean, default=False, nullable=False)
    repeat_count = Column(Integer, default=0, nullable=False)

    def __repr__(self):
        return f"<ActionTask(task_no='{self.task_no}', store_id='{self.store_id}', status='{self.status}')>"
