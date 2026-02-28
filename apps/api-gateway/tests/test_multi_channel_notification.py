"""
多渠道通知服务测试
Tests for Multi-Channel Notification Service
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from src.services.multi_channel_notification import (
    MultiChannelNotificationService,
    NotificationChannel,
    NotificationTemplate,
    EmailNotificationHandler,
    SMSNotificationHandler,
    WeChatNotificationHandler,
    AppPushNotificationHandler,
    multi_channel_notification_service,
)


class TestNotificationTemplate:
    """NotificationTemplate测试类"""

    def test_get_template_exists(self):
        """测试获取存在的模板"""
        template = NotificationTemplate.get_template("order_confirmed")

        assert template is not None
        assert template["title"] == "订单确认"
        assert "order_id" in template["content"]
        assert NotificationChannel.SMS in template["channels"]
        assert template["priority"] == "normal"

    def test_get_template_not_exists(self):
        """测试获取不存在的模板"""
        template = NotificationTemplate.get_template("nonexistent")

        assert template is None

    def test_render_template_success(self):
        """测试渲染模板成功"""
        rendered = NotificationTemplate.render_template(
            "order_confirmed",
            order_id="ORD123",
            estimated_time="30分钟"
        )

        assert rendered is not None
        assert rendered["title"] == "订单确认"
        assert "ORD123" in rendered["content"]
        assert "30分钟" in rendered["content"]
        assert NotificationChannel.SMS in rendered["channels"]

    def test_render_template_not_exists(self):
        """测试渲染不存在的模板"""
        rendered = NotificationTemplate.render_template("nonexistent")

        assert rendered is None

    def test_render_template_inventory_low(self):
        """测试渲染库存预警模板"""
        rendered = NotificationTemplate.render_template(
            "inventory_low",
            item_name="牛肉",
            current_stock="5"
        )

        assert rendered is not None
        assert "牛肉" in rendered["content"]
        assert "5" in rendered["content"]
        assert rendered["priority"] == "high"

    def test_render_template_system_alert(self):
        """测试渲染系统告警模板"""
        rendered = NotificationTemplate.render_template(
            "system_alert",
            alert_message="数据库连接失败"
        )

        assert rendered is not None
        assert "数据库连接失败" in rendered["content"]
        assert rendered["priority"] == "urgent"


class TestEmailNotificationHandler:
    """EmailNotificationHandler测试类"""

    @pytest.mark.asyncio
    @patch('src.services.multi_channel_notification.email_config')
    async def test_send_email_no_config(self, mock_config):
        """测试未配置邮件服务"""
        mock_config.SMTP_PASSWORD = ""
        handler = EmailNotificationHandler()

        result = await handler.send(
            "test@example.com",
            "Test Title",
            "Test Content"
        )

        assert result is False

    @pytest.mark.asyncio
    @patch('src.services.multi_channel_notification.email_config')
    async def test_send_email_with_config(self, mock_config):
        """测试配置邮件服务发送"""
        mock_config.SMTP_PASSWORD = "password"
        mock_config.SMTP_USER = "user@example.com"
        mock_config.SMTP_FROM_NAME = "Test Sender"

        handler = EmailNotificationHandler()
        handler._send_email_sync = Mock()

        result = await handler.send(
            "test@example.com",
            "Test Title",
            "Test Content"
        )

        assert result is True

    @pytest.mark.asyncio
    @patch('src.services.multi_channel_notification.email_config')
    async def test_send_email_with_html(self, mock_config):
        """测试发送HTML邮件"""
        mock_config.SMTP_PASSWORD = "password"
        mock_config.SMTP_USER = "user@example.com"
        mock_config.SMTP_FROM_NAME = "Test Sender"

        handler = EmailNotificationHandler()
        handler._send_email_sync = Mock()

        result = await handler.send(
            "test@example.com",
            "Test Title",
            "Test Content",
            extra_data={"html_content": "<h1>Test</h1>"}
        )

        assert result is True


class TestSMSNotificationHandler:
    """SMSNotificationHandler测试类"""

    @pytest.mark.asyncio
    @patch('src.services.multi_channel_notification.sms_config')
    async def test_send_sms_no_config(self, mock_config):
        """测试未配置短信服务"""
        mock_config.ALIYUN_ACCESS_KEY_ID = ""
        mock_config.TENCENT_SECRET_ID = ""

        handler = SMSNotificationHandler()
        result = await handler.send("13800138000", "Test", "Test Content")

        assert result is False

    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    @patch('src.services.multi_channel_notification.sms_config')
    async def test_send_aliyun_sms(self, mock_config, mock_http_client):
        """测试发送阿里云短信"""
        mock_config.ALIYUN_ACCESS_KEY_ID = "test_key"
        mock_config.ALIYUN_ACCESS_KEY_SECRET = "test_secret"
        mock_config.ALIYUN_SMS_SIGN_NAME = "TestSign"
        mock_config.ALIYUN_SMS_TEMPLATE_CODE = "SMS_TEST"
        mock_config.ALIYUN_SMS_REGION = "cn-hangzhou"
        mock_config.TENCENT_SECRET_ID = ""
        mock_config.SMS_PROVIDER = "aliyun"

        mock_response = MagicMock()
        mock_response.json.return_value = {'Code': 'OK', 'BizId': '123456'}
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_http_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_http_client.return_value.__aexit__ = AsyncMock(return_value=False)

        handler = SMSNotificationHandler()
        result = await handler.send("13800138000", "Test", "Test Content")

        assert result is True

    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    @patch('src.services.multi_channel_notification.sms_config')
    async def test_send_tencent_sms(self, mock_config, mock_http_client):
        """测试发送腾讯云短信"""
        mock_config.ALIYUN_ACCESS_KEY_ID = ""
        mock_config.TENCENT_SECRET_ID = "test_secret"
        mock_config.TENCENT_SECRET_KEY = "test_key"
        mock_config.TENCENT_SMS_APP_ID = "1400000001"
        mock_config.TENCENT_SMS_SIGN = "TestSign"
        mock_config.TENCENT_SMS_TEMPLATE_ID = "1234567"
        mock_config.TENCENT_SMS_REGION = "ap-guangzhou"
        mock_config.SMS_PROVIDER = "tencent"

        mock_response = MagicMock()
        mock_response.json.return_value = {
            'Response': {'SendStatusSet': [{'Code': 'Ok', 'SerialNo': 'abc123'}]}
        }
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_http_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_http_client.return_value.__aexit__ = AsyncMock(return_value=False)

        handler = SMSNotificationHandler()
        result = await handler.send("13800138000", "Test", "Test Content")

        assert result is True

    @pytest.mark.asyncio
    @patch('src.services.multi_channel_notification.sms_config')
    async def test_send_sms_unsupported_provider(self, mock_config):
        """测试不支持的短信提供商"""
        mock_config.ALIYUN_ACCESS_KEY_ID = "test_key"
        mock_config.TENCENT_SECRET_ID = ""
        mock_config.SMS_PROVIDER = "unsupported"

        handler = SMSNotificationHandler()
        result = await handler.send("13800138000", "Test", "Test Content")

        assert result is False


class TestWeChatNotificationHandler:
    """WeChatNotificationHandler测试类"""

    @pytest.mark.asyncio
    @patch('src.services.multi_channel_notification.wechat_config')
    async def test_send_wechat_no_config(self, mock_config):
        """测试未配置微信服务"""
        mock_config.WECHAT_CORP_ID = ""
        mock_config.WECHAT_APP_ID = ""

        handler = WeChatNotificationHandler()
        result = await handler.send("user123", "Test", "Test Content")

        assert result is False

    @pytest.mark.asyncio
    @patch('src.services.multi_channel_notification.wechat_config')
    async def test_send_corp_wechat(self, mock_config):
        """测试发送企业微信消息"""
        mock_config.WECHAT_CORP_ID = "corp123"
        mock_config.WECHAT_APP_ID = ""
        mock_config.WECHAT_TYPE = "corp"

        handler = WeChatNotificationHandler()
        with patch.object(handler, '_send_corp_wechat', new=AsyncMock(return_value=True)):
            result = await handler.send("user123", "Test", "Test Content")

        assert result is True

    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    @patch('src.services.multi_channel_notification.wechat_config')
    async def test_send_official_wechat(self, mock_config, mock_http_client):
        """测试发送微信公众号消息"""
        mock_config.WECHAT_CORP_ID = ""
        mock_config.WECHAT_APP_ID = "app123"
        mock_config.WECHAT_APP_SECRET = "test_secret"
        mock_config.WECHAT_TYPE = "official"

        token_response = MagicMock()
        token_response.json.return_value = {'access_token': 'test_token_abc'}
        send_response = MagicMock()
        send_response.json.return_value = {'errcode': 0, 'errmsg': 'ok'}
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=token_response)
        mock_client.post = AsyncMock(return_value=send_response)
        mock_http_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_http_client.return_value.__aexit__ = AsyncMock(return_value=False)

        handler = WeChatNotificationHandler()
        result = await handler.send("openid123", "Test", "Test Content")

        assert result is True

    @pytest.mark.asyncio
    @patch('src.services.multi_channel_notification.wechat_config')
    async def test_send_wechat_unsupported_type(self, mock_config):
        """测试不支持的微信类型"""
        mock_config.WECHAT_CORP_ID = "corp123"
        mock_config.WECHAT_APP_ID = ""
        mock_config.WECHAT_TYPE = "unsupported"

        handler = WeChatNotificationHandler()
        result = await handler.send("user123", "Test", "Test Content")

        assert result is False


class TestAppPushNotificationHandler:
    """AppPushNotificationHandler测试类"""

    @pytest.mark.asyncio
    async def test_send_app_push(self):
        """测试发送App推送"""
        handler = AppPushNotificationHandler()
        result = await handler.send("device_token_123", "Test", "Test Content")

        assert result is False

    @pytest.mark.asyncio
    async def test_send_app_push_with_extra_data(self):
        """测试发送带额外数据的App推送"""
        handler = AppPushNotificationHandler()
        result = await handler.send(
            "device_token_123",
            "Test",
            "Test Content",
            extra_data={"badge": 1, "sound": "default"}
        )

        assert result is False


class TestMultiChannelNotificationService:
    """MultiChannelNotificationService测试类"""

    def test_init(self):
        """测试服务初始化"""
        service = MultiChannelNotificationService()

        assert NotificationChannel.EMAIL in service.handlers
        assert NotificationChannel.SMS in service.handlers
        assert NotificationChannel.WECHAT in service.handlers
        assert NotificationChannel.APP_PUSH in service.handlers

    @pytest.mark.asyncio
    async def test_send_notification_single_channel(self):
        """测试单渠道发送通知"""
        service = MultiChannelNotificationService()

        with patch.object(service.handlers[NotificationChannel.EMAIL], 'send', new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True

            results = await service.send_notification(
                channels=[NotificationChannel.EMAIL],
                recipient="test@example.com",
                title="Test",
                content="Test Content"
            )

            assert NotificationChannel.EMAIL in results
            assert results[NotificationChannel.EMAIL] is True
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_notification_multiple_channels(self):
        """测试多渠道发送通知"""
        service = MultiChannelNotificationService()

        with patch.object(service.handlers[NotificationChannel.EMAIL], 'send', new_callable=AsyncMock) as mock_email, \
             patch.object(service.handlers[NotificationChannel.SMS], 'send', new_callable=AsyncMock) as mock_sms:
            mock_email.return_value = True
            mock_sms.return_value = True

            results = await service.send_notification(
                channels=[NotificationChannel.EMAIL, NotificationChannel.SMS],
                recipient="test@example.com",
                title="Test",
                content="Test Content"
            )

            assert len(results) == 2
            assert results[NotificationChannel.EMAIL] is True
            assert results[NotificationChannel.SMS] is True

    @pytest.mark.asyncio
    async def test_send_notification_with_failure(self):
        """测试发送通知失败"""
        service = MultiChannelNotificationService()

        with patch.object(service.handlers[NotificationChannel.EMAIL], 'send', new_callable=AsyncMock) as mock_send:
            mock_send.return_value = False

            with patch('src.services.multi_channel_notification.notification_config') as mock_config:
                mock_config.MAX_RETRY_ATTEMPTS = 1
                mock_config.RETRY_DELAY_SECONDS = 0
                mock_config.ENABLE_FALLBACK = False

                results = await service.send_notification(
                    channels=[NotificationChannel.EMAIL],
                    recipient="test@example.com",
                    title="Test",
                    content="Test Content"
                )

                assert results[NotificationChannel.EMAIL] is False

    @pytest.mark.asyncio
    async def test_send_template_notification_success(self):
        """测试使用模板发送通知成功"""
        service = MultiChannelNotificationService()

        with patch.object(service.handlers[NotificationChannel.SMS], 'send', new_callable=AsyncMock) as mock_sms, \
             patch.object(service.handlers[NotificationChannel.APP_PUSH], 'send', new_callable=AsyncMock) as mock_push:
            mock_sms.return_value = True
            mock_push.return_value = True

            results = await service.send_template_notification(
                template_name="order_confirmed",
                recipient="13800138000",
                order_id="ORD123",
                estimated_time="30分钟"
            )

            assert len(results) == 2
            assert NotificationChannel.SMS in results
            assert NotificationChannel.APP_PUSH in results

    @pytest.mark.asyncio
    async def test_send_template_notification_template_not_found(self):
        """测试使用不存在的模板发送通知"""
        service = MultiChannelNotificationService()

        results = await service.send_template_notification(
            template_name="nonexistent",
            recipient="test@example.com"
        )

        assert results == {}

    @pytest.mark.asyncio
    @patch('src.services.multi_channel_notification.notification_config')
    async def test_send_with_retry(self, mock_config):
        """测试重试机制"""
        mock_config.MAX_RETRY_ATTEMPTS = 3
        mock_config.RETRY_DELAY_SECONDS = 0
        mock_config.ENABLE_FALLBACK = False

        service = MultiChannelNotificationService()
        handler = service.handlers[NotificationChannel.EMAIL]

        with patch.object(handler, 'send', new_callable=AsyncMock) as mock_send:
            # 前两次失败,第三次成功
            mock_send.side_effect = [False, False, True]

            result = await service._send_with_channel(
                handler,
                NotificationChannel.EMAIL,
                "test@example.com",
                "Test",
                "Content",
                None
            )

            assert result is True
            assert mock_send.call_count == 3

    @pytest.mark.asyncio
    @patch('src.services.multi_channel_notification.notification_config')
    async def test_send_with_fallback(self, mock_config):
        """测试故障转移"""
        mock_config.MAX_RETRY_ATTEMPTS = 1
        mock_config.RETRY_DELAY_SECONDS = 0
        mock_config.ENABLE_FALLBACK = True
        mock_config.FALLBACK_CHANNEL = "email"

        service = MultiChannelNotificationService()
        sms_handler = service.handlers[NotificationChannel.SMS]
        email_handler = service.handlers[NotificationChannel.EMAIL]

        with patch.object(sms_handler, 'send', new_callable=AsyncMock) as mock_sms, \
             patch.object(email_handler, 'send', new_callable=AsyncMock) as mock_email:
            mock_sms.return_value = False
            mock_email.return_value = True

            result = await service._send_with_channel(
                sms_handler,
                NotificationChannel.SMS,
                "13800138000",
                "Test",
                "Content",
                None
            )

            assert result is True
            mock_email.assert_called_once()


class TestGlobalInstance:
    """测试全局实例"""

    def test_multi_channel_notification_service_instance(self):
        """测试multi_channel_notification_service全局实例"""
        assert multi_channel_notification_service is not None
        assert isinstance(multi_channel_notification_service, MultiChannelNotificationService)
