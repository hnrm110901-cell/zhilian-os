"""
OAuth登录集成测试
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)


class TestWeChatWorkOAuth:
    """企业微信OAuth测试"""

    @patch('src.services.enterprise_oauth_service.EnterpriseOAuthService.wechat_work_oauth_login')
    def test_wechat_work_callback_success(self, mock_login):
        """测试企业微信OAuth回调成功"""
        # Mock返回值
        mock_login.return_value = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "token_type": "bearer",
            "expires_in": 1800,
            "user": {
                "id": "test_user_id",
                "username": "zhangsan",
                "email": "zhangsan@company.com",
                "full_name": "张三",
                "role": "staff",
                "store_id": None,
                "is_active": True
            }
        }

        # 发送请求
        response = client.post(
            "/api/v1/auth/oauth/wechat-work/callback",
            json={
                "code": "test_code",
                "state": "/"
            }
        )

        # 验证响应
        assert response.status_code == 200
        data = response.json()
        assert data["access_token"] == "test_access_token"
        assert data["user"]["username"] == "zhangsan"
        assert mock_login.called

    def test_wechat_work_callback_missing_code(self):
        """测试企业微信OAuth回调缺少code"""
        response = client.post(
            "/api/v1/auth/oauth/wechat-work/callback",
            json={"state": "/"}
        )

        assert response.status_code == 400
        assert "缺少code参数" in response.json()["detail"]

    @patch('src.services.enterprise_oauth_service.EnterpriseOAuthService.wechat_work_oauth_login')
    def test_wechat_work_callback_oauth_error(self, mock_login):
        """测试企业微信OAuth回调授权失败"""
        mock_login.side_effect = ValueError("OAuth授权失败")

        response = client.post(
            "/api/v1/auth/oauth/wechat-work/callback",
            json={
                "code": "invalid_code",
                "state": "/"
            }
        )

        assert response.status_code == 401
        assert "OAuth授权失败" in response.json()["detail"]


class TestFeishuOAuth:
    """飞书OAuth测试"""

    @patch('src.services.enterprise_oauth_service.EnterpriseOAuthService.feishu_oauth_login')
    def test_feishu_callback_success(self, mock_login):
        """测试飞书OAuth回调成功"""
        mock_login.return_value = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "token_type": "bearer",
            "expires_in": 1800,
            "user": {
                "id": "test_user_id",
                "username": "lisi",
                "email": "lisi@company.com",
                "full_name": "李四",
                "role": "staff",
                "store_id": None,
                "is_active": True
            }
        }

        response = client.post(
            "/api/v1/auth/oauth/feishu/callback",
            json={
                "code": "test_code",
                "state": "/"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["access_token"] == "test_access_token"
        assert data["user"]["username"] == "lisi"
        assert mock_login.called

    def test_feishu_callback_missing_code(self):
        """测试飞书OAuth回调缺少code"""
        response = client.post(
            "/api/v1/auth/oauth/feishu/callback",
            json={"state": "/"}
        )

        assert response.status_code == 400
        assert "缺少code参数" in response.json()["detail"]


class TestDingTalkOAuth:
    """钉钉OAuth测试"""

    @patch('src.services.enterprise_oauth_service.EnterpriseOAuthService.dingtalk_oauth_login')
    def test_dingtalk_callback_success(self, mock_login):
        """测试钉钉OAuth回调成功"""
        mock_login.return_value = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "token_type": "bearer",
            "expires_in": 1800,
            "user": {
                "id": "test_user_id",
                "username": "wangwu",
                "email": "wangwu@company.com",
                "full_name": "王五",
                "role": "staff",
                "store_id": None,
                "is_active": True
            }
        }

        response = client.post(
            "/api/v1/auth/oauth/dingtalk/callback",
            json={
                "auth_code": "test_auth_code",
                "state": "/"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["access_token"] == "test_access_token"
        assert data["user"]["username"] == "wangwu"
        assert mock_login.called

    def test_dingtalk_callback_missing_auth_code(self):
        """测试钉钉OAuth回调缺少auth_code"""
        response = client.post(
            "/api/v1/auth/oauth/dingtalk/callback",
            json={"state": "/"}
        )

        assert response.status_code == 400
        assert "缺少auth_code参数" in response.json()["detail"]


class TestOAuthRoleMapping:
    """OAuth角色映射测试"""

    @pytest.mark.parametrize("position,expected_role", [
        ("总经理", "admin"),
        ("CEO", "admin"),
        ("技术总监", "admin"),
        ("店长", "store_manager"),
        ("门店经理", "store_manager"),
        ("服务员", "staff"),
        ("厨师", "staff"),
    ])
    def test_role_mapping_by_position(self, position, expected_role):
        """测试基于职位的角色映射"""
        from src.services.enterprise_oauth_service import EnterpriseOAuthService

        service = EnterpriseOAuthService()
        role = service._determine_role(position=position, department="")

        assert role == expected_role

    @pytest.mark.parametrize("department,expected_role", [
        ("管理层", "admin"),
        ("高管团队", "admin"),
        ("门店运营部", "store_manager"),
        ("店铺管理", "store_manager"),
        ("后厨", "staff"),
        ("前厅", "staff"),
    ])
    def test_role_mapping_by_department(self, department, expected_role):
        """测试基于部门的角色映射"""
        from src.services.enterprise_oauth_service import EnterpriseOAuthService

        service = EnterpriseOAuthService()
        role = service._determine_role(position="", department=department)

        assert role == expected_role


class TestOAuthUserCreation:
    """OAuth用户创建测试"""

    @patch('src.services.enterprise_oauth_service.AuthService')
    async def test_create_new_user(self, mock_auth_service):
        """测试创建新用户"""
        from src.services.enterprise_oauth_service import EnterpriseOAuthService

        # Mock AuthService
        mock_auth_service.get_user_by_username.return_value = None
        mock_auth_service.register_user.return_value = Mock(
            id="new_user_id",
            username="newuser",
            email="newuser@company.com",
            full_name="新用户",
            role="staff",
            store_id=None,
            is_active=True
        )

        service = EnterpriseOAuthService()
        service.auth_service = mock_auth_service

        user_info = {
            "userid": "newuser",
            "name": "新用户",
            "email": "newuser@company.com",
            "mobile": "13800138000",
            "position": "员工",
            "department": "运营部"
        }

        user = await service._create_or_update_user(user_info, "wechat_work")

        assert user.username == "newuser"
        assert mock_auth_service.register_user.called

    @patch('src.services.enterprise_oauth_service.AuthService')
    async def test_update_existing_user(self, mock_auth_service):
        """测试更新现有用户"""
        from src.services.enterprise_oauth_service import EnterpriseOAuthService

        # Mock existing user
        existing_user = Mock(
            id="existing_user_id",
            username="existinguser",
            email="old@company.com",
            full_name="旧名字",
            role="staff",
            store_id=None,
            is_active=True
        )

        mock_auth_service.get_user_by_username.return_value = existing_user
        mock_auth_service.update_user.return_value = Mock(
            id="existing_user_id",
            username="existinguser",
            email="new@company.com",
            full_name="新名字",
            role="staff",
            store_id=None,
            is_active=True
        )

        service = EnterpriseOAuthService()
        service.auth_service = mock_auth_service

        user_info = {
            "userid": "existinguser",
            "name": "新名字",
            "email": "new@company.com",
            "mobile": "13800138000",
            "position": "员工",
            "department": "运营部"
        }

        user = await service._create_or_update_user(user_info, "wechat_work")

        assert user.email == "new@company.com"
        assert user.full_name == "新名字"
        assert mock_auth_service.update_user.called
