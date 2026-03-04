"""
TEST-001 / ARCH-004: 折扣申请→审批→执行→留痕全链路集成测试
"""
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.execution_registry import (
    COMMAND_REGISTRY, ExecutionLevel, get_command_def
)
from src.core.trusted_executor import (
    TrustedExecutor, PermissionDeniedError, ApprovalRequiredError,
    RollbackWindowExpiredError, ExecutionError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def executor():
    """无持久化的 TrustedExecutor（单元测试用）"""
    return TrustedExecutor(db_session=None, redis_client=None)


@pytest.fixture
def store_manager_actor():
    return {
        "user_id": "USER_MGR_001",
        "role": "store_manager",
        "store_id": "STORE_A1",
        "brand_id": "BRAND_A",
    }


@pytest.fixture
def waiter_actor():
    return {
        "user_id": "USER_WAITER_001",
        "role": "waiter",
        "store_id": "STORE_A1",
        "brand_id": "BRAND_A",
    }


@pytest.fixture
def super_admin_actor():
    return {
        "user_id": "USER_SUPER_001",
        "role": "super_admin",
        "store_id": "",
        "brand_id": "",
    }


@pytest.fixture
def discount_payload_small():
    """小额折扣（低于熔断阈值 500 元）"""
    return {
        "store_id": "STORE_A1",
        "brand_id": "BRAND_A",
        "order_id": "ORDER_001",
        "amount": 200.0,
        "reason": "会员折扣",
    }


@pytest.fixture
def discount_payload_large():
    """大额折扣（高于熔断阈值 500 元）"""
    return {
        "store_id": "STORE_A1",
        "brand_id": "BRAND_A",
        "order_id": "ORDER_002",
        "amount": 800.0,
        "reason": "特殊活动折扣",
    }


# ---------------------------------------------------------------------------
# 指令注册表测试
# ---------------------------------------------------------------------------

class TestCommandRegistry:
    def test_discount_apply_registered(self):
        assert "discount_apply" in COMMAND_REGISTRY

    def test_discount_apply_level_is_approve(self):
        cmd = get_command_def("discount_apply")
        assert cmd.level == ExecutionLevel.APPROVE

    def test_discount_apply_circuit_breaker_500(self):
        cmd = get_command_def("discount_apply")
        assert cmd.amount_circuit_breaker == 500.0

    def test_shift_report_level_is_auto(self):
        cmd = get_command_def("shift_report")
        assert cmd.level == ExecutionLevel.AUTO

    def test_stock_alert_level_is_notify(self):
        cmd = get_command_def("stock_alert")
        assert cmd.level == ExecutionLevel.NOTIFY

    def test_unknown_command_raises(self):
        with pytest.raises(ValueError, match="未知指令类型"):
            get_command_def("nonexistent_command")

    def test_store_manager_allowed_for_discount(self):
        cmd = get_command_def("discount_apply")
        assert "store_manager" in cmd.allowed_roles

    def test_waiter_not_allowed_for_discount(self):
        cmd = get_command_def("discount_apply")
        assert "waiter" not in cmd.allowed_roles


# ---------------------------------------------------------------------------
# 权限校验测试
# ---------------------------------------------------------------------------

class TestPermissionCheck:
    @pytest.mark.asyncio
    async def test_waiter_cannot_apply_discount(self, executor, waiter_actor, discount_payload_small):
        """服务员无权申请折扣 → PermissionDeniedError"""
        with pytest.raises(PermissionDeniedError) as exc_info:
            await executor.execute("discount_apply", discount_payload_small, waiter_actor)
        assert "waiter" in str(exc_info.value)
        assert exc_info.value.error_code == "PERMISSION_DENIED"

    @pytest.mark.asyncio
    async def test_super_admin_bypasses_permission(self, executor, super_admin_actor, discount_payload_small):
        """super_admin 豁免权限校验"""
        # discount_apply 是 APPROVE 级别，会抛出 ApprovalRequiredError
        # 但不应该是 PermissionDeniedError
        with pytest.raises(ApprovalRequiredError):
            await executor.execute("discount_apply", discount_payload_small, super_admin_actor)

    @pytest.mark.asyncio
    async def test_unknown_command_raises_execution_error(self, executor, store_manager_actor):
        """未知指令类型 → ExecutionError"""
        with pytest.raises(ExecutionError) as exc_info:
            await executor.execute("nonexistent_cmd", {}, store_manager_actor)
        assert exc_info.value.error_code == "UNKNOWN_COMMAND"


# ---------------------------------------------------------------------------
# 折扣申请全链路测试
# ---------------------------------------------------------------------------

class TestDiscountFlow:
    """折扣申请→审批→执行→留痕全链路"""

    @pytest.mark.asyncio
    async def test_small_discount_requires_approval(self, executor, store_manager_actor, discount_payload_small):
        """小额折扣（200元）也需要审批（APPROVE 级别）"""
        with pytest.raises(ApprovalRequiredError) as exc_info:
            await executor.execute("discount_apply", discount_payload_small, store_manager_actor)
        assert exc_info.value.error_code == "APPROVAL_REQUIRED"

    @pytest.mark.asyncio
    async def test_large_discount_triggers_circuit_breaker(self, executor, store_manager_actor, discount_payload_large):
        """大额折扣（800元，超过500元阈值）触发金额熔断"""
        with pytest.raises(ApprovalRequiredError) as exc_info:
            await executor.execute("discount_apply", discount_payload_large, store_manager_actor)
        # 熔断触发时错误信息包含熔断说明
        assert exc_info.value.error_code == "APPROVAL_REQUIRED"

    @pytest.mark.asyncio
    async def test_auto_command_executes_directly(self, executor, store_manager_actor):
        """AUTO 级别指令（shift_report）直接执行，无需审批"""
        result = await executor.execute(
            "shift_report",
            {"store_id": "STORE_A1", "brand_id": "BRAND_A"},
            store_manager_actor,
        )
        assert result["status"] == "completed"
        assert result["level"] == "auto"

    @pytest.mark.asyncio
    async def test_notify_command_executes_directly(self, executor, store_manager_actor):
        """NOTIFY 级别指令（stock_alert）直接执行"""
        result = await executor.execute(
            "stock_alert",
            {"store_id": "STORE_A1", "brand_id": "BRAND_A"},
            store_manager_actor,
        )
        assert result["status"] == "completed"
        assert result["level"] == "notify"

    @pytest.mark.asyncio
    async def test_execution_returns_execution_id(self, executor, store_manager_actor):
        """执行结果包含 execution_id"""
        result = await executor.execute(
            "shift_report",
            {"store_id": "STORE_A1", "brand_id": "BRAND_A"},
            store_manager_actor,
        )
        assert "execution_id" in result
        assert len(result["execution_id"]) > 0


# ---------------------------------------------------------------------------
# 回滚测试
# ---------------------------------------------------------------------------

class TestRollback:
    @pytest.mark.asyncio
    async def test_rollback_nonexistent_execution(self, executor, store_manager_actor):
        """回滚不存在的执行记录 → ExecutionError"""
        with pytest.raises(ExecutionError) as exc_info:
            await executor.rollback("nonexistent-id-xyz", store_manager_actor)
        assert exc_info.value.error_code == "EXECUTION_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_rollback_expired_window(self, executor, store_manager_actor):
        """模拟超过30分钟的执行记录 → RollbackWindowExpiredError"""
        from datetime import datetime, timedelta

        # Mock _get_audit_record 返回超时记录
        old_time = datetime.utcnow() - timedelta(minutes=35)
        executor._get_audit_record = AsyncMock(return_value={
            "execution_id": "old-exec-id",
            "command_type": "shift_report",
            "store_id": "STORE_A1",
            "brand_id": "BRAND_A",
            "executed_at": old_time,
            "status": "completed",
            "actor_id": "USER_001",
        })

        with pytest.raises(RollbackWindowExpiredError) as exc_info:
            await executor.rollback("old-exec-id", store_manager_actor)
        assert exc_info.value.error_code == "ROLLBACK_WINDOW_EXPIRED"

    @pytest.mark.asyncio
    async def test_rollback_happy_path(self, executor, store_manager_actor):
        """30分钟内，有审批权限的操作员可以成功回滚"""
        from datetime import datetime, timedelta

        recent_time = datetime.utcnow() - timedelta(minutes=5)
        executor._get_audit_record = AsyncMock(return_value={
            "execution_id": "exec-123",
            "command_type": "discount_apply",   # approver_roles includes store_manager
            "store_id": "STORE_A1",
            "brand_id": "BRAND_A",
            "executed_at": recent_time,
            "status": "completed",
            "actor_id": "USER_001",
        })

        result = await executor.rollback("exec-123", store_manager_actor)

        assert result["status"] == "rolled_back"
        assert result["original_execution_id"] == "exec-123"
        assert "rollback_id" in result
        assert result["operator_id"] == store_manager_actor["user_id"]

    @pytest.mark.asyncio
    async def test_rollback_non_approver_denied(self, executor, waiter_actor):
        """非审批角色尝试回滚 → PermissionDeniedError"""
        from datetime import datetime, timedelta

        recent_time = datetime.utcnow() - timedelta(minutes=5)
        executor._get_audit_record = AsyncMock(return_value={
            "execution_id": "exec-456",
            "command_type": "discount_apply",   # waiter not in approver_roles
            "store_id": "STORE_A1",
            "brand_id": "BRAND_A",
            "executed_at": recent_time,
            "status": "completed",
            "actor_id": "USER_001",
        })

        with pytest.raises(PermissionDeniedError) as exc_info:
            await executor.rollback("exec-456", waiter_actor)
        assert exc_info.value.error_code == "PERMISSION_DENIED"
        assert "waiter" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 金额熔断 reason 字符串
# ---------------------------------------------------------------------------

class TestCircuitBreaker:
    @pytest.mark.asyncio
    async def test_circuit_breaker_reason_contains_amount_and_threshold(
        self, executor, store_manager_actor, discount_payload_large
    ):
        """熔断触发时 ApprovalRequiredError.reason 包含实际金额和熔断阈值"""
        with pytest.raises(ApprovalRequiredError) as exc_info:
            await executor.execute("discount_apply", discount_payload_large, store_manager_actor)
        reason = exc_info.value.reason
        # reason = "金额 800.0 超过熔断阈值 500.0 元，自动升级为 APPROVE"
        assert "800" in reason
        assert "500" in reason

    @pytest.mark.asyncio
    async def test_below_circuit_breaker_still_approve_level(
        self, executor, store_manager_actor, discount_payload_small
    ):
        """小额折扣（200元，低于阈值500元）因 APPROVE 级别触发审批，非熔断"""
        with pytest.raises(ApprovalRequiredError) as exc_info:
            await executor.execute("discount_apply", discount_payload_small, store_manager_actor)
        reason = exc_info.value.reason
        # Not circuit-breaker triggered; reason should NOT mention threshold info
        assert "500" not in reason or "超过熔断阈值" not in reason


# ---------------------------------------------------------------------------
# 折扣类指令异常检测触发
# ---------------------------------------------------------------------------

class TestAnomalyDispatch:
    @pytest.mark.asyncio
    async def test_discount_apply_dispatches_anomaly_check(
        self, executor, store_manager_actor
    ):
        """discount_apply 在 AUTO 路由下执行后触发 realtime_anomaly_check.delay"""
        from src.core.execution_registry import COMMAND_REGISTRY, ExecutionLevel

        # Temporarily override level so discount_apply goes through AUTO path
        original_level = COMMAND_REGISTRY["discount_apply"].level
        COMMAND_REGISTRY["discount_apply"].level = ExecutionLevel.AUTO

        mock_check = MagicMock()
        mock_check.delay = MagicMock()
        mock_celery = MagicMock()
        mock_celery.realtime_anomaly_check = mock_check

        try:
            with patch.dict("sys.modules", {"src.core.celery_tasks": mock_celery}):
                await executor.execute(
                    "discount_apply",
                    {"store_id": "STORE_A1", "brand_id": "BRAND_A", "amount": 100.0},
                    store_manager_actor,
                )
            mock_check.delay.assert_called_once()
            kwargs = mock_check.delay.call_args[1]
            assert kwargs["store_id"] == "STORE_A1"
        finally:
            COMMAND_REGISTRY["discount_apply"].level = original_level


# ===========================================================================
# TrustedExecutor with DB session (lines 356-374, 381-395, 406-416)
# ===========================================================================

class TestTrustedExecutorWithDB:
    @pytest.mark.asyncio
    async def test_write_audit_with_db_success(self):
        """_write_audit stores a DB record when db_session is provided (lines 356-374)."""
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()

        with patch.dict("sys.modules", {
            "src.models.execution_audit": MagicMock(
                ExecutionRecord=MagicMock(return_value=MagicMock())
            )
        }):
            executor = TrustedExecutor(db_session=mock_db)
            record = await executor._write_audit(
                execution_id="EX-1",
                command_type="discount_apply",
                payload={"store_id": "S1"},
                actor_id="U1",
                actor_role="store_manager",
                store_id="S1",
                brand_id="B1",
                status="completed",
                level="auto",
                amount=100.0,
            )

        mock_db.add.assert_called_once()
        mock_db.flush.assert_awaited_once()
        assert record["execution_id"] == "EX-1"

    @pytest.mark.asyncio
    async def test_write_audit_with_db_exception_is_swallowed(self):
        """DB exception during audit write is logged and swallowed (line 373-374)."""
        mock_db = AsyncMock()
        mock_db.flush = AsyncMock(side_effect=RuntimeError("DB down"))
        mock_db.add = MagicMock()

        with patch.dict("sys.modules", {
            "src.models.execution_audit": MagicMock(
                ExecutionRecord=MagicMock(return_value=MagicMock())
            )
        }):
            executor = TrustedExecutor(db_session=mock_db)
            # Should NOT raise
            record = await executor._write_audit(
                execution_id="EX-2",
                command_type="shift_report",
                payload={},
                actor_id="U1",
                actor_role="store_manager",
                store_id="S1",
                brand_id="B1",
                status="completed",
                level="auto",
            )
        assert record["execution_id"] == "EX-2"

    @pytest.mark.asyncio
    async def test_get_audit_record_with_db_found(self):
        """_get_audit_record returns dict when DB record found (lines 381-393)."""
        mock_record = MagicMock()
        mock_record.id = "EX-3"
        mock_record.command_type = "shift_report"
        mock_record.store_id = "S1"
        mock_record.brand_id = "B1"
        mock_record.created_at = "2026-01-01T00:00:00"
        mock_record.status = "completed"
        mock_record.actor_id = "U1"

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=mock_record)

        with patch.dict("sys.modules", {
            "src.models.execution_audit": MagicMock(ExecutionRecord=MagicMock())
        }):
            executor = TrustedExecutor(db_session=mock_db)
            result = await executor._get_audit_record("EX-3")

        assert result is not None
        assert result["execution_id"] == "EX-3"
        assert result["command_type"] == "shift_report"

    @pytest.mark.asyncio
    async def test_get_audit_record_with_db_not_found(self):
        """_get_audit_record returns None when DB record not found."""
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=None)

        with patch.dict("sys.modules", {
            "src.models.execution_audit": MagicMock(ExecutionRecord=MagicMock())
        }):
            executor = TrustedExecutor(db_session=mock_db)
            result = await executor._get_audit_record("NONEXISTENT")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_audit_record_exception_returns_none(self):
        """DB exception in _get_audit_record is swallowed, returns None (lines 394-395)."""
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(side_effect=RuntimeError("DB error"))

        with patch.dict("sys.modules", {
            "src.models.execution_audit": MagicMock(ExecutionRecord=MagicMock())
        }):
            executor = TrustedExecutor(db_session=mock_db)
            result = await executor._get_audit_record("EX-X")

        assert result is None

    @pytest.mark.asyncio
    async def test_mark_rolled_back_with_db_success(self):
        """_mark_rolled_back updates record in DB (lines 406-414)."""
        mock_record = MagicMock()
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=mock_record)
        mock_db.flush = AsyncMock()

        with patch.dict("sys.modules", {
            "src.models.execution_audit": MagicMock(ExecutionRecord=MagicMock())
        }):
            executor = TrustedExecutor(db_session=mock_db)
            await executor._mark_rolled_back("EX-4", "U1", "RB-1")

        assert mock_record.status == "rolled_back"
        assert mock_record.rollback_id == "RB-1"
        assert mock_record.rolled_back_by == "U1"
        mock_db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_mark_rolled_back_exception_is_swallowed(self):
        """DB exception in _mark_rolled_back is swallowed (lines 415-416)."""
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(side_effect=RuntimeError("DB error"))

        with patch.dict("sys.modules", {
            "src.models.execution_audit": MagicMock(ExecutionRecord=MagicMock())
        }):
            executor = TrustedExecutor(db_session=mock_db)
            # Should NOT raise
            await executor._mark_rolled_back("EX-5", "U1", "RB-2")


