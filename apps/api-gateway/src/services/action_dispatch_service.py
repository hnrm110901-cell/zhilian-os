"""
L5 行动调度服务（Action Dispatch Service）

职责：
  将 L4 推理报告（ReasoningReport）转化为可执行行动：
    P1 → WeChat FSM（P1 自动升级 2h）+ URGENT 任务 + 审批申请（cost/waste 维度）
    P2 → WeChat FSM（P2 自动升级 24h）+ HIGH 任务
    P3 → WeChat 通知（无任务，仅提示）
    OK → 跳过

整合三大子系统：
  WeChatActionFSM   — 状态机管理 WeChat 推送 + 自动升级
  TaskService       — URGENT/HIGH 任务派发给门店负责人
  ApprovalService   — cost/waste P1 高风险场景触发审批流

设计：
  - 每份 ReasoningReport(P1/P2/P3) 对应唯一一个 ActionPlan（upsert 防重）
  - 子系统调用全部非致命（dispatch_status = partial 而不是 failed）
  - 支持单报告 dispatch 和批量 dispatch_pending
"""

from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.action_plan import ActionOutcome, ActionPlan, DispatchStatus
from src.models.reasoning import ReasoningReport

logger = structlog.get_logger()

# ── 维度 → 行动类别映射 ────────────────────────────────────────────────────────

# WeChatActionFSM 的 ActionCategory 字符串常量
_CAT = {
    "waste":       "waste_alert",
    "efficiency":  "kpi_alert",
    "quality":     "anomaly",
    "cost":        "kpi_alert",
    "inventory":   "inventory_low",
    "cross_store": "kpi_alert",
}

# ApprovalService 需要审批的维度（P1 才触发）
_NEEDS_APPROVAL = {"waste", "cost"}

# 维度 → DecisionType 字符串映射（ApprovalService 使用）
_DECISION_TYPE = {
    "waste":       "cost_optimization",
    "cost":        "cost_optimization",
    "efficiency":  "kpi_improvement",
    "quality":     "kpi_improvement",
    "inventory":   "inventory_alert",
    "cross_store": "kpi_improvement",
}

# 严重程度 → WeChatActionFSM ActionPriority
_WECHAT_PRIORITY = {"P1": "P1", "P2": "P2", "P3": "P3"}

# 严重程度 → TaskPriority
_TASK_PRIORITY = {"P1": "urgent", "P2": "high", "P3": "normal"}

# 跟进诊断等待天数（行动后多少天再做一次 L4 扫描）
_FOLLOWUP_DAYS = {"P1": 3, "P2": 7, "P3": 14}


