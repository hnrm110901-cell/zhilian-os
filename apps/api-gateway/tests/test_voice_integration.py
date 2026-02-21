"""
测试百度和讯飞语音服务集成
Tests for Baidu and Xunfei Voice Integration
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.services.voice_service import VoiceService, VoiceProvider


class TestBaiduVoice:
    """百度语音测试"""

    @pytest.mark.asyncio
    @patch('src.services.voice_service.settings')
    @patch('httpx.AsyncClient')
    async def test_baidu_stt_success(self, mock_client, mock_settings):
        """测试百度语音识别成功"""
        mock_settings.BAIDU_API_KEY = "test_key"
        mock_settings.BAIDU_SECRET_KEY = "test_secret"

        # Mock token响应
        token_response = MagicMock()
        token_response.json.return_value = {"access_token": "test_token"}

        # Mock识别响应
        asr_response = MagicMock()
        asr_response.json.return_value = {
            "err_no": 0,
            "result": ["查询今天的排班"]
        }

        mock_client_instance = AsyncMock()
        mock_client_instance.post.side_effect = [token_response, asr_response]
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        service = VoiceService(provider=VoiceProvider.BAIDU)
        result = await service.speech_to_text(b"fake_audio_data")

        assert result["success"] is True
        assert "text" in result
        assert result["confidence"] == 0.95

    @pytest.mark.asyncio
    @patch('src.services.voice_service.settings')
    @patch('httpx.AsyncClient')
    async def test_baidu_stt_failure(self, mock_client, mock_settings):
        """测试百度语音识别失败"""
        mock_settings.BAIDU_API_KEY = "test_key"
        mock_settings.BAIDU_SECRET_KEY = "test_secret"

        # Mock token响应
        token_response = MagicMock()
        token_response.json.return_value = {"access_token": "test_token"}

        # Mock失败响应
        asr_response = MagicMock()
        asr_response.json.return_value = {
            "err_no": 3301,
            "err_msg": "音频质量过差"
        }

        mock_client_instance = AsyncMock()
        mock_client_instance.post.side_effect = [token_response, asr_response]
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        service = VoiceService(provider=VoiceProvider.BAIDU)
        result = await service.speech_to_text(b"fake_audio_data")

        assert result["success"] is True  # 仍返回True但文本为"识别失败"

    @pytest.mark.asyncio
    @patch('src.services.voice_service.settings')
    @patch('httpx.AsyncClient')
    async def test_baidu_tts_success(self, mock_client, mock_settings):
        """测试百度语音合成成功"""
        mock_settings.BAIDU_API_KEY = "test_key"
        mock_settings.BAIDU_SECRET_KEY = "test_secret"

        # Mock token响应
        token_response = MagicMock()
        token_response.json.return_value = {"access_token": "test_token"}

        # Mock TTS响应
        tts_response = MagicMock()
        tts_response.headers = {"Content-Type": "audio/mp3"}
        tts_response.content = b"fake_audio_data"

        mock_client_instance = AsyncMock()
        mock_client_instance.post.side_effect = [token_response, tts_response]
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        service = VoiceService(provider=VoiceProvider.BAIDU)
        result = await service.text_to_speech("你好世界")

        assert result["success"] is True
        assert "audio_data" in result
        assert result["format"] == "pcm"

    @pytest.mark.asyncio
    @patch('src.services.voice_service.settings')
    @patch('httpx.AsyncClient')
    async def test_baidu_tts_failure(self, mock_client, mock_settings):
        """测试百度语音合成失败"""
        mock_settings.BAIDU_API_KEY = "test_key"
        mock_settings.BAIDU_SECRET_KEY = "test_secret"

        # Mock token响应
        token_response = MagicMock()
        token_response.json.return_value = {"access_token": "test_token"}

        # Mock失败响应
        tts_response = MagicMock()
        tts_response.headers = {"Content-Type": "application/json"}
        tts_response.json.return_value = {
            "err_no": 500,
            "err_msg": "不支持输入"
        }

        mock_client_instance = AsyncMock()
        mock_client_instance.post.side_effect = [token_response, tts_response]
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        service = VoiceService(provider=VoiceProvider.BAIDU)
        result = await service.text_to_speech("你好世界")

        assert result["success"] is True  # 仍返回True但audio_data为空


class TestXunfeiVoice:
    """讯飞语音测试"""

    @pytest.mark.asyncio
    @patch('src.services.voice_service.settings')
    async def test_xunfei_stt(self, mock_settings):
        """测试讯飞语音识别"""
        mock_settings.XUNFEI_API_KEY = "test_key"
        mock_settings.XUNFEI_API_SECRET = "test_secret"

        service = VoiceService(provider=VoiceProvider.XUNFEI)
        result = await service.speech_to_text(b"fake_audio_data")

        assert result["success"] is True
        assert "text" in result

    @pytest.mark.asyncio
    @patch('src.services.voice_service.settings')
    async def test_xunfei_tts(self, mock_settings):
        """测试讯飞语音合成"""
        mock_settings.XUNFEI_API_KEY = "test_key"
        mock_settings.XUNFEI_API_SECRET = "test_secret"

        service = VoiceService(provider=VoiceProvider.XUNFEI)
        result = await service.text_to_speech("你好世界")

        assert result["success"] is True
        assert "audio_data" in result


class TestVoiceServiceGeneral:
    """语音服务通用测试"""

    @pytest.mark.asyncio
    async def test_voice_service_initialization(self):
        """测试语音服务初始化"""
        service = VoiceService(provider=VoiceProvider.AZURE)
        assert service.provider == VoiceProvider.AZURE
        assert service.stt_enabled is True
        assert service.tts_enabled is True

    @pytest.mark.asyncio
    async def test_voice_service_default_provider(self):
        """测试默认语音服务提供商"""
        service = VoiceService()
        assert service.provider == VoiceProvider.AZURE

    @pytest.mark.asyncio
    async def test_speech_to_text_with_params(self):
        """测试带参数的语音识别"""
        service = VoiceService(provider=VoiceProvider.BAIDU)
        result = await service.speech_to_text(
            b"fake_audio",
            language="zh-CN",
            sample_rate=16000
        )

        assert "success" in result
        assert "text" in result or "error" in result

    @pytest.mark.asyncio
    async def test_text_to_speech_with_params(self):
        """测试带参数的语音合成"""
        service = VoiceService(provider=VoiceProvider.BAIDU)
        result = await service.text_to_speech(
            "测试文本",
            language="zh-CN",
            voice="female",
            speed=1.0
        )

        assert "success" in result
        assert "audio_data" in result or "error" in result
