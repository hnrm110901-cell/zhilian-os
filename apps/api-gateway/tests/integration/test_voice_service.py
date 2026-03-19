"""
Unit tests for VoiceService and VoiceCommandRouter.
"""
import sys
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

sys.modules.setdefault("src.services.agent_service", MagicMock())
sys.modules.setdefault("src.services.message_router", MagicMock())
# Config stub: methods import settings lazily; stub prevents Settings() from running
sys.modules.setdefault("src.core.config", MagicMock(settings=MagicMock(
    AZURE_SPEECH_KEY="test-key",
    AZURE_SPEECH_REGION="eastasia",
    BAIDU_API_KEY="ak",
    BAIDU_SECRET_KEY="sk",
)))

from src.services.voice_service import VoiceService, VoiceCommandRouter, VoiceProvider


# ---------------------------------------------------------------------------
# TestVoiceServiceSpeechToText
# ---------------------------------------------------------------------------

class TestVoiceServiceSpeechToText:

    @pytest.mark.asyncio
    async def test_unsupported_provider_returns_mock_text(self):
        svc = VoiceService(VoiceProvider.GOOGLE)
        result = await svc.speech_to_text(b"audio")
        assert result["success"] is True
        assert result["text"] == "模拟识别结果"

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

    def _make_mock_router(self, return_value=(None, None, {})):
        mock_mr = MagicMock()
        mock_mr.route_message.return_value = return_value
        return mock_mr

    def test_kitchen_role_with_订单_routes_to_order(self):
        mock_mr = self._make_mock_router()
        with patch("src.services.voice_service.message_router", mock_mr, create=True), \
             patch("src.services.message_router.message_router", mock_mr, create=True):
            router = VoiceCommandRouter()
            result = router.route_command("查询订单状态", "kitchen", "U1")
        assert result["agent_type"] == "order"
        assert result["action"] == "query_order"

    def test_kitchen_role_with_库存_routes_to_inventory(self):
        mock_mr = self._make_mock_router()
        with patch("src.services.voice_service.message_router", mock_mr, create=True), \
             patch("src.services.message_router.message_router", mock_mr, create=True):
            router = VoiceCommandRouter()
            result = router.route_command("查一下库存", "kitchen", "U1")
        assert result["agent_type"] == "inventory"
        assert result["action"] == "query_inventory"

    def test_front_of_house_with_点单_routes_to_order_create(self):
        mock_mr = self._make_mock_router()
        with patch("src.services.voice_service.message_router", mock_mr, create=True), \
             patch("src.services.message_router.message_router", mock_mr, create=True):
            router = VoiceCommandRouter()
            result = router.route_command("点单", "front_of_house", "U1")
        assert result["agent_type"] == "order"
        assert result["action"] == "create_order"

    def test_front_of_house_with_预定_routes_to_reservation(self):
        mock_mr = self._make_mock_router()
        with patch("src.services.voice_service.message_router", mock_mr, create=True), \
             patch("src.services.message_router.message_router", mock_mr, create=True):
            router = VoiceCommandRouter()
            result = router.route_command("预定一桌", "front_of_house", "U1")
        assert result["agent_type"] == "reservation"
        assert result["action"] == "query_reservation"

    def test_front_of_house_with_结账_routes_to_checkout(self):
        mock_mr = self._make_mock_router()
        with patch("src.services.voice_service.message_router", mock_mr, create=True), \
             patch("src.services.message_router.message_router", mock_mr, create=True):
            router = VoiceCommandRouter()
            result = router.route_command("结账", "front_of_house", "U1")
        assert result["agent_type"] == "order"
        assert result["action"] == "checkout"

    def test_cashier_role_with_结账_routes_to_checkout(self):
        mock_mr = self._make_mock_router()
        with patch("src.services.voice_service.message_router", mock_mr, create=True), \
             patch("src.services.message_router.message_router", mock_mr, create=True):
            router = VoiceCommandRouter()
            result = router.route_command("买单", "cashier", "U1")
        assert result["agent_type"] == "order"
        assert result["action"] == "checkout"

    def test_message_router_result_passthrough(self):
        mock_mr = self._make_mock_router(("schedule", "query_schedule", {"date": "today"}))
        with patch("src.services.voice_service.message_router", mock_mr, create=True), \
             patch("src.services.message_router.message_router", mock_mr, create=True):
            router = VoiceCommandRouter()
            result = router.route_command("排班查询", "kitchen", "U1")
        assert result["agent_type"] == "schedule"
        assert result["params"] == {"date": "today"}

    def test_unknown_role_unrecognized_text_returns_none_agent(self):
        mock_mr = self._make_mock_router()
        with patch("src.services.voice_service.message_router", mock_mr, create=True), \
             patch("src.services.message_router.message_router", mock_mr, create=True):
            router = VoiceCommandRouter()
            result = router.route_command("随便", "stranger", "U1")
        assert result["agent_type"] is None


