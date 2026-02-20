"""
权限系统测试
测试RBAC权限模型和访问控制
"""
import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from unittest.mock import patch

from src.core.permissions import (
    Permission,
    ROLE_PERMISSIONS,
    get_user_permissions,
    has_permission,
    has_any_permission,
    has_all_permissions,
)
from src.core.dependencies import (
    get_current_active_user,
    require_permission,
    require_all_permissions,
)
from src.models.user import User, UserRole


# 测试用户工厂函数
def create_test_user(role: UserRole, user_id: str = "test_user_id") -> User:
    """创建测试用户"""
    return User(
        id=user_id,
        username=f"test_{role.value}",
        email=f"test_{role.value}@example.com",
        role=role,
        is_active=True,
        store_id="test_store_id",
    )


class TestPermissionChecking:
    """测试权限检查函数"""

    def test_get_user_permissions_admin(self):
        """测试获取管理员权限"""
        permissions = get_user_permissions(UserRole.ADMIN)
        # 管理员应该拥有所有权限
        assert len(permissions) == len(Permission)
        assert Permission.AGENT_ORDER_READ in permissions
        assert Permission.SYSTEM_CONFIG in permissions

    def test_get_user_permissions_waiter(self):
        """测试获取服务员权限"""
        permissions = get_user_permissions(UserRole.WAITER)
        # 服务员应该只有基础服务权限
        assert Permission.AGENT_ORDER_READ in permissions
        assert Permission.AGENT_ORDER_WRITE in permissions
        assert Permission.AGENT_SERVICE_READ in permissions
        assert Permission.AGENT_RESERVATION_READ in permissions
        # 服务员不应该有管理权限
        assert Permission.SYSTEM_CONFIG not in permissions
        assert Permission.USER_DELETE not in permissions

    def test_get_user_permissions_store_manager(self):
        """测试获取店长权限"""
        permissions = get_user_permissions(UserRole.STORE_MANAGER)
        # 店长应该有大部分运营权限
        assert Permission.AGENT_SCHEDULE_WRITE in permissions
        assert Permission.AGENT_ORDER_WRITE in permissions
        assert Permission.AGENT_INVENTORY_WRITE in permissions
        assert Permission.USER_WRITE in permissions
        # 但不应该有系统配置权限
        assert Permission.SYSTEM_CONFIG not in permissions

    def test_has_permission_positive(self):
        """测试用户拥有权限的情况"""
        assert has_permission(UserRole.ADMIN, Permission.SYSTEM_CONFIG) is True
        assert has_permission(UserRole.WAITER, Permission.AGENT_ORDER_READ) is True
        assert has_permission(UserRole.HEAD_CHEF, Permission.AGENT_INVENTORY_READ) is True

    def test_has_permission_negative(self):
        """测试用户没有权限的情况"""
        assert has_permission(UserRole.WAITER, Permission.SYSTEM_CONFIG) is False
        assert has_permission(UserRole.CHEF, Permission.AGENT_ORDER_WRITE) is False
        assert has_permission(UserRole.CUSTOMER_MANAGER, Permission.AGENT_INVENTORY_WRITE) is False

    def test_has_any_permission_positive(self):
        """测试用户拥有任意权限的情况"""
        permissions = [Permission.AGENT_ORDER_READ, Permission.AGENT_ORDER_WRITE]
        assert has_any_permission(UserRole.WAITER, permissions) is True
        assert has_any_permission(UserRole.STORE_MANAGER, permissions) is True

    def test_has_any_permission_negative(self):
        """测试用户没有任意权限的情况"""
        permissions = [Permission.SYSTEM_CONFIG, Permission.USER_DELETE]
        assert has_any_permission(UserRole.WAITER, permissions) is False
        assert has_any_permission(UserRole.CHEF, permissions) is False

    def test_has_all_permissions_positive(self):
        """测试用户拥有所有权限的情况"""
        permissions = [Permission.AGENT_ORDER_READ, Permission.AGENT_SERVICE_READ]
        assert has_all_permissions(UserRole.WAITER, permissions) is True
        assert has_all_permissions(UserRole.ADMIN, permissions) is True

    def test_has_all_permissions_negative(self):
        """测试用户没有所有权限的情况"""
        permissions = [Permission.AGENT_ORDER_READ, Permission.SYSTEM_CONFIG]
        assert has_all_permissions(UserRole.WAITER, permissions) is False
        permissions = [Permission.AGENT_INVENTORY_WRITE, Permission.USER_WRITE]
        assert has_all_permissions(UserRole.CHEF, permissions) is False


