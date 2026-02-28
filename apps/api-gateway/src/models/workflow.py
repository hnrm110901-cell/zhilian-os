"""
多阶段工作流引擎 ORM 模型

DailyWorkflow    — 每家门店每日一条规划记录（Day N 晚上规划 Day N+1）
WorkflowPhase    — 工作流的 6 个阶段（各有硬 deadline）
DecisionVersion  — 阶段内决策版本快照（版本链，支持 diff 回溯）

六阶段时间线（Day N 当天）：
  17:00-17:30  Phase 1: initial_plan   初版规划（快速模式）
  17:30-18:00  Phase 2: procurement    采购确认 → 18:00 LOCK
  18:00-19:00  Phase 3: scheduling     排班确认 → 19:00 LOCK
  19:00-20:00  Phase 4: menu           菜单确认 → 20:00 LOCK
  20:00-21:00  Phase 5: menu_sync      菜单同步（自动执行）
  21:00-22:00  Phase 6: marketing      营销推送 → 22:00 LOCK
"""

import uuid
import enum
from datetime import date, datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Date, Float, Index, Integer,
    String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB

from src.models.base import Base, TimestampMixin


# ── 枚举 ─────────────────────────────────────────────────────────────────────

class WorkflowStatus(str, enum.Enum):
    PENDING        = "pending"          # 尚未启动
    RUNNING        = "running"          # 正在进行（有阶段处于 running/reviewing）
    PARTIAL_LOCKED = "partial_locked"   # 部分阶段已锁定
    FULLY_LOCKED   = "fully_locked"     # 全部阶段已锁定
    COMPLETED      = "completed"        # 工作流完成


class PhaseStatus(str, enum.Enum):
    PENDING   = "pending"    # 等待前置阶段完成
    RUNNING   = "running"    # 正在进行（接受版本提交）
    REVIEWING = "reviewing"  # 等待店长确认
    LOCKED    = "locked"     # 已锁定（不可修改）
    COMPLETED = "completed"  # 已完成执行（menu_sync 等自动阶段）
    SKIPPED   = "skipped"    # 跳过（配置禁用）


class GenerationMode(str, enum.Enum):
    FAST    = "fast"     # 快速模式（历史规律 + 简化算法，<30s）
    PRECISE = "precise"  # 精确模式（完整算法，5-10min）
    MANUAL  = "manual"   # 人工录入


# ── 阶段名称常量 ──────────────────────────────────────────────────────────────

PHASE_INITIAL_PLAN  = "initial_plan"
PHASE_PROCUREMENT   = "procurement"
PHASE_SCHEDULING    = "scheduling"
PHASE_MENU          = "menu"
PHASE_MENU_SYNC     = "menu_sync"
PHASE_MARKETING     = "marketing"

ALL_PHASES = [
    PHASE_INITIAL_PLAN,
    PHASE_PROCUREMENT,
    PHASE_SCHEDULING,
    PHASE_MENU,
    PHASE_MENU_SYNC,
    PHASE_MARKETING,
]

# 阶段配置：deadline偏移（相对规划触发时刻，单位分钟）及描述
PHASE_CONFIG: dict = {
    PHASE_INITIAL_PLAN: {"deadline_offset": 30,  "label": "初始规划"},
    PHASE_PROCUREMENT:  {"deadline_offset": 120, "label": "采购下单"},
    PHASE_SCHEDULING:   {"deadline_offset": 180, "label": "排班确认"},
    PHASE_MENU:         {"deadline_offset": 240, "label": "菜单定稿"},
    PHASE_MENU_SYNC:    {"deadline_offset": 300, "label": "菜单同步"},
    PHASE_MARKETING:    {"deadline_offset": 360, "label": "营销发布"},
}


# ── ORM 模型 ──────────────────────────────────────────────────────────────────

class DailyWorkflow(Base, TimestampMixin):
    """
    每家门店每日规划工作流

    每天下午 17:00 自动触发，覆盖 Day N+1 的完整规划：
      采购 → 排班 → 菜单 → 营销，每个阶段有硬 deadline 和自动锁定。

    Example::
        store_id   = "STORE001"
        plan_date  = 2026-03-02  (明天)
        trigger_date = 2026-03-01  (今天)
        status     = "partial_locked"  (采购已锁，其余进行中)
        current_phase = "scheduling"
    """
    __tablename__ = "daily_workflows"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id     = Column(String(50), nullable=False)
    plan_date    = Column(Date(),     nullable=False)   # 被规划的日期（明天）
    trigger_date = Column(Date(),     nullable=False)   # 触发规划的日期（今天）

    status        = Column(String(20), nullable=False, default=WorkflowStatus.PENDING.value)
    current_phase = Column(String(30))

    started_at   = Column(DateTime())
    completed_at = Column(DateTime())

    # 门店个性化截止时间配置（覆盖默认值）
    # {"procurement_deadline": "17:45", "scheduling_deadline": "18:30"}
    store_config = Column(JSONB())

    __table_args__ = (
        UniqueConstraint("store_id", "plan_date", name="uq_daily_workflow_store_plan_date"),
        Index("idx_wf_store_date",   "store_id",     "plan_date"),
        Index("idx_wf_status",       "status"),
        Index("idx_wf_trigger_date", "trigger_date"),
    )

    def __repr__(self) -> str:
        return (
            f"<DailyWorkflow({self.store_id}/{self.plan_date}: "
            f"{self.status}, phase={self.current_phase})>"
        )