# ===========================================================================
# Celery dispatch exception handler (lines 194-204)
# ===========================================================================

class TestCeleryDispatchException:
    @pytest.mark.asyncio
    async def test_celery_unavailable_does_not_block_execution(self):
        """
        When realtime_anomaly_check.delay raises, execution continues normally (lines 194-204).
        Patch get_command_def to return AUTO level so the anomaly-check code path fires.
        """
        # Patch get_command_def to return AUTO level with discount_apply type
        auto_cmd = MagicMock()
        auto_cmd.level = ExecutionLevel.AUTO
        auto_cmd.allowed_roles = {"store_manager"}
        auto_cmd.amount_circuit_breaker = None

        executor = TrustedExecutor()

        # Stub celery_tasks module so the import inside the try block resolves
        mock_celery_task = MagicMock()
        mock_celery_task.delay = MagicMock(side_effect=RuntimeError("celery down"))
        mock_celery_module = MagicMock(realtime_anomaly_check=mock_celery_task)

        with patch("src.core.trusted_executor.get_command_def", return_value=auto_cmd), \
             patch("src.core.trusted_executor.COMMAND_REGISTRY", {}), \
             patch.dict("sys.modules", {"src.core.celery_tasks": mock_celery_module}):
            result = await executor.execute(
                "discount_apply",
                {"store_id": "S1", "brand_id": "B1", "amount": 10.0},
                {"user_id": "U1", "role": "store_manager", "store_id": "S1"},
            )
        # Execution should succeed despite celery failure
        assert result["command_type"] == "discount_apply"
        assert result["status"] == "completed"


