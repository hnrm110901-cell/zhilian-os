"""
Authentication Service
处理用户认证相关业务逻辑
"""
from typing import Optional
from datetime import timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid

from ..models.user import User, UserRole
from ..core.security import verify_password, get_password_hash, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
from ..core.database import get_db_session


class AuthService:
    """认证服务"""

    async def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """验证用户凭证"""
        async with get_db_session() as session:
            stmt = select(User).where(User.username == username)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()

            if not user:
                return None

            if not verify_password(password, user.hashed_password):
                return None

            return user

    async def create_access_token_for_user(self, user: User) -> dict:
        """为用户创建访问令牌"""
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": str(user.id), "username": user.username, "role": user.role.value},
            expires_delta=access_token_expires,
        )

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # seconds
            "user": {
                "id": str(user.id),
                "username": user.username,
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role.value,
                "store_id": user.store_id,
            },
        }

    async def register_user(
        self,
        username: str,
        email: str,
        password: str,
        full_name: str,
        role: UserRole,
        store_id: Optional[str] = None,
    ) -> User:
        """注册新用户"""
        async with get_db_session() as session:
            # Check if username exists
            stmt = select(User).where(User.username == username)
            result = await session.execute(stmt)
            if result.scalar_one_or_none():
                raise ValueError("用户名已存在")

            # Check if email exists
            stmt = select(User).where(User.email == email)
            result = await session.execute(stmt)
            if result.scalar_one_or_none():
                raise ValueError("邮箱已存在")

            # Create new user
            user = User(
                id=uuid.uuid4(),
                username=username,
                email=email,
                hashed_password=get_password_hash(password),
                full_name=full_name,
                role=role,
                store_id=store_id,
                is_active=True,
            )

            session.add(user)
            await session.commit()
            await session.refresh(user)

            return user

    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """根据ID获取用户"""
        async with get_db_session() as session:
            stmt = select(User).where(User.id == user_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_user_by_username(self, username: str) -> Optional[User]:
        """根据用户名获取用户"""
        async with get_db_session() as session:
            stmt = select(User).where(User.username == username)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def update_user(
        self,
        user_id: str,
        full_name: Optional[str] = None,
        email: Optional[str] = None,
        role: Optional[UserRole] = None,
        store_id: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[User]:
        """更新用户信息"""
        async with get_db_session() as session:
            stmt = select(User).where(User.id == user_id)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()

            if not user:
                return None

            if full_name is not None:
                user.full_name = full_name
            if email is not None:
                user.email = email
            if role is not None:
                user.role = role
            if store_id is not None:
                user.store_id = store_id
            if is_active is not None:
                user.is_active = is_active

            await session.commit()
            await session.refresh(user)

            return user

    async def change_password(self, user_id: str, old_password: str, new_password: str) -> bool:
        """修改密码"""
        async with get_db_session() as session:
            stmt = select(User).where(User.id == user_id)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()

            if not user:
                return False

            if not verify_password(old_password, user.hashed_password):
                return False

            user.hashed_password = get_password_hash(new_password)
            await session.commit()

            return True