class WorkflowPhase(Base, TimestampMixin):
    """
    工作流阶段（6 个，各有硬 deadline）

    状态流转: pending → running → reviewing → locked
    locked 后 content 不可修改，current_version_id 指向最终版本。
    """
    __tablename__ = "workflow_phases"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id = Column(UUID(as_uuid=True), nullable=False)

    phase_name  = Column(String(30), nullable=False)   # 见 ALL_PHASES
    phase_order = Column(Integer(),  nullable=False)   # 1-6

    deadline = Column(DateTime(), nullable=False)      # 硬截止时间

    status     = Column(String(20), nullable=False, default=PhaseStatus.PENDING.value)
    started_at = Column(DateTime())
    locked_at  = Column(DateTime())
    locked_by  = Column(String(50))   # 'auto' 或 user_id

    # 最终版本指针（锁定时赋值）
    current_version_id = Column(UUID(as_uuid=True))

    __table_args__ = (
        UniqueConstraint("workflow_id", "phase_name", name="uq_workflow_phase_name"),
        Index("idx_wp_workflow_id", "workflow_id"),
        Index("idx_wp_status",      "status"),
        Index("idx_wp_deadline",    "deadline"),
    )

    def __repr__(self) -> str:
        return (
            f"<WorkflowPhase({self.phase_name}: {self.status}, "
            f"deadline={self.deadline.strftime('%H:%M') if self.deadline else 'N/A'})>"
        )


class DecisionVersion(Base):
    """
    阶段决策版本快照

    每次提交决策（快速规划/人工修改）生成一条记录，形成版本链。
    锁定时将最终版本的 is_final 置 True。

    content 格式按阶段：
      initial_plan:  {forecast_footfall: int, top_dishes: [...], risk_flags: [...]}
      procurement:   {items: [{ingredient, qty, unit, estimated_cost}], total_cost}
      scheduling:    {shifts: [{role, count, start_hour, end_hour}], total_hours}
      menu:          {featured: [...], stop_sell: [...], price_adjustments: [...]}
      menu_sync:     {synced_platforms: [...], sync_status: str}
      marketing:     {push_messages: [...], target_segments: [...], promo_items: [...]}
    """
    __tablename__ = "decision_versions"

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phase_id       = Column(UUID(as_uuid=True), nullable=False)

    # 冗余字段（避免多层 JOIN）
    store_id       = Column(String(50), nullable=False)
    phase_name     = Column(String(30), nullable=False)
    plan_date      = Column(Date(),     nullable=False)
    version_number = Column(Integer(),  nullable=False)   # 从 1 开始递增

    # 决策内容（各阶段格式不同，见文档）
    content = Column(JSONB(), nullable=False)

    # 生成元数据
    generation_mode    = Column(String(20))   # fast / precise / manual
    generation_seconds = Column(Float())      # 实际生成耗时（秒）
    data_completeness  = Column(Float())      # 输入数据完整度（0-1，1=完整）
    confidence         = Column(Float())      # 系统置信度（0-1）

    # 版本差异（与上一版本的 diff）
    changes_from_prev = Column(JSONB())  # {added: [], removed: [], modified: []}
    change_reason     = Column(Text())   # 变更原因说明

    submitted_by = Column(String(50))   # 'system' 或 user_id
    is_final     = Column(Boolean(),    default=False)   # True = 最终锁定版本

    created_at = Column(DateTime(), default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("phase_id", "version_number", name="uq_decision_version_phase_ver"),
        Index("idx_dv_phase_id",   "phase_id"),
        Index("idx_dv_store_date", "store_id", "plan_date"),
        Index("idx_dv_is_final",   "is_final"),
    )

    def __repr__(self) -> str:
        return (
            f"<DecisionVersion({self.phase_name} v{self.version_number} "
            f"[{self.generation_mode}] "
            f"{'★FINAL' if self.is_final else ''})>"
        )
