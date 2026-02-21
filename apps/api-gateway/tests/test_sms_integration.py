"""
测试短信服务的阿里云和腾讯云集成
Tests for Aliyun and Tencent SMS Integration
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.services.multi_channel_notification import SMSNotificationHandler


class TestAliyunSMS:
    """阿里云短信测试"""

    @pytest.mark.asyncio
    @patch('src.services.multi_channel_notification.sms_config')
    @patch('httpx.AsyncClient')
    async def test_aliyun_sms_success(self, mock_client, mock_config):
        """测试阿里云短信发送成功"""
        # 配置mock
        mock_config.SMS_PROVIDER = "aliyun"
        mock_config.ALIYUN_ACCESS_KEY_ID = "test_key"
        mock_config.ALIYUN_ACCESS_KEY_SECRET = "test_secret"
        mock_config.ALIYUN_SMS_SIGN_NAME = "测试签名"
        mock_config.ALIYUN_SMS_TEMPLATE_CODE = "SMS_123456"
        mock_config.ALIYUN_SMS_REGION = "cn-hangzhou"

        # Mock HTTP响应
        mock_response = MagicMock()
        mock_response.json.return_value = {"Code": "OK", "BizId": "test_biz_id"}

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        # 执行测试
        handler = SMSNotificationHandler()
        result = await handler.send(
            "13800138000",
            "测试标题",
            "测试内容"
        )

        assert result is True

    @pytest.mark.asyncio
    @patch('src.services.multi_channel_notification.sms_config')
    @patch('httpx.AsyncClient')
    async def test_aliyun_sms_failure(self, mock_client, mock_config):
        """测试阿里云短信发送失败"""
        mock_config.SMS_PROVIDER = "aliyun"
        mock_config.ALIYUN_ACCESS_KEY_ID = "test_key"
        mock_config.ALIYUN_ACCESS_KEY_SECRET = "test_secret"

        # Mock失败响应
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "Code": "isv.BUSINESS_LIMIT_CONTROL",
            "Message": "触发天级流控Permits:1"
        }

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        handler = SMSNotificationHandler()
        result = await handler.send(
            "13800138000",
            "测试标题",
            "测试内容"
        )

        assert result is False


class TestTencentSMS:
    """腾讯云短信测试"""

    @pytest.mark.asyncio
    @patch('src.services.multi_channel_notification.sms_config')
    @patch('httpx.AsyncClient')
    async def test_tencent_sms_success(self, mock_client, mock_config):
        """测试腾讯云短信发送成功"""
        mock_config.SMS_PROVIDER = "tencent"
        mock_config.TENCENT_SECRET_ID = "test_id"
        mock_config.TENCENT_SECRET_KEY = "test_key"
        mock_config.TENCENT_SMS_APP_ID = "1400000000"
        mock_config.TENCENT_SMS_SIGN = "测试签名"
        mock_config.TENCENT_SMS_TEMPLATE_ID = "123456"
        mock_config.TENCENT_SMS_REGION = "ap-guangzhou"

        # Mock成功响应
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "Response": {
                "SendStatusSet": [
                    {
                        "Code": "Ok",
                        "SerialNo": "test_serial_no"
                    }
                ]
            }
        }

        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        handler = SMSNotificationHandler()
        result = await handler.send(
            "13800138000",
            "测试标题",
            "测试内容"
        )

        assert result is True

    @pytest.mark.asyncio
    @patch('src.services.multi_channel_notification.sms_config')
    @patch('httpx.AsyncClient')
    async def test_tencent_sms_failure(self, mock_client, mock_config):
        """测试腾讯云短信发送失败"""
        mock_config.SMS_PROVIDER = "tencent"
        mock_config.TENCENT_SECRET_ID = "test_id"
        mock_config.TENCENT_SECRET_KEY = "test_key"

        # Mock失败响应
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "Response": {
                "Error": {
                    "Code": "FailedOperation.ContainSensitiveWord",
                    "Message": "短信内容包含敏感词"
                }
            }
        }

        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        handler = SMSNotificationHandler()
        result = await handler.send(
            "13800138000",
            "测试标题",
            "测试内容"
        )

        assert result is False

    @pytest.mark.asyncio
    @patch('src.services.multi_channel_notification.sms_config')
    async def test_sms_no_config(self, mock_config):
        """测试未配置短信服务"""
        mock_config.ALIYUN_ACCESS_KEY_ID = ""
        mock_config.TENCENT_SECRET_ID = ""

        handler = SMSNotificationHandler()
        result = await handler.send(
            "13800138000",
            "测试标题",
            "测试内容"
        )

        # 未配置时应该返回True(模拟发送)
        assert result is True
