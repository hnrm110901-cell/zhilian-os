"""
经营复盘会模型 — Review Session Models

五步闭环经营分析：
  Step 1: 拆细账 — 多维度拆解（渠道×品类×时段）
  Step 2: 找真因 — 核查清单（必须逐项验证才能进入下一步）
  Step 3: 定措施 — 四字段措施（责任人 + 时限 + 动作 + 量化结果）
  Step 4: 追执行 — KPI 阈值偏离自动预警 + 进度追踪
  Step 5: 看结果 — 周/月复盘闭环验证

金额单位：数据库存分（fen），API 返回时用 /100 转元
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from .base import Base, TimestampMixin


class ReviewSession(Base, TimestampMixin):
    """经营复盘会——一次完整的五步闭环实例"""

    __tablename__ = "review_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(50), nullable=False, index=True)  # 多租户隔离
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)

    # 周复盘 / 月复盘
    review_type = Column(String(10), nullable=False)  # "weekly" | "monthly"
    # 复盘周期标识：周 → "2026-W12"，月 → "2026-03"
    period_label = Column(String(20), nullable=False)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)

    # 当前所在步骤 1-5
    current_step = Column(Integer, nullable=False, default=1)
    # draft → in_progress → completed → archived
    status = Column(String(20), nullable=False, default="draft")

    # Step 1 拆细账快照（JSON: 维度拆解结果 + 菜品四象限矩阵）
    breakdown_snapshot = Column(JSON, default=dict)
    # Step 5 结果摘要
    result_summary = Column(JSON, default=dict)

    # 主持人 / 创建人
    created_by = Column(String(50))
    completed_at = Column(DateTime)

    # 关联
    checklists = relationship(
        "ReviewChecklist", back_populates="session",
        cascade="all, delete-orphan", order_by="ReviewChecklist.sort_order",
    )
    actions = relationship(
        "ReviewAction", back_populates="session",
        cascade="all, delete-orphan", order_by="ReviewAction.created_at",
    )

    __table_args__ = (
        Index("idx_review_session_store_period", "store_id", "review_type", "period_label"),
    )

    def __repr__(self):
        return f"<ReviewSession({self.review_type} {self.period_label} step={self.current_step})>"


class ReviewChecklist(Base, TimestampMixin):
    """
    Step 2: 找真因——核查清单

    每个条目代表一个需要一线验证的根因假设。
    没有全部勾选 verified=True，系统不允许进入 Step 3。
    """

    __tablename__ = "review_checklists"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(
        UUID(as_uuid=True), ForeignKey("review_sessions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # 核查维度：翻台率下降 / 出餐慢 / 等位管理差 / 渠道结构变化 / 菜品结构偏移 …
    dimension = Column(String(50), nullable=False)
    # 问题描述
    description = Column(Text, nullable=False)
    # 是否已现场验证
    verified = Column(Boolean, nullable=False, default=False)
    # 验证人
    verified_by = Column(String(50))
    verified_at = Column(DateTime)
    # 验证备注（一线实况）
    verification_note = Column(Text, default="")
    # 排序
    sort_order = Column(Integer, nullable=False, default=0)

    session = relationship("ReviewSession", back_populates="checklists")

    def __repr__(self):
        return f"<ReviewChecklist({self.dimension} verified={self.verified})>"


class ReviewAction(Base, TimestampMixin):
    """
    Step 3: 定措施——四字段强制模板

    四个字段缺一不可：
      1. owner       — 责任人
      2. deadline     — 完成时限
      3. action_desc  — 具体动作（"加强培训"是空话，要写清楚频次+方法）
      4. target_kpi   — 可量化结果（如 "饮品搭售率从 39% 提升至 52%"）

    Step 4: 追执行——KPI 偏离阈值后自动预警
    """

    __tablename__ = "review_actions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(
        UUID(as_uuid=True), ForeignKey("review_sessions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # ── 四字段措施（缺一不可） ──
    owner = Column(String(50), nullable=False)         # 责任人
    deadline = Column(Date, nullable=False)             # 完成时限
    action_desc = Column(Text, nullable=False)          # 具体动作
    target_kpi = Column(String(200), nullable=False)    # 可量化结果

    # ── 追执行 ──
    # pending → in_progress → completed → overdue
    progress_status = Column(String(20), nullable=False, default="pending")
    # 当前进度 0-100
    progress_pct = Column(Integer, nullable=False, default=0)
    # KPI 当前值（用于对比 target）
    current_kpi_value = Column(String(200), default="")
    # 偏离阈值后的预警级别：null → normal → warning → critical
    alert_level = Column(String(20))
    # 执行备注
    progress_notes = Column(JSON, default=list)  # [{date, note, updated_by}]

    # ── 看结果 ──
    # 最终是否达标
    is_achieved = Column(Boolean)
    # 实际产生的 ¥ 影响（分）
    actual_impact_fen = Column(Integer, default=0)
    closed_at = Column(DateTime)
    closed_note = Column(Text, default="")

    session = relationship("ReviewSession", back_populates="actions")

    __table_args__ = (
        Index("idx_review_action_session_status", "session_id", "progress_status"),
    )

    def __repr__(self):
        return f"<ReviewAction(owner='{self.owner}' status={self.progress_status})>"
