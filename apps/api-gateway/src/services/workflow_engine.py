"""
多阶段工作流引擎（Workflow Engine）

职责：
  管理 Day N 晚上（17:00-22:00）的 6 阶段规划流程：
    1. initial_plan  17:00-17:30  初版规划
    2. procurement   17:30-18:00  采购确认 → 18:00 LOCK
    3. scheduling    18:00-19:00  排班确认 → 19:00 LOCK
    4. menu          19:00-20:00  菜单确认 → 20:00 LOCK
    5. menu_sync     20:00-21:00  菜单同步（自动）
    6. marketing     21:00-22:00  营销推送 → 22:00 LOCK

核心保证：
  - 每阶段有硬 deadline，过期自动锁定
  - 后阶段无法修改前阶段已锁定内容
  - 每次决策提交生成 DecisionVersion 快照（版本链）
  - start_daily_workflow 幂等（同日重复调用安全）
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import structlog
from sqlalchemy import and_, select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.workflow import (
    ALL_PHASES,
    PHASE_INITIAL_PLAN, PHASE_PROCUREMENT, PHASE_SCHEDULING,
    PHASE_MENU, PHASE_MENU_SYNC, PHASE_MARKETING,
    DailyWorkflow, DecisionVersion, GenerationMode,
    PhaseStatus, WorkflowPhase, WorkflowStatus,
)

logger = structlog.get_logger()


# ── 阶段配置（默认截止时间） ──────────────────────────────────────────────────

PHASE_CONFIG: Dict[str, Dict] = {
    PHASE_INITIAL_PLAN: {
        "order":           1,
        "deadline_hour":   17,
        "deadline_minute": 30,
        "is_auto":         False,   # 需要店长确认
        "label":           "初版规划",
    },
    PHASE_PROCUREMENT: {
        "order":           2,
        "deadline_hour":   18,
        "deadline_minute": 0,
        "is_auto":         False,
        "label":           "采购确认",
    },
    PHASE_SCHEDULING: {
        "order":           3,
        "deadline_hour":   19,
        "deadline_minute": 0,
        "is_auto":         False,
        "label":           "排班确认",
    },
    PHASE_MENU: {
        "order":           4,
        "deadline_hour":   20,
        "deadline_minute": 0,
        "is_auto":         False,
        "label":           "菜单确认",
    },
    PHASE_MENU_SYNC: {
        "order":           5,
        "deadline_hour":   21,
        "deadline_minute": 0,
        "is_auto":         True,    # 自动执行，无需人工确认
        "label":           "菜单同步",
    },
    PHASE_MARKETING: {
        "order":           6,
        "deadline_hour":   22,
        "deadline_minute": 0,
        "is_auto":         False,
        "label":           "营销推送",
    },
}


class WorkflowEngine:
    """
    多阶段规划工作流引擎

    使用示例::

        engine = WorkflowEngine(db)
        wf = await engine.start_daily_workflow("STORE001", date(2026, 3, 2))
        phase = await engine.get_phase(wf.id, PHASE_PROCUREMENT)
        version = await engine.submit_decision(
            phase.id,
            content={"items": [...]},
            submitted_by="store_manager",
            mode="fast",
        )
        await engine.lock_phase(phase.id, locked_by="store_manager")
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── 工作流生命周期 ─────────────────────────────────────────────────────────

    async def start_daily_workflow(
        self,
        store_id:    str,
        plan_date:   date,
        store_config: Optional[Dict] = None,
    ) -> DailyWorkflow:
        """
        启动（或获取已有的）每日规划工作流（幂等）。

        同时初始化全部 6 个 WorkflowPhase 记录。

        Args:
            store_id:     门店 ID
            plan_date:    被规划的日期（明天）
            store_config: 个性化截止时间覆盖

        Returns:
            DailyWorkflow — 新建或已存在的工作流
        """
        # 幂等检查
        existing = await self.get_workflow_by_date(store_id, plan_date)
        if existing:
            logger.info("工作流已存在", store_id=store_id, plan_date=str(plan_date))
            return existing

        trigger_date = date.today()
        wf = DailyWorkflow(
            id=uuid.uuid4(),
            store_id=store_id,
            plan_date=plan_date,
            trigger_date=trigger_date,
            status=WorkflowStatus.RUNNING.value,
            current_phase=PHASE_INITIAL_PLAN,
            started_at=datetime.utcnow(),
            store_config=store_config or {},
        )
        self.db.add(wf)
        await self.db.flush()

        # 初始化 6 个阶段（第一个 RUNNING，其余 PENDING）
        for phase_name, cfg in PHASE_CONFIG.items():
            deadline = self._calc_deadline(trigger_date, cfg, store_config)
            status   = PhaseStatus.RUNNING.value if phase_name == PHASE_INITIAL_PLAN else PhaseStatus.PENDING.value
            phase    = WorkflowPhase(
                id=uuid.uuid4(),
                workflow_id=wf.id,
                phase_name=phase_name,
                phase_order=cfg["order"],
                deadline=deadline,
                status=status,
                started_at=datetime.utcnow() if phase_name == PHASE_INITIAL_PLAN else None,
            )
            self.db.add(phase)

        await self.db.flush()
        logger.info(
            "工作流已启动",
            store_id=store_id,
            plan_date=str(plan_date),
            workflow_id=str(wf.id),
        )
        return wf

    async def get_current_workflow(self, store_id: str) -> Optional[DailyWorkflow]:
        """获取门店当日（今天 trigger）正在进行的工作流"""
        today = date.today()
        stmt  = (
            select(DailyWorkflow)
            .where(
                and_(
                    DailyWorkflow.store_id    == store_id,
                    DailyWorkflow.trigger_date == today,
                )
            )
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_workflow_by_date(
        self, store_id: str, plan_date: date
    ) -> Optional[DailyWorkflow]:
        """按 store_id + plan_date 查找工作流"""
        stmt = select(DailyWorkflow).where(
            and_(
                DailyWorkflow.store_id  == store_id,
                DailyWorkflow.plan_date == plan_date,
            )
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    # ── 阶段管理 ──────────────────────────────────────────────────────────────

    async def get_phase(
        self, workflow_id: uuid.UUID, phase_name: str
    ) -> Optional[WorkflowPhase]:
        stmt = select(WorkflowPhase).where(
            and_(
                WorkflowPhase.workflow_id == workflow_id,
                WorkflowPhase.phase_name  == phase_name,
            )
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_all_phases(
        self, workflow_id: uuid.UUID
    ) -> List[WorkflowPhase]:
        stmt = (
            select(WorkflowPhase)
            .where(WorkflowPhase.workflow_id == workflow_id)
            .order_by(WorkflowPhase.phase_order)
        )
        return (await self.db.execute(stmt)).scalars().all()

    async def advance_to_next_phase(self, workflow_id: uuid.UUID) -> Optional[WorkflowPhase]:
        """
        完成当前阶段后推进到下一个阶段（将其状态改为 RUNNING）。

        Returns:
            下一个 WorkflowPhase，如果已是最后阶段则返回 None
        """
        phases = await self.get_all_phases(workflow_id)
        running_idx = next(
            (i for i, p in enumerate(phases) if p.status == PhaseStatus.RUNNING.value),
            None,
        )
        if running_idx is None or running_idx + 1 >= len(phases):
            return None

        next_phase            = phases[running_idx + 1]
        next_phase.status     = PhaseStatus.RUNNING.value
        next_phase.started_at = datetime.utcnow()

        # 更新工作流当前阶段
        wf = await self._get_workflow(workflow_id)
        if wf:
            wf.current_phase = next_phase.phase_name
            wf.status        = WorkflowStatus.PARTIAL_LOCKED.value

        return next_phase

    # ── 决策版本提交 ──────────────────────────────────────────────────────────

    async def submit_decision(
        self,
        phase_id:     uuid.UUID,
        content:      Dict[str, Any],
        submitted_by: str = "system",
        mode:         str = GenerationMode.FAST.value,
        generation_seconds: float = 0.0,
        data_completeness:  float = 1.0,
        confidence:         float = 0.8,
        change_reason:      str   = "",
    ) -> DecisionVersion:
        """
        向阶段提交新的决策版本。

        若阶段已 LOCKED，抛出 ValueError（已锁定不可修改）。

        Returns:
            新创建的 DecisionVersion
        """
        phase = await self._get_phase(phase_id)
        if phase.status == PhaseStatus.LOCKED.value:
            raise ValueError(f"阶段 {phase.phase_name} 已锁定，不可提交新版本")

        # 确定版本号
        count_stmt = select(func.count()).where(DecisionVersion.phase_id == phase_id)
        current_count = (await self.db.execute(count_stmt)).scalar() or 0
        version_number = current_count + 1

        # 计算与上一版本的 diff
        changes = {}
        if version_number > 1:
            prev_stmt = (
                select(DecisionVersion)
                .where(DecisionVersion.phase_id == phase_id)
                .order_by(DecisionVersion.version_number.desc())
                .limit(1)
            )
            prev = (await self.db.execute(prev_stmt)).scalar_one_or_none()
            if prev:
                changes = _simple_diff(prev.content, content)

        # 获取工作流上下文（plan_date 等冗余字段）
        wf_stmt = (
            select(DailyWorkflow)
            .join(WorkflowPhase, WorkflowPhase.workflow_id == DailyWorkflow.id)
            .where(WorkflowPhase.id == phase_id)
        )
        wf = (await self.db.execute(wf_stmt)).scalar_one_or_none()

        version = DecisionVersion(
            id=uuid.uuid4(),
            phase_id=phase_id,
            store_id=wf.store_id if wf else "",
            phase_name=phase.phase_name,
            plan_date=wf.plan_date if wf else date.today(),
            version_number=version_number,
            content=content,
            generation_mode=mode,
            generation_seconds=generation_seconds,
            data_completeness=data_completeness,
            confidence=confidence,
            changes_from_prev=changes,
            change_reason=change_reason,
            submitted_by=submitted_by,
            is_final=False,
        )
        self.db.add(version)
        await self.db.flush()

        # 更新阶段状态为 REVIEWING
        if phase.status == PhaseStatus.RUNNING.value:
            phase.status = PhaseStatus.REVIEWING.value
        phase.current_version_id = version.id

        logger.info(
            "决策版本提交",
            phase_name=phase.phase_name,
            version=version_number,
            mode=mode,
            confidence=confidence,
        )
        return version

    # ── 阶段锁定 ──────────────────────────────────────────────────────────────

    async def lock_phase(
        self,
        phase_id:  uuid.UUID,
        locked_by: str = "auto",
    ) -> WorkflowPhase:
        """
        锁定阶段：将当前版本标记为 is_final，阶段状态改为 LOCKED。

        Args:
            phase_id:  WorkflowPhase.id
            locked_by: 'auto'（超时自动锁）或 user_id（手动锁）

        Returns:
            已锁定的 WorkflowPhase
        """
        phase = await self._get_phase(phase_id)
        if phase.status == PhaseStatus.LOCKED.value:
            return phase  # 幂等

        # 标记最新版本为最终版
        if phase.current_version_id:
            ver_stmt = select(DecisionVersion).where(
                DecisionVersion.id == phase.current_version_id
            )
            version = (await self.db.execute(ver_stmt)).scalar_one_or_none()
            if version:
                version.is_final = True

        phase.status    = PhaseStatus.LOCKED.value
        phase.locked_at = datetime.utcnow()
        phase.locked_by = locked_by

        # 自动推进到下一阶段
        await self.advance_to_next_phase(phase.workflow_id)

        logger.info(
            "阶段已锁定",
            phase_name=phase.phase_name,
            locked_by=locked_by,
        )
        return phase

    # ── 超时检查 & Human-in-the-Loop 审批 ────────────────────────────────────

    async def check_expired_phases(self) -> List[WorkflowPhase]:
        """
        扫描所有已超过 deadline 的阶段并自动锁定。

        由 Celery Beat 定时任务调用（每 15 分钟一次）。

        Returns:
            本次被自动锁定的 WorkflowPhase 列表
        """
        now = datetime.utcnow()
        stmt = (
            select(WorkflowPhase)
            .where(
                and_(
                    WorkflowPhase.status.in_([
                        PhaseStatus.RUNNING.value,
                        PhaseStatus.REVIEWING.value,
                    ]),
                    WorkflowPhase.deadline < now,
                )
            )
        )
        expired_phases = (await self.db.execute(stmt)).scalars().all()

        locked: List[WorkflowPhase] = []
        for phase in expired_phases:
            try:
                result = await self.lock_phase(phase.id, locked_by="auto_expired")
                locked.append(result)
                logger.warning(
                    "阶段超时自动锁定",
                    phase_name=phase.phase_name,
                    phase_id=str(phase.id),
                    deadline=str(phase.deadline),
                )
            except Exception as exc:
                logger.error(
                    "自动锁定失败",
                    phase_id=str(phase.id),
                    error=str(exc),
                )

        return locked

    async def request_approval(
        self,
        phase_id:        uuid.UUID,
        approver_id:     Optional[str] = None,
        timeout_minutes: int = 120,
    ) -> Dict[str, Any]:
        """
        为阶段决策发起人工审批请求，向企业微信推送审批通知。

        通常在 submit_decision() 之后、phase 非 is_auto 时调用。
        推送失败不阻断流程（降级为日志记录）。

        Args:
            phase_id:        WorkflowPhase.id
            approver_id:     指定审批人（None 则广播给门店所有店长）
            timeout_minutes: 审批超时分钟数，超时后 check_expired_phases 自动锁定

        Returns:
            {"request_id", "phase_id", "phase_name", "phase_label", "expires_at", "approver_id"}
        """
        phase = await self._get_phase(phase_id)
        if phase.status not in (PhaseStatus.REVIEWING.value, PhaseStatus.RUNNING.value):
            raise ValueError(
                f"阶段 {phase.phase_name} 当前状态 {phase.status} 不支持发起审批"
            )

        cfg       = PHASE_CONFIG.get(phase.phase_name, {})
        label     = cfg.get("label", phase.phase_name)
        expires   = datetime.utcnow() + timedelta(minutes=timeout_minutes)
        request_id = f"wf_approval_{phase_id}_{int(datetime.utcnow().timestamp())}"

        # 获取最新版本内容
        content_summary: Dict = {}
        store_id = ""
        if phase.current_version_id:
            ver_stmt = select(DecisionVersion).where(
                DecisionVersion.id == phase.current_version_id
            )
            ver = (await self.db.execute(ver_stmt)).scalar_one_or_none()
            if ver:
                content_summary = ver.content or {}
                store_id = ver.store_id or ""

        # 非阻塞推送企微通知
        try:
            from .wechat_work_message_service import WeChatWorkMessageService
            wechat   = WeChatWorkMessageService()
            message  = self._build_approval_message(label, content_summary, expires, request_id)
            target   = approver_id or "@all"
            await wechat.send_text_message(target, message)
        except Exception as exc:
            logger.warning(
                "企微审批通知失败（已降级）",
                phase_name=phase.phase_name,
                error=str(exc),
            )

        logger.info(
            "工作流审批请求已创建",
            phase_name=phase.phase_name,
            request_id=request_id,
            expires_at=str(expires),
            approver_id=approver_id,
        )
        return {
            "request_id":  request_id,
            "phase_id":    str(phase_id),
            "phase_name":  phase.phase_name,
            "phase_label": label,
            "expires_at":  expires.isoformat(),
            "approver_id": approver_id,
        }

    async def approve_phase(
        self,
        phase_id:    uuid.UUID,
        approver_id: str,
        comment:     str = "",
    ) -> WorkflowPhase:
        """
        店长批准阶段决策，触发阶段锁定并推进到下一阶段。

        Args:
            phase_id:    WorkflowPhase.id
            approver_id: 审批人 user_id
            comment:     审批意见（记录到日志）

        Returns:
            已锁定的 WorkflowPhase
        """
        phase = await self._get_phase(phase_id)
        if phase.status == PhaseStatus.LOCKED.value:
            return phase  # 幂等

        if phase.status not in (PhaseStatus.REVIEWING.value, PhaseStatus.RUNNING.value):
            raise ValueError(
                f"阶段 {phase.phase_name} 状态 {phase.status} 不支持审批"
            )

        logger.info(
            "工作流阶段人工批准",
            phase_name=phase.phase_name,
            approver_id=approver_id,
            comment=comment,
        )
        return await self.lock_phase(phase_id, locked_by=approver_id)

    async def reject_phase(
        self,
        phase_id:    uuid.UUID,
        approver_id: str,
        reason:      str,
    ) -> WorkflowPhase:
        """
        店长拒绝阶段决策，阶段回退至 RUNNING（允许重新 submit_decision）。

        拒绝原因写入当前版本的 change_reason 字段，作为审计记录。

        Args:
            phase_id:    WorkflowPhase.id
            approver_id: 拒绝人 user_id
            reason:      拒绝原因

        Returns:
            回退到 RUNNING 状态的 WorkflowPhase
        """
        phase = await self._get_phase(phase_id)
        if phase.status == PhaseStatus.LOCKED.value:
            raise ValueError(f"阶段 {phase.phase_name} 已锁定，无法拒绝")

        phase.status = PhaseStatus.RUNNING.value

        # 在版本记录上追加拒绝原因
        if phase.current_version_id:
            ver_stmt = select(DecisionVersion).where(
                DecisionVersion.id == phase.current_version_id
            )
            ver = (await self.db.execute(ver_stmt)).scalar_one_or_none()
            if ver:
                ver.change_reason = f"[拒绝] {reason}"

        logger.info(
            "工作流阶段人工拒绝",
            phase_name=phase.phase_name,
            approver_id=approver_id,
            reason=reason,
        )
        return phase

    def _build_approval_message(
        self,
        label:      str,
        content:    Dict[str, Any],
        expires_at: datetime,
        request_id: str,
    ) -> str:
        """构建企微审批通知文本（截断超长内容）"""
        import json
        summary      = json.dumps(content, ensure_ascii=False)[:400]
        deadline_str = expires_at.strftime("%m-%d %H:%M")
        return (
            f"【智链OS · 工作流审批】\n\n"
            f"阶段: {label}\n"
            f"内容摘要:\n{summary}\n\n"
            f"请在 {deadline_str} 前批准或拒绝。\n"
            f"审批ID: {request_id}"
        )

    # ── 版本查询 ──────────────────────────────────────────────────────────────

    async def get_phase_versions(
        self, phase_id: uuid.UUID
    ) -> List[DecisionVersion]:
        """获取阶段所有版本（按版本号升序）"""
        stmt = (
            select(DecisionVersion)
            .where(DecisionVersion.phase_id == phase_id)
            .order_by(DecisionVersion.version_number)
        )
        return (await self.db.execute(stmt)).scalars().all()

    async def get_latest_version(
        self, phase_id: uuid.UUID
    ) -> Optional[DecisionVersion]:
        stmt = (
            select(DecisionVersion)
            .where(DecisionVersion.phase_id == phase_id)
            .order_by(DecisionVersion.version_number.desc())
            .limit(1)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    # ── 工具方法 ──────────────────────────────────────────────────────────────

    def _calc_deadline(
        self,
        trigger_date: date,
        cfg:          Dict,
        store_config: Optional[Dict],
    ) -> datetime:
        """计算阶段硬 deadline（支持门店个性化覆盖）"""
        hour   = cfg["deadline_hour"]
        minute = cfg["deadline_minute"]

        if store_config:
            key = f"{cfg.get('phase_name', '')}_deadline"
            custom = store_config.get(key)
            if custom and ":" in str(custom):
                parts  = str(custom).split(":")
                hour   = int(parts[0])
                minute = int(parts[1])

        return datetime(
            trigger_date.year, trigger_date.month, trigger_date.day,
            hour, minute, 0,
        )

    async def _get_workflow(self, workflow_id: uuid.UUID) -> Optional[DailyWorkflow]:
        stmt = select(DailyWorkflow).where(DailyWorkflow.id == workflow_id)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def _get_phase(self, phase_id: uuid.UUID) -> WorkflowPhase:
        stmt = select(WorkflowPhase).where(WorkflowPhase.id == phase_id)
        phase = (await self.db.execute(stmt)).scalar_one_or_none()
        if not phase:
            raise ValueError(f"WorkflowPhase {phase_id} 不存在")
        return phase


# ── 辅助函数 ──────────────────────────────────────────────────────────────────

def _simple_diff(prev: Dict, curr: Dict) -> Dict:
    """计算两个 dict 的简单 diff（只处理一层 key 变化）"""
    added    = {k: curr[k] for k in curr if k not in prev}
    removed  = {k: prev[k] for k in prev if k not in curr}
    modified = {
        k: {"before": prev[k], "after": curr[k]}
        for k in curr
        if k in prev and prev[k] != curr[k]
    }
    return {
        "added":    added,
        "removed":  removed,
        "modified": modified,
    }
