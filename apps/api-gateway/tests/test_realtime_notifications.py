"""
Real-time Notification System Tests
实时通知系统测试
"""
import pytest
import json
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime

from src.main import app
from src.models.user import User, UserRole
from src.models.notification import NotificationType, NotificationPriority
from src.core.dependencies import get_current_active_user


@pytest.fixture
def client():
    """Test client fixture"""
    return TestClient(app)


@pytest.fixture
def mock_user():
    """Mock authenticated user"""
    user = MagicMock(spec=User)
    user.id = "test-user-123"
    user.username = "testuser"
    user.full_name = "Test User"
    user.role = UserRole.STORE_MANAGER
    user.store_id = "store-123"
    return mock_user


@pytest.fixture
def auth_client(mock_user):
    """Test client with authentication"""
    def override_get_current_user():
        return mock_user

    app.dependency_overrides[get_current_active_user] = override_get_current_user
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


class TestWebSocketConnection:
    """测试WebSocket连接"""

    def test_websocket_connection_with_valid_token(self, client):
        """测试使用有效token建立WebSocket连接"""
        # Generate a test token
        from src.core.security import create_access_token

        token = create_access_token(
            data={
                "sub": "test-user-123",
                "role": "store_manager",
                "store_id": "store-123"
            }
        )

        with client.websocket_connect(f"/api/v1/ws?token={token}") as websocket:
            # Send ping
            websocket.send_text("ping")
            # Receive pong
            data = websocket.receive_text()
            assert data == "pong"

    def test_websocket_connection_without_token(self, client):
        """测试没有token的WebSocket连接"""
        with pytest.raises(Exception):
            with client.websocket_connect("/api/v1/ws"):
                pass

    def test_websocket_connection_with_invalid_token(self, client):
        """测试使用无效token的WebSocket连接"""
        with pytest.raises(Exception):
            with client.websocket_connect("/api/v1/ws?token=invalid_token"):
                pass


