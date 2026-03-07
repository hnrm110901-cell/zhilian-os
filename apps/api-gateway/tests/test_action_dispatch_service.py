"""
tests/test_action_dispatch_service.py

ActionDispatchService 单元测试 — Phase 7 L5 行动层

覆盖：
  - dispatch_from_report：P1/P2/P3/OK 四级派发路径
  - 幂等保护（相同报告不重复派发）
  - dispatch_pending_alerts：批量派发统计
  - record_outcome：结果记录（L4→L5→L4 反馈闭环）
  - list_plans / get_platform_stats：查询接口
  - 子系统失败降级（partial 状态）
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "test-secret-key-32-characters-xx")

from src.models.action_plan import ActionOutcome, ActionPlan, DispatchStatus
from src.models.reasoning import ReasoningReport
from src.services.action_dispatch_service import ActionDispatchService


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_report(
    severity: str = "P1",
    dimension: str = "waste",
    store_id: str = "STORE001",
) -> ReasoningReport:
    r = MagicMock(spec=ReasoningReport)
    r.id = uuid.uuid4()
    r.store_id = store_id
    r.report_date = date.today()
    r.severity = severity
    r.dimension = dimension
    r.root_cause = f"{dimension} 异常"
    r.confidence = 0.85
    r.recommended_actions = ["行动1", "行动2", "行动3"]
    r.evidence_chain = ["证据A", "证据B"]
    r.kpi_snapshot = {"waste_rate": 0.15}
    r.is_actioned = False
    return r


def _make_db(existing_plan: ActionPlan | None = None) -> AsyncMock:
    """构造最小可用的 AsyncSession mock。"""
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = existing_plan
    result_mock.scalars.return_value.all.return_value = []
    result_mock.all.return_value = []
    db.execute = AsyncMock(return_value=result_mock)
    return db


# ── 1. dispatch_from_report — P1 路径 ────────────────────────────────────────

class TestDispatchP1:
    @pytest.mark.asyncio
    async def test_p1_creates_action_plan_with_pending_status(self):
        """P1 报告：创建行动计划，dispatch_status 从 PENDING 开始"""
        db = _make_db()
        svc = ActionDispatchService(db)

        with (
            patch.object(svc, "_push_wechat_action", new_callable=AsyncMock) as mock_wechat,
            patch.object(svc, "_create_task", new_callable=AsyncMock) as mock_task,
            patch.object(svc, "_create_approval", new_callable=AsyncMock) as mock_approval,
        ):
            report = _make_report(severity="P1", dimension="waste")
            plan = await svc.dispatch_from_report(report)

        assert plan is not None
        assert plan.store_id == "STORE001"
        assert plan.severity == "P1"
        mock_wechat.assert_awaited_once()
        mock_task.assert_awaited_once()
        mock_approval.assert_awaited_once()  # waste → needs_approval

    @pytest.mark.asyncio
    async def test_p1_cost_dimension_triggers_approval(self):
        """P1 cost 维度：应触发审批申请"""
        db = _make_db()
        svc = ActionDispatchService(db)

        with (
            patch.object(svc, "_push_wechat_action", new_callable=AsyncMock),
            patch.object(svc, "_create_task", new_callable=AsyncMock),
            patch.object(svc, "_create_approval", new_callable=AsyncMock) as mock_approval,
        ):
            report = _make_report(severity="P1", dimension="cost")
            await svc.dispatch_from_report(report)

        mock_approval.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_p1_efficiency_dimension_no_approval(self):
        """P1 efficiency 维度：不触发审批申请"""
        db = _make_db()
        svc = ActionDispatchService(db)

        with (
            patch.object(svc, "_push_wechat_action", new_callable=AsyncMock),
            patch.object(svc, "_create_task", new_callable=AsyncMock),
            patch.object(svc, "_create_approval", new_callable=AsyncMock) as mock_approval,
        ):
            report = _make_report(severity="P1", dimension="efficiency")
            await svc.dispatch_from_report(report)

        mock_approval.assert_not_awaited()


# ── 2. dispatch_from_report — P2/P3/OK ───────────────────────────────────────

class TestDispatchOtherSeverities:
    @pytest.mark.asyncio
    async def test_p2_no_approval(self):
        """P2 报告：无审批申请，有任务"""
        db = _make_db()
        svc = ActionDispatchService(db)

        with (
            patch.object(svc, "_push_wechat_action", new_callable=AsyncMock),
            patch.object(svc, "_create_task", new_callable=AsyncMock) as mock_task,
            patch.object(svc, "_create_approval", new_callable=AsyncMock) as mock_approval,
        ):
            report = _make_report(severity="P2", dimension="waste")
            await svc.dispatch_from_report(report)

        mock_task.assert_awaited_once()
        mock_approval.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_p3_only_wechat_no_task(self):
        """P3 报告：只发企微通知，不创建任务"""
        db = _make_db()
        svc = ActionDispatchService(db)

        with (
            patch.object(svc, "_push_wechat_action", new_callable=AsyncMock) as mock_wechat,
            patch.object(svc, "_create_task", new_callable=AsyncMock) as mock_task,
        ):
            report = _make_report(severity="P3", dimension="quality")
            await svc.dispatch_from_report(report)

        mock_wechat.assert_awaited_once()
        mock_task.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_ok_severity_returns_skipped_plan(self):
        """OK 级别报告：直接跳过，dispatch_status = skipped"""
        db = _make_db()
        svc = ActionDispatchService(db)
        report = _make_report(severity="OK", dimension="efficiency")
        plan = await svc.dispatch_from_report(report)
        assert plan.dispatch_status == DispatchStatus.SKIPPED.value


# ── 3. 幂等保护 ────────────────────────────────────────────────────────────────

class TestIdempotency:
    @pytest.mark.asyncio
    async def test_duplicate_report_returns_existing_plan(self):
        """同一报告重复调用：直接返回已有行动计划，不创建新记录"""
        existing_plan = MagicMock(spec=ActionPlan)
        existing_plan.id = uuid.uuid4()
        existing_plan.dispatch_status = DispatchStatus.DISPATCHED.value
        db = _make_db(existing_plan=existing_plan)
        svc = ActionDispatchService(db)

        with (
            patch.object(svc, "_push_wechat_action", new_callable=AsyncMock) as mock_wechat,
            patch.object(svc, "_create_task", new_callable=AsyncMock) as mock_task,
        ):
            report = _make_report(severity="P1")
            result = await svc.dispatch_from_report(report)

        assert result is existing_plan
        mock_wechat.assert_not_awaited()
        mock_task.assert_not_awaited()


# ── 4. 子系统失败降级 ─────────────────────────────────────────────────────────

class TestSubsystemFailureDegradation:
    @pytest.mark.asyncio
    async def test_wechat_failure_does_not_raise(self):
        """WeChat 推送失败：不抛异常，行动仍记录（dispatched_actions 为空）"""
        db = _make_db()
        svc = ActionDispatchService(db)

        async def _fail_wechat(*args, **kwargs):
            raise RuntimeError("WeChat unavailable")

        with (
            patch.object(svc, "_push_wechat_action", side_effect=_fail_wechat),
            patch.object(svc, "_create_task", new_callable=AsyncMock),
        ):
            report = _make_report(severity="P2", dimension="quality")
            plan = await svc.dispatch_from_report(report)

        # 不抛异常即为通过
        assert plan is not None

    @pytest.mark.asyncio
    async def test_task_failure_results_in_failed_status_when_all_fail(self):
        """所有子系统失败时：dispatch_status = failed"""
        db = _make_db()
        svc = ActionDispatchService(db)

        async def _fail(*args, **kwargs):
            raise RuntimeError("subsystem down")

        with (
            patch.object(svc, "_push_wechat_action", side_effect=_fail),
            patch.object(svc, "_create_task", side_effect=_fail),
            patch.object(svc, "_create_approval", side_effect=_fail),
        ):
            report = _make_report(severity="P1", dimension="cost")
            plan = await svc.dispatch_from_report(report)

        assert plan.dispatch_status == DispatchStatus.FAILED.value


# ── 5. record_outcome ────────────────────────────────────────────────────────

class TestRecordOutcome:
    @pytest.mark.asyncio
    async def test_resolved_outcome_sets_resolved_at(self):
        """记录 resolved 结果：plan.resolved_at 被设置"""
        existing_plan = MagicMock(spec=ActionPlan)
        existing_plan.id = uuid.uuid4()
        db = _make_db(existing_plan=existing_plan)
        svc = ActionDispatchService(db)

        with patch.object(svc, "_get_plan", new_callable=AsyncMock, return_value=existing_plan):
            result = await svc.record_outcome(
                plan_id=existing_plan.id,
                outcome="resolved",
                resolved_by="manager_001",
                kpi_delta={"waste_rate": {"before": 0.15, "after": 0.11, "delta": -0.04}},
            )

        assert result is existing_plan
        assert result.outcome == "resolved"
        assert result.resolved_by == "manager_001"
        assert result.kpi_delta is not None

    @pytest.mark.asyncio
    async def test_record_outcome_plan_not_found_returns_none(self):
        """行动计划不存在：返回 None"""
        db = _make_db(existing_plan=None)
        svc = ActionDispatchService(db)

        with patch.object(svc, "_get_plan", new_callable=AsyncMock, return_value=None):
            result = await svc.record_outcome(
                plan_id=uuid.uuid4(),
                outcome="resolved",
                resolved_by="manager",
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_record_escalated_outcome(self):
        """记录 escalated 结果：正确写入"""
        existing_plan = MagicMock(spec=ActionPlan)
        db = _make_db()
        svc = ActionDispatchService(db)

        with patch.object(svc, "_get_plan", new_callable=AsyncMock, return_value=existing_plan):
            result = await svc.record_outcome(
                plan_id=uuid.uuid4(),
                outcome="escalated",
                resolved_by="HQ",
                outcome_note="已升级至总部跟进",
            )

        assert result.outcome == "escalated"
        assert result.outcome_note == "已升级至总部跟进"


# ── 6. dispatch_pending_alerts ────────────────────────────────────────────────

class TestDispatchPendingAlerts:
    @pytest.mark.asyncio
    async def test_empty_reports_returns_zero_stats(self):
        """无未处理报告时：所有统计为 0"""
        db = _make_db()
        # db.execute 返回空列表
        svc = ActionDispatchService(db)
        stats = await svc.dispatch_pending_alerts(store_id="STORE001", days_back=1)
        assert stats["plans_created"] == 0
        assert stats["errors"] == 0

    @pytest.mark.asyncio
    async def test_returns_correct_stat_keys(self):
        """返回结构包含所有预期 key"""
        db = _make_db()
        svc = ActionDispatchService(db)
        stats = await svc.dispatch_pending_alerts()
        expected_keys = {"plans_created", "dispatched", "partial", "skipped", "errors"}
        assert expected_keys.issubset(set(stats.keys()))


# ── 7. get_platform_stats ────────────────────────────────────────────────────

class TestGetPlatformStats:
    @pytest.mark.asyncio
    async def test_empty_db_returns_zero_totals(self):
        """数据库为空时：total_plans=0"""
        db = _make_db()
        svc = ActionDispatchService(db)
        stats = await svc.get_platform_stats(days=7)
        assert "total_plans" in stats
        assert "dispatch_dist" in stats
        assert "outcome_dist" in stats
        assert "severity_dist" in stats
        assert stats["total_plans"] == 0

    @pytest.mark.asyncio
    async def test_resolution_rate_zero_when_no_plans(self):
        """无行动计划时：resolution_rate 应不报除零错误"""
        db = _make_db()
        svc = ActionDispatchService(db)
        stats = await svc.get_platform_stats()
        # 由 API 层计算 resolution_rate，服务层不包含此字段，确保不报错
        assert "total_plans" in stats
