"""
审计日志系统测试
测试审计日志记录、查询和统计功能
"""
import pytest
from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock

from src.models.audit_log import AuditLog, AuditAction, ResourceType
from src.services.audit_log_service import audit_log_service
from src.models.user import User, UserRole
from src.core.dependencies import get_current_active_user


# 测试用户工厂函数
def create_test_user(role: UserRole = UserRole.ADMIN, user_id: str = "test_user_id") -> User:
    """创建测试用户"""
    return User(
        id=user_id,
        username=f"test_{role.value}",
        email=f"test_{role.value}@example.com",
        role=role,
        is_active=True,
        store_id="test_store_id",
    )


class TestAuditLogModel:
    """测试审计日志模型"""

    def test_audit_log_creation(self):
        """测试创建审计日志"""
        audit_log = AuditLog(
            action=AuditAction.LOGIN,
            resource_type=ResourceType.SYSTEM,
            user_id="user123",
            username="testuser",
            user_role="admin",
            description="用户登录",
            ip_address="192.168.1.1",
            request_method="POST",
            request_path="/api/v1/auth/login",
            status="success",
        )

        assert audit_log.action == AuditAction.LOGIN
        assert audit_log.resource_type == ResourceType.SYSTEM
        assert audit_log.user_id == "user123"
        assert audit_log.status == "success"

    def test_audit_log_to_dict(self):
        """测试审计日志转字典"""
        audit_log = AuditLog(
            id="log123",
            action=AuditAction.USER_CREATE,
            resource_type=ResourceType.USER,
            resource_id="user456",
            user_id="admin123",
            username="admin",
            user_role="admin",
            description="创建用户",
            status="success",
            created_at=datetime.utcnow(),
        )

        log_dict = audit_log.to_dict()

        assert log_dict["id"] == "log123"
        assert log_dict["action"] == AuditAction.USER_CREATE
        assert log_dict["resource_type"] == ResourceType.USER
        assert log_dict["user_id"] == "admin123"


class TestAuditLogService:
    """测试审计日志服务"""

    @pytest.mark.asyncio
    async def test_log_action(self):
        """测试记录操作"""
        with patch('src.core.database.get_db_session') as mock_db:
            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            audit_log = await audit_log_service.log_action(
                action=AuditAction.LOGIN,
                resource_type=ResourceType.SYSTEM,
                user_id="user123",
                username="testuser",
                user_role="waiter",
                description="用户登录",
                ip_address="192.168.1.1",
                status="success",
            )

            # 验证session.add被调用
            mock_session.add.assert_called_once()
            mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_logs_with_filters(self):
        """测试带过滤条件查询日志"""
        with patch('src.core.database.get_db_session') as mock_db:
            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            # Mock查询结果
            mock_result = MagicMock()
            mock_result.scalar.return_value = 10
            mock_result.scalars.return_value.all.return_value = []
            mock_session.execute.return_value = mock_result

            logs, total = await audit_log_service.get_logs(
                user_id="user123",
                action=AuditAction.LOGIN,
                status="success",
                skip=0,
                limit=50,
            )

            assert total == 10
            assert isinstance(logs, list)

    @pytest.mark.asyncio
    async def test_get_user_activity_stats(self):
        """测试获取用户活动统计"""
        with patch('src.core.database.get_db_session') as mock_db:
            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            # Mock不同查询的结果 - 返回None for last_login
            call_count = [0]

            def mock_execute_side_effect(*args, **kwargs):
                mock_result = MagicMock()
                call_count[0] += 1
                # 前面的查询返回数字，最后一个查询(last_login)返回None
                if call_count[0] <= 3:
                    mock_result.scalar.return_value = 100
                else:
                    mock_result.scalar.return_value = None
                return mock_result

            mock_session.execute.side_effect = mock_execute_side_effect

            stats = await audit_log_service.get_user_activity_stats(
                user_id="user123",
                days=30,
            )

            assert "user_id" in stats
            assert "total_actions" in stats
            assert "success_rate" in stats
            assert stats["last_login"] is None

    @pytest.mark.asyncio
    async def test_get_system_activity_stats(self):
        """测试获取系统活动统计"""
        with patch('src.core.database.get_db_session') as mock_db:
            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            # Mock统计结果
            mock_result = MagicMock()
            mock_result.scalar.return_value = 500
            mock_session.execute.return_value = mock_result

            stats = await audit_log_service.get_system_activity_stats(days=7)

            assert "period_days" in stats
            assert "total_actions" in stats
            assert "active_users" in stats

    @pytest.mark.asyncio
    async def test_delete_old_logs(self):
        """测试删除旧日志"""
        with patch('src.core.database.get_db_session') as mock_db:
            mock_session = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_session

            # Mock要删除的日志
            old_log1 = AuditLog(id="log1", action=AuditAction.LOGIN, resource_type=ResourceType.SYSTEM, user_id="user1")
            old_log2 = AuditLog(id="log2", action=AuditAction.LOGOUT, resource_type=ResourceType.SYSTEM, user_id="user2")

            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [old_log1, old_log2]
            mock_session.execute.return_value = mock_result

            count = await audit_log_service.delete_old_logs(days=90)

            assert count == 2
            assert mock_session.delete.call_count == 2
            mock_session.commit.assert_called_once()


