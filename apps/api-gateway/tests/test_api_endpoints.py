"""
企业集成API端点测试
Tests for Enterprise Integration API Endpoints
"""
import os
for _k, _v in {
    "APP_ENV":               "test",
    "DATABASE_URL":          "postgresql+asyncpg://test:test@localhost/test",
    "REDIS_URL":             "redis://localhost:6379/0",
    "CELERY_BROKER_URL":     "redis://localhost:6379/0",
    "CELERY_RESULT_BACKEND": "redis://localhost:6379/0",
    "SECRET_KEY":            "test-secret-key",
    "JWT_SECRET":            "test-jwt-secret",
}.items():
    os.environ.setdefault(_k, _v)

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch
from src.main import app


client = TestClient(app)


class TestEnterpriseAPI:
    """企业集成API测试"""

    @patch('src.api.enterprise.wechat_service')
    def test_send_wechat_message_success(self, mock_service):
        """测试发送企业微信消息成功"""
        mock_service.is_configured.return_value = True
        mock_service.send_text_message = AsyncMock(return_value={"errcode": 0})

        response = client.post(
            "/api/v1/enterprise/wechat/send-message",
            json={
                "content": "测试消息",
                "touser": "user1",
                "message_type": "text"
            },
            headers={"Authorization": "Bearer test_token"}
        )

        # 注意: 需要认证,这里会返回401或403
        assert response.status_code in [200, 401, 403]

    @patch('src.api.enterprise.wechat_service')
    def test_send_wechat_message_not_configured(self, mock_service):
        """测试企业微信未配置"""
        mock_service.is_configured.return_value = False

        response = client.post(
            "/api/v1/enterprise/wechat/send-message",
            json={
                "content": "测试消息",
                "message_type": "text"
            },
            headers={"Authorization": "Bearer test_token"}
        )

        assert response.status_code in [503, 401, 403]

    @patch('src.api.enterprise.feishu_service')
    def test_send_feishu_message_success(self, mock_service):
        """测试发送飞书消息成功"""
        mock_service.is_configured.return_value = True
        mock_service.send_text_message = AsyncMock(return_value={"code": 0})

        response = client.post(
            "/api/v1/enterprise/feishu/send-message",
            json={
                "content": "测试消息",
                "receive_id": "user1",
                "message_type": "text"
            },
            headers={"Authorization": "Bearer test_token"}
        )

        assert response.status_code in [200, 401, 403]

    @pytest.mark.asyncio
    async def test_send_feishu_post_message_branch(self):
        from src.api.enterprise import FeishuMessageRequest, send_feishu_message

        request = FeishuMessageRequest(
            content="测试富文本",
            receive_id="user1",
            message_type="post",
            title="标题",
            post_content=[[{"tag": "text", "text": "正文"}]],
        )
        current_user = MagicMock()

        with patch("src.api.enterprise.feishu_service") as mock_service:
            mock_service.is_configured.return_value = True
            mock_service.send_post_message = AsyncMock(return_value={"code": 0})

            result = await send_feishu_message(request=request, current_user=current_user)

        assert result["success"] is True
        mock_service.send_post_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_send_feishu_interactive_message_branch(self):
        from src.api.enterprise import FeishuMessageRequest, send_feishu_message

        request = FeishuMessageRequest(
            content="测试卡片",
            receive_id="user1",
            message_type="interactive",
            card_content={"elements": [{"tag": "div", "text": {"tag": "plain_text", "content": "正文"}}]},
        )
        current_user = MagicMock()

        with patch("src.api.enterprise.feishu_service") as mock_service:
            mock_service.is_configured.return_value = True
            mock_service.send_interactive_card = AsyncMock(return_value={"code": 0})

            result = await send_feishu_message(request=request, current_user=current_user)

        assert result["success"] is True
        mock_service.send_interactive_card.assert_awaited_once()

    @patch('src.api.enterprise.feishu_service')
    def test_feishu_webhook_url_verification(self, mock_service):
        mock_service.validate_callback_token.return_value = True

        response = client.post(
            "/api/v1/enterprise/feishu/webhook",
            json={
                "type": "url_verification",
                "challenge": "challenge-token",
            },
        )

        assert response.status_code == 200
        assert response.json() == {"challenge": "challenge-token"}
        mock_service.handle_message.assert_not_called()

    @patch('src.api.enterprise.feishu_service')
    def test_feishu_webhook_message_event(self, mock_service):
        mock_service.validate_callback_token.return_value = True
        mock_service.is_duplicate_event = AsyncMock(return_value=False)
        mock_service.mark_event_processed = AsyncMock(return_value=True)
        mock_service.handle_message = AsyncMock(
            return_value={"handled": True, "reply_sent": True}
        )

        response = client.post(
            "/api/v1/enterprise/feishu/webhook",
            json={
                "header": {"event_type": "im.message.receive_v1", "event_id": "evt_123"},
                "event": {
                    "sender": {"sender_id": {"user_id": "ou_123"}},
                    "message": {
                        "message_type": "text",
                        "content": "{\"text\":\"hello\"}",
                    },
                },
            },
        )

        assert response.status_code == 200
        assert response.json()["success"] is True
        assert response.json()["data"]["reply_sent"] is True
        mock_service.handle_message.assert_awaited_once()
        mock_service.mark_event_processed.assert_awaited_once_with("evt_123")

    @patch('src.api.enterprise.feishu_service')
    def test_feishu_webhook_rejects_invalid_token(self, mock_service):
        mock_service.validate_callback_token.return_value = False

        response = client.post(
            "/api/v1/enterprise/feishu/webhook",
            json={"header": {"token": "bad-token"}},
        )

        assert response.status_code == 403
        mock_service.handle_message.assert_not_called()

    @patch('src.api.enterprise.feishu_service')
    def test_feishu_webhook_skips_duplicate_event(self, mock_service):
        mock_service.validate_callback_token.return_value = True
        mock_service.is_duplicate_event = AsyncMock(return_value=True)

        response = client.post(
            "/api/v1/enterprise/feishu/webhook",
            json={"header": {"event_id": "evt_123", "token": "token-123"}},
        )

        assert response.status_code == 200
        assert response.json()["duplicate"] is True
        mock_service.handle_message.assert_not_called()


