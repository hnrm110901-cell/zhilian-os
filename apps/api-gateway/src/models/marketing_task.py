"""营销任务体系 — P3：总部创建 → 店长分配 → 员工执行 → 数据回流"""

import uuid
from sqlalchemy import Column, Date, Integer, String, Text, ForeignKey, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMP

from .base import Base, TimestampMixin


class MarketingTask(Base, TimestampMixin):
    """营销任务"""

    __tablename__ = "marketing_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(String(50), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    audience_type = Column(String(20), nullable=False)  # preset | ai_query
    audience_config = Column(JSONB, nullable=False)
    script_template = Column(Text, nullable=True)
    coupon_config = Column(JSONB, nullable=True)
    status = Column(String(20), nullable=False, default="draft")  # draft | published | in_progress | completed | cancelled
    deadline = Column(TIMESTAMP(timezone=True), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    published_at = Column(TIMESTAMP(timezone=True), nullable=True)


class MarketingTaskTarget(Base, TimestampMixin):
    """目标人群快照"""

    __tablename__ = "marketing_task_targets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(UUID(as_uuid=True), ForeignKey("marketing_tasks.id"), nullable=False)
    consumer_id = Column(UUID(as_uuid=True), ForeignKey("consumer_identities.id"), nullable=False)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False)
    profile_snapshot = Column(JSONB, nullable=True)

    __table_args__ = (
        UniqueConstraint("task_id", "consumer_id", "store_id", name="uq_task_consumer_store"),
    )


class MarketingTaskAssignment(Base, TimestampMixin):
    """门店分配"""

    __tablename__ = "marketing_task_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(UUID(as_uuid=True), ForeignKey("marketing_tasks.id"), nullable=False)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False)
    assigned_to = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    target_count = Column(Integer, default=0)
    completed_count = Column(Integer, default=0)
    status = Column(String(20), nullable=False, default="pending")  # pending | assigned | in_progress | completed
    assigned_at = Column(TIMESTAMP(timezone=True), nullable=True)
    completed_at = Column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_assign_task_status", "task_id", "status"),
    )


class MarketingTaskExecution(Base, TimestampMixin):
    """执行记录"""

    __tablename__ = "marketing_task_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assignment_id = Column(UUID(as_uuid=True), ForeignKey("marketing_task_assignments.id"), nullable=False)
    target_id = Column(UUID(as_uuid=True), ForeignKey("marketing_task_targets.id"), nullable=False)
    executor_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    action_type = Column(String(20), nullable=False)  # wechat_msg | coupon | call | in_store
    action_detail = Column(JSONB, nullable=True)
    distribution_id = Column(UUID(as_uuid=True), ForeignKey("coupon_distributions.id"), nullable=True)
    feedback = Column(Text, nullable=True)
    executed_at = Column(TIMESTAMP(timezone=True), nullable=False)


class MarketingTaskStats(Base, TimestampMixin):
    """效果统计日汇总"""

    __tablename__ = "marketing_task_stats"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(UUID(as_uuid=True), ForeignKey("marketing_tasks.id"), nullable=False)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False)
    date = Column(Date, nullable=False)
    target_count = Column(Integer, default=0)
    reached_count = Column(Integer, default=0)
    coupon_distributed = Column(Integer, default=0)
    coupon_redeemed = Column(Integer, default=0)
    driven_gmv_fen = Column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint("task_id", "store_id", "date", name="uq_task_stats_daily"),
    )
