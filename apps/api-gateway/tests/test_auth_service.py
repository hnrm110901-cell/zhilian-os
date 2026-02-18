"""
Tests for Authentication Service
"""
import pytest
from datetime import timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.auth_service import AuthService
from src.models.user import User, UserRole


class TestAuthService:
    """Test cases for AuthService"""

    @pytest.fixture
    def auth_service(self):
        """Create AuthService instance"""
        return AuthService()

    @pytest.mark.asyncio
    async def test_register_user(self, auth_service, test_db):
        """Test user registration"""
        user = await auth_service.register_user(
            username="testuser",
            email="test@example.com",
            password="password123",
            full_name="Test User",
            role=UserRole.STAFF,
        )

        assert user is not None
        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.full_name == "Test User"
        assert user.role == UserRole.STAFF
        assert user.is_active is True

    @pytest.mark.asyncio
    async def test_register_duplicate_username(self, auth_service, test_db, sample_user):
        """Test registration with duplicate username"""
        with pytest.raises(ValueError, match="用户名已存在"):
            await auth_service.register_user(
                username=sample_user.username,
                email="different@example.com",
                password="password123",
                full_name="Different User",
                role=UserRole.STAFF,
            )

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self, auth_service, test_db, sample_user):
        """Test registration with duplicate email"""
        with pytest.raises(ValueError, match="邮箱已存在"):
            await auth_service.register_user(
                username="differentuser",
                email=sample_user.email,
                password="password123",
                full_name="Different User",
                role=UserRole.STAFF,
            )

    @pytest.mark.asyncio
    async def test_authenticate_user_success(self, auth_service, test_db, sample_user):
        """Test successful user authentication"""
        user = await auth_service.authenticate_user(sample_user.username, "password123")

        assert user is not None
        assert user.username == sample_user.username
        assert user.email == sample_user.email

    @pytest.mark.asyncio
    async def test_authenticate_user_wrong_password(self, auth_service, test_db, sample_user):
        """Test authentication with wrong password"""
        user = await auth_service.authenticate_user(sample_user.username, "wrongpassword")

        assert user is None

    @pytest.mark.asyncio
    async def test_authenticate_user_nonexistent(self, auth_service, test_db):
        """Test authentication with nonexistent user"""
        user = await auth_service.authenticate_user("nonexistent", "password123")

        assert user is None

    @pytest.mark.asyncio
    async def test_create_access_token_for_user(self, auth_service, test_db, sample_user):
        """Test access token creation for user"""
        token_data = await auth_service.create_access_token_for_user(sample_user)

        assert "access_token" in token_data
        assert "token_type" in token_data
        assert "expires_in" in token_data
        assert "user" in token_data
        assert token_data["token_type"] == "bearer"
        assert token_data["user"]["username"] == sample_user.username

    @pytest.mark.asyncio
    async def test_get_user_by_id(self, auth_service, test_db, sample_user):
        """Test getting user by ID"""
        user = await auth_service.get_user_by_id(str(sample_user.id))

        assert user is not None
        assert user.id == sample_user.id
        assert user.username == sample_user.username

    @pytest.mark.asyncio
    async def test_get_user_by_username(self, auth_service, test_db, sample_user):
        """Test getting user by username"""
        user = await auth_service.get_user_by_username(sample_user.username)

        assert user is not None
        assert user.id == sample_user.id
        assert user.username == sample_user.username

    @pytest.mark.asyncio
    async def test_update_user(self, auth_service, test_db, sample_user):
        """Test updating user information"""
        updated_user = await auth_service.update_user(
            user_id=str(sample_user.id),
            full_name="Updated Name",
            email="updated@example.com",
        )

        assert updated_user is not None
        assert updated_user.full_name == "Updated Name"
        assert updated_user.email == "updated@example.com"

    @pytest.mark.asyncio
    async def test_change_password_success(self, auth_service, test_db, sample_user):
        """Test successful password change"""
        result = await auth_service.change_password(
            user_id=str(sample_user.id),
            old_password="password123",
            new_password="newpassword456",
        )

        assert result is True

        # Verify new password works
        user = await auth_service.authenticate_user(sample_user.username, "newpassword456")
        assert user is not None

    @pytest.mark.asyncio
    async def test_change_password_wrong_old_password(self, auth_service, test_db, sample_user):
        """Test password change with wrong old password"""
        result = await auth_service.change_password(
            user_id=str(sample_user.id),
            old_password="wrongpassword",
            new_password="newpassword456",
        )

        assert result is False
