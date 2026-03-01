"""
可信执行层 API 端点测试

覆盖：
POST /api/v1/execution/execute
  - AUTO 指令 → 200，executor.execute 结果透传
  - ApprovalRequiredError → 200 pending_approval（不是4xx）
  - PermissionDeniedError → 403
  - ExecutionError → 400
  - 未知异常 → 500

POST /api/v1/execution/{id}/rollback
  - 成功回滚 → 200
  - RollbackWindowExpiredError → 409
  - PermissionDeniedError → 403
  - ExecutionError → 400
"""
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.modules.setdefault("src.services.agent_service", MagicMock())

from src.api.execution import router, get_executor, get_current_user
from src.core.trusted_executor import (
    ApprovalRequiredError,
    ExecutionError,
    PermissionDeniedError,
    RollbackWindowExpiredError,
)


# ---------------------------------------------------------------------------
# App fixture with dependency overrides
# ---------------------------------------------------------------------------

_app = FastAPI()
_app.include_router(router)

_ACTOR = {"user_id": "U1", "role": "admin", "store_id": "S1", "brand_id": "B1"}

# Always use test actor
_app.dependency_overrides[get_current_user] = lambda: _ACTOR

client = TestClient(_app)


def _override_executor(mock_executor):
    """Install a mock TrustedExecutor as a FastAPI dependency override."""
    _app.dependency_overrides[get_executor] = lambda: mock_executor


def _clear_executor_override():
    _app.dependency_overrides.pop(get_executor, None)


# ---------------------------------------------------------------------------
# POST /api/v1/execution/execute
# ---------------------------------------------------------------------------

class TestExecuteCommand:
    def setup_method(self):
        _clear_executor_override()

    def test_auto_command_returns_200(self):
        exc = MagicMock()
        exc.execute = AsyncMock(return_value={"status": "completed", "execution_id": "EX001"})
        _override_executor(exc)
        resp = client.post(
            "/api/v1/execution/execute",
            json={"command_type": "shift_report", "payload": {"store_id": "S1"}},
        )
        assert resp.status_code == 200

    def test_auto_command_result_is_returned(self):
        exc = MagicMock()
        exc.execute = AsyncMock(return_value={"status": "completed", "execution_id": "EX001"})
        _override_executor(exc)
        resp = client.post(
            "/api/v1/execution/execute",
            json={"command_type": "shift_report", "payload": {}},
        )
        assert resp.json()["status"] == "completed"

    def test_approval_required_returns_200_with_pending(self):
        exc = MagicMock()
        exc.execute = AsyncMock(
            side_effect=ApprovalRequiredError("discount_apply", "金额超过200元")
        )
        _override_executor(exc)
        resp = client.post(
            "/api/v1/execution/execute",
            json={"command_type": "discount_apply", "payload": {"amount": 300}},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending_approval"

    def test_approval_required_contains_command_type(self):
        exc = MagicMock()
        exc.execute = AsyncMock(
            side_effect=ApprovalRequiredError("discount_apply", "金额超过200元")
        )
        _override_executor(exc)
        resp = client.post(
            "/api/v1/execution/execute",
            json={"command_type": "discount_apply", "payload": {}},
        )
        assert resp.json()["command_type"] == "discount_apply"

    def test_permission_denied_returns_403(self):
        exc = MagicMock()
        exc.execute = AsyncMock(
            side_effect=PermissionDeniedError("cashier", "discount_apply")
        )
        _override_executor(exc)
        resp = client.post(
            "/api/v1/execution/execute",
            json={"command_type": "discount_apply", "payload": {}},
        )
        assert resp.status_code == 403

    def test_permission_denied_detail_has_error_code(self):
        exc = MagicMock()
        exc.execute = AsyncMock(
            side_effect=PermissionDeniedError("cashier", "discount_apply")
        )
        _override_executor(exc)
        resp = client.post(
            "/api/v1/execution/execute",
            json={"command_type": "discount_apply", "payload": {}},
        )
        assert resp.json()["detail"]["error_code"] == "PERMISSION_DENIED"

    def test_execution_error_returns_400(self):
        exc = MagicMock()
        exc.execute = AsyncMock(
            side_effect=ExecutionError("无效的指令参数", "INVALID_PAYLOAD")
        )
        _override_executor(exc)
        resp = client.post(
            "/api/v1/execution/execute",
            json={"command_type": "bad_cmd", "payload": {}},
        )
        assert resp.status_code == 400

    def test_unexpected_exception_returns_500(self):
        exc = MagicMock()
        exc.execute = AsyncMock(side_effect=RuntimeError("unexpected"))
        _override_executor(exc)
        resp = client.post(
            "/api/v1/execution/execute",
            json={"command_type": "shift_report", "payload": {}},
        )
        assert resp.status_code == 500

    def test_500_has_internal_error_code(self):
        exc = MagicMock()
        exc.execute = AsyncMock(side_effect=RuntimeError("unexpected"))
        _override_executor(exc)
        resp = client.post(
            "/api/v1/execution/execute",
            json={"command_type": "shift_report", "payload": {}},
        )
        assert resp.json()["detail"]["error_code"] == "INTERNAL_ERROR"


# ---------------------------------------------------------------------------
# POST /api/v1/execution/{id}/rollback
# ---------------------------------------------------------------------------

class TestRollbackExecution:
    def setup_method(self):
        _clear_executor_override()

    def test_successful_rollback_returns_200(self):
        exc = MagicMock()
        exc.rollback = AsyncMock(return_value={"status": "rolled_back", "execution_id": "EX001"})
        _override_executor(exc)
        resp = client.post("/api/v1/execution/EX001/rollback", json={})
        assert resp.status_code == 200

    def test_rollback_result_is_returned(self):
        exc = MagicMock()
        exc.rollback = AsyncMock(return_value={"status": "rolled_back", "execution_id": "EX001"})
        _override_executor(exc)
        resp = client.post("/api/v1/execution/EX001/rollback", json={})
        assert resp.json()["status"] == "rolled_back"

    def test_window_expired_returns_409(self):
        exc = MagicMock()
        exc.rollback = AsyncMock(
            side_effect=RollbackWindowExpiredError("EX001")
        )
        _override_executor(exc)
        resp = client.post("/api/v1/execution/EX001/rollback", json={})
        assert resp.status_code == 409

    def test_window_expired_detail_has_error_code(self):
        exc = MagicMock()
        exc.rollback = AsyncMock(
            side_effect=RollbackWindowExpiredError("EX001")
        )
        _override_executor(exc)
        resp = client.post("/api/v1/execution/EX001/rollback", json={})
        assert resp.json()["detail"]["error_code"] == "ROLLBACK_WINDOW_EXPIRED"

    def test_permission_denied_returns_403(self):
        exc = MagicMock()
        exc.rollback = AsyncMock(
            side_effect=PermissionDeniedError("cashier", "rollback")
        )
        _override_executor(exc)
        resp = client.post("/api/v1/execution/EX001/rollback", json={})
        assert resp.status_code == 403

    def test_execution_error_returns_400(self):
        exc = MagicMock()
        exc.rollback = AsyncMock(
            side_effect=ExecutionError("找不到执行记录", "NOT_FOUND")
        )
        _override_executor(exc)
        resp = client.post("/api/v1/execution/EX001/rollback", json={})
        assert resp.status_code == 400