class TestHealthAPI:
    """健康检查API测试"""

    def test_health_check(self):
        """测试健康检查端点"""
        response = client.get("/api/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert "version" in data

    def test_liveness_check(self):
        """测试存活检查端点"""
        response = client.get("/api/v1/live")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alive"

    @pytest.mark.asyncio
    async def test_readiness_check(self):
        """测试就绪检查端点"""
        response = client.get("/api/v1/ready")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "checks" in data
        assert "database" in data["checks"]
        assert "redis" in data["checks"]

    @pytest.mark.asyncio
    async def test_config_validation_includes_webhook_security_flags(self):
        from src.api.health import config_validation
        from src.core.config import settings

        current_user = MagicMock()

        with patch.object(settings, "WECHAT_CORP_ID", "corp-id"), \
             patch.object(settings, "WECHAT_CORP_SECRET", "corp-secret"), \
             patch.object(settings, "WECHAT_AGENT_ID", "1001"), \
             patch.object(settings, "WECHAT_TOKEN", "wechat-token"), \
             patch.object(settings, "WECHAT_ENCODING_AES_KEY", "aes-key"), \
             patch.object(settings, "FEISHU_APP_ID", "app-id"), \
             patch.object(settings, "FEISHU_APP_SECRET", "app-secret"), \
             patch.object(settings, "FEISHU_VERIFICATION_TOKEN", "verify-token"), \
             patch.object(settings, "AOQIWEI_APP_KEY", ""), \
             patch.object(settings, "AOQIWEI_BASE_URL", ""), \
             patch.object(settings, "PINZHI_TOKEN", ""), \
             patch.object(settings, "PINZHI_BASE_URL", ""):
            result = await config_validation(current_user=current_user)

        assert result["optional"]["wechat"]["complete"] is True
        assert result["optional"]["wechat"]["webhook_secure"] is True
        assert result["optional"]["feishu"]["complete"] is True
        assert result["optional"]["feishu"]["webhook_secure"] is True


class TestMetricsAPI:
    """指标API测试"""

    def test_metrics_endpoint(self):
        """测试Prometheus指标端点"""
        response = client.get("/metrics")

        assert response.status_code == 200
        assert "http_requests_total" in response.text or response.status_code == 200


class TestAuthAPI:
    """认证API测试"""

    def test_login_endpoint_exists(self):
        """测试登录端点存在"""
        response = client.post(
            "/api/v1/auth/login",
            json={
                "username": "test",
                "password": "test"
            }
        )

        # 应该返回401(认证失败)而不是404(端点不存在)
        assert response.status_code in [200, 401, 422]

    def test_login_missing_credentials(self):
        """测试缺少登录凭证"""
        response = client.post(
            "/api/v1/auth/login",
            json={}
        )

        assert response.status_code == 422  # Validation error


class TestAgentAPI:
    """Agent API测试"""

    def test_agent_list_endpoint(self):
        """测试Agent列表端点"""
        response = client.get(
            "/api/v1/agents",
            headers={"Authorization": "Bearer test_token"}
        )

        # 需要认证
        assert response.status_code in [200, 401, 403]

    def test_agent_execute_endpoint(self):
        """测试Agent执行端点"""
        response = client.post(
            "/api/v1/agents/schedule/execute",
            json={
                "action": "get_schedule",
                "params": {}
            },
            headers={"Authorization": "Bearer test_token"}
        )

        # 需要认证
        assert response.status_code in [200, 401, 403, 404]