# ---------------------------------------------------------------------------
# TestVoiceServiceBaiduXunfei — additional TTS/STT provider coverage
# ---------------------------------------------------------------------------

class TestVoiceServiceBaiduTTS:
    @pytest.mark.asyncio
    async def test_baidu_provider_calls_baidu_tts(self):
        svc = VoiceService(VoiceProvider.BAIDU)
        svc._baidu_tts = AsyncMock(return_value=b"baidu_audio")
        result = await svc.text_to_speech("你好")
        assert result["success"] is True
        assert result["audio_data"] == b"baidu_audio"

    @pytest.mark.asyncio
    async def test_xunfei_provider_calls_xunfei_tts(self):
        svc = VoiceService(VoiceProvider.XUNFEI)
        svc._xunfei_tts = AsyncMock(return_value=b"xunfei_audio")
        result = await svc.text_to_speech("你好")
        assert result["success"] is True
        assert result["audio_data"] == b"xunfei_audio"

    @pytest.mark.asyncio
    async def test_xunfei_provider_stt(self):
        svc = VoiceService(VoiceProvider.XUNFEI)
        svc._xunfei_stt = AsyncMock(return_value="讯飞识别结果")
        result = await svc.speech_to_text(b"audio")
        assert result["success"] is True
        assert result["text"] == "讯飞识别结果"


