"""
WeeklyReview + WeeklyReviewItem — 周复盘单 + 周复盘问题项
记录每周经营总结与下周计划。
"""
from sqlalchemy import Column, String, Integer, Text, DateTime, Date, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from .base import Base, TimestampMixin


class WeeklyReview(Base, TimestampMixin):
    """周复盘单"""
    __tablename__ = "weekly_reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    review_no = Column(String(64), unique=True, nullable=False, index=True)
    review_scope = Column(String(32), nullable=False)       # store/region/hq
    scope_id = Column(String(64), nullable=False, index=True)
    week_start_date = Column(Date, nullable=False, index=True)
    week_end_date = Column(Date, nullable=False)

    # 销售目标 vs 实际（金额：分）
    sales_target_amount = Column(Integer, default=0)
    actual_sales_amount = Column(Integer, default=0)
    target_achievement_rate = Column(Integer, default=0)    # 达成率×10000

    # 率值×10000
    gross_profit_rate = Column(Integer, default=0)
    net_profit_rate = Column(Integer, default=0)

    # 天数统计
    profit_day_count = Column(Integer, default=0)           # 盈利天数
    loss_day_count = Column(Integer, default=0)             # 亏损天数
    abnormal_day_count = Column(Integer, default=0)         # 异常天数
    cost_abnormal_day_count = Column(Integer, default=0)    # 成本异常天数
    discount_abnormal_day_count = Column(Integer, default=0)
    labor_abnormal_day_count = Column(Integer, default=0)

    # 任务统计
    submitted_task_count = Column(Integer, default=0)
    closed_task_count = Column(Integer, default=0)
    pending_task_count = Column(Integer, default=0)
    repeated_issue_count = Column(Integer, default=0)       # 复发问题数

    # 复盘内容
    system_summary = Column(Text)                           # 系统生成摘要
    manager_summary = Column(Text)                          # 店长/负责人总结
    next_week_plan = Column(Text)                           # 下周计划
    next_week_focus_targets = Column(JSON)                  # 下周目标值

    # 状态：draft/pending_submit/submitted/pending_review/approved/returned/archived
    status = Column(String(32), default="draft", nullable=False, index=True)

    submitted_by = Column(String(64))
    submitted_at = Column(DateTime)
    reviewed_by = Column(String(64))
    reviewed_at = Column(DateTime)
    review_comment = Column(Text)

    # 关联问题项
    items = relationship("WeeklyReviewItem", back_populates="review", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<WeeklyReview(review_no='{self.review_no}', scope='{self.review_scope}:{self.scope_id}')>"


class WeeklyReviewItem(Base, TimestampMixin):
    """周复盘问题项"""
    __tablename__ = "weekly_review_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    weekly_review_id = Column(UUID(as_uuid=True), ForeignKey("weekly_reviews.id"), nullable=False, index=True)
    item_type = Column(String(64), nullable=False)          # 问题类型
    title = Column(String(256), nullable=False)
    description = Column(Text)
    related_dates = Column(JSON)                            # 涉及日期列表
    related_warning_ids = Column(JSON)                      # 关联预警ID列表
    root_cause = Column(Text)                               # 根因
    corrective_action = Column(Text)                        # 整改动作
    owner_id = Column(String(64))                           # 责任人
    owner_role = Column(String(32))                         # 责任角色
    due_date = Column(Date)
    status = Column(String(32), default="pending", nullable=False)  # pending/in_progress/done

    review = relationship("WeeklyReview", back_populates="items")

    def __repr__(self):
        return f"<WeeklyReviewItem(title='{self.title[:30]}', type='{self.item_type}')>"