class TestAuditLogAPI:
    """测试审计日志API"""

    @pytest.fixture
    def app(self):
        """创建测试应用"""
        from src.api.audit import router
        app = FastAPI()
        app.include_router(router, prefix="/api/v1/audit")
        return app

    @pytest.fixture
    def client(self, app):
        """创建测试客户端"""
        return TestClient(app)

    def test_get_audit_logs(self, app, client):
        """测试查询审计日志"""
        test_user = create_test_user(UserRole.ADMIN)
        app.dependency_overrides[get_current_active_user] = lambda: test_user

        with patch('src.api.audit.audit_log_service.get_logs') as mock_get_logs:
            # Mock返回数据
            mock_log = AuditLog(
                id="log123",
                action=AuditAction.LOGIN,
                resource_type=ResourceType.SYSTEM,
                user_id="user123",
                username="testuser",
                status="success",
                created_at=datetime.utcnow(),
            )
            mock_get_logs.return_value = ([mock_log], 1)

            response = client.get("/api/v1/audit/logs")

            assert response.status_code == 200
            data = response.json()
            assert "logs" in data
            assert "total" in data
            assert data["total"] == 1

    def test_get_audit_logs_with_filters(self, app, client):
        """测试带过滤条件查询审计日志"""
        test_user = create_test_user(UserRole.STORE_MANAGER)
        app.dependency_overrides[get_current_active_user] = lambda: test_user

        with patch('src.api.audit.audit_log_service.get_logs') as mock_get_logs:
            mock_get_logs.return_value = ([], 0)

            response = client.get(
                "/api/v1/audit/logs",
                params={
                    "user_id": "user123",
                    "action": "login",
                    "status": "success",
                    "skip": 0,
                    "limit": 20,
                }
            )

            assert response.status_code == 200
            mock_get_logs.assert_called_once()

    def test_get_user_activity_stats(self, app, client):
        """测试获取用户活动统计"""
        test_user = create_test_user(UserRole.ADMIN)
        app.dependency_overrides[get_current_active_user] = lambda: test_user

        with patch('src.api.audit.audit_log_service.get_user_activity_stats') as mock_stats:
            mock_stats.return_value = {
                "user_id": "user123",
                "period_days": 30,
                "total_actions": 150,
                "success_actions": 145,
                "failed_actions": 5,
                "success_rate": 96.67,
            }

            response = client.get("/api/v1/audit/logs/user/user123/stats")

            assert response.status_code == 200
            data = response.json()
            assert data["total_actions"] == 150
            assert data["success_rate"] == 96.67

    def test_get_system_activity_stats(self, app, client):
        """测试获取系统活动统计"""
        test_user = create_test_user(UserRole.ADMIN)
        app.dependency_overrides[get_current_active_user] = lambda: test_user

        with patch('src.api.audit.audit_log_service.get_system_activity_stats') as mock_stats:
            mock_stats.return_value = {
                "period_days": 7,
                "total_actions": 1000,
                "active_users": 50,
                "failed_actions": 20,
                "success_rate": 98.0,
            }

            response = client.get("/api/v1/audit/logs/system/stats")

            assert response.status_code == 200
            data = response.json()
            assert data["total_actions"] == 1000
            assert data["active_users"] == 50

    def test_cleanup_old_logs(self, app, client):
        """测试清理旧日志"""
        test_user = create_test_user(UserRole.ADMIN)
        app.dependency_overrides[get_current_active_user] = lambda: test_user

        with patch('src.api.audit.audit_log_service.delete_old_logs') as mock_delete:
            mock_delete.return_value = 100

            response = client.delete("/api/v1/audit/logs/cleanup?days=90")

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["deleted_count"] == 100

    def test_get_available_actions(self, app, client):
        """测试获取可用操作类型"""
        test_user = create_test_user(UserRole.WAITER)
        app.dependency_overrides[get_current_active_user] = lambda: test_user

        response = client.get("/api/v1/audit/logs/actions")

        assert response.status_code == 200
        data = response.json()
        assert "actions" in data
        assert "count" in data
        assert isinstance(data["actions"], list)

    def test_get_available_resource_types(self, app, client):
        """测试获取可用资源类型"""
        test_user = create_test_user(UserRole.WAITER)
        app.dependency_overrides[get_current_active_user] = lambda: test_user

        response = client.get("/api/v1/audit/logs/resource-types")

        assert response.status_code == 200
        data = response.json()
        assert "resource_types" in data
        assert "count" in data
        assert isinstance(data["resource_types"], list)

    def test_audit_log_permission_denied(self, app, client):
        """测试无权限访问审计日志"""
        # 服务员没有审计日志读权限
        test_user = create_test_user(UserRole.WAITER)
        app.dependency_overrides[get_current_active_user] = lambda: test_user

        response = client.get("/api/v1/audit/logs")

        assert response.status_code == 403


