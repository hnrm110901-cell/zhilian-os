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
        svc.send_text_message = AsyncMock(side_effect=RuntimeError("net"))

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
