"""
Unit tests for WeChatService
"""
import sys
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

# Mock settings BEFORE importing wechat_service
mock_settings = MagicMock()
mock_settings.WECHAT_CORP_ID = "test_corp"
mock_settings.WECHAT_CORP_SECRET = "test_secret"
mock_settings.WECHAT_AGENT_ID = 1
mock_config = MagicMock()
mock_config.settings = mock_settings
sys.modules["src.core.config"] = mock_config
sys.modules.setdefault("src.services.agent_service", MagicMock())

from src.services.wechat_service import WeChatService, TEMPLATES, DEDUP_KEY_PREFIX, FAILED_MSG_QUEUE_KEY


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_redis():
    """Return a minimal async-capable mock redis client."""
    redis = MagicMock()
    redis.exists = AsyncMock(return_value=False)
    redis.set = AsyncMock(return_value=True)
    redis.rpush = AsyncMock(return_value=1)
    redis.lpop = AsyncMock(return_value=None)
    return redis


# ===========================================================================
# TestTemplates
# ===========================================================================

class TestTemplates:
    """Sync tests — no mocks needed, just call the template lambdas."""

    def test_discount_approval_contains_store_id(self):
        result = TEMPLATES["discount_approval"]({"store_id": "S1", "amount": 50.0, "reason": "VIP"})
        assert "S1" in result

    def test_discount_approval_contains_amount(self):
        result = TEMPLATES["discount_approval"]({"store_id": "S1", "amount": 50.0, "reason": "VIP"})
        assert "50.00" in result

    def test_anomaly_alert_contains_anomaly_type(self):
        result = TEMPLATES["anomaly_alert"]({"store_id": "S1", "anomaly_type": "高折扣", "severity": "high"})
        assert "高折扣" in result

    def test_shift_report_contains_revenue(self):
        result = TEMPLATES["shift_report"]({"store_id": "S1", "revenue": 1234.5, "order_count": 10})
        assert "1234.50" in result

    def test_daily_forecast_contains_target_date(self):
        result = TEMPLATES["daily_forecast"]({"target_date": "2026-03-02", "estimated_revenue": 5000})
        assert "2026-03-02" in result

    def test_daily_forecast_note_included_when_present(self):
        result = TEMPLATES["daily_forecast"]({"note": "数据积累中"})
        assert "数据积累中" in result

    def test_daily_forecast_no_note_when_absent(self):
        result = TEMPLATES["daily_forecast"]({})
        assert "数据积累中" not in result


# ===========================================================================
# TestIsConfigured
# ===========================================================================

class TestIsConfigured:
    def test_fully_configured_returns_true(self):
        svc = WeChatService()
        assert svc.is_configured() is True

    def test_empty_corp_id_returns_false(self):
        svc = WeChatService()
        svc.corp_id = ""
        assert svc.is_configured() is False

    def test_empty_corp_secret_returns_false(self):
        svc = WeChatService()
        svc.corp_secret = ""
        assert svc.is_configured() is False


# ===========================================================================
# TestGetAccessToken
# ===========================================================================

class TestGetAccessToken:
    @pytest.mark.asyncio
    async def test_cached_token_not_expired_returns_without_http(self):
        svc = WeChatService()
        svc.access_token = "CACHED"
        svc.token_expire_time = datetime.now() + timedelta(hours=1)

        # If HTTP were called this patch would raise; absence of error proves no HTTP call
        with patch("httpx.AsyncClient") as mock_client_cls:
            result = await svc.get_access_token()

        assert result == "CACHED"
        mock_client_cls.assert_not_called()


# ===========================================================================
# TestSendTemplatedMessage
# ===========================================================================

