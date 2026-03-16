"""
评论行动引擎模型
ReviewActionRule: 评论自动处理规则
ReviewActionLog: 规则执行日志
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from src.models.base import Base, TimestampMixin


class ReviewActionRule(Base, TimestampMixin):
    """
    评论行动规则表
    定义当评论满足特定条件时自动触发的行动
    """

    __tablename__ = "review_action_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(String(50), nullable=False, index=True)

    rule_name = Column(String(100), nullable=False)

    # 触发条件: {sentiment: "negative", rating_lte: 2, keywords: ["投诉","退款"]}
    trigger_condition = Column(JSON, nullable=False, default=dict)

    # 行动类型: auto_reply / alert_manager / create_task / signal_bus / wechat_notify
    action_type = Column(String(30), nullable=False)

    # 行动配置: {reply_template: "...", alert_level: "high", task_assignee: "store_manager"}
    action_config = Column(JSON, nullable=False, default=dict)

    is_enabled = Column(Boolean, default=True, nullable=False)
    trigger_count = Column(Integer, default=0, nullable=False)
    priority = Column(Integer, default=0, nullable=False)

    __table_args__ = (
        Index("idx_review_action_rule_brand", "brand_id"),
        Index("idx_review_action_rule_enabled", "is_enabled"),
        Index("idx_review_action_rule_type", "action_type"),
    )

    def __repr__(self):
        return (
            f"<ReviewActionRule(id={self.id}, name={self.rule_name}, "
            f"action_type={self.action_type}, enabled={self.is_enabled})>"
        )

    def to_dict(self):
        return {
            "id": str(self.id),
            "brand_id": self.brand_id,
            "rule_name": self.rule_name,
            "trigger_condition": self.trigger_condition,
            "action_type": self.action_type,
            "action_config": self.action_config,
            "is_enabled": self.is_enabled,
            "trigger_count": self.trigger_count,
            "priority": self.priority,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ReviewActionLog(Base, TimestampMixin):
    """
    评论行动执行日志表
    记录每次规则触发的执行详情和结果
    """

    __tablename__ = "review_action_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_id = Column(UUID(as_uuid=True), ForeignKey("review_action_rules.id"), nullable=True)
    review_id = Column(UUID(as_uuid=True), ForeignKey("dianping_reviews.id"), nullable=False)

    brand_id = Column(String(50), nullable=False, index=True)
    store_id = Column(String(50), nullable=False, index=True)

    action_type = Column(String(30), nullable=False)
    action_detail = Column(JSON, nullable=True)  # 执行详情

    # success / failed / pending
    status = Column(String(20), nullable=False, default="pending")
    error_message = Column(Text, nullable=True)

    executed_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_review_action_log_brand", "brand_id"),
        Index("idx_review_action_log_store", "store_id"),
        Index("idx_review_action_log_status", "status"),
        Index("idx_review_action_log_type", "action_type"),
        Index("idx_review_action_log_executed", "executed_at"),
    )

    def __repr__(self):
        return f"<ReviewActionLog(id={self.id}, action_type={self.action_type}, " f"status={self.status})>"

    def to_dict(self):
        return {
            "id": str(self.id),
            "rule_id": str(self.rule_id) if self.rule_id else None,
            "review_id": str(self.review_id),
            "brand_id": self.brand_id,
            "store_id": self.store_id,
            "action_type": self.action_type,
            "action_detail": self.action_detail,
            "status": self.status,
            "error_message": self.error_message,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
