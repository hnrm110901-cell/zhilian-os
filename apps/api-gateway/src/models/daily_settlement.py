"""
StoreDailySettlement — 门店日结单
承载每日确认、异常说明、明日动作、审核流。
"""
from sqlalchemy import Column, String, Integer, Text, DateTime, JSON
from sqlalchemy.dialects.postgresql import UUID
import uuid
from .base import Base, TimestampMixin


class StoreDailySettlement(Base, TimestampMixin):
    """门店日结单"""
    __tablename__ = "store_daily_settlements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(64), nullable=False, index=True)
    biz_date = Column(String(10), nullable=False, index=True)  # yyyy-MM-dd
    settlement_no = Column(String(64), unique=True, nullable=False)

    # 日结状态：pending_collect/pending_validate/pending_confirm/
    #            abnormal_wait_comment/submitted/pending_review/approved/returned/closed
    status = Column(String(32), default="pending_collect", nullable=False, index=True)

    # 预警摘要
    warning_level = Column(String(16), default="green", nullable=False)  # green/yellow/red
    warning_count = Column(Integer, default=0, nullable=False)
    major_issue_types = Column(JSON)          # 主要异常类型数组
    auto_summary = Column(Text)               # 系统自动摘要

    # 各角色说明
    manager_comment = Column(Text)            # 店长说明
    chef_comment = Column(Text)               # 厨师长说明
    finance_comment = Column(Text)            # 财务/稽核备注
    next_day_action_plan = Column(Text)       # 明日动作计划
    next_day_focus_targets = Column(JSON)     # 明日重点指标

    # 提交信息
    submitted_by = Column(String(64))
    submitted_at = Column(DateTime)

    # 审核信息
    reviewed_by = Column(String(64))
    reviewed_at = Column(DateTime)
    review_comment = Column(Text)
    returned_reason = Column(Text)
    closed_at = Column(DateTime)

    def __repr__(self):
        return f"<StoreDailySettlement(store_id='{self.store_id}', biz_date='{self.biz_date}', status='{self.status}')>"
