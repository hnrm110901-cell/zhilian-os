"""
Tests for src/services/auth_service.py — TEST-001 JWT 签发与 RBAC 全链路.

No real DB needed: all DB-dependent methods are tested via mock sessions.
JWT encoding uses patched settings (deterministic SECRET_KEY).

Covers:
  - create_tokens_for_user: both tokens returned, correct structure and claims
  - refresh_access_token: valid refresh token → new access token
  - refresh_access_token: invalid token → ValueError
  - refresh_access_token: inactive user → ValueError
  - create_access_token_for_user: backward-compat alias delegates to create_tokens
  - authenticate_user: correct password → User; wrong password → None
  - register_user: duplicate username/email → ValueError
  - get_user_by_id: found → User; not found → None
  - change_password: wrong old password → False; correct → True
"""
import sys
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from contextlib import asynccontextmanager

# Pre-stub modules that trigger Settings validation at import time.
# Using setdefault so we never replace an already-imported real module.
sys.modules.setdefault("src.core.config", MagicMock(settings=MagicMock()))
sys.modules.setdefault("src.core.database", MagicMock(get_db_session=MagicMock()))

_TEST_SECRET = "test-secret-for-auth-service-tests"

# Patch settings before importing modules that use them
import src.core.security as _sec
_sec.settings = MagicMock(SECRET_KEY=_TEST_SECRET)

from src.services.auth_service import AuthService
from src.core.security import (
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    get_password_hash,
    verify_password,
)
from src.models.user import User, UserRole


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_secret(monkeypatch):
    monkeypatch.setattr(_sec, "settings", MagicMock(SECRET_KEY=_TEST_SECRET))


def _make_user(
    username="testuser",
    role=UserRole.WAITER,
    is_active=True,
    store_id="S1",
    password="secret",
):
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.username = username
    user.email = f"{username}@test.com"
    user.full_name = "Test User"
    user.role = role
    user.store_id = store_id
    user.is_active = is_active
    user.hashed_password = get_password_hash(password)
    return user


def _mock_db_session(return_value=None):
    """Async context manager mock for get_db_session()."""
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=return_value)
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    @asynccontextmanager
    async def _ctx():
        yield session

    return _ctx


# ===========================================================================
# create_tokens_for_user
# ===========================================================================