class TestAzureSTTInternal:
    """Test _azure_stt private method with httpx mocked."""

    def _mock_settings(self, **overrides):
        """Create a mock settings with Azure keys configured."""
        defaults = {
            "AZURE_SPEECH_KEY": "test-key",
            "AZURE_SPEECH_REGION": "eastasia",
            "BAIDU_API_KEY": "ak",
            "BAIDU_SECRET_KEY": "sk",
        }
        defaults.update(overrides)
        return MagicMock(**defaults)

    @pytest.mark.asyncio
    async def test_azure_stt_no_key_returns_mock_result(self):
        svc = VoiceService(VoiceProvider.AZURE)
        mock_s = self._mock_settings(AZURE_SPEECH_KEY="")
        with patch("src.services.voice_service.settings", mock_s, create=True), \
             patch("src.core.config.settings", mock_s):
            text = await svc._azure_stt(b"audio", "zh-CN", 16000)
        assert text == "模拟识别结果"

    @pytest.mark.asyncio
    async def test_azure_stt_success(self):
        svc = VoiceService(VoiceProvider.AZURE)
        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value={
            "RecognitionStatus": "Success",
            "DisplayText": "订单状态",
        })
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_s = self._mock_settings()
        import httpx
        with patch("src.core.config.settings", mock_s), \
             patch.object(httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            text = await svc._azure_stt(b"audio", "zh-CN", 16000)
        assert text == "订单状态"

    @pytest.mark.asyncio
    async def test_azure_stt_non_success_status(self):
        svc = VoiceService(VoiceProvider.AZURE)
        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value={"RecognitionStatus": "NoMatch"})
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_s = self._mock_settings()
        import httpx
        with patch("src.core.config.settings", mock_s), \
             patch.object(httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            text = await svc._azure_stt(b"audio", "zh-CN", 16000)
        assert text == "识别失败"

    @pytest.mark.asyncio
    async def test_azure_stt_exception_returns_failure(self):
        svc = VoiceService(VoiceProvider.AZURE)
        mock_s = self._mock_settings()
        import httpx
        with patch("src.core.config.settings", mock_s), \
             patch.object(httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(side_effect=RuntimeError("network"))
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            text = await svc._azure_stt(b"audio", "zh-CN", 16000)
        assert text == "识别失败"


class TestAzureTTSInternal:

    def _mock_settings(self, **overrides):
        defaults = {
            "AZURE_SPEECH_KEY": "test-key",
            "AZURE_SPEECH_REGION": "eastasia",
        }
        defaults.update(overrides)
        return MagicMock(**defaults)

    @pytest.mark.asyncio
    async def test_azure_tts_no_key_returns_empty(self):
        svc = VoiceService(VoiceProvider.AZURE)
        mock_s = self._mock_settings(AZURE_SPEECH_KEY="")
        with patch("src.core.config.settings", mock_s):
            audio = await svc._azure_tts("你好", "zh-CN", "female", 1.0)
        assert audio == b""

    @pytest.mark.asyncio
    async def test_azure_tts_success(self):
        svc = VoiceService(VoiceProvider.AZURE)
        mock_token_resp = MagicMock()
        mock_token_resp.text = "test-access-token"
        mock_tts_resp = MagicMock()
        mock_tts_resp.status_code = 200
        mock_tts_resp.content = b"audio_bytes"
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=[mock_token_resp, mock_tts_resp])
        mock_s = self._mock_settings()
        import httpx
        with patch("src.core.config.settings", mock_s), \
             patch.object(httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            audio = await svc._azure_tts("你好", "zh-CN", "female", 1.0)
        assert audio == b"audio_bytes"

    @pytest.mark.asyncio
    async def test_azure_tts_non_200_returns_empty(self):
        svc = VoiceService(VoiceProvider.AZURE)
        mock_token_resp = MagicMock()
        mock_token_resp.text = "tok"
        mock_tts_resp = MagicMock()
        mock_tts_resp.status_code = 400
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=[mock_token_resp, mock_tts_resp])
        import httpx
        with patch.object(httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            audio = await svc._azure_tts("你好", "zh-CN", "male", 1.5)
        assert audio == b""

    @pytest.mark.asyncio
    async def test_azure_tts_exception_returns_empty(self):
        svc = VoiceService(VoiceProvider.AZURE)
        import httpx
        with patch.object(httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(side_effect=RuntimeError("net"))
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            audio = await svc._azure_tts("你好", "zh-CN", "female", 1.0)
        assert audio == b""


class TestBaiduSTTInternal:

    def _mock_settings(self):
        return MagicMock(BAIDU_API_KEY="ak", BAIDU_SECRET_KEY="sk")

    @pytest.mark.asyncio
    async def test_baidu_stt_success(self):
        svc = VoiceService(VoiceProvider.BAIDU)
        mock_token_resp = MagicMock()
        mock_token_resp.json = MagicMock(return_value={"access_token": "tok"})
        mock_asr_resp = MagicMock()
        mock_asr_resp.json = MagicMock(return_value={"err_no": 0, "result": ["你好"]})
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=[mock_token_resp, mock_asr_resp])
        mock_s = self._mock_settings()
        import httpx
        with patch("src.core.config.settings", mock_s), \
             patch.object(httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            text = await svc._baidu_stt(b"audio", "zh-CN", 16000)
        assert text == "你好"

    @pytest.mark.asyncio
    async def test_baidu_stt_no_token_returns_failure(self):
        svc = VoiceService(VoiceProvider.BAIDU)
        mock_token_resp = MagicMock()
        mock_token_resp.json = MagicMock(return_value={})  # no access_token
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_token_resp)
        mock_s = self._mock_settings()
        import httpx
        with patch("src.core.config.settings", mock_s), \
             patch.object(httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            text = await svc._baidu_stt(b"audio", "zh-CN", 16000)
        assert text == "识别失败"

    @pytest.mark.asyncio
    async def test_baidu_stt_asr_error(self):
        svc = VoiceService(VoiceProvider.BAIDU)
        mock_token_resp = MagicMock()
        mock_token_resp.json = MagicMock(return_value={"access_token": "tok"})
        mock_asr_resp = MagicMock()
        mock_asr_resp.json = MagicMock(return_value={"err_no": 3303, "err_msg": "limit exceeded"})
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=[mock_token_resp, mock_asr_resp])
        mock_s = self._mock_settings()
        import httpx
        with patch("src.core.config.settings", mock_s), \
             patch.object(httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            text = await svc._baidu_stt(b"audio", "zh-CN", 16000)
        assert text == "识别失败"


class TestBaiduTTSInternal:

    def _mock_settings(self):
        return MagicMock(BAIDU_API_KEY="ak", BAIDU_SECRET_KEY="sk")

    @pytest.mark.asyncio
    async def test_baidu_tts_no_token_returns_empty(self):
        """Baidu TTS: token response has no access_token → raises inside try → caught → b''."""
        svc = VoiceService(VoiceProvider.BAIDU)
        mock_token_resp = MagicMock()
        mock_token_resp.json = MagicMock(return_value={})  # no access_token
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_token_resp)
        mock_s = self._mock_settings()
        import httpx
        with patch("src.core.config.settings", mock_s), \
             patch.object(httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            audio = await svc._baidu_tts("你好", "zh-CN", "female", 1.0)
        assert audio == b""

    @pytest.mark.asyncio
    async def test_baidu_tts_audio_response(self):
        svc = VoiceService(VoiceProvider.BAIDU)
        mock_token_resp = MagicMock()
        mock_token_resp.json = MagicMock(return_value={"access_token": "tok"})
        mock_tts_resp = MagicMock()
        mock_tts_resp.headers = {"Content-Type": "audio/mp3"}
        mock_tts_resp.content = b"audio_data"
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=[mock_token_resp, mock_tts_resp])
        mock_s = self._mock_settings()
        import httpx
        with patch("src.core.config.settings", mock_s), \
             patch.object(httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            audio = await svc._baidu_tts("你好", "zh-CN", "female", 1.0)
        assert audio == b"audio_data"

    @pytest.mark.asyncio
    async def test_baidu_tts_error_response_returns_empty(self):
        svc = VoiceService(VoiceProvider.BAIDU)
        mock_token_resp = MagicMock()
        mock_token_resp.json = MagicMock(return_value={"access_token": "tok"})
        mock_tts_resp = MagicMock()
        mock_tts_resp.headers = {"Content-Type": "application/json"}
        mock_tts_resp.json = MagicMock(return_value={"err_no": 500})
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=[mock_token_resp, mock_tts_resp])
        import httpx
        with patch.object(httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            audio = await svc._baidu_tts("你好", "zh-CN", "male", 1.0)
        assert audio == b""


class TestXunfeiInternal:
    @pytest.mark.asyncio
    async def test_xunfei_stt_delegates_to_iflytek(self):
        svc = VoiceService(VoiceProvider.XUNFEI)
        mock_iflytek = AsyncMock()
        mock_iflytek.speech_to_text = AsyncMock(return_value="讯飞文字")
        with patch.dict("sys.modules", {
            "src.services.iflytek_websocket_service": MagicMock(
                iflytek_ws_service=mock_iflytek
            )
        }):
            text = await svc._xunfei_stt(b"audio", "zh-CN", 16000)
        assert text == "讯飞文字"
        mock_iflytek.speech_to_text.assert_awaited_once_with(
            audio_data=b"audio",
            language="zh_cn",
            sample_rate=16000,
        )

    @pytest.mark.asyncio
    async def test_xunfei_tts_delegates_to_iflytek(self):
        svc = VoiceService(VoiceProvider.XUNFEI)
        mock_iflytek = AsyncMock()
        mock_iflytek.text_to_speech = AsyncMock(return_value=b"xunfei_bytes")
        with patch.dict("sys.modules", {
            "src.services.iflytek_websocket_service": MagicMock(
                iflytek_ws_service=mock_iflytek
            )
        }):
            audio = await svc._xunfei_tts("你好", "zh-CN", "female", 1.0)
        assert audio == b"xunfei_bytes"
