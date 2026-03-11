"""
集成服务 P1 增强功能测试
覆盖6项新增能力：自动重试、转换规则、批量同步、实时状态、健康评分、冲突解决
"""
import asyncio
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.integration_service import IntegrationService
from src.models.integration import (
    ExternalSystem,
    IntegrationStatus,
    IntegrationType,
    SyncLog,
    SyncStatus,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────

def _make_system(status: IntegrationStatus = IntegrationStatus.ACTIVE, last_error=None) -> ExternalSystem:
    sys = ExternalSystem(
        id="SYS001",
        name="美团POS",
        type=IntegrationType.POS,
        provider="meituan",
        status=status,
        last_error=last_error,
    )
    return sys


def _make_sync_log(status: SyncStatus, created_at: datetime = None) -> SyncLog:
    log = SyncLog(
        id="LOG001",
        system_id="SYS001",
        sync_type="order",
        status=status,
        created_at=created_at or datetime.utcnow(),
    )
    return log


# ─── #1 自动重试机制 ──────────────────────────────────────────────────────────

class TestAutoRetry:

    @pytest.mark.asyncio
    async def test_retry_succeeds_on_second_attempt(self):
        """自动重试：第1次失败，第2次成功"""
        service = IntegrationService()
        call_count = 0

        async def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("暂时性网络错误")
            return "ok"

        result = await service.with_retry(flaky_func, max_attempts=3, base_delay=0.01)
        assert result == "ok"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retry_raises_after_max_attempts(self):
        """自动重试：超过最大次数后抛出最后一次异常"""
        service = IntegrationService()
        call_count = 0

        async def always_fail():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("持续失败")

        with pytest.raises(ConnectionError, match="持续失败"):
            await service.with_retry(always_fail, max_attempts=3, base_delay=0.01)

        assert call_count == 3

    @pytest.mark.asyncio
    async def test_non_retryable_exception_not_retried(self):
        """非可重试异常不触发重试"""
        service = IntegrationService()
        call_count = 0

        async def value_error():
            nonlocal call_count
            call_count += 1
            raise ValueError("不可重试")

        with pytest.raises(ValueError):
            await service.with_retry(
                value_error,
                max_attempts=3,
                base_delay=0.01,
                retryable_exceptions=(ConnectionError,),
            )
        assert call_count == 1  # 不重试，只调用一次


# ─── #2 数据转换规则配置 ──────────────────────────────────────────────────────

class TestTransformRules:

    def test_register_and_apply_rule(self):
        """注册并应用转换规则"""
        service = IntegrationService()

        def meituan_to_standard(raw: dict) -> dict:
            return {
                "transaction_id": raw.get("order_id"),
                "total": raw.get("amount"),
                "payment_method": raw.get("pay_type"),
            }

        service.register_transform_rule("meituan_pos", "order", meituan_to_standard)
        raw = {"order_id": "MT12345", "amount": 288.0, "pay_type": "wechat"}
        result = service.apply_transform("meituan_pos", "order", raw)

        assert result["transaction_id"] == "MT12345"
        assert result["total"] == 288.0
        assert result["payment_method"] == "wechat"

    def test_apply_returns_original_if_no_rule(self):
        """无规则时原样返回"""
        service = IntegrationService()
        raw = {"foo": "bar"}
        result = service.apply_transform("unknown_system", "order", raw)
        assert result == raw

    def test_get_registered_rules(self):
        """get_registered_rules 返回所有规则 key"""
        service = IntegrationService()
        service.register_transform_rule("sys_a", "member", lambda x: x)
        service.register_transform_rule("sys_a", "order", lambda x: x)
        rules = service.get_registered_rules()
        assert "sys_a:member" in rules
        assert "sys_a:order" in rules

    def test_broken_transform_falls_back_to_raw(self):
        """转换函数异常时返回原始数据"""
        service = IntegrationService()

        def bad_transform(raw):
            raise RuntimeError("transform error")

        service.register_transform_rule("bad_sys", "order", bad_transform)
        raw = {"id": "X"}
        result = service.apply_transform("bad_sys", "order", raw)
        assert result == raw


# ─── #3 批量同步优化 ──────────────────────────────────────────────────────────

class TestBatchSync:

    @pytest.mark.asyncio
    async def test_batch_sync_members_all_success(self):
        """批量同步：全部成功"""
        service = IntegrationService()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        members = [{"member_id": f"M{i}", "name": f"用户{i}", "phone": f"1380000{i:04d}"} for i in range(10)]
        result = await service.batch_sync_members(mock_db, "SYS001", members, chunk_size=5)

        assert result["total"] == 10
        assert result["success"] == 10
        assert result["failed"] == 0

    @pytest.mark.asyncio
    async def test_batch_sync_members_partial_failure(self):
        """批量同步：部分失败不中断，统计正确"""
        service = IntegrationService()

        call_count = {"n": 0}

        async def mock_sync_member(session, system_id, data):
            call_count["n"] += 1
            if call_count["n"] % 3 == 0:
                raise ValueError("同步失败")

        with patch.object(service, "sync_member", side_effect=mock_sync_member):
            members = [{"member_id": f"M{i}"} for i in range(9)]
            result = await service.batch_sync_members(AsyncMock(), "SYS001", members)

        assert result["total"] == 9
        assert result["failed"] == 3
        assert result["success"] == 6

    @pytest.mark.asyncio
    async def test_batch_sync_applies_transform(self):
        """批量同步：正确应用转换规则"""
        service = IntegrationService()
        transformed = []

        async def mock_sync_member(session, system_id, data):
            transformed.append(data)

        service.register_transform_rule("meituan", "member", lambda r: {**r, "transformed": True})
        with patch.object(service, "sync_member", side_effect=mock_sync_member):
            members = [{"member_id": "M1"}]
            await service.batch_sync_members(AsyncMock(), "SYS001", members, system_type="meituan")

        assert transformed[0].get("transformed") is True


# ─── #4 实时同步状态 ──────────────────────────────────────────────────────────

class TestRealtimeSyncStatus:

    @pytest.mark.asyncio
    async def test_get_realtime_sync_status_returns_snapshot(self):
        """实时状态快照包含所有必要字段"""
        service = IntegrationService()
        system = _make_system()
        log = _make_sync_log(SyncStatus.SUCCESS)

        mock_db = AsyncMock()
        system_result = MagicMock()
        system_result.scalar_one_or_none.return_value = system
        logs_result = MagicMock()
        logs_result.scalars.return_value.all.return_value = [log]
        mock_db.execute.side_effect = [system_result, logs_result]

        status = await service.get_realtime_sync_status(mock_db, "SYS001")

        assert status["system_id"] == "SYS001"
        assert "health_score" in status
        assert "last_24h_success" in status
        assert "snapshot_at" in status

    @pytest.mark.asyncio
    async def test_get_realtime_sync_status_system_not_found(self):
        """系统不存在时返回 error 字段"""
        service = IntegrationService()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        status = await service.get_realtime_sync_status(mock_db, "NONEXISTENT")
        assert status.get("error") == "system_not_found"


# ─── #5 集成健康度评分 ────────────────────────────────────────────────────────

class TestHealthScore:

    def test_healthy_system_scores_high(self):
        """活跃系统 + 无错误 + 全部成功 → 接近100分"""
        service = IntegrationService()
        system = _make_system(IntegrationStatus.ACTIVE, last_error=None)
        score = service._compute_health_score(100, 0, system)
        assert score >= 90.0

    def test_error_system_scores_low(self):
        """ERROR状态系统健康度偏低"""
        service = IntegrationService()
        system = _make_system(IntegrationStatus.ERROR, last_error="connection refused")
        score = service._compute_health_score(5, 20, system)
        assert score < 50.0

    def test_partial_failures_reduce_score(self):
        """部分失败降低健康度"""
        service = IntegrationService()
        system = _make_system()
        score_perfect = service._compute_health_score(100, 0, system)
        score_partial = service._compute_health_score(70, 30, system)
        assert score_partial < score_perfect

    def test_score_bounded_0_to_100(self):
        """分数始终在 [0, 100]"""
        service = IntegrationService()
        system = _make_system(IntegrationStatus.ERROR, last_error="err")
        score = service._compute_health_score(0, 1000, system)
        assert 0.0 <= score <= 100.0


# ─── #6 数据冲突解决 ──────────────────────────────────────────────────────────

class TestConflictResolution:

    def test_last_write_wins_remote_newer(self):
        """last_write_wins：远端更新时间晚，远端胜"""
        service = IntegrationService()
        local = {"member_id": "M1", "points": 100, "updated_at": "2026-03-10T10:00:00"}
        remote = {"member_id": "M1", "points": 150, "updated_at": "2026-03-11T08:00:00"}
        result = service.resolve_conflict(local, remote, strategy="last_write_wins")
        assert result["points"] == 150

    def test_last_write_wins_local_newer(self):
        """last_write_wins：本地更新时间晚，本地胜"""
        service = IntegrationService()
        local = {"member_id": "M1", "points": 200, "updated_at": "2026-03-11T12:00:00"}
        remote = {"member_id": "M1", "points": 150, "updated_at": "2026-03-11T08:00:00"}
        result = service.resolve_conflict(local, remote, strategy="last_write_wins")
        assert result["points"] == 200

    def test_remote_wins_always(self):
        """remote_wins：始终用远端数据"""
        service = IntegrationService()
        local = {"name": "旧名字", "level": "gold"}
        remote = {"name": "新名字"}
        result = service.resolve_conflict(local, remote, strategy="remote_wins")
        assert result["name"] == "新名字"

    def test_local_wins_always(self):
        """local_wins：始终保留本地"""
        service = IntegrationService()
        local = {"name": "旧名字"}
        remote = {"name": "新名字", "extra": "data"}
        result = service.resolve_conflict(local, remote, strategy="local_wins")
        assert result["name"] == "旧名字"
        assert "extra" not in result

    def test_merge_remote_keeps_non_null_local(self):
        """merge_remote：本地非空字段不被覆盖，缺失字段从远端补充"""
        service = IntegrationService()
        local = {"name": "本地名", "email": None, "phone": "13800138000"}
        remote = {"name": "远端名", "email": "test@test.com", "level": "silver"}
        result = service.resolve_conflict(local, remote, strategy="merge_remote")
        assert result["name"] == "本地名"        # 本地非空，不覆盖
        assert result["email"] == "test@test.com"  # 本地为 None，用远端补充
        assert result["phone"] == "13800138000"  # 本地有值保留
        assert result["level"] == "silver"       # 远端独有字段补充

    def test_missing_timestamps_fallback(self):
        """无时间戳字段时不崩溃"""
        service = IntegrationService()
        local = {"points": 100}
        remote = {"points": 200}
        result = service.resolve_conflict(local, remote, strategy="last_write_wins")
        assert "points" in result
