"""
Unit tests for VoiceService and VoiceCommandRouter.
"""
import sys
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

sys.modules.setdefault("src.services.agent_service", MagicMock())
sys.modules.setdefault("src.services.message_router", MagicMock())

from src.services.voice_service import VoiceService, VoiceCommandRouter, VoiceProvider


# ---------------------------------------------------------------------------
# TestVoiceServiceSpeechToText
# ---------------------------------------------------------------------------

class TestVoiceServiceSpeechToText:

    @pytest.mark.asyncio
    async def test_unsupported_provider_returns_empty_text(self):
        svc = VoiceService(VoiceProvider.GOOGLE)
        result = await svc.speech_to_text(b"audio")
        assert result["success"] is True
        assert result["text"] == ""

    @pytest.mark.asyncio
    async def test_unsupported_provider_has_language_in_result(self):
        svc = VoiceService(VoiceProvider.GOOGLE)
        result = await svc.speech_to_text(b"audio")
        assert result["language"] == "zh-CN"

    @pytest.mark.asyncio
    async def test_azure_provider_calls_azure_stt(self):
        svc = VoiceService(VoiceProvider.AZURE)
        svc._azure_stt = AsyncMock(return_value="你好")
        result = await svc.speech_to_text(b"audio")
        assert result["text"] == "你好"
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_baidu_provider_calls_baidu_stt(self):
        svc = VoiceService(VoiceProvider.BAIDU)
        svc._baidu_stt = AsyncMock(return_value="你好百度")
        result = await svc.speech_to_text(b"audio")
        assert result["text"] == "你好百度"
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_exception_returns_success_false(self):
        svc = VoiceService(VoiceProvider.AZURE)
        svc._azure_stt = AsyncMock(side_effect=RuntimeError("network error"))
        result = await svc.speech_to_text(b"audio")
        assert result["success"] is False
        assert "error" in result


# ---------------------------------------------------------------------------
# TestVoiceServiceTextToSpeech
# ---------------------------------------------------------------------------

class TestVoiceServiceTextToSpeech:

    @pytest.mark.asyncio
    async def test_unsupported_provider_returns_empty_audio(self):
        svc = VoiceService(VoiceProvider.GOOGLE)
        result = await svc.text_to_speech("你好")
        assert result["success"] is True
        assert result["audio_data"] == b""

    @pytest.mark.asyncio
    async def test_unsupported_provider_has_format_field(self):
        svc = VoiceService(VoiceProvider.GOOGLE)
        result = await svc.text_to_speech("你好")
        assert result["format"] == "pcm"

    @pytest.mark.asyncio
    async def test_azure_provider_calls_azure_tts(self):
        svc = VoiceService(VoiceProvider.AZURE)
        svc._azure_tts = AsyncMock(return_value=b"audio_bytes")
        result = await svc.text_to_speech("你好")
        assert result["audio_data"] == b"audio_bytes"

    @pytest.mark.asyncio
    async def test_exception_returns_success_false(self):
        svc = VoiceService(VoiceProvider.AZURE)
        svc._azure_tts = AsyncMock(side_effect=RuntimeError("tts failed"))
        result = await svc.text_to_speech("你好")
        assert result["success"] is False


# ---------------------------------------------------------------------------
# TestVoiceCommandRouter
# ---------------------------------------------------------------------------

class TestVoiceCommandRouter:

    def setup_method(self):
        """Reset the message_router mock before each test."""
        from src.services import message_router as mr_module
        mr_module.message_router.route_message.return_value = (None, None, {})

    def test_kitchen_role_with_订单_routes_to_order(self):
        from src.services import message_router as mr_module
        mr_module.message_router.route_message.return_value = (None, None, {})
        router = VoiceCommandRouter()
        result = router.route_command("查询订单状态", "kitchen", "U1")
        assert result["agent_type"] == "order"
        assert result["action"] == "query_order"

    def test_kitchen_role_with_库存_routes_to_inventory(self):
        from src.services import message_router as mr_module
        mr_module.message_router.route_message.return_value = (None, None, {})
        router = VoiceCommandRouter()
        result = router.route_command("查一下库存", "kitchen", "U1")
        assert result["agent_type"] == "inventory"
        assert result["action"] == "query_inventory"

    def test_front_of_house_with_点单_routes_to_order_create(self):
        from src.services import message_router as mr_module
        mr_module.message_router.route_message.return_value = (None, None, {})
        router = VoiceCommandRouter()
        result = router.route_command("点单", "front_of_house", "U1")
        assert result["agent_type"] == "order"
        assert result["action"] == "create_order"

    def test_front_of_house_with_预定_routes_to_reservation(self):
        from src.services import message_router as mr_module
        mr_module.message_router.route_message.return_value = (None, None, {})
        router = VoiceCommandRouter()
        result = router.route_command("预定一桌", "front_of_house", "U1")
        assert result["agent_type"] == "reservation"
        assert result["action"] == "query_reservation"

    def test_front_of_house_with_结账_routes_to_checkout(self):
        from src.services import message_router as mr_module
        mr_module.message_router.route_message.return_value = (None, None, {})
        router = VoiceCommandRouter()
        result = router.route_command("结账", "front_of_house", "U1")
        assert result["agent_type"] == "order"
        assert result["action"] == "checkout"

    def test_cashier_role_with_结账_routes_to_checkout(self):
        from src.services import message_router as mr_module
        mr_module.message_router.route_message.return_value = (None, None, {})
        router = VoiceCommandRouter()
        result = router.route_command("买单", "cashier", "U1")
        assert result["agent_type"] == "order"
        assert result["action"] == "checkout"

    def test_message_router_result_passthrough(self):
        from src.services import message_router as mr_module
        mr_module.message_router.route_message.return_value = (
            "schedule", "query_schedule", {"date": "today"}
        )
        router = VoiceCommandRouter()
        result = router.route_command("排班查询", "kitchen", "U1")
        assert result["agent_type"] == "schedule"
        assert result["params"] == {"date": "today"}

    def test_unknown_role_unrecognized_text_returns_none_agent(self):
        from src.services import message_router as mr_module
        mr_module.message_router.route_message.return_value = (None, None, {})
        router = VoiceCommandRouter()
        result = router.route_command("随便", "stranger", "U1")
        assert result["agent_type"] is None
