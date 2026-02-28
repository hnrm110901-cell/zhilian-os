"""
Deadline 定时管理服务（Timing Service）

职责：
  - 计算各阶段距离 deadline 的剩余时间
  - T-10 分钟发 WeChat 预警（非致命）
  - 过期阶段自动锁定（由 Celery 每 5 分钟调用）
  - 为 API 提供实时倒计时信息

设计原则：
  - 所有方法非致命（单个门店失败不影响全局扫描）
  - auto_lock 后推进到下一阶段（WorkflowEngine.lock_phase 负责）
  - 日志详细，便于事后审计
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.workflow import PhaseStatus, WorkflowPhase, WorkflowStatus

logger = structlog.get_logger()

# 发送 WeChat 预警的时间点（距 deadline 多少分钟）
WARNING_MINUTES = [30, 10, 5]


class TimingService:
    """
    Deadline 管理服务

    使用示例::

        svc = TimingService(db)
        overdue = await svc.check_and_auto_lock_all()
        # overdue = ["STORE001/procurement", "STORE002/scheduling"]
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── 核心：扫描并自动锁定所有过期阶段 ─────────────────────────────────────

    async def check_and_auto_lock_all(self) -> List[str]:
        """
        扫描全平台所有 running/reviewing 阶段：
          - 已过 deadline → 自动锁定
          - 距 deadline ≤ 10 min → 发送 WeChat 预警

        由 Celery 每 5 分钟调用（`check_workflow_deadlines` 任务）。

        Returns:
            已自动锁定的阶段列表，格式 ["STORE001/procurement", ...]
        """
        now      = datetime.utcnow()
        locked   = []
        warned   = []

        stmt = select(WorkflowPhase).where(
            WorkflowPhase.status.in_([
                PhaseStatus.RUNNING.value,
                PhaseStatus.REVIEWING.value,
            ])
        )
        phases = (await self.db.execute(stmt)).scalars().all()

        for phase in phases:
            try:
                remaining = self.get_time_remaining(phase, now)

                if remaining.total_seconds() <= 0:
                    # 过期 → 自动锁定
                    await self._auto_lock(phase)
                    locked.append(f"{phase.phase_name}@{phase.workflow_id}")

                elif remaining.total_seconds() <= 10 * 60:
                    # ≤10 分钟 → 发预警
                    mins = int(remaining.total_seconds() / 60)
                    await self._send_deadline_warning(phase, mins)
                    warned.append(f"{phase.phase_name}({mins}min)")

            except Exception as e:
                logger.warning(
                    "阶段 deadline 检查失败",
                    phase_id=str(phase.id),
                    error=str(e),
                )

        if locked:
            logger.info("自动锁定阶段", locked=locked)
        if warned:
            logger.info("Deadline 预警发送", warned=warned)

        return locked

    # ── 倒计时查询 ────────────────────────────────────────────────────────────

    def get_time_remaining(
        self,
        phase: WorkflowPhase,
        now:   Optional[datetime] = None,
    ) -> timedelta:
        """返回距 deadline 的剩余时间（负数表示已过期）"""
        if now is None:
            now = datetime.utcnow()
        if phase.deadline is None:
            return timedelta(hours=24)   # 无 deadline = 宽松
        return phase.deadline - now

    def is_overdue(self, phase: WorkflowPhase) -> bool:
        return self.get_time_remaining(phase).total_seconds() < 0

    def format_countdown(self, phase: WorkflowPhase) -> str:
        """返回可读倒计时字符串，如 '剩余 23 分钟' 或 '已逾期 5 分钟'"""
        remaining = self.get_time_remaining(phase)
        secs      = int(remaining.total_seconds())
        if secs < 0:
            mins = abs(secs) // 60
            return f"已逾期 {mins} 分钟"
        elif secs < 3600:
            return f"剩余 {secs // 60} 分钟"
        else:
            h, m = divmod(secs // 60, 60)
            return f"剩余 {h}h{m}min"

    # ── 当前工作流所有阶段的 deadline 摘要 ───────────────────────────────────

    async def get_workflow_countdown(
        self, workflow_id
    ) -> List[Dict[str, Any]]:
        """
        返回工作流所有阶段的 deadline 状态摘要（供前端倒计时组件使用）。

        Returns:
            [{phase_name, phase_order, deadline_str, status,
              countdown, is_overdue, locked_at}]
        """
        stmt = (
            select(WorkflowPhase)
            .where(WorkflowPhase.workflow_id == workflow_id)
            .order_by(WorkflowPhase.phase_order)
        )
        phases = (await self.db.execute(stmt)).scalars().all()

        result = []
        for phase in phases:
            result.append({
                "phase_name":  phase.phase_name,
                "phase_order": phase.phase_order,
                "deadline":    phase.deadline.strftime("%H:%M") if phase.deadline else None,
                "status":      phase.status,
                "countdown":   self.format_countdown(phase),
                "is_overdue":  self.is_overdue(phase),
                "locked_at":   phase.locked_at.isoformat() if phase.locked_at else None,
                "locked_by":   phase.locked_by,
            })
        return result

    # ── 内部方法 ──────────────────────────────────────────────────────────────

    async def _auto_lock(self, phase: WorkflowPhase) -> None:
        """自动锁定过期阶段（调用 WorkflowEngine.lock_phase）"""
        from src.services.workflow_engine import WorkflowEngine
        engine = WorkflowEngine(self.db)
        await engine.lock_phase(phase.id, locked_by="auto")
        logger.info(
            "阶段自动锁定（deadline 过期）",
            phase_name=phase.phase_name,
            deadline=str(phase.deadline),
        )

    async def _send_deadline_warning(
        self, phase: WorkflowPhase, minutes_remaining: int
    ) -> None:
        """发送 deadline 预警到企业微信（非致命）"""
        try:
            from src.services.wechat_action_fsm import get_wechat_fsm, ActionCategory, ActionPriority

            # 查询所属门店 ID
            from src.models.workflow import DailyWorkflow
            wf_stmt = select(DailyWorkflow).where(DailyWorkflow.id == phase.workflow_id)
            wf = (await self.db.execute(wf_stmt)).scalar_one_or_none()
            store_id = wf.store_id if wf else "unknown"

            PHASE_LABELS = {
                "initial_plan": "初版规划",
                "procurement":  "采购确认",
                "scheduling":   "排班确认",
                "menu":         "菜单确认",
                "menu_sync":    "菜单同步",
                "marketing":    "营销推送",
            }
            label    = PHASE_LABELS.get(phase.phase_name, phase.phase_name)
            priority = ActionPriority.P0 if minutes_remaining <= 5 else ActionPriority.P1
            receiver = os.getenv("WECHAT_DEFAULT_RECEIVER", "store_manager")

            fsm = get_wechat_fsm()
            action = await fsm.create_action(
                store_id=store_id,
                category=ActionCategory.SYSTEM,
                priority=priority,
                title=f"⏰ {label}即将截止",
                content=(
                    f"距「{label}」截止时间还有 {minutes_remaining} 分钟\n"
                    f"截止时间：{phase.deadline.strftime('%H:%M') if phase.deadline else 'N/A'}\n"
                    f"请尽快确认并锁定，逾期将自动锁定当前版本"
                ),
                receiver_user_id=receiver,
                source_event_id=str(phase.id),
            )
            await fsm.push_to_wechat(action.action_id)

        except Exception as e:
            logger.warning(
                "Deadline 预警推送失败（非致命）",
                phase_name=phase.phase_name,
                error=str(e),
            )