# ===========================================================================
# rollback with string executed_at (line 265)
# ===========================================================================

class TestRollbackWithStringTimestamp:
    @pytest.mark.asyncio
    async def test_rollback_parses_string_executed_at(self):
        """
        When executed_at in the audit record is a string (ISO format),
        it gets parsed via datetime.fromisoformat() (line 265).
        """
        from datetime import datetime, timedelta

        executor = TrustedExecutor()

        # Mock _get_audit_record to return a record with string executed_at
        fresh_ts = (datetime.utcnow() - timedelta(minutes=5)).isoformat()
        mock_record = {
            "execution_id": "EX-OLD",
            "command_type": "shift_report",
            "store_id": "S1",
            "brand_id": "B1",
            "executed_at": fresh_ts,  # string, not datetime
            "status": "completed",
            "actor_id": "U1",
        }

        executor._get_audit_record = AsyncMock(return_value=mock_record)
        executor._write_audit = AsyncMock(return_value=mock_record)
        executor._mark_rolled_back = AsyncMock()

        result = await executor.rollback(
            "EX-OLD",
            {"user_id": "ADMIN", "role": "super_admin"},
        )
        assert result["original_execution_id"] == "EX-OLD"
        assert result["status"] == "rolled_back"


# ===========================================================================
# Defensive else branch (lines 203-204): level is not APPROVE/AUTO/NOTIFY
# ===========================================================================

class TestUnknownLevelBranch:
    @pytest.mark.asyncio
    async def test_unknown_level_status_is_unknown(self):
        """
        When effective_level is not APPROVE, AUTO, or NOTIFY, the else branch
        sets result={} and status='unknown' (lines 203-204).
        """
        class _SentinelLevel:
            """Not equal to any ExecutionLevel enum value."""
            value = "unknown_level"

        mock_cmd = MagicMock()
        mock_cmd.level = _SentinelLevel()
        mock_cmd.allowed_roles = {"store_manager"}
        mock_cmd.amount_circuit_breaker = None  # no circuit breaking

        executor = TrustedExecutor()

        with patch("src.core.trusted_executor.get_command_def", return_value=mock_cmd), \
             patch("src.core.trusted_executor.COMMAND_REGISTRY", {}):
            result = await executor.execute(
                "mystery_command",
                {"store_id": "S1"},
                {"user_id": "U1", "role": "store_manager", "store_id": "S1"},
            )

        assert result["status"] == "unknown"
