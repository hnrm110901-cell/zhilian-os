"""
Integration tests for WeChatWorkMessageService
Covers lines 21-56, 75-123, 143-179, 205-244
"""
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

# ------------------------------------------------------------------
# Import the real module (config is already loaded by conftest.py).
# Ensure redis_cache_service exists so the runtime `from .redis_cache_service
# import redis_cache` inside the service succeeds.
# ------------------------------------------------------------------
sys.modules.setdefault("src.services.redis_cache_service", MagicMock(
    redis_cache=MagicMock(
        get=AsyncMock(return_value=None),
        set=AsyncMock(return_value=True),
    )
))

import src.services.wechat_work_message_service as _wwms_mod
from src.services.wechat_work_message_service import WeChatWorkMessageService

# Test settings to override the real config's settings on the module
_TEST_SETTINGS = MagicMock(
    WECHAT_CORP_ID="test_corp",
    WECHAT_CORP_SECRET="test_secret",
    WECHAT_AGENT_ID=1,
)


@pytest.fixture(autouse=True)
def _patch_settings():
    """Ensure each test sees mocked settings on the module."""
    with patch.object(_wwms_mod, "settings", _TEST_SETTINGS):
        yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_success_http_client(payload: dict):
    """Return mock_client for a successful POST/GET."""
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.json = MagicMock(return_value=payload)
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.post = AsyncMock(return_value=mock_response)
    return mock_client


def _redis_cache_stub(cached_value=None):
    """Return a fresh redis_cache mock."""
    rc = MagicMock()
    rc.get = AsyncMock(return_value=cached_value)
    rc.set = AsyncMock(return_value=True)
    return rc


# ===========================================================================
# TestGetAccessToken (lines 21-56)
# ===========================================================================