class TestAuditLogMiddleware:
    """测试审计日志中间件"""

    def test_should_audit_included_path(self):
        """测试应该记录的路径"""
        from src.middleware.audit_log import AuditLogMiddleware

        middleware = AuditLogMiddleware(None)

        assert middleware._should_audit("/api/v1/auth/login") is True
        assert middleware._should_audit("/api/v1/users") is True
        assert middleware._should_audit("/api/v1/finance/transactions") is True

    def test_should_audit_excluded_path(self):
        """测试不应该记录的路径"""
        from src.middleware.audit_log import AuditLogMiddleware

        middleware = AuditLogMiddleware(None)

        assert middleware._should_audit("/api/v1/health") is False
        assert middleware._should_audit("/api/v1/audit/logs") is False
        assert middleware._should_audit("/docs") is False

    def test_determine_action_and_resource_login(self):
        """测试确定登录操作类型"""
        from src.middleware.audit_log import AuditLogMiddleware

        middleware = AuditLogMiddleware(None)

        action, resource = middleware._determine_action_and_resource("POST", "/api/v1/auth/login")

        assert action == AuditAction.LOGIN
        assert resource == ResourceType.SYSTEM

    def test_determine_action_and_resource_user_create(self):
        """测试确定用户创建操作类型"""
        from src.middleware.audit_log import AuditLogMiddleware

        middleware = AuditLogMiddleware(None)

        action, resource = middleware._determine_action_and_resource("POST", "/api/v1/users")

        assert action == AuditAction.USER_CREATE
        assert resource == ResourceType.USER

    def test_generate_description(self):
        """测试生成操作描述"""
        from src.middleware.audit_log import AuditLogMiddleware

        middleware = AuditLogMiddleware(None)

        description = middleware._generate_description("POST", "/api/v1/users", 201)

        assert "创建" in description
        assert "成功" in description


class TestAuditActionConstants:
    """测试审计操作常量"""

    def test_audit_action_constants(self):
        """测试审计操作常量定义"""
        assert AuditAction.LOGIN == "login"
        assert AuditAction.LOGOUT == "logout"
        assert AuditAction.USER_CREATE == "user_create"
        assert AuditAction.ORDER_CREATE == "order_create"
        assert AuditAction.BACKUP_CREATE == "backup_create"

    def test_resource_type_constants(self):
        """测试资源类型常量定义"""
        assert ResourceType.USER == "user"
        assert ResourceType.STORE == "store"
        assert ResourceType.ORDER == "order"
        assert ResourceType.SYSTEM == "system"
