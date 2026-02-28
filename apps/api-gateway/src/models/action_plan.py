"""
L5 行动层 ORM 模型

ActionPlan — L5 行动计划（每条 P1/P2/P3 推理报告 → 一个行动计划）

设计：
  - 每份触发行动的 ReasoningReport 对应唯一一个 ActionPlan
  - 追踪 WeChat 推送 / Task 创建 / 审批申请 / 通知发送
  - outcome 字段形成 L4→L5→L4 反馈闭环
"""

import uuid
import enum
from datetime import date, datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Date, Float, Index, String, Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB

from src.models.base import Base, TimestampMixin


class DispatchStatus(str, enum.Enum):
    PENDING    = "pending"     # 待派发
    DISPATCHED = "dispatched"  # 全部派发成功
    PARTIAL    = "partial"     # 部分派发（有子系统失败）
    FAILED     = "failed"      # 全部失败
    SKIPPED    = "skipped"     # 跳过（OK 或重复）


class ActionOutcome(str, enum.Enum):
    PENDING   = "pending"    # 尚未结果
    RESOLVED  = "resolved"   # 问题已解决
    ESCALATED = "escalated"  # 已升级处理
    EXPIRED   = "expired"    # 超时未处理
    NO_EFFECT = "no_effect"  # 行动无效果
    CANCELLED = "cancelled"  # 已取消


class ActionPlan(Base, TimestampMixin):
    """
    L5 行动计划

    每条记录描述「针对某份推理报告，L5 层派发了哪些行动，以及最终结果」。

    Example::
        report: STORE001 / 2026-03-01 / waste / P1 / confidence=0.85
        action_plan:
          wechat_action_id = "act_20260301_waste_001"   # WeChat FSM
          task_id          = UUID(...)                   # URGENT 任务
          dispatch_status  = DISPATCHED
          outcome          = RESOLVED (3 天后)
          kpi_delta        = {"waste_rate": {"before": 0.15, "after": 0.11, "delta": -0.04}}
    """
    __tablename__ = "action_plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 关联 L4 推理报告
    reasoning_report_id = Column(UUID(as_uuid=True), nullable=False)

    # 冗余索引字段（避免频繁 JOIN）
    store_id    = Column(String(50),  nullable=False)
    report_date = Column(Date(),      nullable=False)
    dimension   = Column(String(30),  nullable=False)
    severity    = Column(String(10),  nullable=False)
    root_cause  = Column(String(200))
    confidence  = Column(Float())

    # 派发结果
    wechat_action_id = Column(String(100))           # WeChatActionFSM action_id
    task_id          = Column(UUID(as_uuid=True))    # tasks.id
    decision_log_id  = Column(UUID(as_uuid=True))    # decision_logs.id（审批流）
    notification_ids = Column(JSONB())               # List[str]

    # 派发状态
    dispatch_status    = Column(String(20), nullable=False, default=DispatchStatus.PENDING.value)
    dispatched_at      = Column(DateTime())
    dispatched_actions = Column(JSONB())             # List[str] 实际执行的行动类型

    # 结果追踪
    outcome      = Column(String(20), nullable=False, default=ActionOutcome.PENDING.value)
    outcome_note = Column(Text())
    resolved_at  = Column(DateTime())
    resolved_by  = Column(String(100))

    # 跟进诊断（行动后下一次 L4 扫描报告）
    followup_report_id = Column(UUID(as_uuid=True))

    # KPI 变化量（行动效果评估）
    kpi_delta = Column(JSONB())

    __table_args__ = (
        UniqueConstraint(
            "reasoning_report_id",
            name="uq_action_plan_report_id",
        ),
        Index("idx_ap_store_date",      "store_id",       "report_date"),
        Index("idx_ap_severity",        "severity"),
        Index("idx_ap_dispatch_status", "dispatch_status"),
        Index("idx_ap_outcome",         "outcome"),
        Index("idx_ap_dimension",       "dimension"),
    )

    def __repr__(self) -> str:
        return (
            f"<ActionPlan({self.store_id}/{self.dimension}/{self.report_date}: "
            f"{self.severity} → {self.dispatch_status}/{self.outcome})>"
        )
