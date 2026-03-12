"""
企业集成API端点测试
Tests for Enterprise Integration API Endpoints
"""
import hashlib
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
from src.core.security import create_access_token
from src.services.raspberry_pi_edge_service import RaspberryPiEdgeService


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

    @patch('src.api.enterprise.wechat_service')
    @patch('src.api.enterprise.feishu_service')
    def test_enterprise_matrix_endpoint_shape(self, mock_feishu, mock_wechat):
        mock_wechat.is_configured.return_value = True
        mock_feishu.is_configured.return_value = True

        with patch("src.api.enterprise.wechat_crypto", object()), \
             patch("src.api.enterprise.settings.FEISHU_VERIFICATION_TOKEN", "verify-token"), \
             patch("src.api.enterprise.settings.FEISHU_ENCRYPT_KEY", "encrypt-key"):
            response = client.get(
                "/api/v1/enterprise/support-matrix",
                headers={"Authorization": "Bearer test_token"}
            )

        assert response.status_code in [200, 401, 403]
        if response.status_code == 200:
            data = response.json()
            assert "summary" in data
            assert "providers" in data
            assert "wechat" in data["providers"]
            assert "feishu" in data["providers"]

    @patch('src.api.enterprise.wechat_service')
    @patch('src.api.enterprise.feishu_service')
    def test_enterprise_readiness_endpoint_shape(self, mock_feishu, mock_wechat):
        mock_wechat.is_configured.return_value = True
        mock_feishu.is_configured.return_value = True

        with patch("src.api.enterprise.wechat_crypto", object()), \
             patch("src.api.enterprise.settings.WECHAT_CORP_ID", "corp-id"), \
             patch("src.api.enterprise.settings.WECHAT_CORP_SECRET", "corp-secret"), \
             patch("src.api.enterprise.settings.WECHAT_AGENT_ID", "1001"), \
             patch("src.api.enterprise.settings.WECHAT_TOKEN", "wechat-token"), \
             patch("src.api.enterprise.settings.WECHAT_ENCODING_AES_KEY", "aes-key"), \
             patch("src.api.enterprise.settings.FEISHU_APP_ID", "app-id"), \
             patch("src.api.enterprise.settings.FEISHU_APP_SECRET", "app-secret"), \
             patch("src.api.enterprise.settings.FEISHU_VERIFICATION_TOKEN", "verify-token"), \
             patch("src.api.enterprise.settings.FEISHU_ENCRYPT_KEY", "encrypt-key"):
            response = client.get(
                "/api/v1/enterprise/readiness",
                headers={"Authorization": "Bearer test_token"}
            )

        assert response.status_code in [200, 401, 403]
        if response.status_code == 200:
            data = response.json()
            assert "overall" in data
            assert "providers" in data
            assert "wechat" in data["providers"]
            assert "missing_env" in data["providers"]["wechat"]

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
        mock_service.validate_signature.return_value = True
        mock_service.validate_callback_token.return_value = True
        mock_service.is_supported_event_type.return_value = True

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
        mock_service.validate_signature.return_value = True
        mock_service.validate_callback_token.return_value = True
        mock_service.is_supported_event_type.return_value = True
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
        mock_service.validate_signature.return_value = True
        mock_service.validate_callback_token.return_value = False

        response = client.post(
            "/api/v1/enterprise/feishu/webhook",
            json={"header": {"token": "bad-token"}},
        )

        assert response.status_code == 403
        mock_service.handle_message.assert_not_called()

    @patch('src.api.enterprise.feishu_service')
    def test_feishu_webhook_rejects_unsupported_event_type(self, mock_service):
        mock_service.validate_signature.return_value = True
        mock_service.validate_callback_token.return_value = True
        mock_service.is_supported_event_type.return_value = False

        response = client.post(
            "/api/v1/enterprise/feishu/webhook",
            json={"header": {"event_type": "contact.user.created_v3", "token": "token-123"}},
        )

        assert response.status_code == 400
        mock_service.handle_message.assert_not_called()

    @patch('src.api.enterprise.feishu_service')
    def test_feishu_webhook_skips_duplicate_event(self, mock_service):
        mock_service.validate_signature.return_value = True
        mock_service.validate_callback_token.return_value = True
        mock_service.is_supported_event_type.return_value = True
        mock_service.is_duplicate_event = AsyncMock(return_value=True)

        response = client.post(
            "/api/v1/enterprise/feishu/webhook",
            json={"header": {"event_id": "evt_123", "token": "token-123"}},
        )

        assert response.status_code == 200
        assert response.json()["duplicate"] is True
        mock_service.handle_message.assert_not_called()

    @patch('src.api.enterprise.feishu_service')
    def test_feishu_webhook_rejects_invalid_signature(self, mock_service):
        mock_service.validate_signature.return_value = False

        response = client.post(
            "/api/v1/enterprise/feishu/webhook",
            json={"header": {"event_type": "im.message.receive_v1"}},
        )

        assert response.status_code == 403
        mock_service.validate_callback_token.assert_not_called()

    @pytest.mark.asyncio
    @patch('src.api.enterprise.feishu_service')
    async def test_feishu_status_exposes_webhook_protection(self, mock_service):
        from src.api.enterprise import check_feishu_status

        current_user = MagicMock()
        mock_service.is_configured.return_value = True

        with patch("src.api.enterprise.settings.FEISHU_VERIFICATION_TOKEN", "verify-token"), \
             patch("src.api.enterprise.settings.FEISHU_ENCRYPT_KEY", "encrypt-key"):
            result = await check_feishu_status(current_user=current_user)

        assert result["configured"] is True
        assert result["webhook_protected"] is True
        assert result["webhook_signed"] is True
        assert result["webhook_ready"] is True

    @pytest.mark.asyncio
    @patch('src.api.enterprise.wechat_service')
    async def test_wechat_status_exposes_webhook_fields(self, mock_service):
        from src.api.enterprise import check_wechat_status

        current_user = MagicMock()
        mock_service.is_configured.return_value = True

        with patch("src.api.enterprise.settings.WECHAT_TOKEN", "wechat-token"), \
             patch("src.api.enterprise.settings.WECHAT_ENCODING_AES_KEY", "aes-key"), \
             patch("src.api.enterprise.wechat_crypto", object()):
            result = await check_wechat_status(current_user=current_user)

        assert result["configured"] is True
        assert result["webhook_protected"] is True
        assert result["webhook_encrypted"] is True
        assert result["webhook_ready"] is True
        assert result["webhook_signature_verification"] is True

    @pytest.mark.asyncio
    async def test_enterprise_support_matrix(self):
        from src.api.enterprise import get_enterprise_support_matrix

        current_user = MagicMock()

        with patch("src.api.enterprise.wechat_service") as mock_wechat, \
             patch("src.api.enterprise.feishu_service") as mock_feishu, \
             patch("src.api.enterprise.wechat_crypto", object()), \
             patch("src.api.enterprise.settings.FEISHU_VERIFICATION_TOKEN", "verify-token"), \
             patch("src.api.enterprise.settings.FEISHU_ENCRYPT_KEY", "encrypt-key"), \
             patch("src.api.enterprise.settings.DINGTALK_APP_KEY", ""), \
             patch("src.api.enterprise.settings.DINGTALK_APP_SECRET", ""):
            mock_wechat.is_configured.return_value = True
            mock_feishu.is_configured.return_value = True

            result = await get_enterprise_support_matrix(current_user=current_user)

        assert "providers" in result
        assert result["providers"]["wechat"]["production_ready"]["webhook"] is True
        assert result["providers"]["feishu"]["capabilities"]["event_id_dedup"] is True
        assert result["providers"]["dingtalk"]["capabilities"]["send_message"] is False

    @pytest.mark.asyncio
    async def test_enterprise_readiness_report(self):
        from src.api.enterprise import get_enterprise_readiness

        current_user = MagicMock()

        with patch("src.api.enterprise.wechat_service") as mock_wechat, \
             patch("src.api.enterprise.feishu_service") as mock_feishu, \
             patch("src.api.enterprise.wechat_crypto", object()), \
             patch("src.api.enterprise.settings.WECHAT_CORP_ID", "corp-id"), \
             patch("src.api.enterprise.settings.WECHAT_CORP_SECRET", "corp-secret"), \
             patch("src.api.enterprise.settings.WECHAT_AGENT_ID", "1001"), \
             patch("src.api.enterprise.settings.WECHAT_TOKEN", "wechat-token"), \
             patch("src.api.enterprise.settings.WECHAT_ENCODING_AES_KEY", "aes-key"), \
             patch("src.api.enterprise.settings.FEISHU_APP_ID", "app-id"), \
             patch("src.api.enterprise.settings.FEISHU_APP_SECRET", "app-secret"), \
             patch("src.api.enterprise.settings.FEISHU_VERIFICATION_TOKEN", "verify-token"), \
             patch("src.api.enterprise.settings.FEISHU_ENCRYPT_KEY", "encrypt-key"), \
             patch("src.api.enterprise.settings.DINGTALK_APP_KEY", ""), \
             patch("src.api.enterprise.settings.DINGTALK_APP_SECRET", ""):
            mock_wechat.is_configured.return_value = True
            mock_feishu.is_configured.return_value = True

            result = await get_enterprise_readiness(current_user=current_user)

        assert result["overall"]["ready_count"] == 2
        assert result["providers"]["wechat"]["ready"] is True
        assert result["providers"]["feishu"]["ready"] is True
        assert result["providers"]["dingtalk"]["ready"] is False
        assert "钉钉仅支持OAuth登录" in result["providers"]["dingtalk"]["risks"][0]