class ActionDispatchService:
    """
    L5 行动调度服务

    使用方式::

        svc = ActionDispatchService(db)
        plan = await svc.dispatch_from_report(report)
        # plan.dispatch_status → "dispatched" / "partial"
        # plan.wechat_action_id → "ACT-..."
        # plan.task_id → UUID

    批量模式::

        result = await svc.dispatch_pending_alerts()
        # result = {plans_created, dispatched, partial, skipped, errors}
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── 主入口：单报告派发 ────────────────────────────────────────────────────

    async def dispatch_from_report(
        self,
        report: ReasoningReport,
    ) -> ActionPlan:
        """
        从一条 L4 推理报告生成并执行行动计划。

        幂等：若 (reasoning_report_id) 已有 ActionPlan，直接返回现有记录。

        Args:
            report: ReasoningReport ORM 对象（severity ∈ P1/P2/P3）

        Returns:
            ActionPlan — 新建或已存在的行动计划
        """
        if report.severity == "OK":
            return await self._make_skipped_plan(report)

        # 幂等检查
        existing = await self._get_plan_by_report(report.id)
        if existing:
            logger.info(
                "行动计划已存在，跳过重复派发",
                report_id=str(report.id),
                plan_id=str(existing.id),
            )
            return existing

        # 创建行动计划骨架
        plan = ActionPlan(
            id=uuid.uuid4(),
            reasoning_report_id=report.id,
            store_id=report.store_id,
            report_date=report.report_date,
            dimension=report.dimension,
            severity=report.severity,
            root_cause=report.root_cause,
            confidence=report.confidence,
            dispatch_status=DispatchStatus.PENDING.value,
            outcome=ActionOutcome.PENDING.value,
        )
        self.db.add(plan)
        await self.db.flush()  # 获取 plan.id，尚未提交

        # 按严重程度执行行动
        dispatched_actions: List[str] = []
        try:
            if report.severity == "P1":
                await self._dispatch_p1(plan, report, dispatched_actions)
            elif report.severity == "P2":
                await self._dispatch_p2(plan, report, dispatched_actions)
            else:  # P3
                await self._dispatch_p3(plan, report, dispatched_actions)
        except Exception as e:
            logger.error("行动派发异常", plan_id=str(plan.id), error=str(e))

        # 更新状态
        plan.dispatched_actions = dispatched_actions
        plan.dispatched_at = datetime.utcnow()
        plan.dispatch_status = (
            DispatchStatus.DISPATCHED.value if dispatched_actions
            else DispatchStatus.FAILED.value
        )

        logger.info(
            "行动计划派发完成",
            plan_id=str(plan.id),
            store_id=plan.store_id,
            severity=plan.severity,
            dimension=plan.dimension,
            actions=dispatched_actions,
        )
        return plan

    # ── 批量派发（扫描所有未处理的 P1/P2 报告） ──────────────────────────────

    async def dispatch_pending_alerts(
        self,
        store_id: Optional[str] = None,
        days_back: int = 1,
    ) -> Dict[str, Any]:
        """
        扫描近 N 天内未派发行动的 P1/P2 推理报告，批量生成行动计划。

        Args:
            store_id:  指定门店（None = 全平台）
            days_back: 回溯天数（默认 1 = 仅处理昨日和今日报告）

        Returns:
            {plans_created, dispatched, partial, skipped, errors}
        """
        since = date.today() - timedelta(days=days_back)

        # 找出无行动计划的 P1/P2 报告
        conditions = [
            ReasoningReport.severity.in_(["P1", "P2"]),
            ReasoningReport.report_date >= since,
            ReasoningReport.is_actioned == False,  # noqa: E712
        ]
        if store_id:
            conditions.append(ReasoningReport.store_id == store_id)

        # 已有行动计划的报告 ID
        existing_stmt = select(ActionPlan.reasoning_report_id)
        existing_ids = {r for (r,) in (await self.db.execute(existing_stmt)).all()}

        stmt = (
            select(ReasoningReport)
            .where(and_(*conditions))
            .order_by(ReasoningReport.severity, ReasoningReport.report_date.desc())
            .limit(500)
        )
        reports = (await self.db.execute(stmt)).scalars().all()

        stats = {"plans_created": 0, "dispatched": 0, "partial": 0, "skipped": 0, "errors": 0}
        for report in reports:
            if report.id in existing_ids:
                stats["skipped"] += 1
                continue
            try:
                plan = await self.dispatch_from_report(report)
                stats["plans_created"] += 1
                if plan.dispatch_status == DispatchStatus.DISPATCHED.value:
                    stats["dispatched"] += 1
                elif plan.dispatch_status == DispatchStatus.PARTIAL.value:
                    stats["partial"] += 1
            except Exception as e:
                logger.error(
                    "批量派发单报告失败",
                    report_id=str(report.id),
                    error=str(e),
                )
                stats["errors"] += 1

        logger.info("批量行动派发完成", **stats)
        return stats

    # ── 结果记录（反馈闭环） ──────────────────────────────────────────────────

    async def record_outcome(
        self,
        plan_id: uuid.UUID,
        outcome: str,
        resolved_by: str,
        outcome_note: str = "",
        kpi_delta: Optional[Dict] = None,
        followup_report_id: Optional[uuid.UUID] = None,
    ) -> Optional[ActionPlan]:
        """
        记录行动结果（L4→L5→L4 反馈闭环）。

        Args:
            plan_id:            ActionPlan.id
            outcome:            resolved / escalated / expired / no_effect / cancelled
            resolved_by:        操作人（员工 ID 或 "system"）
            outcome_note:       补充说明
            kpi_delta:          {metric: {before, after, delta}} KPI 改善量
            followup_report_id: 行动后下一次 L4 诊断报告 ID

        Returns:
            更新后的 ActionPlan，若不存在返回 None
        """
        plan = await self._get_plan(plan_id)
        if not plan:
            return None

        plan.outcome            = outcome
        plan.outcome_note       = outcome_note
        plan.resolved_at        = datetime.utcnow()
        plan.resolved_by        = resolved_by
        plan.kpi_delta          = kpi_delta
        plan.followup_report_id = followup_report_id

        logger.info(
            "行动结果记录",
            plan_id=str(plan_id),
            outcome=outcome,
            resolved_by=resolved_by,
        )
        return plan

    # ── 查询接口 ──────────────────────────────────────────────────────────────

    async def list_plans(
        self,
        store_id: str,
        days:     int = 30,
        severity: Optional[str] = None,
        outcome:  Optional[str] = None,
        limit:    int = 50,
    ) -> List[ActionPlan]:
        """查询门店行动计划历史"""
        since = date.today() - timedelta(days=days)
        conditions = [
            ActionPlan.store_id    == store_id,
            ActionPlan.report_date >= since,
        ]
        if severity:
            conditions.append(ActionPlan.severity == severity)
        if outcome:
            conditions.append(ActionPlan.outcome == outcome)

        stmt = (
            select(ActionPlan)
            .where(and_(*conditions))
            .order_by(ActionPlan.report_date.desc())
            .limit(limit)
        )
        return (await self.db.execute(stmt)).scalars().all()

    async def get_platform_stats(self, days: int = 7) -> Dict[str, Any]:
        """全平台行动派发统计（供大屏展示）"""
        from sqlalchemy import func
        since = date.today() - timedelta(days=days)

        # dispatch_status 分布
        ds_stmt = (
            select(ActionPlan.dispatch_status, func.count().label("cnt"))
            .where(ActionPlan.report_date >= since)
            .group_by(ActionPlan.dispatch_status)
        )
        dispatch_dist = {
            row.dispatch_status: row.cnt
            for row in (await self.db.execute(ds_stmt)).all()
        }

        # outcome 分布
        oc_stmt = (
            select(ActionPlan.outcome, func.count().label("cnt"))
            .where(ActionPlan.report_date >= since)
            .group_by(ActionPlan.outcome)
        )
        outcome_dist = {
            row.outcome: row.cnt
            for row in (await self.db.execute(oc_stmt)).all()
        }

        # severity 分布
        sv_stmt = (
            select(ActionPlan.severity, func.count().label("cnt"))
            .where(ActionPlan.report_date >= since)
            .group_by(ActionPlan.severity)
        )
        severity_dist = {
            row.severity: row.cnt
            for row in (await self.db.execute(sv_stmt)).all()
        }

        total = sum(dispatch_dist.values())
        return {
            "days":          days,
            "total_plans":   total,
            "dispatch_dist": dispatch_dist,
            "outcome_dist":  outcome_dist,
            "severity_dist": severity_dist,
        }

    # ── P1 行动：WeChat P1 + URGENT Task + 审批（cost/waste 维度） ────────────

    async def _dispatch_p1(
        self,
        plan: ActionPlan,
        report: ReasoningReport,
        dispatched: List[str],
    ) -> None:
        await self._push_wechat_action(plan, report, "P1", dispatched)
        await self._create_task(plan, report, "urgent", dispatched)
        if report.dimension in _NEEDS_APPROVAL:
            await self._create_approval(plan, report, dispatched)

    # ── P2 行动：WeChat P2 + HIGH Task ───────────────────────────────────────

    async def _dispatch_p2(
        self,
        plan: ActionPlan,
        report: ReasoningReport,
        dispatched: List[str],
    ) -> None:
        await self._push_wechat_action(plan, report, "P2", dispatched)
        await self._create_task(plan, report, "high", dispatched)

    # ── P3 行动：WeChat 通知（轻量，无任务）──────────────────────────────────

    async def _dispatch_p3(
        self,
        plan: ActionPlan,
        report: ReasoningReport,
        dispatched: List[str],
    ) -> None:
        await self._push_wechat_action(plan, report, "P3", dispatched)

    # ── WeChat FSM 推送 ───────────────────────────────────────────────────────

    async def _push_wechat_action(
        self,
        plan: ActionPlan,
        report: ReasoningReport,
        priority_str: str,
        dispatched: List[str],
    ) -> None:
        try:
            from src.services.wechat_action_fsm import (
                ActionCategory, ActionPriority, get_wechat_fsm,
            )
            fsm      = get_wechat_fsm()
            category = ActionCategory(_CAT.get(report.dimension, "kpi_alert"))
            priority = ActionPriority(priority_str)

            dim_cn = {
                "waste": "损耗", "efficiency": "效率",
                "quality": "质量", "cost": "成本",
                "inventory": "库存", "cross_store": "跨店",
            }.get(report.dimension, report.dimension)

            actions_text = ""
            if report.recommended_actions:
                actions_text = "\n".join(
                    f"  {i+1}. {a}"
                    for i, a in enumerate(report.recommended_actions[:3])
                )

            receiver = os.getenv("WECHAT_DEFAULT_RECEIVER", "store_manager")
            action   = await fsm.create_action(
                store_id=report.store_id,
                category=category,
                priority=priority,
                title=f"[{priority_str}] {report.store_id} {dim_cn}维度异常",
                content=(
                    f"根因：{report.root_cause or '待分析'}\n"
                    f"置信度：{report.confidence:.0%}\n"
                    f"建议行动：\n{actions_text or '请查看推理报告详情'}"
                ),
                receiver_user_id=receiver,
                source_event_id=str(report.id),
                evidence={
                    "dimension":  report.dimension,
                    "severity":   report.severity,
                    "confidence": report.confidence,
                    "root_cause": report.root_cause,
                },
            )
            await fsm.push_to_wechat(action.action_id)
            plan.wechat_action_id = action.action_id
            dispatched.append("wechat_action")
        except Exception as e:
            logger.warning("WeChat 行动推送失败（非致命）", error=str(e))

    # ── Task 创建 ─────────────────────────────────────────────────────────────

    async def _create_task(
        self,
        plan: ActionPlan,
        report: ReasoningReport,
        priority_str: str,
        dispatched: List[str],
    ) -> None:
        try:
            from src.services.task_service import TaskService
            from src.models.task import TaskPriority

            task_svc = TaskService()
            priority = TaskPriority(priority_str)

            dim_cn = {
                "waste": "损耗管控", "efficiency": "效率提升",
                "quality": "质量改善", "cost": "成本控制",
                "inventory": "库存优化", "cross_store": "跨店对标",
            }.get(report.dimension, report.dimension)

            actions_text = "\n".join(
                f"{i+1}. {a}"
                for i, a in enumerate((report.recommended_actions or [])[:5])
            ) or "请参考推理报告详情制定改善方案"

            due_days = {"urgent": 1, "high": 3}.get(priority_str, 7)
            due_at   = datetime.utcnow().replace(hour=23, minute=59, second=0) + timedelta(days=due_days - 1)

            system_user_id = uuid.UUID(os.getenv("SYSTEM_USER_ID", "00000000-0000-0000-0000-000000000001"))
            task = await task_svc.create_task(
                title=f"[{report.severity}] {dim_cn}改善任务 — {report.store_id}",
                content=(
                    f"推理报告：{str(report.id)}\n"
                    f"报告日期：{report.report_date}\n"
                    f"根因分析：{report.root_cause or '待分析'}\n"
                    f"建议行动：\n{actions_text}"
                ),
                creator_id=system_user_id,
                store_id=report.store_id,
                category=f"l4_reasoning_{report.dimension}",
                priority=priority,
                due_at=due_at,
            )
            plan.task_id = task.id
            dispatched.append("task")
        except Exception as e:
            logger.warning("任务创建失败（非致命）", error=str(e))

    # ── 审批申请（cost/waste P1） ─────────────────────────────────────────────

    async def _create_approval(
        self,
        plan: ActionPlan,
        report: ReasoningReport,
        dispatched: List[str],
    ) -> None:
        try:
            from src.services.approval_service import ApprovalService
            from src.models.decision_log import DecisionType

            approval_svc = ApprovalService()
            dtype_str    = _DECISION_TYPE.get(report.dimension, "kpi_improvement")
            dtype        = DecisionType(dtype_str)

            dl = await approval_svc.create_approval_request(
                decision_type=dtype,
                agent_type="L4ReasoningEngine",
                agent_method=f"diagnose_{report.dimension}",
                store_id=report.store_id,
                ai_suggestion={
                    "dimension":  report.dimension,
                    "root_cause": report.root_cause,
                    "actions":    report.recommended_actions,
                },
                ai_confidence=report.confidence or 0.0,
                ai_reasoning="\n".join(report.evidence_chain or []),
                context_data={
                    "report_id":  str(report.id),
                    "report_date": str(report.report_date),
                    "severity":   report.severity,
                    "kpi_snapshot": report.kpi_snapshot,
                },
                db=self.db,
            )
            plan.decision_log_id = uuid.UUID(str(dl.id))
            dispatched.append("approval_request")
        except Exception as e:
            logger.warning("审批申请创建失败（非致命）", error=str(e))

    # ── 内部工具 ──────────────────────────────────────────────────────────────

    async def _make_skipped_plan(self, report: ReasoningReport) -> ActionPlan:
        """为 OK 级别报告创建 SKIPPED 行动计划"""
        existing = await self._get_plan_by_report(report.id)
        if existing:
            return existing
        plan = ActionPlan(
            id=uuid.uuid4(),
            reasoning_report_id=report.id,
            store_id=report.store_id,
            report_date=report.report_date,
            dimension=report.dimension,
            severity=report.severity,
            confidence=report.confidence,
            dispatch_status=DispatchStatus.SKIPPED.value,
            outcome=ActionOutcome.RESOLVED.value,  # OK 视为无需处理
        )
        self.db.add(plan)
        await self.db.flush()
        return plan

    async def _get_plan_by_report(self, report_id: uuid.UUID) -> Optional[ActionPlan]:
        stmt = select(ActionPlan).where(ActionPlan.reasoning_report_id == report_id)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def _get_plan(self, plan_id: uuid.UUID) -> Optional[ActionPlan]:
        stmt = select(ActionPlan).where(ActionPlan.id == plan_id)
        return (await self.db.execute(stmt)).scalar_one_or_none()