class TestPermissionDecorators:
    """测试权限装饰器"""

    @pytest.fixture
    def app(self):
        """创建测试应用"""
        app = FastAPI()

        @app.get("/test/order/read")
        async def read_order(current_user: User = Depends(require_permission(Permission.AGENT_ORDER_READ))):
            return {"message": "success", "user": current_user.username}

        @app.post("/test/order/write")
        async def write_order(current_user: User = Depends(require_permission(Permission.AGENT_ORDER_WRITE))):
            return {"message": "success", "user": current_user.username}

        @app.get("/test/inventory/any")
        async def inventory_any(current_user: User = Depends(require_permission(Permission.AGENT_INVENTORY_READ, Permission.AGENT_INVENTORY_WRITE))):
            return {"message": "success", "user": current_user.username}

        @app.post("/test/store/config")
        async def store_config(current_user: User = Depends(require_all_permissions(Permission.STORE_WRITE, Permission.SYSTEM_LOGS))):
            return {"message": "success", "user": current_user.username}

        return app

    @pytest.fixture
    def client(self, app):
        """创建测试客户端"""
        return TestClient(app)

    def test_require_permission_success(self, app, client):
        """测试权限装饰器 - 成功场景"""
        # 创建有权限的用户（服务员可以读订单）
        test_user = create_test_user(UserRole.WAITER)
        app.dependency_overrides[get_current_active_user] = lambda: test_user

        response = client.get("/test/order/read")
        assert response.status_code == 200
        assert response.json()["message"] == "success"
        assert response.json()["user"] == test_user.username

    def test_require_permission_denied(self, app, client):
        """测试权限装饰器 - 权限拒绝场景"""
        # 创建没有权限的用户（厨师不能写订单）
        test_user = create_test_user(UserRole.CHEF)
        app.dependency_overrides[get_current_active_user] = lambda: test_user

        response = client.post("/test/order/write")
        assert response.status_code == 403
        assert "权限不足" in response.json()["detail"]

    def test_require_any_permission_success(self, app, client):
        """测试任意权限装饰器 - 成功场景"""
        # 创建有任意一个权限的用户（库管有读权限）
        test_user = create_test_user(UserRole.WAREHOUSE_MANAGER)
        app.dependency_overrides[get_current_active_user] = lambda: test_user

        response = client.get("/test/inventory/any")
        assert response.status_code == 200
        assert response.json()["message"] == "success"

    def test_require_any_permission_denied(self, app, client):
        """测试任意权限装饰器 - 权限拒绝场景"""
        # 创建没有任何权限的用户（服务员没有库存权限）
        test_user = create_test_user(UserRole.WAITER)
        app.dependency_overrides[get_current_active_user] = lambda: test_user

        response = client.get("/test/inventory/any")
        assert response.status_code == 403
        assert "权限不足" in response.json()["detail"]
    """测试角色权限映射"""

    def test_all_roles_have_permissions(self):
        """测试所有角色都有权限定义"""
        for role in UserRole:
            permissions = get_user_permissions(role)
            assert isinstance(permissions, set)
            # 管理员应该有所有权限，其他角色至少有一些权限
            if role == UserRole.ADMIN:
                assert len(permissions) == len(Permission)
            else:
                assert len(permissions) > 0

    def test_role_hierarchy(self):
        """测试角色层级关系"""
        # 店长应该比店长助理有更多权限
        manager_perms = get_user_permissions(UserRole.STORE_MANAGER)
        assistant_perms = get_user_permissions(UserRole.ASSISTANT_MANAGER)
        assert len(manager_perms) > len(assistant_perms)
        # 店长助理的权限应该是店长权限的子集
        assert assistant_perms.issubset(manager_perms)

        # 厨师长应该比厨师有更多权限
        head_chef_perms = get_user_permissions(UserRole.HEAD_CHEF)
        chef_perms = get_user_permissions(UserRole.CHEF)
        assert len(head_chef_perms) > len(chef_perms)
        assert chef_perms.issubset(head_chef_perms)

    def test_separation_of_duties(self):
        """测试职责分离"""
        # 服务员不应该有库存写权限
        waiter_perms = get_user_permissions(UserRole.WAITER)
        assert Permission.AGENT_INVENTORY_WRITE not in waiter_perms

        # 厨师不应该有订单写权限
        chef_perms = get_user_permissions(UserRole.CHEF)
        assert Permission.AGENT_ORDER_WRITE not in chef_perms

        # 财务不应该有用户删除权限
        finance_perms = get_user_permissions(UserRole.FINANCE)
        assert Permission.USER_DELETE not in finance_perms


class TestPermissionLogging:
    """测试权限日志记录"""

    @pytest.fixture
    def app(self):
        """创建测试应用"""
        app = FastAPI()

        @app.get("/test/logged")
        async def logged_endpoint(current_user: User = Depends(require_permission(Permission.AGENT_ORDER_READ))):
            return {"message": "success"}

        return app

    @pytest.fixture
    def client(self, app):
        """创建测试客户端"""
        return TestClient(app)

    def test_permission_granted(self, app, client):
        """测试权限授予场景"""
        test_user = create_test_user(UserRole.WAITER)
        app.dependency_overrides[get_current_active_user] = lambda: test_user

        response = client.get("/test/logged")
        assert response.status_code == 200

    def test_permission_denied(self, app, client):
        """测试权限拒绝场景"""
        # 采购人员没有订单读取权限
        test_user = create_test_user(UserRole.PROCUREMENT)
        app.dependency_overrides[get_current_active_user] = lambda: test_user

        response = client.get("/test/logged")
        assert response.status_code == 403
