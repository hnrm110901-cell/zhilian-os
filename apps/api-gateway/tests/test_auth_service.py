"""
Tests for Authentication Service
认证服务测试
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
import uuid
from src.services.auth_service import AuthService
from src.models.user import User, UserRole


@pytest.fixture
def mock_user():
    """创建模拟用户"""
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.username = "testuser"
    user.email = "test@example.com"
    user.full_name = "Test User"
    user.hashed_password = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYqVqN8Ld8u"  # "password123"
    user.role = UserRole.WAITER
    user.store_id = "STORE001"
    user.is_active = True
    user.created_at = datetime.now()
    return user


@pytest.fixture
def service():
    """创建服务实例"""
    return AuthService()


@pytest.mark.asyncio
class TestAuthenticateUser:
    """测试用户认证"""

    async def test_authenticate_user_success(self, service, mock_user):
        """测试成功认证用户"""
        with patch("src.services.auth_service.get_db_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_user
            mock_db.execute = AsyncMock(return_value=mock_result)

            with patch("src.services.auth_service.verify_password") as mock_verify:
                mock_verify.return_value = True

                result = await service.authenticate_user("testuser", "password123")

                assert result is not None
                assert result.username == "testuser"
                mock_verify.assert_called_once()

    async def test_authenticate_user_not_found(self, service):
        """测试用户不存在"""
        with patch("src.services.auth_service.get_db_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute = AsyncMock(return_value=mock_result)

            result = await service.authenticate_user("nonexistent", "password")

            assert result is None

    async def test_authenticate_user_wrong_password(self, service, mock_user):
        """测试密码错误"""
        with patch("src.services.auth_service.get_db_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_user
            mock_db.execute = AsyncMock(return_value=mock_result)

            with patch("src.services.auth_service.verify_password") as mock_verify:
                mock_verify.return_value = False

                result = await service.authenticate_user("testuser", "wrongpassword")

                assert result is None


@pytest.mark.asyncio
class TestCreateTokensForUser:
    """测试创建令牌"""

    async def test_create_tokens_for_user(self, service, mock_user):
        """测试为用户创建令牌"""
        with patch("src.services.auth_service.create_access_token") as mock_access:
            with patch("src.services.auth_service.create_refresh_token") as mock_refresh:
                mock_access.return_value = "access_token_123"
                mock_refresh.return_value = "refresh_token_456"

                result = await service.create_tokens_for_user(mock_user)

                assert result["access_token"] == "access_token_123"
                assert result["refresh_token"] == "refresh_token_456"
                assert result["token_type"] == "bearer"
                assert "expires_in" in result
                assert "user" in result
                assert result["user"]["username"] == "testuser"
                assert result["user"]["role"] == UserRole.WAITER.value

    async def test_create_tokens_includes_user_info(self, service, mock_user):
        """测试令牌包含用户信息"""
        with patch("src.services.auth_service.create_access_token") as mock_access:
            with patch("src.services.auth_service.create_refresh_token") as mock_refresh:
                mock_access.return_value = "token"
                mock_refresh.return_value = "refresh"

                result = await service.create_tokens_for_user(mock_user)

                user_info = result["user"]
                assert user_info["id"] == str(mock_user.id)
                assert user_info["username"] == mock_user.username
                assert user_info["email"] == mock_user.email
                assert user_info["full_name"] == mock_user.full_name
                assert user_info["role"] == mock_user.role.value
                assert user_info["store_id"] == mock_user.store_id
                assert user_info["is_active"] == mock_user.is_active


@pytest.mark.asyncio
class TestRefreshAccessToken:
    """测试刷新访问令牌"""

    async def test_refresh_access_token_success(self, service, mock_user):
        """测试成功刷新令牌"""
        with patch("src.services.auth_service.decode_refresh_token") as mock_decode:
            mock_decode.return_value = {"sub": str(mock_user.id)}

            with patch.object(service, "get_user_by_id") as mock_get_user:
                mock_get_user.return_value = mock_user

                with patch("src.services.auth_service.create_access_token") as mock_create:
                    mock_create.return_value = "new_access_token"

                    result = await service.refresh_access_token("refresh_token")

                    assert result["access_token"] == "new_access_token"
                    assert result["token_type"] == "bearer"
                    assert "expires_in" in result

    async def test_refresh_access_token_invalid_token(self, service):
        """测试无效的刷新令牌"""
        with patch("src.services.auth_service.decode_refresh_token") as mock_decode:
            mock_decode.return_value = {}

            with pytest.raises(ValueError, match="无效的刷新令牌"):
                await service.refresh_access_token("invalid_token")

    async def test_refresh_access_token_user_not_found(self, service):
        """测试用户不存在"""
        with patch("src.services.auth_service.decode_refresh_token") as mock_decode:
            mock_decode.return_value = {"sub": "user123"}

            with patch.object(service, "get_user_by_id") as mock_get_user:
                mock_get_user.return_value = None

                with pytest.raises(ValueError, match="用户不存在或已被禁用"):
                    await service.refresh_access_token("refresh_token")

    async def test_refresh_access_token_user_inactive(self, service, mock_user):
        """测试用户已被禁用"""
        mock_user.is_active = False

        with patch("src.services.auth_service.decode_refresh_token") as mock_decode:
            mock_decode.return_value = {"sub": str(mock_user.id)}

            with patch.object(service, "get_user_by_id") as mock_get_user:
                mock_get_user.return_value = mock_user

                with pytest.raises(ValueError, match="用户不存在或已被禁用"):
                    await service.refresh_access_token("refresh_token")


@pytest.mark.asyncio
class TestRegisterUser:
    """测试用户注册"""

    async def test_register_user_success(self, service):
        """测试成功注册用户"""
        with patch("src.services.auth_service.get_db_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            # 模拟用户名和邮箱不存在
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute = AsyncMock(return_value=mock_result)
            mock_db.add = MagicMock()
            mock_db.commit = AsyncMock()
            mock_db.refresh = AsyncMock()

            with patch("src.services.auth_service.get_password_hash") as mock_hash:
                mock_hash.return_value = "hashed_password"

                result = await service.register_user(
                    username="newuser",
                    email="new@example.com",
                    password="password123",
                    full_name="New User",
                    role=UserRole.WAITER,
                    store_id="STORE001",
                )

                assert result.username == "newuser"
                assert result.email == "new@example.com"
                assert result.full_name == "New User"
                assert result.role == UserRole.WAITER
                assert result.store_id == "STORE001"
                assert result.is_active is True
                mock_db.add.assert_called_once()
                mock_db.commit.assert_called_once()

    async def test_register_user_duplicate_username(self, service, mock_user):
        """测试用户名已存在"""
        with patch("src.services.auth_service.get_db_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            # 第一次查询返回已存在的用户
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_user
            mock_db.execute = AsyncMock(return_value=mock_result)

            with pytest.raises(ValueError, match="用户名已存在"):
                await service.register_user(
                    username="testuser",
                    email="new@example.com",
                    password="password123",
                    full_name="New User",
                    role=UserRole.WAITER,
                )

    async def test_register_user_duplicate_email(self, service, mock_user):
        """测试邮箱已存在"""
        with patch("src.services.auth_service.get_db_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            # 第一次查询用户名不存在,第二次查询邮箱已存在
            mock_result1 = MagicMock()
            mock_result1.scalar_one_or_none.return_value = None
            mock_result2 = MagicMock()
            mock_result2.scalar_one_or_none.return_value = mock_user
            mock_db.execute = AsyncMock(side_effect=[mock_result1, mock_result2])

            with pytest.raises(ValueError, match="邮箱已存在"):
                await service.register_user(
                    username="newuser",
                    email="test@example.com",
                    password="password123",
                    full_name="New User",
                    role=UserRole.WAITER,
                )


@pytest.mark.asyncio
class TestGetUser:
    """测试获取用户"""

    async def test_get_user_by_id_success(self, service, mock_user):
        """测试根据ID获取用户"""
        with patch("src.services.auth_service.get_db_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_user
            mock_db.execute = AsyncMock(return_value=mock_result)

            result = await service.get_user_by_id(str(mock_user.id))

            assert result is not None
            assert result.id == mock_user.id

    async def test_get_user_by_id_not_found(self, service):
        """测试用户不存在"""
        with patch("src.services.auth_service.get_db_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute = AsyncMock(return_value=mock_result)

            result = await service.get_user_by_id("nonexistent")

            assert result is None

    async def test_get_user_by_username_success(self, service, mock_user):
        """测试根据用户名获取用户"""
        with patch("src.services.auth_service.get_db_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_user
            mock_db.execute = AsyncMock(return_value=mock_result)

            result = await service.get_user_by_username("testuser")

            assert result is not None
            assert result.username == "testuser"

    async def test_get_user_by_username_not_found(self, service):
        """测试用户名不存在"""
        with patch("src.services.auth_service.get_db_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute = AsyncMock(return_value=mock_result)

            result = await service.get_user_by_username("nonexistent")

            assert result is None


@pytest.mark.asyncio
class TestUpdateUser:
    """测试更新用户"""

    async def test_update_user_full_name(self, service, mock_user):
        """测试更新用户全名"""
        with patch("src.services.auth_service.get_db_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_user
            mock_db.execute = AsyncMock(return_value=mock_result)
            mock_db.commit = AsyncMock()
            mock_db.refresh = AsyncMock()

            result = await service.update_user(
                str(mock_user.id),
                full_name="Updated Name",
            )

            assert result is not None
            assert result.full_name == "Updated Name"
            mock_db.commit.assert_called_once()

    async def test_update_user_email(self, service, mock_user):
        """测试更新用户邮箱"""
        with patch("src.services.auth_service.get_db_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_user
            mock_db.execute = AsyncMock(return_value=mock_result)
            mock_db.commit = AsyncMock()
            mock_db.refresh = AsyncMock()

            result = await service.update_user(
                str(mock_user.id),
                email="newemail@example.com",
            )

            assert result.email == "newemail@example.com"

    async def test_update_user_role(self, service, mock_user):
        """测试更新用户角色"""
        with patch("src.services.auth_service.get_db_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_user
            mock_db.execute = AsyncMock(return_value=mock_result)
            mock_db.commit = AsyncMock()
            mock_db.refresh = AsyncMock()

            result = await service.update_user(
                str(mock_user.id),
                role=UserRole.STORE_MANAGER,
            )

            assert result.role == UserRole.STORE_MANAGER

    async def test_update_user_store_id(self, service, mock_user):
        """测试更新用户门店"""
        with patch("src.services.auth_service.get_db_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_user
            mock_db.execute = AsyncMock(return_value=mock_result)
            mock_db.commit = AsyncMock()
            mock_db.refresh = AsyncMock()

            result = await service.update_user(
                str(mock_user.id),
                store_id="STORE002",
            )

            assert result.store_id == "STORE002"

    async def test_update_user_is_active(self, service, mock_user):
        """测试更新用户活跃状态"""
        with patch("src.services.auth_service.get_db_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_user
            mock_db.execute = AsyncMock(return_value=mock_result)
            mock_db.commit = AsyncMock()
            mock_db.refresh = AsyncMock()

            result = await service.update_user(
                str(mock_user.id),
                is_active=False,
            )

            assert result.is_active is False

    async def test_update_user_multiple_fields(self, service, mock_user):
        """测试同时更新多个字段"""
        with patch("src.services.auth_service.get_db_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_user
            mock_db.execute = AsyncMock(return_value=mock_result)
            mock_db.commit = AsyncMock()
            mock_db.refresh = AsyncMock()

            result = await service.update_user(
                str(mock_user.id),
                full_name="New Name",
                email="new@example.com",
                role=UserRole.CHEF,
            )

            assert result.full_name == "New Name"
            assert result.email == "new@example.com"
            assert result.role == UserRole.CHEF

    async def test_update_user_not_found(self, service):
        """测试更新不存在的用户"""
        with patch("src.services.auth_service.get_db_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute = AsyncMock(return_value=mock_result)

            result = await service.update_user("nonexistent", full_name="New Name")

            assert result is None


@pytest.mark.asyncio
class TestChangePassword:
    """测试修改密码"""

    async def test_change_password_success(self, service, mock_user):
        """测试成功修改密码"""
        with patch("src.services.auth_service.get_db_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_user
            mock_db.execute = AsyncMock(return_value=mock_result)
            mock_db.commit = AsyncMock()

            with patch("src.services.auth_service.verify_password") as mock_verify:
                with patch("src.services.auth_service.get_password_hash") as mock_hash:
                    mock_verify.return_value = True
                    mock_hash.return_value = "new_hashed_password"

                    result = await service.change_password(
                        str(mock_user.id),
                        "oldpassword",
                        "newpassword",
                    )

                    assert result is True
                    assert mock_user.hashed_password == "new_hashed_password"
                    mock_db.commit.assert_called_once()

    async def test_change_password_user_not_found(self, service):
        """测试用户不存在"""
        with patch("src.services.auth_service.get_db_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute = AsyncMock(return_value=mock_result)

            result = await service.change_password("nonexistent", "old", "new")

            assert result is False

    async def test_change_password_wrong_old_password(self, service, mock_user):
        """测试旧密码错误"""
        with patch("src.services.auth_service.get_db_session") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_user
            mock_db.execute = AsyncMock(return_value=mock_result)

            with patch("src.services.auth_service.verify_password") as mock_verify:
                mock_verify.return_value = False

                result = await service.change_password(
                    str(mock_user.id),
                    "wrongpassword",
                    "newpassword",
                )

                assert result is False


@pytest.mark.asyncio
class TestAuthServiceIntegration:
    """测试认证服务集成功能"""

    async def test_create_access_token_for_user_backward_compatibility(self, service, mock_user):
        """测试向后兼容的令牌创建方法"""
        with patch.object(service, "create_tokens_for_user") as mock_create:
            mock_create.return_value = {"access_token": "token"}

            result = await service.create_access_token_for_user(mock_user)

            assert result == {"access_token": "token"}
            mock_create.assert_called_once_with(mock_user)
