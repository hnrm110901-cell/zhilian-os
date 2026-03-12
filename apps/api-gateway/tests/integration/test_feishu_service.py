"""
Unit tests for FeishuService message handling.
"""
import hashlib
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest


mock_settings = MagicMock()
mock_settings.FEISHU_APP_ID = "test_app_id"
mock_settings.FEISHU_APP_SECRET = "test_app_secret"
mock_config = MagicMock()
mock_config.settings = mock_settings
sys.modules["src.core.config"] = mock_config

from src.services.feishu_service import FeishuService


class TestHandleMessage:
    @pytest.mark.asyncio
    async def test_text_event_auto_replies_to_user(self):
        svc = FeishuService()
        svc._process_text_message = AsyncMock(
            return_value={"type": "text", "content": "已为您处理"}
        )
        svc.send_text_message = AsyncMock(return_value={"code": 0, "data": {"message_id": "m1"}})

        result = await svc.handle_message(
            {
                "header": {"event_type": "im.message.receive_v1"},
                "event": {
                    "sender": {"sender_id": {"user_id": "ou_123"}},
                    "message": {
                        "message_type": "text",
                        "content": "{\"text\":\"查询今日营收\"}",
                    },
                },
            }
        )

        assert result["handled"] is True
        assert result["reply_sent"] is True
        svc._process_text_message.assert_awaited_once_with("ou_123", "查询今日营收")
        svc.send_text_message.assert_awaited_once_with(
            content="已为您处理",
            receive_id="ou_123",
            receive_id_type="user_id",
        )

    @pytest.mark.asyncio
    async def test_text_event_without_target_does_not_send_reply(self):
        svc = FeishuService()
        svc._process_text_message = AsyncMock(
            return_value={"type": "text", "content": "已为您处理"}
        )
        svc.send_text_message = AsyncMock()

        result = await svc.handle_message(
            {
                "header": {"event_type": "im.message.receive_v1"},
                "event": {
                    "sender": {"sender_id": {}},
                    "message": {
                        "message_type": "text",
                        "content": "{\"text\":\"查询今日营收\"}",
                    },
                },
            }
        )

        assert result["handled"] is True
        assert result["reply_sent"] is False
        svc.send_text_message.assert_not_awaited()


class TestWebhookGuards:
    def test_validate_callback_token_matches_configured_token(self):
        svc = FeishuService()

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("src.services.feishu_service.settings.FEISHU_VERIFICATION_TOKEN", "token-123")
            assert svc.validate_callback_token({"header": {"token": "token-123"}}) is True
            assert svc.validate_callback_token({"token": "bad-token"}) is False

    def test_supported_event_type_whitelist(self):
        svc = FeishuService()

        assert svc.is_supported_event_type({"type": "url_verification"}) is True
        assert svc.is_supported_event_type(
            {"header": {"event_type": "im.message.receive_v1"}}
        ) is True
        assert svc.is_supported_event_type(
            {"header": {"event_type": "contact.user.created_v3"}}
        ) is False

    def test_validate_signature_with_encrypt_key(self):
        svc = FeishuService()
        raw_body = b'{"type":"url_verification"}'
        timestamp = "1700000000"
        nonce = "nonce-1"

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("src.services.feishu_service.settings.FEISHU_ENCRYPT_KEY", "encrypt-key")
            signature = hashlib.sha256(
                timestamp.encode("utf-8")
                + nonce.encode("utf-8")
                + b"encrypt-key"
                + raw_body
            ).hexdigest()

            assert svc.validate_signature(raw_body, timestamp, nonce, signature) is True
            assert svc.validate_signature(raw_body, timestamp, nonce, "bad-signature") is False

    @pytest.mark.asyncio
    async def test_mark_and_detect_duplicate_event(self):
        svc = FeishuService()
        fake_cache = MagicMock()
        fake_cache.exists = AsyncMock(side_effect=[False, True])
        fake_cache.set = AsyncMock(return_value=True)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("src.services.feishu_service.redis_cache", fake_cache)
            assert await svc.is_duplicate_event("evt_1") is False
            assert await svc.mark_event_processed("evt_1") is True
            assert await svc.is_duplicate_event("evt_1") is True
