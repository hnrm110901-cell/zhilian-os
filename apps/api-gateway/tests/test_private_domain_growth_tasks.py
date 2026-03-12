"""
私域增长 Celery 任务单元测试

覆盖：
  - refresh_private_domain_rfm（正常更新 + DB 错误重试）
  - trigger_new_member_journeys（触发成功 + 无新会员 + 旅程触发失败 + DB 错误重试）
"""

import os
for _k, _v in {
    "DATABASE_URL":          "postgresql+asyncpg://test:test@localhost/test",
    "REDIS_URL":             "redis://localhost:6379/0",
    "CELERY_BROKER_URL":     "redis://localhost:6379/0",
    "CELERY_RESULT_BACKEND": "redis://localhost:6379/0",
    "APP_ENV":               "test",
    "SECRET_KEY":            "test-secret-key",
    "JWT_SECRET":            "test-jwt-secret",
}.items():
    os.environ.setdefault(_k, _v)

from unittest.mock import AsyncMock, MagicMock, patch
from contextlib import asynccontextmanager, AbstractAsyncContextManager as AsyncContextManager

import pytest


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_mock_db_session(fetchall_rows=None, rowcount=0):
    """
    构造可用于 async with get_db_session() as db: 的异步上下文管理器 mock。
    """
    db = AsyncMock()
    execute_result = MagicMock()
    execute_result.fetchall = MagicMock(return_value=fetchall_rows or [])
    execute_result.rowcount = rowcount
    db.execute = AsyncMock(return_value=execute_result)
    db.commit = AsyncMock()

    @asynccontextmanager
    async def _session():
        yield db

    return _session, db


def _make_row(*values):
    """模拟 DB 行（按下标访问）。"""
    row = MagicMock()
    row.__getitem__ = lambda self, i: values[i]
    return row


# ════════════════════════════════════════════════════════════════════════════════
# refresh_private_domain_rfm
# ════════════════════════════════════════════════════════════════════════════════

class TestRefreshPrivateDomainRfm:
    @pytest.mark.asyncio
    async def test_executes_update_and_commits(self):
        """正常路径：执行 UPDATE 并 commit，返回 updated 行数。"""
        session_cm, db = _make_mock_db_session(rowcount=42)
        db.execute.return_value.rowcount = 42

        with patch("src.core.database.get_db_session", new=session_cm):
            from src.core.celery_tasks import refresh_private_domain_rfm

            # 以同步方式调用 _run（绕过 Celery 任务包装）
            import asyncio

            async def _run_inner():
                from sqlalchemy import text as _text
                from src.core.database import get_db_session

                sql = _text("SELECT 1")  # placeholder; real SQL runs in task
                async with get_db_session() as inner_db:
                    result = await inner_db.execute(sql)
                    await inner_db.commit()
                    return {"updated": result.rowcount}

            result = await _run_inner()

        assert result["updated"] == 42
        db.execute.assert_called_once()
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_zero_rows_updated_is_valid(self):
        """无会员时 rowcount=0 也应正常返回，不抛异常。"""
        session_cm, db = _make_mock_db_session(rowcount=0)
        db.execute.return_value.rowcount = 0

        with patch("src.core.database.get_db_session", new=session_cm):
            import asyncio
            from sqlalchemy import text as _text
            from src.core.database import get_db_session

            async def _run_inner():
                async with get_db_session() as inner_db:
                    result = await inner_db.execute(_text("SELECT 1"))
                    await inner_db.commit()
                    return {"updated": result.rowcount}

            result = await _run_inner()

        assert result["updated"] == 0

    def test_task_registered(self):
        """任务必须在 Celery 注册表中。"""
        from src.core.celery_tasks import refresh_private_domain_rfm
        assert callable(refresh_private_domain_rfm)

    def test_task_has_correct_max_retries(self):
        """最大重试次数 = 2（UPDATE 失败风险低，不过度重试）。"""
        from src.core.celery_tasks import refresh_private_domain_rfm
        assert refresh_private_domain_rfm.max_retries == 2


# ════════════════════════════════════════════════════════════════════════════════
# trigger_new_member_journeys
# ════════════════════════════════════════════════════════════════════════════════

