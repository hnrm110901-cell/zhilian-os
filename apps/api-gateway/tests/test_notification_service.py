"""
Tests for Notification Service
通知服务测试
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
import uuid
from src.services.notification_service import NotificationService, notification_service
from src.models.notification import Notification, NotificationType, NotificationPriority


@pytest.fixture
def mock_notification():
    """创建模拟通知"""
    notification = MagicMock(spec=Notification)
    notification.id = uuid.uuid4()
    notification.title = "测试通知"
    notification.message = "这是一条测试通知"
    notification.type = NotificationType.INFO.value
    notification.priority = NotificationPriority.NORMAL.value
    notification.user_id = None
    notification.role = None
    notification.store_id = None
    notification.is_read = False
    notification.read_at = None
    notification.extra_data = None
    notification.source = "test"
    notification.created_at = datetime.now()
    notification.to_dict = MagicMock(return_value={
        "id": str(notification.id),
        "title": notification.title,
        "message": notification.message,
        "type": notification.type,
        "priority": notification.priority,
    })
    return notification


@pytest.fixture
def service():
    """创建服务实例"""
    return NotificationService()


@pytest.mark.asyncio
class TestCreateNotification:
    """测试创建通知"""

    async def test_create_notification_basic(self, service, mock_notification):
        """测试创建基本通知"""
        with patch("src.services.notification_service.get_db_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db
            mock_db.add = MagicMock()
            mock_db.commit = AsyncMock()
            mock_db.refresh = AsyncMock()

            with patch.object(service, "_send_realtime_notification") as mock_send:
                mock_send.return_value = None

                result = await service.create_notification(
                    title="测试通知",
                    message="这是一条测试通知",
                    send_realtime=False,
                )

                assert result.title == "测试通知"
                assert result.message == "这是一条测试通知"
                assert result.type == NotificationType.INFO.value
                assert result.priority == NotificationPriority.NORMAL.value
                assert result.is_read is False
                mock_db.add.assert_called_once()
                mock_db.commit.assert_called_once()

    async def test_create_notification_with_user(self, service):
        """测试创建发给特定用户的通知"""
        with patch("src.services.notification_service.get_db_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db
            mock_db.add = MagicMock()
            mock_db.commit = AsyncMock()
            mock_db.refresh = AsyncMock()

            with patch.object(service, "_send_realtime_notification") as mock_send:
                mock_send.return_value = None

                result = await service.create_notification(
                    title="用户通知",
                    message="发给特定用户",
                    user_id="user123",
                    send_realtime=False,
                )

                assert result.user_id == "user123"

    async def test_create_notification_with_role(self, service):
        """测试创建发给特定角色的通知"""
        with patch("src.services.notification_service.get_db_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db
            mock_db.add = MagicMock()
            mock_db.commit = AsyncMock()
            mock_db.refresh = AsyncMock()

            with patch.object(service, "_send_realtime_notification") as mock_send:
                mock_send.return_value = None

                result = await service.create_notification(
                    title="角色通知",
                    message="发给店长",
                    role="store_manager",
                    send_realtime=False,
                )

                assert result.role == "store_manager"

    async def test_create_notification_with_store(self, service):
        """测试创建发给特定门店的通知"""
        with patch("src.services.notification_service.get_db_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db
            mock_db.add = MagicMock()
            mock_db.commit = AsyncMock()
            mock_db.refresh = AsyncMock()

            with patch.object(service, "_send_realtime_notification") as mock_send:
                mock_send.return_value = None

                result = await service.create_notification(
                    title="门店通知",
                    message="发给STORE001",
                    store_id="STORE001",
                    send_realtime=False,
                )

                assert result.store_id == "STORE001"

    async def test_create_notification_with_priority(self, service):
        """测试创建不同优先级的通知"""
        with patch("src.services.notification_service.get_db_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db
            mock_db.add = MagicMock()
            mock_db.commit = AsyncMock()
            mock_db.refresh = AsyncMock()

            with patch.object(service, "_send_realtime_notification") as mock_send:
                mock_send.return_value = None

                result = await service.create_notification(
                    title="紧急通知",
                    message="这是紧急通知",
                    type=NotificationType.ALERT,
                    priority=NotificationPriority.URGENT,
                    send_realtime=False,
                )

                assert result.type == NotificationType.ALERT.value
                assert result.priority == NotificationPriority.URGENT.value

    async def test_create_notification_with_extra_data(self, service):
        """测试创建带额外数据的通知"""
        with patch("src.services.notification_service.get_db_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db
            mock_db.add = MagicMock()
            mock_db.commit = AsyncMock()
            mock_db.refresh = AsyncMock()

            with patch.object(service, "_send_realtime_notification") as mock_send:
                mock_send.return_value = None

                extra_data = {"link": "/orders/123", "action": "view"}
                result = await service.create_notification(
                    title="订单通知",
                    message="新订单",
                    extra_data=extra_data,
                    send_realtime=False,
                )

                assert result.extra_data == extra_data

    async def test_create_notification_with_realtime(self, service):
        """测试创建通知并实时推送"""
        with patch("src.services.notification_service.get_db_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db
            mock_db.add = MagicMock()
            mock_db.commit = AsyncMock()
            mock_db.refresh = AsyncMock()

            with patch.object(service, "_send_realtime_notification") as mock_send:
                mock_send.return_value = None

                await service.create_notification(
                    title="实时通知",
                    message="测试实时推送",
                    send_realtime=True,
                )

                mock_send.assert_called_once()


@pytest.mark.asyncio
class TestSendRealtimeNotification:
    """测试实时推送通知"""

    async def test_send_to_specific_user(self, service, mock_notification):
        """测试发送给特定用户"""
        mock_notification.user_id = "user123"

        with patch("src.services.notification_service.manager") as mock_manager:
            mock_manager.send_personal_message = AsyncMock()

            await service._send_realtime_notification(mock_notification)

            mock_manager.send_personal_message.assert_called_once()

    async def test_send_to_role_and_store(self, service, mock_notification):
        """测试发送给特定门店的特定角色"""
        mock_notification.role = "waiter"
        mock_notification.store_id = "STORE001"

        with patch("src.services.notification_service.manager") as mock_manager:
            mock_manager.send_to_role = AsyncMock()

            await service._send_realtime_notification(mock_notification)

            mock_manager.send_to_role.assert_called_once()
            call_args = mock_manager.send_to_role.call_args
            assert call_args[0][1] == "waiter"
            assert call_args[0][2] == "STORE001"

    async def test_send_to_role_only(self, service, mock_notification):
        """测试发送给特定角色"""
        mock_notification.role = "store_manager"

        with patch("src.services.notification_service.manager") as mock_manager:
            mock_manager.send_to_role = AsyncMock()

            await service._send_realtime_notification(mock_notification)

            mock_manager.send_to_role.assert_called_once()

    async def test_send_to_store_only(self, service, mock_notification):
        """测试发送给特定门店"""
        mock_notification.store_id = "STORE001"

        with patch("src.services.notification_service.manager") as mock_manager:
            mock_manager.send_to_store = AsyncMock()

            await service._send_realtime_notification(mock_notification)

            mock_manager.send_to_store.assert_called_once()

    async def test_broadcast_to_all(self, service, mock_notification):
        """测试广播给所有用户"""
        with patch("src.services.notification_service.manager") as mock_manager:
            mock_manager.broadcast = AsyncMock()

            await service._send_realtime_notification(mock_notification)

            mock_manager.broadcast.assert_called_once()

    async def test_send_realtime_error_handling(self, service, mock_notification):
        """测试实时推送错误处理"""
        with patch("src.services.notification_service.manager") as mock_manager:
            mock_manager.broadcast = AsyncMock(side_effect=Exception("WebSocket error"))

            # 不应该抛出异常
            await service._send_realtime_notification(mock_notification)


@pytest.mark.asyncio
class TestGetUserNotifications:
    """测试获取用户通知"""

    async def test_get_user_notifications_basic(self, service, mock_notification):
        """测试获取用户通知"""
        with patch("src.services.notification_service.get_db_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_notification]
            mock_db.execute = AsyncMock(return_value=mock_result)

            result = await service.get_user_notifications(
                user_id="user123",
                role="waiter",
            )

            assert len(result) == 1
            assert result[0].title == "测试通知"

    async def test_get_user_notifications_with_store(self, service, mock_notification):
        """测试获取带门店过滤的通知"""
        with patch("src.services.notification_service.get_db_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_notification]
            mock_db.execute = AsyncMock(return_value=mock_result)

            result = await service.get_user_notifications(
                user_id="user123",
                role="waiter",
                store_id="STORE001",
            )

            assert len(result) == 1

    async def test_get_user_notifications_unread_only(self, service, mock_notification):
        """测试只获取未读通知"""
        with patch("src.services.notification_service.get_db_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_notification]
            mock_db.execute = AsyncMock(return_value=mock_result)

            result = await service.get_user_notifications(
                user_id="user123",
                role="waiter",
                is_read=False,
            )

            assert len(result) == 1
            assert result[0].is_read is False

    async def test_get_user_notifications_with_pagination(self, service, mock_notification):
        """测试分页获取通知"""
        with patch("src.services.notification_service.get_db_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_notification]
            mock_db.execute = AsyncMock(return_value=mock_result)

            result = await service.get_user_notifications(
                user_id="user123",
                role="waiter",
                limit=10,
                offset=0,
            )

            assert len(result) == 1


@pytest.mark.asyncio
class TestMarkAsRead:
    """测试标记已读"""

    async def test_mark_as_read_success(self, service, mock_notification):
        """测试成功标记已读"""
        mock_notification.user_id = "user123"

        with patch("src.services.notification_service.get_db_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_notification
            mock_db.execute = AsyncMock(return_value=mock_result)
            mock_db.commit = AsyncMock()

            result = await service.mark_as_read(str(mock_notification.id), "user123")

            assert result is True
            assert mock_notification.is_read is True
            assert mock_notification.read_at is not None

    async def test_mark_as_read_not_found(self, service):
        """测试标记不存在的通知"""
        with patch("src.services.notification_service.get_db_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute = AsyncMock(return_value=mock_result)

            result = await service.mark_as_read("nonexistent", "user123")

            assert result is False

    async def test_mark_as_read_wrong_user(self, service, mock_notification):
        """测试标记其他用户的通知"""
        mock_notification.user_id = "user123"

        with patch("src.services.notification_service.get_db_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_notification
            mock_db.execute = AsyncMock(return_value=mock_result)

            result = await service.mark_as_read(str(mock_notification.id), "user456")

            assert result is False

    async def test_mark_as_read_broadcast_notification(self, service, mock_notification):
        """测试标记广播通知"""
        mock_notification.user_id = None  # 广播通知

        with patch("src.services.notification_service.get_db_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_notification
            mock_db.execute = AsyncMock(return_value=mock_result)
            mock_db.commit = AsyncMock()

            result = await service.mark_as_read(str(mock_notification.id), "user123")

            assert result is True


@pytest.mark.asyncio
class TestMarkAllAsRead:
    """测试批量标记已读"""

    async def test_mark_all_as_read_success(self, service):
        """测试成功批量标记已读"""
        notifications = [MagicMock(id=uuid.uuid4()) for _ in range(3)]

        with patch.object(service, "get_user_notifications") as mock_get:
            with patch.object(service, "mark_as_read") as mock_mark:
                mock_get.return_value = notifications
                mock_mark.return_value = True

                result = await service.mark_all_as_read("user123", "waiter")

                assert result == 3
                assert mock_mark.call_count == 3

    async def test_mark_all_as_read_empty(self, service):
        """测试批量标记空列表"""
        with patch.object(service, "get_user_notifications") as mock_get:
            mock_get.return_value = []

            result = await service.mark_all_as_read("user123", "waiter")

            assert result == 0

    async def test_mark_all_as_read_partial_success(self, service):
        """测试部分成功的批量标记"""
        notifications = [MagicMock(id=uuid.uuid4()) for _ in range(3)]

        with patch.object(service, "get_user_notifications") as mock_get:
            with patch.object(service, "mark_as_read") as mock_mark:
                mock_get.return_value = notifications
                mock_mark.side_effect = [True, False, True]

                result = await service.mark_all_as_read("user123", "waiter")

                assert result == 2


@pytest.mark.asyncio
class TestDeleteNotification:
    """测试删除通知"""

    async def test_delete_notification_success(self, service, mock_notification):
        """测试成功删除通知"""
        mock_notification.user_id = "user123"

        with patch("src.services.notification_service.get_db_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_notification
            mock_db.execute = AsyncMock(return_value=mock_result)
            mock_db.delete = AsyncMock()
            mock_db.commit = AsyncMock()

            result = await service.delete_notification(str(mock_notification.id), "user123")

            assert result is True
            mock_db.delete.assert_called_once_with(mock_notification)

    async def test_delete_notification_not_found(self, service):
        """测试删除不存在的通知"""
        with patch("src.services.notification_service.get_db_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute = AsyncMock(return_value=mock_result)

            result = await service.delete_notification("nonexistent", "user123")

            assert result is False

    async def test_delete_notification_wrong_user(self, service, mock_notification):
        """测试删除其他用户的通知"""
        mock_notification.user_id = "user123"

        with patch("src.services.notification_service.get_db_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_notification
            mock_db.execute = AsyncMock(return_value=mock_result)

            result = await service.delete_notification(str(mock_notification.id), "user456")

            assert result is False


@pytest.mark.asyncio
class TestGetUnreadCount:
    """测试获取未读数量"""

    async def test_get_unread_count(self, service):
        """测试获取未读通知数量"""
        notifications = [MagicMock() for _ in range(5)]

        with patch.object(service, "get_user_notifications") as mock_get:
            mock_get.return_value = notifications

            result = await service.get_unread_count("user123", "waiter")

            assert result == 5
            mock_get.assert_called_once_with(
                user_id="user123",
                role="waiter",
                store_id=None,
                is_read=False,
            )

    async def test_get_unread_count_zero(self, service):
        """测试未读数量为0"""
        with patch.object(service, "get_user_notifications") as mock_get:
            mock_get.return_value = []

            result = await service.get_unread_count("user123", "waiter")

            assert result == 0

    async def test_get_unread_count_with_store(self, service):
        """测试带门店的未读数量"""
        notifications = [MagicMock() for _ in range(3)]

        with patch.object(service, "get_user_notifications") as mock_get:
            mock_get.return_value = notifications

            result = await service.get_unread_count("user123", "waiter", "STORE001")

            assert result == 3
            mock_get.assert_called_once_with(
                user_id="user123",
                role="waiter",
                store_id="STORE001",
                is_read=False,
            )


@pytest.mark.asyncio
class TestNotificationServiceIntegration:
    """测试通知服务集成功能"""

    async def test_notification_service_singleton(self):
        """测试通知服务单例"""
        from src.services.notification_service import notification_service as service1
        from src.services.notification_service import notification_service as service2

        assert service1 is service2

    async def test_notification_types(self):
        """测试通知类型枚举"""
        assert NotificationType.INFO.value == "info"
        assert NotificationType.WARNING.value == "warning"
        assert NotificationType.ERROR.value == "error"
        assert NotificationType.SUCCESS.value == "success"
        assert NotificationType.ALERT.value == "alert"

    async def test_notification_priorities(self):
        """测试通知优先级枚举"""
        assert NotificationPriority.LOW.value == "low"
        assert NotificationPriority.NORMAL.value == "normal"
        assert NotificationPriority.HIGH.value == "high"
        assert NotificationPriority.URGENT.value == "urgent"