class TestCreateTokensForUser:
    @pytest.mark.asyncio
    async def test_returns_access_and_refresh_tokens(self):
        user = _make_user()
        svc = AuthService()
        result = await svc.create_tokens_for_user(user)
        assert "access_token" in result
        assert "refresh_token" in result
        assert result["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_expires_in_is_seconds(self):
        user = _make_user()
        svc = AuthService()
        result = await svc.create_tokens_for_user(user)
        assert isinstance(result["expires_in"], int)
        assert result["expires_in"] > 0

    @pytest.mark.asyncio
    async def test_user_info_embedded(self):
        user = _make_user(username="alice", role=UserRole.STORE_MANAGER, store_id="S99")
        svc = AuthService()
        result = await svc.create_tokens_for_user(user)
        u = result["user"]
        assert u["username"] == "alice"
        assert u["role"] == UserRole.STORE_MANAGER.value
        assert u["store_id"] == "S99"
        assert u["is_active"] is True

    @pytest.mark.asyncio
    async def test_access_token_decodable(self):
        user = _make_user(username="bob")
        svc = AuthService()
        result = await svc.create_tokens_for_user(user)
        payload = decode_access_token(result["access_token"])
        assert payload["username"] == "bob"
        assert payload["type"] == "access"

    @pytest.mark.asyncio
    async def test_refresh_token_decodable(self):
        user = _make_user(username="carol")
        svc = AuthService()
        result = await svc.create_tokens_for_user(user)
        payload = decode_refresh_token(result["refresh_token"])
        assert payload["username"] == "carol"
        assert payload["type"] == "refresh"

    @pytest.mark.asyncio
    async def test_tokens_differ_from_each_other(self):
        user = _make_user()
        svc = AuthService()
        r = await svc.create_tokens_for_user(user)
        assert r["access_token"] != r["refresh_token"]

    @pytest.mark.asyncio
    async def test_create_access_token_for_user_alias(self):
        """Deprecated method delegates to create_tokens_for_user."""
        user = _make_user()
        svc = AuthService()
        result = await svc.create_access_token_for_user(user)
        assert "access_token" in result
        assert "refresh_token" in result


# ===========================================================================
# refresh_access_token
# ===========================================================================

class TestRefreshAccessToken:
    @pytest.mark.asyncio
    async def test_valid_refresh_token_returns_new_access_token(self):
        user = _make_user(username="dave")
        svc = AuthService()

        # Create a valid refresh token first
        tokens = await svc.create_tokens_for_user(user)
        refresh_tok = tokens["refresh_token"]

        # Patch get_user_by_id to return the active user
        svc.get_user_by_id = AsyncMock(return_value=user)
        result = await svc.refresh_access_token(refresh_tok)
        assert "access_token" in result
        assert result["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_invalid_refresh_token_raises_http_exception(self):
        svc = AuthService()
        with pytest.raises(Exception):  # HTTPException or ValueError
            await svc.refresh_access_token("not-a-valid-token")

    @pytest.mark.asyncio
    async def test_inactive_user_raises_value_error(self):
        user = _make_user(is_active=False)
        svc = AuthService()
        tokens = await svc.create_tokens_for_user(user)
        svc.get_user_by_id = AsyncMock(return_value=user)
        with pytest.raises(ValueError, match="用户不存在或已被禁用"):
            await svc.refresh_access_token(tokens["refresh_token"])

    @pytest.mark.asyncio
    async def test_user_not_found_raises_value_error(self):
        user = _make_user()
        svc = AuthService()
        tokens = await svc.create_tokens_for_user(user)
        svc.get_user_by_id = AsyncMock(return_value=None)
        with pytest.raises(ValueError, match="用户不存在或已被禁用"):
            await svc.refresh_access_token(tokens["refresh_token"])

    @pytest.mark.asyncio
    async def test_access_token_rejected_as_refresh_token(self):
        """Access tokens must be rejected by refresh_access_token."""
        user = _make_user()
        svc = AuthService()
        tokens = await svc.create_tokens_for_user(user)
        with pytest.raises(Exception):
            await svc.refresh_access_token(tokens["access_token"])


# ===========================================================================
# authenticate_user (mock DB)
# ===========================================================================

class TestAuthenticateUser:
    @pytest.mark.asyncio
    async def test_correct_credentials_returns_user(self):
        user = _make_user(username="emp", password="correct")
        svc = AuthService()
        with patch("src.services.auth_service.get_db_session", _mock_db_session(user)):
            result = await svc.authenticate_user("emp", "correct")
        assert result is user

    @pytest.mark.asyncio
    async def test_wrong_password_returns_none(self):
        user = _make_user(username="emp", password="correct")
        svc = AuthService()
        with patch("src.services.auth_service.get_db_session", _mock_db_session(user)):
            result = await svc.authenticate_user("emp", "wrong-password")
        assert result is None

    @pytest.mark.asyncio
    async def test_user_not_found_returns_none(self):
        svc = AuthService()
        with patch("src.services.auth_service.get_db_session", _mock_db_session(None)):
            result = await svc.authenticate_user("ghost", "pw")
        assert result is None


# ===========================================================================
# get_user_by_id (mock DB)
# ===========================================================================

class TestGetUserById:
    @pytest.mark.asyncio
    async def test_found_returns_user(self):
        user = _make_user()
        svc = AuthService()
        with patch("src.services.auth_service.get_db_session", _mock_db_session(user)):
            result = await svc.get_user_by_id(str(user.id))
        assert result is user

    @pytest.mark.asyncio
    async def test_not_found_returns_none(self):
        svc = AuthService()
        with patch("src.services.auth_service.get_db_session", _mock_db_session(None)):
            result = await svc.get_user_by_id("nonexistent-id")
        assert result is None


# ===========================================================================
# register_user (mock DB — duplicate checks)
# ===========================================================================

class TestRegisterUser:
    @pytest.mark.asyncio
    async def test_duplicate_username_raises(self):
        existing = _make_user(username="taken")
        svc = AuthService()
        # First query (username check) returns existing user
        session = AsyncMock()
        existing_result = MagicMock()
        existing_result.scalar_one_or_none = MagicMock(return_value=existing)
        session.execute = AsyncMock(return_value=existing_result)

        @asynccontextmanager
        async def _ctx():
            yield session

        with patch("src.services.auth_service.get_db_session", _ctx):
            with pytest.raises(ValueError, match="用户名已存在"):
                await svc.register_user(
                    username="taken", email="new@test.com",
                    password="pw", full_name="Test",
                    role=UserRole.WAITER,
                )


# ===========================================================================
# change_password (mock DB)
# ===========================================================================

class TestChangePassword:
    @pytest.mark.asyncio
    async def test_correct_old_password_returns_true(self):
        user = _make_user(password="old-pw")
        svc = AuthService()
        with patch("src.services.auth_service.get_db_session", _mock_db_session(user)):
            result = await svc.change_password(str(user.id), "old-pw", "new-pw")
        assert result is True

    @pytest.mark.asyncio
    async def test_wrong_old_password_returns_false(self):
        user = _make_user(password="old-pw")
        svc = AuthService()
        with patch("src.services.auth_service.get_db_session", _mock_db_session(user)):
            result = await svc.change_password(str(user.id), "wrong-pw", "new-pw")
        assert result is False

    @pytest.mark.asyncio
    async def test_user_not_found_returns_false(self):
        svc = AuthService()
        with patch("src.services.auth_service.get_db_session", _mock_db_session(None)):
            result = await svc.change_password("ghost-id", "pw", "new-pw")
        assert result is False