class TestNotificationCreation:
    """测试通知创建"""

    @patch("src.services.notification_service.get_db_session")
    @patch("src.services.notification_service.notification_service._send_realtime_notification")
    async def test_create_notification_success(
        self,
        mock_send_realtime,
        mock_db_session,
        auth_client,
    ):
        """测试成功创建通知"""
        # Mock database session
        mock_session = AsyncMock()
        mock_db_session.return_value.__aenter__.return_value = mock_session
        mock_send_realtime.return_value = None

        request_data = {
            "title": "Test Notification",
            "message": "This is a test notification",
            "type": "info",
            "priority": "normal",
            "user_id": "test-user-123",
        }

        response = auth_client.post("/api/v1/notifications", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Test Notification"
        assert data["message"] == "This is a test notification"

    @patch("src.services.notification_service.get_db_session")
    async def test_create_notification_for_role(
        self,
        mock_db_session,
        auth_client,
    ):
        """测试为特定角色创建通知"""
        mock_session = AsyncMock()
        mock_db_session.return_value.__aenter__.return_value = mock_session

        request_data = {
            "title": "Role Notification",
            "message": "Notification for all store managers",
            "type": "info",
            "priority": "high",
            "role": "store_manager",
        }

        response = auth_client.post("/api/v1/notifications", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "store_manager"

    @patch("src.services.notification_service.get_db_session")
    async def test_create_notification_for_store(
        self,
        mock_db_session,
        auth_client,
    ):
        """测试为特定门店创建通知"""
        mock_session = AsyncMock()
        mock_db_session.return_value.__aenter__.return_value = mock_session

        request_data = {
            "title": "Store Notification",
            "message": "Notification for store 123",
            "type": "warning",
            "priority": "high",
            "store_id": "store-123",
        }

        response = auth_client.post("/api/v1/notifications", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["store_id"] == "store-123"


class TestNotificationQuery:
    """测试通知查询"""

    @patch("src.services.notification_service.get_db_session")
    async def test_get_user_notifications(
        self,
        mock_db_session,
        auth_client,
    ):
        """测试获取用户通知列表"""
        mock_session = AsyncMock()
        mock_db_session.return_value.__aenter__.return_value = mock_session

        # Mock query result
        mock_result = AsyncMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        response = auth_client.get("/api/v1/notifications")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @patch("src.services.notification_service.get_db_session")
    async def test_get_unread_notifications(
        self,
        mock_db_session,
        auth_client,
    ):
        """测试获取未读通知"""
        mock_session = AsyncMock()
        mock_db_session.return_value.__aenter__.return_value = mock_session

        mock_result = AsyncMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        response = auth_client.get("/api/v1/notifications?is_read=false")

        assert response.status_code == 200

    @patch("src.services.notification_service.get_db_session")
    async def test_get_unread_count(
        self,
        mock_db_session,
        auth_client,
    ):
        """测试获取未读通知数量"""
        mock_session = AsyncMock()
        mock_db_session.return_value.__aenter__.return_value = mock_session

        mock_result = AsyncMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        response = auth_client.get("/api/v1/notifications/unread-count")

        assert response.status_code == 200
        data = response.json()
        assert "unread_count" in data


class TestNotificationActions:
    """测试通知操作"""

    @patch("src.services.notification_service.get_db_session")
    async def test_mark_notification_as_read(
        self,
        mock_db_session,
        auth_client,
    ):
        """测试标记通知为已读"""
        mock_session = AsyncMock()
        mock_db_session.return_value.__aenter__.return_value = mock_session

        # Mock notification
        mock_notification = MagicMock()
        mock_notification.id = "notif-123"
        mock_notification.user_id = "test-user-123"
        mock_notification.is_read = False

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = mock_notification
        mock_session.execute.return_value = mock_result

        response = auth_client.put("/api/v1/notifications/notif-123/read")

        assert response.status_code == 200

    @patch("src.services.notification_service.get_db_session")
    async def test_mark_all_as_read(
        self,
        mock_db_session,
        auth_client,
    ):
        """测试标记所有通知为已读"""
        mock_session = AsyncMock()
        mock_db_session.return_value.__aenter__.return_value = mock_session

        mock_result = AsyncMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        response = auth_client.put("/api/v1/notifications/read-all")

        assert response.status_code == 200
        data = response.json()
        assert "count" in data

    @patch("src.services.notification_service.get_db_session")
    async def test_delete_notification(
        self,
        mock_db_session,
        auth_client,
    ):
        """测试删除通知"""
        mock_session = AsyncMock()
        mock_db_session.return_value.__aenter__.return_value = mock_session

        mock_notification = MagicMock()
        mock_notification.id = "notif-123"
        mock_notification.user_id = "test-user-123"

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = mock_notification
        mock_session.execute.return_value = mock_result

        response = auth_client.delete("/api/v1/notifications/notif-123")

        assert response.status_code == 200


class TestRealtimePush:
    """测试实时推送"""

    @patch("src.core.websocket.manager")
    async def test_send_personal_notification(self, mock_manager):
        """测试发送个人通知"""
        from src.services.notification_service import notification_service

        mock_manager.send_personal_message = AsyncMock()

        # Create notification with realtime push
        with patch("src.services.notification_service.get_db_session"):
            notification = MagicMock()
            notification.id = "notif-123"
            notification.user_id = "user-123"
            notification.to_dict.return_value = {"id": "notif-123"}

            await notification_service._send_realtime_notification(notification)

            mock_manager.send_personal_message.assert_called_once()

    @patch("src.core.websocket.manager")
    async def test_send_role_notification(self, mock_manager):
        """测试发送角色通知"""
        from src.services.notification_service import notification_service

        mock_manager.send_to_role = AsyncMock()

        notification = MagicMock()
        notification.id = "notif-123"
        notification.user_id = None
        notification.role = "store_manager"
        notification.store_id = "store-123"
        notification.to_dict.return_value = {"id": "notif-123"}

        await notification_service._send_realtime_notification(notification)

        mock_manager.send_to_role.assert_called_once()

    @patch("src.core.websocket.manager")
    async def test_broadcast_notification(self, mock_manager):
        """测试广播通知"""
        from src.services.notification_service import notification_service

        mock_manager.broadcast = AsyncMock()

        notification = MagicMock()
        notification.id = "notif-123"
        notification.user_id = None
        notification.role = None
        notification.store_id = None
        notification.to_dict.return_value = {"id": "notif-123"}

        await notification_service._send_realtime_notification(notification)

        mock_manager.broadcast.assert_called_once()


class TestConnectionManager:
    """测试连接管理器"""

    def test_connection_manager_connect(self):
        """测试连接管理器连接"""
        from src.core.websocket import ConnectionManager

        manager = ConnectionManager()
        websocket = MagicMock()

        # Test connection
        assert len(manager.get_active_users()) == 0

    def test_connection_manager_disconnect(self):
        """测试连接管理器断开"""
        from src.core.websocket import ConnectionManager

        manager = ConnectionManager()
        websocket = MagicMock()

        manager.disconnect(websocket, "user-123")

        assert "user-123" not in manager.active_connections

    def test_get_connection_count(self):
        """测试获取连接数"""
        from src.core.websocket import ConnectionManager

        manager = ConnectionManager()

        count = manager.get_connection_count()
        assert count == 0


class TestNotificationTemplates:
    """测试通知模板"""

    def test_get_template(self):
        """测试获取模板"""
        from src.services.multi_channel_notification import NotificationTemplate

        template = NotificationTemplate.get_template("inventory_low")

        assert template is not None
        assert template["title"] == "库存预警"
        assert "channels" in template

    def test_render_template(self):
        """测试渲染模板"""
        from src.services.multi_channel_notification import NotificationTemplate

        rendered = NotificationTemplate.render_template(
            "inventory_low",
            item_name="鸡肉",
            current_stock=5
        )

        assert rendered is not None
        assert "鸡肉" in rendered["content"]
        assert "5" in rendered["content"]

    def test_get_nonexistent_template(self):
        """测试获取不存在的模板"""
        from src.services.multi_channel_notification import NotificationTemplate

        template = NotificationTemplate.get_template("nonexistent")

        assert template is None


class TestMultiChannelNotification:
    """测试多渠道通知"""

    @patch("src.services.multi_channel_notification.EmailNotificationHandler.send")
    async def test_send_email_notification(self, mock_send):
        """测试发送邮件通知"""
        from src.services.multi_channel_notification import EmailNotificationHandler

        handler = EmailNotificationHandler()
        mock_send.return_value = True

        result = await handler.send(
            recipient="test@example.com",
            title="Test Email",
            content="This is a test email"
        )

        assert result is True

    @patch("src.services.multi_channel_notification.SMSNotificationHandler.send")
    async def test_send_sms_notification(self, mock_send):
        """测试发送短信通知"""
        from src.services.multi_channel_notification import SMSNotificationHandler

        handler = SMSNotificationHandler()
        mock_send.return_value = True

        result = await handler.send(
            recipient="13800138000",
            title="Test SMS",
            content="This is a test SMS"
        )

        assert result is True


class TestNotificationPriority:
    """测试通知优先级"""

    @patch("src.services.notification_service.get_db_session")
    async def test_urgent_notification(
        self,
        mock_db_session,
        auth_client,
    ):
        """测试紧急通知"""
        mock_session = AsyncMock()
        mock_db_session.return_value.__aenter__.return_value = mock_session

        request_data = {
            "title": "Urgent Alert",
            "message": "System critical error",
            "type": "alert",
            "priority": "urgent",
        }

        response = auth_client.post("/api/v1/notifications", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["priority"] == "urgent"


class TestNotificationPerformance:
    """测试通知性能"""

    @patch("src.services.notification_service.get_db_session")
    async def test_bulk_notification_creation(
        self,
        mock_db_session,
        auth_client,
    ):
        """测试批量创建通知的性能"""
        import time

        mock_session = AsyncMock()
        mock_db_session.return_value.__aenter__.return_value = mock_session

        start_time = time.time()

        # Create 10 notifications
        for i in range(10):
            request_data = {
                "title": f"Notification {i}",
                "message": f"Test notification {i}",
                "type": "info",
                "priority": "normal",
            }

            response = auth_client.post("/api/v1/notifications", json=request_data)
            assert response.status_code == 200

        end_time = time.time()

        # Should complete in reasonable time (< 5 seconds for 10 notifications)
        assert (end_time - start_time) < 5.0