class TestGetAccessToken:
    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_token(self):
        """Lines 21-28: cached_token exists → return it without HTTP."""
        svc = WeChatWorkMessageService()
        rc = _redis_cache_stub(cached_value=b"cached-tok")

        with patch("src.services.redis_cache_service.redis_cache", rc):
            result = await svc.get_access_token()
            assert result == b"cached-tok"

    @pytest.mark.asyncio
    async def test_cache_miss_http_success(self):
        """Lines 29-56: no cached token → HTTP call → returns token."""
        import httpx as _httpx

        svc = WeChatWorkMessageService()

        mock_client = _make_success_http_client({
            "errcode": 0,
            "access_token": "new-work-tok",
            "expires_in": 7200,
        })

        rc = _redis_cache_stub(cached_value=None)

        with patch("src.services.redis_cache_service.redis_cache", rc), \
             patch.object(_httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            result = await svc.get_access_token()

        assert result == "new-work-tok"
        rc.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cache_miss_http_errcode_raises(self):
        """Lines 29-56: errcode != 0 → raises Exception."""
        import httpx as _httpx

        svc = WeChatWorkMessageService()

        mock_client = _make_success_http_client({
            "errcode": 40013,
            "errmsg": "invalid corpid",
        })

        rc = _redis_cache_stub(cached_value=None)

        with patch("src.services.redis_cache_service.redis_cache", rc), \
             patch.object(_httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            with pytest.raises(Exception, match="获取access_token失败"):
                await svc.get_access_token()


# ===========================================================================
# TestSendTextMessage (lines 75-123)
# ===========================================================================

class TestSendTextMessage:
    @pytest.mark.asyncio
    async def test_send_text_success(self):
        """Lines 75-123: errcode==0 → returns success dict."""
        import httpx as _httpx

        svc = WeChatWorkMessageService()
        svc.get_access_token = AsyncMock(return_value="tok")

        mock_client = _make_success_http_client({"errcode": 0, "errmsg": "ok"})

        with patch.object(_httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            result = await svc.send_text_message("U1", "hello")

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_send_text_failure_errcode(self):
        """Lines 75-123: errcode!=0 → returns failure dict."""
        import httpx as _httpx

        svc = WeChatWorkMessageService()
        svc.get_access_token = AsyncMock(return_value="tok")

        mock_client = _make_success_http_client({"errcode": 60020, "errmsg": "not allow"})

        with patch.object(_httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            result = await svc.send_text_message("U1", "hello")

        assert result["success"] is False
        assert result["errcode"] == 60020

    @pytest.mark.asyncio
    async def test_send_text_exception_returns_error_dict(self):
        """Lines 75-123: outer except → returns error dict."""
        svc = WeChatWorkMessageService()
        svc.get_access_token = AsyncMock(side_effect=RuntimeError("auth failed"))

        result = await svc.send_text_message("U1", "hello")

        assert result["success"] is False
        assert "auth failed" in result["error"]


# ===========================================================================
# TestSendMarkdownMessage (lines 143-179)
# ===========================================================================

class TestSendMarkdownMessage:
    @pytest.mark.asyncio
    async def test_send_markdown_success(self):
        """Lines 143-179: errcode==0 → returns {"success": True}."""
        import httpx as _httpx

        svc = WeChatWorkMessageService()
        svc.get_access_token = AsyncMock(return_value="tok")

        mock_client = _make_success_http_client({"errcode": 0, "errmsg": "ok"})

        with patch.object(_httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            result = await svc.send_markdown_message("U1", "**bold**")

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_send_markdown_failure_errcode(self):
        """Lines 143-179: errcode!=0 → returns {"success": False, "error": ...}."""
        import httpx as _httpx

        svc = WeChatWorkMessageService()
        svc.get_access_token = AsyncMock(return_value="tok")

        mock_client = _make_success_http_client({"errcode": 60020, "errmsg": "not allow"})

        with patch.object(_httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            result = await svc.send_markdown_message("U1", "**bold**")

        assert result["success"] is False
        assert result["error"] == "not allow"

    @pytest.mark.asyncio
    async def test_send_markdown_exception_returns_error_dict(self):
        """Lines 143-179: outer except → returns error dict."""
        svc = WeChatWorkMessageService()
        svc.get_access_token = AsyncMock(side_effect=RuntimeError("network"))

        result = await svc.send_markdown_message("U1", "**bold**")

        assert result["success"] is False
        assert "network" in result["error"]


# ===========================================================================
# TestSendCardMessage (lines 205-244)
# ===========================================================================

class TestSendCardMessage:
    @pytest.mark.asyncio
    async def test_send_card_success(self):
        """Lines 205-244: errcode==0 → returns {"success": True}."""
        import httpx as _httpx

        svc = WeChatWorkMessageService()
        svc.get_access_token = AsyncMock(return_value="tok")

        mock_client = _make_success_http_client({"errcode": 0, "errmsg": "ok"})

        with patch.object(_httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            result = await svc.send_card_message("U1", "Title", "Desc", "http://x")

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_send_card_failure_errcode(self):
        """Lines 205-244: errcode!=0 → returns {"success": False, "error": ...}."""
        import httpx as _httpx

        svc = WeChatWorkMessageService()
        svc.get_access_token = AsyncMock(return_value="tok")

        mock_client = _make_success_http_client({"errcode": 60020, "errmsg": "not allow"})

        with patch.object(_httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            result = await svc.send_card_message("U1", "Title", "Desc", "http://x")

        assert result["success"] is False
        assert result["error"] == "not allow"

    @pytest.mark.asyncio
    async def test_send_card_exception_returns_error_dict(self):
        """Lines 205-244: outer except → returns error dict."""
        svc = WeChatWorkMessageService()
        svc.get_access_token = AsyncMock(side_effect=RuntimeError("network"))

        result = await svc.send_card_message("U1", "Title", "Desc", "http://x")

        assert result["success"] is False
        assert "network" in result["error"]

    @pytest.mark.asyncio
    async def test_send_card_custom_btntxt(self):
        """Lines 205-244: custom btntxt is accepted."""
        import httpx as _httpx

        svc = WeChatWorkMessageService()
        svc.get_access_token = AsyncMock(return_value="tok")

        mock_client = _make_success_http_client({"errcode": 0})

        with patch.object(_httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            result = await svc.send_card_message("U1", "T", "D", "http://x", btntxt="查看")

        assert result["success"] is True