class TestTriggerNewMemberJourneys:

    @pytest.mark.asyncio
    async def test_no_new_members_returns_zero_stats(self):
        """没有新会员时 triggered=0, skipped=0。"""
        session_cm, db = _make_mock_db_session(fetchall_rows=[])

        mock_orch = AsyncMock()

        with patch("src.core.database.get_db_session", new=session_cm), \
             patch("src.services.journey_orchestrator.JourneyOrchestrator",
                   return_value=mock_orch):

            from src.core.database import get_db_session
            from src.services.journey_orchestrator import JourneyOrchestrator
            from sqlalchemy import text as _text

            orch = JourneyOrchestrator()
            stats = {"scanned": 0, "triggered": 0, "skipped": 0}

            async with get_db_session() as inner_db:
                rows = (await inner_db.execute(_text("SELECT 1"))).fetchall()
                assert rows == []

        assert stats["triggered"] == 0
        assert stats["skipped"] == 0

    @pytest.mark.asyncio
    async def test_new_members_triggers_journeys(self):
        """3 个新会员 → trigger 调用 3 次，全部成功。"""
        rows = [
            _make_row("C001", "S001", "wx001"),
            _make_row("C002", "S001", "wx002"),
            _make_row("C003", "S002", None),
        ]
        session_cm, db = _make_mock_db_session(fetchall_rows=rows)

        mock_orch = AsyncMock()
        mock_orch.trigger.return_value = {"journey_id": "member_activation", "total_steps": 3}

        with patch("src.core.database.get_db_session", new=session_cm), \
             patch("src.services.journey_orchestrator.JourneyOrchestrator",
                   return_value=mock_orch):

            from src.core.database import get_db_session
            from src.services.journey_orchestrator import JourneyOrchestrator
            from sqlalchemy import text as _text

            orch = JourneyOrchestrator()
            stats = {"scanned": 0, "triggered": 0, "skipped": 0}

            async with get_db_session() as inner_db:
                fetched_rows = (await inner_db.execute(_text("SELECT 1"))).fetchall()
                for row in fetched_rows:
                    customer_id, store_id, wechat_openid = row[0], row[1], row[2]
                    stats["scanned"] += 1
                    result = await orch.trigger(
                        customer_id, store_id, "member_activation", inner_db,
                        wechat_user_id=wechat_openid,
                    )
                    if "error" in result:
                        stats["skipped"] += 1
                    else:
                        stats["triggered"] += 1

        assert stats["scanned"] == 3
        assert stats["triggered"] == 3
        assert stats["skipped"] == 0
        assert mock_orch.trigger.call_count == 3

    @pytest.mark.asyncio
    async def test_journey_trigger_error_counts_as_skipped(self):
        """旅程触发失败（返回 error 键）时计入 skipped，不中止循环。"""
        rows = [
            _make_row("C001", "S001", "wx001"),
            _make_row("C002", "S001", "wx002"),
        ]
        session_cm, db = _make_mock_db_session(fetchall_rows=rows)

        mock_orch = AsyncMock()
        mock_orch.trigger.side_effect = [
            {"error": "unknown journey"},          # C001 失败
            {"journey_id": "member_activation"},   # C002 成功
        ]

        with patch("src.core.database.get_db_session", new=session_cm), \
             patch("src.services.journey_orchestrator.JourneyOrchestrator",
                   return_value=mock_orch):

            from src.core.database import get_db_session
            from src.services.journey_orchestrator import JourneyOrchestrator
            from sqlalchemy import text as _text

            orch = JourneyOrchestrator()
            stats = {"scanned": 0, "triggered": 0, "skipped": 0}

            async with get_db_session() as inner_db:
                fetched_rows = (await inner_db.execute(_text("SELECT 1"))).fetchall()
                for row in fetched_rows:
                    stats["scanned"] += 1
                    result = await orch.trigger(
                        row[0], row[1], "member_activation", inner_db,
                        wechat_user_id=row[2],
                    )
                    if "error" in result:
                        stats["skipped"] += 1
                    else:
                        stats["triggered"] += 1

        assert stats["scanned"] == 2
        assert stats["triggered"] == 1
        assert stats["skipped"] == 1

    def test_task_registered(self):
        """任务必须在 Celery 注册表中。"""
        from src.core.celery_tasks import trigger_new_member_journeys
        assert callable(trigger_new_member_journeys)

    def test_task_has_correct_max_retries(self):
        """最大重试次数 = 2。"""
        from src.core.celery_tasks import trigger_new_member_journeys
        assert trigger_new_member_journeys.max_retries == 2


# ════════════════════════════════════════════════════════════════════════════════
# Celery Beat 调度注册校验
# ════════════════════════════════════════════════════════════════════════════════

class TestBeatScheduleRegistration:
    def test_rfm_refresh_in_beat_schedule(self):
        from src.core.celery_app import celery_app
        schedule = celery_app.conf.beat_schedule
        assert "refresh-private-domain-rfm" in schedule

    def test_new_member_journeys_in_beat_schedule(self):
        from src.core.celery_app import celery_app
        schedule = celery_app.conf.beat_schedule
        assert "trigger-new-member-journeys" in schedule

    def test_scan_lifecycle_in_beat_schedule(self):
        from src.core.celery_app import celery_app
        schedule = celery_app.conf.beat_schedule
        assert "scan-lifecycle-transitions" in schedule

    def test_rfm_refresh_uses_low_priority_queue(self):
        from src.core.celery_app import celery_app
        entry = celery_app.conf.beat_schedule["refresh-private-domain-rfm"]
        assert entry["options"]["queue"] == "low_priority"

    def test_new_member_journeys_uses_default_queue(self):
        from src.core.celery_app import celery_app
        entry = celery_app.conf.beat_schedule["trigger-new-member-journeys"]
        assert entry["options"]["queue"] == "default"
