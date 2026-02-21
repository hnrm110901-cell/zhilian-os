"""
审计日志服务测试
Tests for Audit Log Service
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from src.services.audit_log_service import AuditLogService, audit_log_service
from src.models.audit_log import AuditLog, AuditAction


class TestAuditLogService:
    """AuditLogService测试类"""

    @pytest.mark.asyncio
    @patch('src.core.database.get_db_session')
    async def test_log_action(self, mock_get_session):
        """测试记录审计日志"""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_get_session.return_value.__aenter__.return_value = mock_session

        mock_log = MagicMock(spec=AuditLog)
        mock_log.id = uuid.uuid4()
        mock_log.action = "create"
        mock_log.resource_type = "order"
        mock_log.user_id = "USER001"
        mock_log.status = "success"

        async def mock_refresh(obj):
            obj.id = mock_log.id
            obj.action = mock_log.action
            obj.resource_type = mock_log.resource_type
            obj.user_id = mock_log.user_id
            obj.status = mock_log.status

        mock_session.refresh = mock_refresh

        service = AuditLogService()
        result = await service.log_action(
            action="create",
            resource_type="order",
            user_id="USER001",
            username="张三",
            description="创建订单",
            status="success"
        )

        assert result.action == "create"
        assert result.resource_type == "order"
        assert result.user_id == "USER001"
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    @patch('src.core.database.get_db_session')
    async def test_get_logs_no_filters(self, mock_get_session):
        """测试查询审计日志（无过滤）"""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_get_session.return_value.__aenter__.return_value = mock_session

        # Mock logs
        mock_log = MagicMock(spec=AuditLog)
        mock_log.id = uuid.uuid4()
        mock_log.action = "create"
        mock_log.resource_type = "order"
        mock_log.user_id = "USER001"
        mock_log.created_at = datetime.now()

        # Mock count result
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1

        # Mock logs result
        mock_logs_result = MagicMock()
        mock_logs_result.scalars.return_value.all.return_value = [mock_log]

        mock_session.execute.side_effect = [mock_count_result, mock_logs_result]

        service = AuditLogService()
        logs, total = await service.get_logs()

        assert len(logs) == 1
        assert total == 1
        assert logs[0].action == "create"

    @pytest.mark.asyncio
    @patch('src.core.database.get_db_session')
    async def test_get_logs_with_filters(self, mock_get_session):
        """测试查询审计日志（带过滤）"""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_get_session.return_value.__aenter__.return_value = mock_session

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0

        mock_logs_result = MagicMock()
        mock_logs_result.scalars.return_value.all.return_value = []

        mock_session.execute.side_effect = [mock_count_result, mock_logs_result]

        service = AuditLogService()
        logs, total = await service.get_logs(
            user_id="USER001",
            action="create",
            resource_type="order",
            status="success"
        )

        assert len(logs) == 0
        assert total == 0

    @pytest.mark.asyncio
    @patch('src.core.database.get_db_session')
    async def test_get_logs_with_search(self, mock_get_session):
        """测试查询审计日志（带搜索）"""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_get_session.return_value.__aenter__.return_value = mock_session

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0

        mock_logs_result = MagicMock()
        mock_logs_result.scalars.return_value.all.return_value = []

        mock_session.execute.side_effect = [mock_count_result, mock_logs_result]

        service = AuditLogService()
        logs, total = await service.get_logs(search_query="订单")

        assert len(logs) == 0
        assert total == 0

    @pytest.mark.asyncio
    @patch('src.core.database.get_db_session')
    async def test_get_user_activity_stats(self, mock_get_session):
        """测试获取用户活动统计"""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_get_session.return_value.__aenter__.return_value = mock_session

        # Mock total actions
        mock_total_result = MagicMock()
        mock_total_result.scalar.return_value = 100

        # Mock success actions
        mock_success_result = MagicMock()
        mock_success_result.scalar.return_value = 95

        # Mock action stats
        mock_action_stats_result = MagicMock()
        mock_action_stats_result.__iter__.return_value = [
            ("create", 50),
            ("update", 30),
            ("delete", 20)
        ]

        # Mock last login
        mock_last_login_result = MagicMock()
        mock_last_login_result.scalar.return_value = datetime.now()

        mock_session.execute.side_effect = [
            mock_total_result,
            mock_success_result,
            mock_action_stats_result,
            mock_last_login_result
        ]

        service = AuditLogService()
        result = await service.get_user_activity_stats("USER001", days=30)

        assert result["user_id"] == "USER001"
        assert result["total_actions"] == 100
        assert result["success_actions"] == 95
        assert result["failed_actions"] == 5
        assert result["success_rate"] == 95.0
        assert "action_stats" in result
        assert "last_login" in result

    @pytest.mark.asyncio
    @patch('src.core.database.get_db_session')
    async def test_get_user_activity_stats_no_actions(self, mock_get_session):
        """测试获取用户活动统计（无操作）"""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_get_session.return_value.__aenter__.return_value = mock_session

        mock_total_result = MagicMock()
        mock_total_result.scalar.return_value = 0

        mock_success_result = MagicMock()
        mock_success_result.scalar.return_value = 0

        mock_action_stats_result = MagicMock()
        mock_action_stats_result.__iter__.return_value = []

        mock_last_login_result = MagicMock()
        mock_last_login_result.scalar.return_value = None

        mock_session.execute.side_effect = [
            mock_total_result,
            mock_success_result,
            mock_action_stats_result,
            mock_last_login_result
        ]

        service = AuditLogService()
        result = await service.get_user_activity_stats("USER001", days=30)

        assert result["total_actions"] == 0
        assert result["success_rate"] == 0
        assert result["last_login"] is None

    @pytest.mark.asyncio
    @patch('src.core.database.get_db_session')
    async def test_get_system_activity_stats(self, mock_get_session):
        """测试获取系统活动统计"""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_get_session.return_value.__aenter__.return_value = mock_session

        # Mock total actions
        mock_total_result = MagicMock()
        mock_total_result.scalar.return_value = 1000

        # Mock active users
        mock_active_users_result = MagicMock()
        mock_active_users_result.scalar.return_value = 50

        # Mock top actions
        mock_action_stats_result = MagicMock()
        mock_action_stats_result.__iter__.return_value = [
            ("create", 400),
            ("update", 300),
            ("delete", 200)
        ]

        # Mock resource stats
        mock_resource_stats_result = MagicMock()
        mock_resource_stats_result.__iter__.return_value = [
            ("order", 500),
            ("user", 300)
        ]

        # Mock failed actions
        mock_failed_result = MagicMock()
        mock_failed_result.scalar.return_value = 50

        mock_session.execute.side_effect = [
            mock_total_result,
            mock_active_users_result,
            mock_action_stats_result,
            mock_resource_stats_result,
            mock_failed_result
        ]

        service = AuditLogService()
        result = await service.get_system_activity_stats(days=7)

        assert result["period_days"] == 7
        assert result["total_actions"] == 1000
        assert result["active_users"] == 50
        assert result["failed_actions"] == 50
        assert result["success_rate"] == 95.0
        assert len(result["top_actions"]) == 3
        assert len(result["resource_stats"]) == 2

    @pytest.mark.asyncio
    @patch('src.core.database.get_db_session')
    async def test_delete_old_logs(self, mock_get_session):
        """测试删除旧日志"""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_get_session.return_value.__aenter__.return_value = mock_session

        # Mock old logs
        mock_log1 = MagicMock(spec=AuditLog)
        mock_log2 = MagicMock(spec=AuditLog)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_log1, mock_log2]
        mock_session.execute.return_value = mock_result

        service = AuditLogService()
        count = await service.delete_old_logs(days=90)

        assert count == 2
        assert mock_session.delete.call_count == 2
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    @patch('src.core.database.get_db_session')
    async def test_delete_old_logs_none_found(self, mock_get_session):
        """测试删除旧日志（无旧日志）"""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_get_session.return_value.__aenter__.return_value = mock_session

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        service = AuditLogService()
        count = await service.delete_old_logs(days=90)

        assert count == 0
        mock_session.delete.assert_not_called()
        mock_session.commit.assert_called_once()


class TestGlobalInstance:
    """测试全局实例"""

    def test_audit_log_service_instance(self):
        """测试audit_log_service全局实例"""
        assert audit_log_service is not None
        assert isinstance(audit_log_service, AuditLogService)