class TestSendTemplatedMessage:
    @pytest.mark.asyncio
    async def test_unknown_template_raises_value_error(self):
        svc = WeChatService(redis_client=_make_redis())
        with pytest.raises(ValueError):
            await svc.send_templated_message("bad_template", {}, "U1")

    @pytest.mark.asyncio
    async def test_duplicate_message_id_returns_skipped(self):
        redis = _make_redis()
        redis.exists = AsyncMock(return_value=True)
        svc = WeChatService(redis_client=redis)

        result = await svc.send_templated_message(
            "discount_approval", {"amount": 10}, "U1", message_id="MSG1"
        )
        assert result["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_duplicate_skipped_result_contains_message_id(self):
        redis = _make_redis()
        redis.exists = AsyncMock(return_value=True)
        svc = WeChatService(redis_client=redis)

        result = await svc.send_templated_message(
            "discount_approval", {"amount": 10}, "U1", message_id="MSG1"
        )
        assert result["message_id"] == "MSG1"

    @pytest.mark.asyncio
    async def test_success_returns_sent_status(self):
        redis = _make_redis()
        redis.exists = AsyncMock(return_value=False)
        redis.set = AsyncMock(return_value=True)
        svc = WeChatService(redis_client=redis)
        svc.send_text_message = AsyncMock(return_value={"errcode": 0})

        result = await svc.send_templated_message("shift_report", {"revenue": 100}, "U1")
        assert result["status"] == "sent"

    @pytest.mark.asyncio
    async def test_success_marks_dedup_in_redis(self):
        redis = _make_redis()
        redis.exists = AsyncMock(return_value=False)
        redis.set = AsyncMock(return_value=True)
        svc = WeChatService(redis_client=redis)
        svc.send_text_message = AsyncMock(return_value={"errcode": 0})

        await svc.send_templated_message("shift_report", {"revenue": 100}, "U1")
        redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_failure_enqueues_and_returns_failed(self):
        redis = _make_redis()
        redis.exists = AsyncMock(return_value=False)
        redis.rpush = AsyncMock(return_value=1)
        svc = WeChatService(redis_client=redis)
        svc.send_text_message = AsyncMock(side_effect=ConnectionError("net"))

        result = await svc.send_templated_message("anomaly_alert", {"anomaly_type": "x"}, "U1")
        assert result["status"] == "failed"
        redis.rpush.assert_called_once()


# ===========================================================================
# TestRetryFailedMessages
# ===========================================================================

class TestRetryFailedMessages:
    @pytest.mark.asyncio
    async def test_no_redis_returns_zero_counts(self):
        svc = WeChatService(redis_client=None)
        result = await svc.retry_failed_messages()
        assert result == {"retried": 0, "succeeded": 0}

    @pytest.mark.asyncio
    async def test_empty_queue_returns_zero_retried(self):
        redis = _make_redis()
        redis.lpop = AsyncMock(return_value=None)
        svc = WeChatService(redis_client=redis)

        result = await svc.retry_failed_messages()
        assert result == {"retried": 0, "succeeded": 0}

    @pytest.mark.asyncio
    async def test_max_retries_exceeded_skips_message(self):
        redis = _make_redis()
        msg = json.dumps({
            "template": "shift_report",
            "data": {},
            "to_user_id": "U1",
            "message_id": "MSG99",
            "retry_count": 3,
        })
        # First lpop returns the message, second returns None to stop the loop
        redis.lpop = AsyncMock(side_effect=[msg.encode(), None])
        svc = WeChatService(redis_client=redis)

        result = await svc.retry_failed_messages(max_retries=3)
        assert result["retried"] == 0
        assert result["succeeded"] == 0

    @pytest.mark.asyncio
    async def test_successful_retry_increments_succeeded(self):
        redis = _make_redis()
        msg = json.dumps({
            "template": "shift_report",
            "data": {"revenue": 500},
            "to_user_id": "U1",
            "message_id": "MSG_OK",
            "retry_count": 0,
        })
        # First lpop returns the message, second returns None to stop the loop
        redis.lpop = AsyncMock(side_effect=[msg.encode(), None])
        svc = WeChatService(redis_client=redis)
        svc.send_templated_message = AsyncMock(return_value={"status": "sent"})

        result = await svc.retry_failed_messages(max_retries=3)
        assert result["succeeded"] == 1


# ===========================================================================
# TestHandleMessage
# ===========================================================================

class TestHandleMessage:
    @pytest.mark.asyncio
    async def test_text_message_calls_process_text(self):
        svc = WeChatService()
        svc._process_text_message = AsyncMock(return_value={"type": "text", "content": "ok"})

        await svc.handle_message({"MsgType": "text", "FromUserName": "U1", "Content": "hello"})

        svc._process_text_message.assert_awaited_once_with("U1", "hello")

    @pytest.mark.asyncio
    async def test_event_subscribe_returns_welcome(self):
        svc = WeChatService()
        result = await svc.handle_message({"MsgType": "event", "Event": "subscribe"})
        assert "欢迎" in result["content"]

    @pytest.mark.asyncio
    async def test_event_unsubscribe_returns_empty(self):
        svc = WeChatService()
        result = await svc.handle_message({"MsgType": "event", "Event": "unsubscribe"})
        assert result == {}

    @pytest.mark.asyncio
    async def test_unknown_msgtype_returns_fallback(self):
        svc = WeChatService()
        result = await svc.handle_message({"MsgType": "image"})
        assert "暂不支持" in result["content"]


# ===========================================================================
# TestGetAccessToken – HTTP path (lines 97-123)
# ===========================================================================

class TestGetAccessTokenHTTP:
    @pytest.mark.asyncio
    async def test_new_token_success_via_httpx(self):
        """Lines 97-123: errcode==0 branch – stores token and returns it."""
        import httpx as _httpx

        svc = WeChatService()
        svc.access_token = None
        svc.token_expire_time = None

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json = MagicMock(
            return_value={"errcode": 0, "access_token": "new-tok", "expires_in": 7200}
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch.object(_httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            result = await svc.get_access_token()

        assert result == "new-tok"
        assert svc.access_token == "new-tok"

    @pytest.mark.asyncio
    async def test_new_token_failure_via_httpx_raises(self):
        """Lines 97-123: errcode!=0 branch – raises Exception."""
        import httpx as _httpx

        svc = WeChatService()
        svc.access_token = None
        svc.token_expire_time = None

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json = MagicMock(
            return_value={"errcode": 40013, "errmsg": "invalid corpid"}
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch.object(_httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            with pytest.raises(Exception, match="获取access_token失败"):
                await svc.get_access_token()


# ===========================================================================
# TestSendTextMessageHTTP – HTTP body (lines 141-172)
# ===========================================================================

class TestSendTextMessageHTTP:
    @pytest.mark.asyncio
    async def test_send_text_success(self):
        """Lines 141-172: errcode==0 → returns result dict."""
        import httpx as _httpx

        svc = WeChatService()
        svc.access_token = "tok"
        svc.token_expire_time = datetime.now() + timedelta(hours=1)

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value={"errcode": 0, "errmsg": "ok"})
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.object(_httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            result = await svc.send_text_message(content="hello", touser="U1")

        assert result["errcode"] == 0

    @pytest.mark.asyncio
    async def test_send_text_failure_raises(self):
        """Lines 141-172: errcode!=0 → raises Exception."""
        import httpx as _httpx

        svc = WeChatService()
        svc.access_token = "tok"
        svc.token_expire_time = datetime.now() + timedelta(hours=1)

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value={"errcode": 60020, "errmsg": "not allow"})
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.object(_httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            with pytest.raises(Exception, match="发送消息失败"):
                await svc.send_text_message(content="hello", touser="U1")

    @pytest.mark.asyncio
    async def test_send_text_outer_exception_reraises(self):
        """Lines 141-172: outer exception propagates."""
        import httpx as _httpx

        svc = WeChatService()
        svc.access_token = "tok"
        svc.token_expire_time = datetime.now() + timedelta(hours=1)

        with patch.object(_httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(side_effect=RuntimeError("network down"))
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            with pytest.raises(RuntimeError, match="network down"):
                await svc.send_text_message(content="hello", touser="U1")


# ===========================================================================
# TestSendMarkdownMessageHTTP – HTTP body (lines 190-220)
# ===========================================================================

class TestSendMarkdownMessageHTTP:
    @pytest.mark.asyncio
    async def test_send_markdown_success(self):
        """Lines 190-220: errcode==0 → returns result."""
        import httpx as _httpx

        svc = WeChatService()
        svc.access_token = "tok"
        svc.token_expire_time = datetime.now() + timedelta(hours=1)

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value={"errcode": 0, "errmsg": "ok"})
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.object(_httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            result = await svc.send_markdown_message(content="**bold**", touser="U1")

        assert result["errcode"] == 0

    @pytest.mark.asyncio
    async def test_send_markdown_failure_raises(self):
        """Lines 190-220: errcode!=0 → raises Exception."""
        import httpx as _httpx

        svc = WeChatService()
        svc.access_token = "tok"
        svc.token_expire_time = datetime.now() + timedelta(hours=1)

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value={"errcode": 60020, "errmsg": "not allow"})
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.object(_httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            with pytest.raises(Exception, match="发送消息失败"):
                await svc.send_markdown_message(content="**bold**", touser="U1")

    @pytest.mark.asyncio
    async def test_send_markdown_outer_exception_reraises(self):
        """Lines 190-220: outer exception propagates."""
        import httpx as _httpx

        svc = WeChatService()
        svc.access_token = "tok"
        svc.token_expire_time = datetime.now() + timedelta(hours=1)

        with patch.object(_httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(side_effect=RuntimeError("net fail"))
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            with pytest.raises(RuntimeError, match="net fail"):
                await svc.send_markdown_message(content="**bold**", touser="U1")


# ===========================================================================
# TestSendCardMessageHTTP – HTTP body (lines 240-273)
# ===========================================================================

class TestSendCardMessageHTTP:
    @pytest.mark.asyncio
    async def test_send_card_success(self):
        """Lines 240-273: errcode==0 → returns result."""
        import httpx as _httpx

        svc = WeChatService()
        svc.access_token = "tok"
        svc.token_expire_time = datetime.now() + timedelta(hours=1)

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value={"errcode": 0, "errmsg": "ok"})
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.object(_httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            result = await svc.send_card_message(title="T", description="D", url="http://x")

        assert result["errcode"] == 0

    @pytest.mark.asyncio
    async def test_send_card_failure_raises(self):
        """Lines 240-273: errcode!=0 → raises Exception."""
        import httpx as _httpx

        svc = WeChatService()
        svc.access_token = "tok"
        svc.token_expire_time = datetime.now() + timedelta(hours=1)

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value={"errcode": 60020, "errmsg": "not allow"})
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.object(_httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            with pytest.raises(Exception, match="发送消息失败"):
                await svc.send_card_message(title="T", description="D", url="http://x")

    @pytest.mark.asyncio
    async def test_send_card_outer_exception_reraises(self):
        """Lines 240-273: outer exception propagates."""
        import httpx as _httpx

        svc = WeChatService()
        svc.access_token = "tok"
        svc.token_expire_time = datetime.now() + timedelta(hours=1)

        with patch.object(_httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(side_effect=RuntimeError("net fail"))
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            with pytest.raises(RuntimeError, match="net fail"):
                await svc.send_card_message(title="T", description="D", url="http://x")


# ===========================================================================
# TestGetUserInfoHTTP – HTTP body (lines 282-302)
# ===========================================================================

class TestGetUserInfoHTTP:
    @pytest.mark.asyncio
    async def test_get_user_info_success(self):
        """Lines 282-302: errcode==0 → returns result."""
        import httpx as _httpx

        svc = WeChatService()
        svc.access_token = "tok"
        svc.token_expire_time = datetime.now() + timedelta(hours=1)

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value={"errcode": 0, "userid": "U1", "name": "Alice"})
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch.object(_httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            result = await svc.get_user_info("U1")

        assert result["userid"] == "U1"

    @pytest.mark.asyncio
    async def test_get_user_info_failure_raises(self):
        """Lines 282-302: errcode!=0 → raises Exception."""
        import httpx as _httpx

        svc = WeChatService()
        svc.access_token = "tok"
        svc.token_expire_time = datetime.now() + timedelta(hours=1)

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value={"errcode": 60111, "errmsg": "invalid userid"})
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch.object(_httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            with pytest.raises(Exception, match="获取用户信息失败"):
                await svc.get_user_info("U1")


# ===========================================================================
# TestGetDepartmentUsersHTTP – HTTP body (lines 311-335)
# ===========================================================================

class TestGetDepartmentUsersHTTP:
    @pytest.mark.asyncio
    async def test_get_department_users_success(self):
        """Lines 311-335: errcode==0 → returns userlist."""
        import httpx as _httpx

        svc = WeChatService()
        svc.access_token = "tok"
        svc.token_expire_time = datetime.now() + timedelta(hours=1)

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json = MagicMock(
            return_value={"errcode": 0, "userlist": [{"userid": "U1"}, {"userid": "U2"}]}
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch.object(_httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            result = await svc.get_department_users(department_id=1)

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_department_users_failure_raises(self):
        """Lines 311-335: errcode!=0 → raises Exception."""
        import httpx as _httpx

        svc = WeChatService()
        svc.access_token = "tok"
        svc.token_expire_time = datetime.now() + timedelta(hours=1)

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value={"errcode": 60003, "errmsg": "dept not found"})
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch.object(_httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            with pytest.raises(Exception, match="获取部门成员列表失败"):
                await svc.get_department_users(department_id=1)


# ===========================================================================
# TestProcessTextMessage – agent found path (lines 364-398)
# ===========================================================================

class TestProcessTextMessageWithAgent:
    @pytest.mark.asyncio
    async def test_agent_found_success_path(self):
        """Lines 364-398: agent_type found → calls AgentService, returns response."""
        mock_mr = MagicMock()
        mock_mr.route_message = MagicMock(return_value=("order", "query", {}))
        mock_mr.format_agent_response = MagicMock(return_value="Agent result")

        mock_agent_cls = MagicMock()
        mock_agent_cls.return_value.execute_agent = AsyncMock(return_value={"data": "ok"})

        svc = WeChatService()
        with patch.dict("sys.modules", {
            "src.services.message_router": MagicMock(message_router=mock_mr),
            "src.services.agent_service": MagicMock(AgentService=mock_agent_cls),
        }):
            result = await svc._process_text_message("U1", "查询订单")

        assert result["type"] == "text"
        assert result["content"] == "Agent result"

    @pytest.mark.asyncio
    async def test_agent_found_exception_path(self):
        """Lines 364-398: agent_type found but execute_agent raises → error response."""
        mock_mr = MagicMock()
        mock_mr.route_message = MagicMock(return_value=("order", "query", {}))

        mock_agent_cls = MagicMock()
        mock_agent_cls.return_value.execute_agent = AsyncMock(
            side_effect=RuntimeError("agent boom")
        )

        svc = WeChatService()
        with patch.dict("sys.modules", {
            "src.services.message_router": MagicMock(message_router=mock_mr),
            "src.services.agent_service": MagicMock(AgentService=mock_agent_cls),
        }):
            result = await svc._process_text_message("U1", "查询订单")

        assert result["type"] == "text"
        assert "agent boom" in result["content"]


# ===========================================================================
# TestProcessEvent – unknown event else branch (line 414)
# ===========================================================================

class TestProcessEventUnknown:
    @pytest.mark.asyncio
    async def test_unknown_event_returns_notification(self):
        """Line 414: else branch → returns '收到事件通知'."""
        svc = WeChatService()
        result = await svc._process_event("click", {})
        assert result["content"] == "收到事件通知"


# ===========================================================================
# TestRetryFailedMessages – retry still fails / inner exception (lines 545-552)
# ===========================================================================

class TestRetryFailedMessagesExtended:
    @pytest.mark.asyncio
    async def test_retry_still_fails_reenqueues(self):
        """Lines 545-552: send_templated_message returns 'failed' → re-enqueue via rpush."""
        redis = _make_redis()
        msg = json.dumps({
            "template": "shift_report",
            "data": {"revenue": 100},
            "to_user_id": "U1",
            "message_id": "MSG_FAIL",
            "retry_count": 0,
        })
        redis.lpop = AsyncMock(side_effect=[msg.encode(), None])
        redis.rpush = AsyncMock(return_value=1)

        svc = WeChatService(redis_client=redis)
        svc.send_templated_message = AsyncMock(return_value={"status": "failed", "error": "still broken"})

        result = await svc.retry_failed_messages(max_retries=3)

        assert result["retried"] == 1
        assert result["succeeded"] == 0
        redis.rpush.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_inner_exception_reenqueues(self):
        """Lines 545-552: send_templated_message raises → inner except re-enqueues."""
        redis = _make_redis()
        msg = json.dumps({
            "template": "shift_report",
            "data": {"revenue": 100},
            "to_user_id": "U1",
            "message_id": "MSG_EX",
            "retry_count": 0,
        })
        redis.lpop = AsyncMock(side_effect=[msg.encode(), None])
        redis.rpush = AsyncMock(return_value=1)

        svc = WeChatService(redis_client=redis)
        svc.send_templated_message = AsyncMock(side_effect=ConnectionError("boom"))

        result = await svc.retry_failed_messages(max_retries=3)

        assert result["retried"] == 1
        redis.rpush.assert_called_once()


# ===========================================================================
# TestIsDuplicate – no redis + exception path (lines 560, 564-565)
# ===========================================================================

class TestIsDuplicate:
    @pytest.mark.asyncio
    async def test_no_redis_returns_false(self):
        """Line 560: _redis is None → returns False immediately."""
        svc = WeChatService(redis_client=None)
        result = await svc._is_duplicate("MSG1")
        assert result is False

    @pytest.mark.asyncio
    async def test_redis_exists_raises_returns_false(self):
        """Lines 564-565: redis.exists raises → except returns False."""
        redis = _make_redis()
        redis.exists = AsyncMock(side_effect=ConnectionError("redis down"))
        svc = WeChatService(redis_client=redis)
        result = await svc._is_duplicate("MSG1")
        assert result is False


# ===========================================================================
# TestMarkSent – no redis + exception path (lines 570, 574-575)
# ===========================================================================

class TestMarkSent:
    @pytest.mark.asyncio
    async def test_no_redis_early_return(self):
        """Line 570: _redis is None → returns without calling set."""
        svc = WeChatService(redis_client=None)
        # Should not raise
        await svc._mark_sent("MSG1")

    @pytest.mark.asyncio
    async def test_redis_set_raises_logs_warning(self):
        """Lines 574-575: redis.set raises → except logs warning (no re-raise)."""
        redis = _make_redis()
        redis.set = AsyncMock(side_effect=OSError("redis down"))
        svc = WeChatService(redis_client=redis)
        # Should not raise
        await svc._mark_sent("MSG1")


# ===========================================================================
# TestEnqueueFailedMessage – no redis + exception path (lines 587, 600-601)
# ===========================================================================

class TestEnqueueFailedMessage:
    @pytest.mark.asyncio
    async def test_no_redis_early_return(self):
        """Line 587: _redis is None → returns without calling rpush."""
        svc = WeChatService(redis_client=None)
        # Should not raise
        await svc._enqueue_failed_message("shift_report", {}, "U1", "MSG1", "err")

    @pytest.mark.asyncio
    async def test_redis_rpush_raises_logs_error(self):
        """Lines 600-601: redis.rpush raises → except logs error (no re-raise)."""
        redis = _make_redis()
        redis.rpush = AsyncMock(side_effect=OSError("redis down"))
        svc = WeChatService(redis_client=redis)
        # Should not raise
        await svc._enqueue_failed_message("shift_report", {}, "U1", "MSG1", "err")


# ===========================================================================
# Additional coverage for missed lines
# ===========================================================================

class TestProcessTextMessageNoAgent:
    @pytest.mark.asyncio
    async def test_no_agent_type_returns_help_text(self):
        """Line 372: agent_type is falsy → returns help message."""
        mock_mr = MagicMock()
        mock_mr.route_message = MagicMock(return_value=(None, None, {}))

        svc = WeChatService()
        with patch.dict("sys.modules", {
            "src.services.message_router": MagicMock(message_router=mock_mr),
            "src.services.agent_service": MagicMock(),
        }):
            result = await svc._process_text_message("U1", "你好")

        assert result["type"] == "text"
        assert "收到您的消息" in result["content"]


class TestRetryFailedMessagesOuterException:
    @pytest.mark.asyncio
    async def test_json_loads_error_breaks_loop(self):
        """Lines 550-552: json.loads fails → outer except logs warning and breaks."""
        redis = _make_redis()
        # Return invalid JSON so json.loads raises
        redis.lpop = AsyncMock(return_value=b"not-valid-json{{{")

        svc = WeChatService(redis_client=redis)
        result = await svc.retry_failed_messages(max_retries=3)

        # Loop should have broken; counts remain at 0
        assert result == {"retried": 0, "succeeded": 0}
