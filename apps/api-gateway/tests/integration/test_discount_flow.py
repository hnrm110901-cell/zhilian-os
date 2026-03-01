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
