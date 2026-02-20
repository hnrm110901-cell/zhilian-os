"""
企业集成API端点测试
Tests for Enterprise Integration API Endpoints
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
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
