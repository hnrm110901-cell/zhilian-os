"""
语音交互服务测试
Tests for Voice Interaction Service
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.services.voice_service import (
    VoiceService,
    VoiceProvider,
    VoiceCommandRouter,
    voice_service,
    voice_command_router,
)


class TestVoiceService:
    """VoiceService测试类"""

    def test_init_default_provider(self):
        """测试默认提供商初始化"""
        service = VoiceService()
        assert service.provider == VoiceProvider.AZURE
        assert service.stt_enabled is True
        assert service.tts_enabled is True

    def test_init_custom_provider(self):
        """测试自定义提供商初始化"""
        service = VoiceService(provider=VoiceProvider.BAIDU)
        assert service.provider == VoiceProvider.BAIDU
        assert service.stt_enabled is True
        assert service.tts_enabled is True

    @pytest.mark.asyncio
    async def test_speech_to_text_azure_success(self):
        """测试Azure语音识别成功"""
        service = VoiceService(provider=VoiceProvider.AZURE)
        audio_data = b"fake_audio_data"

        with patch.object(service, '_azure_stt', new_callable=AsyncMock) as mock_stt:
            mock_stt.return_value = "测试文本"

            result = await service.speech_to_text(audio_data)

            assert result["success"] is True
            assert result["text"] == "测试文本"
            assert result["language"] == "zh-CN"
            assert result["confidence"] == 0.95
            mock_stt.assert_called_once_with(audio_data, "zh-CN", 16000)

    @pytest.mark.asyncio
    async def test_speech_to_text_baidu_success(self):
        """测试百度语音识别成功"""
        service = VoiceService(provider=VoiceProvider.BAIDU)
        audio_data = b"fake_audio_data"

        with patch.object(service, '_baidu_stt', new_callable=AsyncMock) as mock_stt:
            mock_stt.return_value = "百度识别结果"

            result = await service.speech_to_text(audio_data, language="zh-CN", sample_rate=16000)

            assert result["success"] is True
            assert result["text"] == "百度识别结果"
            assert result["language"] == "zh-CN"
            mock_stt.assert_called_once_with(audio_data, "zh-CN", 16000)

    @pytest.mark.asyncio
    async def test_speech_to_text_xunfei_success(self):
        """测试讯飞语音识别成功"""
        service = VoiceService(provider=VoiceProvider.XUNFEI)
        audio_data = b"fake_audio_data"

        with patch.object(service, '_xunfei_stt', new_callable=AsyncMock) as mock_stt:
            mock_stt.return_value = "讯飞识别结果"

            result = await service.speech_to_text(audio_data)

            assert result["success"] is True
            assert result["text"] == "讯飞识别结果"
            mock_stt.assert_called_once()

    @pytest.mark.asyncio
    async def test_speech_to_text_default_provider(self):
        """测试默认提供商语音识别"""
        service = VoiceService(provider=VoiceProvider.GOOGLE)
        audio_data = b"fake_audio_data"

        result = await service.speech_to_text(audio_data)

        assert result["success"] is True
        assert result["text"] == "查询今天的排班"
        assert result["language"] == "zh-CN"

    @pytest.mark.asyncio
    async def test_speech_to_text_custom_language(self):
        """测试自定义语言语音识别"""
        service = VoiceService(provider=VoiceProvider.AZURE)
        audio_data = b"fake_audio_data"

        with patch.object(service, '_azure_stt', new_callable=AsyncMock) as mock_stt:
            mock_stt.return_value = "English text"

            result = await service.speech_to_text(audio_data, language="en-US", sample_rate=48000)

            assert result["success"] is True
            assert result["language"] == "en-US"
            mock_stt.assert_called_once_with(audio_data, "en-US", 48000)

    @pytest.mark.asyncio
    async def test_speech_to_text_error(self):
        """测试语音识别失败"""
        service = VoiceService(provider=VoiceProvider.AZURE)
        audio_data = b"fake_audio_data"

        with patch.object(service, '_azure_stt', new_callable=AsyncMock) as mock_stt:
            mock_stt.side_effect = Exception("API调用失败")

            result = await service.speech_to_text(audio_data)

            assert result["success"] is False
            assert "API调用失败" in result["error"]

    @pytest.mark.asyncio
    async def test_text_to_speech_azure_success(self):
        """测试Azure语音合成成功"""
        service = VoiceService(provider=VoiceProvider.AZURE)
        text = "你好，欢迎光临"

        with patch.object(service, '_azure_tts', new_callable=AsyncMock) as mock_tts:
            mock_tts.return_value = b"fake_audio_data"

            result = await service.text_to_speech(text)

            assert result["success"] is True
            assert result["audio_data"] == b"fake_audio_data"
            assert result["format"] == "pcm"
            assert result["sample_rate"] == 16000
            assert result["duration"] == len(text) * 0.3
            mock_tts.assert_called_once_with(text, "zh-CN", "female", 1.0)

    @pytest.mark.asyncio
    async def test_text_to_speech_baidu_success(self):
        """测试百度语音合成成功"""
        service = VoiceService(provider=VoiceProvider.BAIDU)
        text = "测试文本"

        with patch.object(service, '_baidu_tts', new_callable=AsyncMock) as mock_tts:
            mock_tts.return_value = b"baidu_audio"

            result = await service.text_to_speech(text, voice="male", speed=1.5)

            assert result["success"] is True
            assert result["audio_data"] == b"baidu_audio"
            mock_tts.assert_called_once_with(text, "zh-CN", "male", 1.5)

    @pytest.mark.asyncio
    async def test_text_to_speech_xunfei_success(self):
        """测试讯飞语音合成成功"""
        service = VoiceService(provider=VoiceProvider.XUNFEI)
        text = "讯飞测试"

        with patch.object(service, '_xunfei_tts', new_callable=AsyncMock) as mock_tts:
            mock_tts.return_value = b"xunfei_audio"

            result = await service.text_to_speech(text)

            assert result["success"] is True
            assert result["audio_data"] == b"xunfei_audio"
            mock_tts.assert_called_once()

    @pytest.mark.asyncio
    async def test_text_to_speech_default_provider(self):
        """测试默认提供商语音合成"""
        service = VoiceService(provider=VoiceProvider.ALIYUN)
        text = "阿里云测试"

        result = await service.text_to_speech(text)

        assert result["success"] is True
        assert result["audio_data"] == b""
        assert result["format"] == "pcm"

    @pytest.mark.asyncio
    async def test_text_to_speech_custom_params(self):
        """测试自定义参数语音合成"""
        service = VoiceService(provider=VoiceProvider.AZURE)
        text = "Custom parameters test"

        with patch.object(service, '_azure_tts', new_callable=AsyncMock) as mock_tts:
            mock_tts.return_value = b"custom_audio"

            result = await service.text_to_speech(
                text,
                language="en-US",
                voice="male",
                speed=0.8
            )

            assert result["success"] is True
            mock_tts.assert_called_once_with(text, "en-US", "male", 0.8)

    @pytest.mark.asyncio
    async def test_text_to_speech_error(self):
        """测试语音合成失败"""
        service = VoiceService(provider=VoiceProvider.AZURE)
        text = "测试文本"

        with patch.object(service, '_azure_tts', new_callable=AsyncMock) as mock_tts:
            mock_tts.side_effect = Exception("合成失败")

            result = await service.text_to_speech(text)

            assert result["success"] is False
            assert "合成失败" in result["error"]

    @pytest.mark.asyncio
    async def test_azure_stt_returns_mock(self):
        """测试Azure STT返回模拟结果"""
        service = VoiceService(provider=VoiceProvider.AZURE)
        result = await service._azure_stt(b"audio", "zh-CN", 16000)
        assert result == "模拟识别结果"

    @pytest.mark.asyncio
    async def test_azure_tts_returns_empty(self):
        """测试Azure TTS返回空数据"""
        service = VoiceService(provider=VoiceProvider.AZURE)
        result = await service._azure_tts("text", "zh-CN", "female", 1.0)
        assert result == b""

    @pytest.mark.asyncio
    async def test_baidu_stt_returns_mock(self):
        """测试百度STT返回模拟结果"""
        service = VoiceService(provider=VoiceProvider.BAIDU)
        result = await service._baidu_stt(b"audio", "zh-CN", 16000)
        assert result == "模拟识别结果"

    @pytest.mark.asyncio
    async def test_baidu_tts_returns_empty(self):
        """测试百度TTS返回空数据"""
        service = VoiceService(provider=VoiceProvider.BAIDU)
        result = await service._baidu_tts("text", "zh-CN", "female", 1.0)
        assert result == b""

    @pytest.mark.asyncio
    async def test_xunfei_stt_returns_mock(self):
        """测试讯飞STT返回模拟结果"""
        service = VoiceService(provider=VoiceProvider.XUNFEI)
        result = await service._xunfei_stt(b"audio", "zh-CN", 16000)
        assert result == "模拟识别结果"

    @pytest.mark.asyncio
    async def test_xunfei_tts_returns_empty(self):
        """测试讯飞TTS返回空数据"""
        service = VoiceService(provider=VoiceProvider.XUNFEI)
        result = await service._xunfei_tts("text", "zh-CN", "female", 1.0)
        assert result == b""


class TestVoiceCommandRouter:
    """VoiceCommandRouter测试类"""

    def test_init(self):
        """测试初始化"""
        router = VoiceCommandRouter()
        assert "查询" in router.front_of_house_commands
        assert "查询" in router.kitchen_commands
        assert len(router.front_of_house_commands) == 4
        assert len(router.kitchen_commands) == 4

    @patch('src.services.message_router.message_router')
    def test_route_command_kitchen_order(self, mock_router):
        """测试后厨订单命令路由"""
        router = VoiceCommandRouter()
        mock_router.route_message.return_value = (None, None, {})

        result = router.route_command("查询订单", "kitchen", "user123")

        assert result["agent_type"] == "order"
        assert result["action"] == "query_order"
        mock_router.route_message.assert_called_once_with("查询订单", "user123")

    @patch('src.services.message_router.message_router')
    def test_route_command_kitchen_inventory(self, mock_router):
        """测试后厨库存命令路由"""
        router = VoiceCommandRouter()
        mock_router.route_message.return_value = (None, None, {})

        result = router.route_command("查询库存", "kitchen", "user123")

        assert result["agent_type"] == "inventory"
        assert result["action"] == "query_inventory"

    @patch('src.services.message_router.message_router')
    def test_route_command_kitchen_restock(self, mock_router):
        """测试后厨补货命令路由"""
        router = VoiceCommandRouter()
        mock_router.route_message.return_value = (None, None, {})

        result = router.route_command("需要补货", "kitchen", "user123")

        assert result["agent_type"] == "inventory"
        assert result["action"] == "query_inventory"

    @patch('src.services.message_router.message_router')
    def test_route_command_front_order(self, mock_router):
        """测试前厅订单命令路由"""
        router = VoiceCommandRouter()
        mock_router.route_message.return_value = (None, None, {})

        result = router.route_command("创建订单", "front_of_house", "user123")

        assert result["agent_type"] == "order"
        assert result["action"] == "create_order"

    @patch('src.services.message_router.message_router')
    def test_route_command_cashier_checkout(self, mock_router):
        """测试收银结账命令路由"""
        router = VoiceCommandRouter()
        mock_router.route_message.return_value = (None, None, {})

        result = router.route_command("结账", "cashier", "user123")

        assert result["agent_type"] == "order"
        assert result["action"] == "checkout"

    @patch('src.services.message_router.message_router')
    def test_route_command_front_reservation(self, mock_router):
        """测试前厅预定命令路由"""
        router = VoiceCommandRouter()
        mock_router.route_message.return_value = (None, None, {})

        result = router.route_command("查询预定", "front_of_house", "user123")

        assert result["agent_type"] == "reservation"
        assert result["action"] == "query_reservation"

    @patch('src.services.message_router.message_router')
    def test_route_command_with_existing_agent(self, mock_router):
        """测试已有agent类型的命令路由"""
        router = VoiceCommandRouter()
        mock_router.route_message.return_value = ("member", "query_member", {"id": "123"})

        result = router.route_command("查询会员", "front_of_house", "user123")

        assert result["agent_type"] == "member"
        assert result["action"] == "query_member"
        assert result["params"] == {"id": "123"}

    @patch('src.services.message_router.message_router')
    def test_route_command_kitchen_dish(self, mock_router):
        """测试后厨菜品命令路由"""
        router = VoiceCommandRouter()
        mock_router.route_message.return_value = (None, None, {})

        result = router.route_command("完成菜品", "kitchen", "user123")

        assert result["agent_type"] == "order"
        assert result["action"] == "query_order"

    @patch('src.services.message_router.message_router')
    def test_route_command_front_seat(self, mock_router):
        """测试前厅座位命令路由"""
        router = VoiceCommandRouter()
        mock_router.route_message.return_value = (None, None, {})

        result = router.route_command("查询座位", "front_of_house", "user123")

        assert result["agent_type"] == "reservation"
        assert result["action"] == "query_reservation"


class TestGlobalInstances:
    """测试全局实例"""

    def test_voice_service_instance(self):
        """测试voice_service全局实例"""
        assert voice_service is not None
        assert isinstance(voice_service, VoiceService)
        assert voice_service.provider == VoiceProvider.AZURE

    def test_voice_command_router_instance(self):
        """测试voice_command_router全局实例"""
        assert voice_command_router is not None
        assert isinstance(voice_command_router, VoiceCommandRouter)