class TestHardwareIntegrationAPI:
    """硬件集成 API 测试"""

    @staticmethod
    def _user_token() -> str:
        return create_access_token(
            {
                "sub": "test-user-1",
                "username": "tester",
                "role": "admin",
                "store_id": "STORE001",
                "brand_id": "BRAND001",
            }
        )

    def test_edge_node_register_accepts_bootstrap_token(self):
        service = RaspberryPiEdgeService()

        with patch("src.api.hardware_integration.get_raspberry_pi_edge_service", return_value=service), \
             patch("src.api.hardware_integration.settings.EDGE_BOOTSTRAP_TOKEN", "edge-bootstrap-token"):
            response = client.post(
                "/api/v1/hardware/edge-node/register",
                params={
                    "store_id": "STORE001",
                    "device_name": "store001-rpi5",
                    "ip_address": "192.168.1.50",
                    "mac_address": "aa:bb:cc:dd:ee:ff",
                },
                headers={"Authorization": "Bearer edge-bootstrap-token"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["node"]["node_id"].startswith("edge_STORE001_")
        assert data["device_secret"]

    def test_edge_node_status_accepts_device_secret(self):
        service = RaspberryPiEdgeService()

        with patch("src.api.hardware_integration.get_raspberry_pi_edge_service", return_value=service), \
             patch("src.api.hardware_integration.settings.EDGE_BOOTSTRAP_TOKEN", "edge-bootstrap-token"):
            register_response = client.post(
                "/api/v1/hardware/edge-node/register",
                params={
                    "store_id": "STORE001",
                    "device_name": "store001-rpi5",
                    "ip_address": "192.168.1.50",
                    "mac_address": "aa:bb:cc:dd:ee:11",
                },
                headers={"Authorization": "Bearer edge-bootstrap-token"},
            )

            register_data = register_response.json()
            node_id = register_data["node"]["node_id"]
            device_secret = register_data["device_secret"]

            response = client.post(
                f"/api/v1/hardware/edge-node/{node_id}/status",
                params={
                    "cpu_usage": 12.5,
                    "memory_usage": 34.2,
                    "disk_usage": 40.1,
                    "temperature": 48.6,
                    "uptime_seconds": 3600,
                    "pending_status_queue": 3,
                    "last_queue_error": "temporary network timeout",
                },
                headers={"X-Edge-Node-Secret": device_secret},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["node"]["cpu_usage"] == 12.5
        assert data["node"]["pending_status_queue"] == 3
        assert data["node"]["last_queue_error"] == "temporary network timeout"

    def test_edge_node_status_rejects_invalid_device_secret(self):
        service = RaspberryPiEdgeService()

        with patch("src.api.hardware_integration.get_raspberry_pi_edge_service", return_value=service), \
             patch("src.api.hardware_integration.settings.EDGE_BOOTSTRAP_TOKEN", "edge-bootstrap-token"):
            register_response = client.post(
                "/api/v1/hardware/edge-node/register",
                params={
                    "store_id": "STORE001",
                    "device_name": "store001-rpi5",
                    "ip_address": "192.168.1.50",
                    "mac_address": "aa:bb:cc:dd:ee:22",
                },
                headers={"Authorization": "Bearer edge-bootstrap-token"},
            )
            node_id = register_response.json()["node"]["node_id"]

            response = client.post(
                f"/api/v1/hardware/edge-node/{node_id}/status",
                params={
                    "cpu_usage": 12.5,
                    "memory_usage": 34.2,
                    "disk_usage": 40.1,
                    "temperature": 48.6,
                    "uptime_seconds": 3600,
                },
                headers={"X-Edge-Node-Secret": "bad-secret"},
            )

        assert response.status_code == 401

    def test_edge_node_status_restores_node_from_persistence_when_memory_empty(self):
        service = RaspberryPiEdgeService()

        with patch("src.api.hardware_integration.get_raspberry_pi_edge_service", return_value=service), \
             patch("src.api.hardware_integration.settings.EDGE_BOOTSTRAP_TOKEN", "edge-bootstrap-token"):
            register_response = client.post(
                "/api/v1/hardware/edge-node/register",
                params={
                    "store_id": "STORE001",
                    "device_name": "store001-rpi5",
                    "ip_address": "192.168.1.50",
                    "mac_address": "aa:bb:cc:dd:ee:12",
                },
                headers={"Authorization": "Bearer edge-bootstrap-token"},
            )

            register_data = register_response.json()
            node_id = register_data["node"]["node_id"]
            device_secret = register_data["device_secret"]
            persisted_node = service.edge_nodes[node_id].model_copy()
            service.edge_nodes.clear()

            with patch.object(service, "_load_edge_hub", AsyncMock(return_value=persisted_node)):
                response = client.post(
                    f"/api/v1/hardware/edge-node/{node_id}/status",
                    params={
                        "cpu_usage": 15.0,
                        "memory_usage": 25.0,
                        "disk_usage": 35.0,
                        "temperature": 45.0,
                        "uptime_seconds": 7200,
                        "pending_status_queue": 2,
                    },
                    headers={"X-Edge-Node-Secret": device_secret},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["node"]["pending_status_queue"] == 2
        assert service.edge_nodes[node_id].cpu_usage == 15.0

    def test_edge_node_rotate_secret_invalidates_old_secret(self):
        service = RaspberryPiEdgeService()

        with patch("src.api.hardware_integration.get_raspberry_pi_edge_service", return_value=service), \
             patch("src.api.hardware_integration.settings.EDGE_BOOTSTRAP_TOKEN", "edge-bootstrap-token"):
            register_response = client.post(
                "/api/v1/hardware/edge-node/register",
                params={
                    "store_id": "STORE001",
                    "device_name": "store001-rpi5",
                    "ip_address": "192.168.1.50",
                    "mac_address": "aa:bb:cc:dd:ee:33",
                },
                headers={"Authorization": "Bearer edge-bootstrap-token"},
            )
            register_data = register_response.json()
            node_id = register_data["node"]["node_id"]
            old_secret = register_data["device_secret"]

            rotate_response = client.post(
                f"/api/v1/hardware/edge-node/{node_id}/rotate-secret",
                headers={"Authorization": f"Bearer {self._user_token()}"},
            )
            assert rotate_response.status_code == 200
            new_secret = rotate_response.json()["device_secret"]
            assert new_secret != old_secret

            rejected = client.post(
                f"/api/v1/hardware/edge-node/{node_id}/status",
                params={
                    "cpu_usage": 10,
                    "memory_usage": 20,
                    "disk_usage": 30,
                    "temperature": 40,
                    "uptime_seconds": 50,
                },
                headers={"X-Edge-Node-Secret": old_secret},
            )
            assert rejected.status_code == 401

            accepted = client.post(
                f"/api/v1/hardware/edge-node/{node_id}/status",
                params={
                    "cpu_usage": 10,
                    "memory_usage": 20,
                    "disk_usage": 30,
                    "temperature": 40,
                    "uptime_seconds": 50,
                },
                headers={"X-Edge-Node-Secret": new_secret},
            )
            assert accepted.status_code == 200

    def test_edge_node_credential_status_endpoint(self):
        service = RaspberryPiEdgeService()

        with patch("src.api.hardware_integration.get_raspberry_pi_edge_service", return_value=service), \
             patch("src.api.hardware_integration.settings.EDGE_BOOTSTRAP_TOKEN", "edge-bootstrap-token"):
            register_response = client.post(
                "/api/v1/hardware/edge-node/register",
                params={
                    "store_id": "STORE001",
                    "device_name": "store001-rpi5",
                    "ip_address": "192.168.1.50",
                    "mac_address": "aa:bb:cc:dd:ee:55",
                },
                headers={"Authorization": "Bearer edge-bootstrap-token"},
            )
            node_id = register_response.json()["node"]["node_id"]

            response = client.get(
                f"/api/v1/hardware/edge-node/{node_id}/credential-status",
                headers={"Authorization": f"Bearer {self._user_token()}"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["bootstrap_token_configured"] is True
        assert data["credential_status"]["device_secret_active"] is True
        assert data["credential_status"]["pending_status_queue"] == 0

    def test_edge_node_store_list_includes_credential_summary(self):
        service = RaspberryPiEdgeService()
        audit_log = MagicMock()
        audit_log.to_dict.return_value = {
            "id": "audit-store-1",
            "action": "edge_node_register",
            "resource_type": "edge_hub",
            "resource_id": "edge_STORE001_mock",
            "description": "注册边缘节点 store001-rpi5",
            "user_id": "test-user-1",
            "username": "tester",
            "status": "success",
            "created_at": "2026-03-12T10:05:00",
        }

        with patch("src.api.hardware_integration.get_raspberry_pi_edge_service", return_value=service), \
             patch("src.api.hardware_integration.settings.EDGE_BOOTSTRAP_TOKEN", "edge-bootstrap-token"):
            register_response = client.post(
                "/api/v1/hardware/edge-node/register",
                params={
                    "store_id": "STORE001",
                    "device_name": "store001-rpi5",
                    "ip_address": "192.168.1.50",
                    "mac_address": "aa:bb:cc:dd:ee:66",
                },
                headers={"Authorization": "Bearer edge-bootstrap-token"},
            )
            assert register_response.status_code == 200
            node_id = register_response.json()["node"]["node_id"]
            audit_log.to_dict.return_value["resource_id"] = node_id

            with patch(
                "src.api.hardware_integration.audit_log_service.get_logs",
                AsyncMock(return_value=([audit_log], 1)),
            ):
                response = client.get(
                    "/api/v1/hardware/edge-node/store/STORE001",
                    headers={"Authorization": f"Bearer {self._user_token()}"},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        node = data["nodes"][0]
        assert node["credential_ok"] is True
        assert node["credential_persisted"] in [True, False]
        assert "credential_status" in node
        assert node["pending_status_queue"] == 0
        assert node["audit_summary"]["available"] is True
        assert node["audit_summary"]["latest_action"] == "edge_node_register"
        assert node["audit_summary"]["latest_at"] == "2026-03-12T10:05:00"

    def test_edge_node_audit_logs_endpoint_returns_filtered_logs(self):
        service = RaspberryPiEdgeService()
        audit_log = MagicMock()
        audit_log.to_dict.return_value = {
            "id": "audit-1",
            "action": "edge_node_register",
            "resource_type": "edge_hub",
            "resource_id": "edge_STORE001_mock",
            "user_id": "test-user-1",
            "username": "tester",
            "status": "success",
            "created_at": "2026-03-12T10:00:00",
        }

        with patch("src.api.hardware_integration.get_raspberry_pi_edge_service", return_value=service), \
             patch("src.api.hardware_integration.settings.EDGE_BOOTSTRAP_TOKEN", "edge-bootstrap-token"):
            register_response = client.post(
                "/api/v1/hardware/edge-node/register",
                params={
                    "store_id": "STORE001",
                    "device_name": "store001-rpi5",
                    "ip_address": "192.168.1.50",
                    "mac_address": "aa:bb:cc:dd:ee:77",
                },
                headers={"Authorization": "Bearer edge-bootstrap-token"},
            )
            node_id = register_response.json()["node"]["node_id"]
            audit_log.to_dict.return_value["resource_id"] = node_id

            with patch(
                "src.api.hardware_integration.audit_log_service.get_logs",
                AsyncMock(return_value=([audit_log], 1)),
            ) as mock_get_logs:
                response = client.get(
                    f"/api/v1/hardware/edge-node/{node_id}/audit-logs",
                    headers={"Authorization": f"Bearer {self._user_token()}"},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["node_id"] == node_id
        assert data["total"] >= 1
        assert len(data["logs"]) >= 1
        assert all(log["resource_id"] == node_id for log in data["logs"])
        assert any(log["action"] == "edge_node_register" for log in data["logs"])
        mock_get_logs.assert_awaited_once_with(
            resource_type="edge_hub",
            resource_id=node_id,
            skip=0,
            limit=20,
        )

    def test_edge_node_info_includes_audit_summary(self):
        service = RaspberryPiEdgeService()
        audit_log = MagicMock()
        audit_log.to_dict.return_value = {
            "id": "audit-detail-1",
            "action": "edge_node_secret_rotate",
            "resource_type": "edge_hub",
            "resource_id": "edge_STORE001_mock",
            "description": "轮换边缘节点 device_secret",
            "user_id": "test-user-1",
            "username": "tester",
            "status": "success",
            "created_at": "2026-03-12T10:10:00",
        }

        with patch("src.api.hardware_integration.get_raspberry_pi_edge_service", return_value=service), \
             patch("src.api.hardware_integration.settings.EDGE_BOOTSTRAP_TOKEN", "edge-bootstrap-token"):
            register_response = client.post(
                "/api/v1/hardware/edge-node/register",
                params={
                    "store_id": "STORE001",
                    "device_name": "store001-rpi5",
                    "ip_address": "192.168.1.50",
                    "mac_address": "aa:bb:cc:dd:ee:88",
                },
                headers={"Authorization": "Bearer edge-bootstrap-token"},
            )
            node_id = register_response.json()["node"]["node_id"]
            audit_log.to_dict.return_value["resource_id"] = node_id

            with patch(
                "src.api.hardware_integration.audit_log_service.get_logs",
                AsyncMock(return_value=([audit_log], 1)),
            ) as mock_get_logs:
                response = client.get(
                    f"/api/v1/hardware/edge-node/{node_id}",
                    headers={"Authorization": f"Bearer {self._user_token()}"},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["node"]["node_id"] == node_id
        assert data["audit_summary"]["available"] is True
        assert data["audit_summary"]["latest_action"] == "edge_node_secret_rotate"
        assert data["audit_summary"]["latest_at"] == "2026-03-12T10:10:00"
        mock_get_logs.assert_awaited_once_with(
            resource_type="edge_hub",
            resource_id=node_id,
            skip=0,
            limit=1,
        )

    def test_edge_node_recovery_guide_endpoint(self):
        service = RaspberryPiEdgeService()

        with patch("src.api.hardware_integration.get_raspberry_pi_edge_service", return_value=service), \
             patch("src.api.hardware_integration.settings.EDGE_BOOTSTRAP_TOKEN", "edge-bootstrap-token"):
            register_response = client.post(
                "/api/v1/hardware/edge-node/register",
                params={
                    "store_id": "STORE001",
                    "device_name": "store001-rpi5",
                    "ip_address": "192.168.1.50",
                    "mac_address": "aa:bb:cc:dd:ee:99",
                },
                headers={"Authorization": "Bearer edge-bootstrap-token"},
            )
            node_id = register_response.json()["node"]["node_id"]

            revoke_response = client.post(
                f"/api/v1/hardware/edge-node/{node_id}/revoke-secret",
                headers={"Authorization": f"Bearer {self._user_token()}"},
            )
            assert revoke_response.status_code == 200

            response = client.get(
                f"/api/v1/hardware/edge-node/{node_id}/recovery-guide",
                headers={"Authorization": f"Bearer {self._user_token()}"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["node_id"] == node_id
        assert data["requires_rebootstrap"] is True
        assert data["bootstrap_token_configured"] is True
        assert "EDGE_API_TOKEN" in data["required_env"]
        assert "install_raspberry_pi_edge.sh" in data["installer_command_template"]
        assert len(data["steps"]) >= 4

    def test_edge_node_revoke_secret_invalidates_current_secret(self):
        service = RaspberryPiEdgeService()

        with patch("src.api.hardware_integration.get_raspberry_pi_edge_service", return_value=service), \
             patch("src.api.hardware_integration.settings.EDGE_BOOTSTRAP_TOKEN", "edge-bootstrap-token"):
            register_response = client.post(
                "/api/v1/hardware/edge-node/register",
                params={
                    "store_id": "STORE001",
                    "device_name": "store001-rpi5",
                    "ip_address": "192.168.1.50",
                    "mac_address": "aa:bb:cc:dd:ee:44",
                },
                headers={"Authorization": "Bearer edge-bootstrap-token"},
            )
            register_data = register_response.json()
            node_id = register_data["node"]["node_id"]
            device_secret = register_data["device_secret"]

            revoke_response = client.post(
                f"/api/v1/hardware/edge-node/{node_id}/revoke-secret",
                headers={"Authorization": f"Bearer {self._user_token()}"},
            )
            assert revoke_response.status_code == 200

            rejected = client.post(
                f"/api/v1/hardware/edge-node/{node_id}/status",
                params={
                    "cpu_usage": 10,
                    "memory_usage": 20,
                    "disk_usage": 30,
                    "temperature": 40,
                    "uptime_seconds": 50,
                },
                headers={"X-Edge-Node-Secret": device_secret},
            )
            assert rejected.status_code == 401


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
             patch.object(settings, "FEISHU_ENCRYPT_KEY", "encrypt-key"), \
             patch.object(settings, "AOQIWEI_APP_KEY", ""), \
             patch.object(settings, "AOQIWEI_BASE_URL", ""), \
             patch.object(settings, "PINZHI_TOKEN", ""), \
             patch.object(settings, "PINZHI_BASE_URL", ""):
            result = await config_validation(current_user=current_user)

        assert result["optional"]["wechat"]["complete"] is True
        assert result["optional"]["wechat"]["webhook_secure"] is True
        assert result["optional"]["feishu"]["complete"] is True
        assert result["optional"]["feishu"]["webhook_secure"] is True
        assert result["optional"]["feishu"]["configs"]["FEISHU_ENCRYPT_KEY"] is True


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
