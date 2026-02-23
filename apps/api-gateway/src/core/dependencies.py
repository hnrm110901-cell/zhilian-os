"""
FastAPI dependencies for authentication and authorization
"""
from typing import Optional, List
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from .security import decode_access_token
from .database import get_db
from .permissions import Permission, has_permission, has_any_permission
from ..models.user import User, UserRole

# HTTP Bearer token scheme
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    session: AsyncSession = Depends(get_db),
) -> User:
    """获取当前登录用户"""
    token = credentials.credentials
    payload = decode_access_token(token)

    user_id: str = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证凭证",
        )

    # Query user from database
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被禁用",
        )

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """获取当前活跃用户"""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被禁用",
        )
    return current_user


def require_role(*allowed_roles: UserRole):
    """角色权限检查装饰器"""

    async def role_checker(current_user: User = Depends(get_current_active_user)) -> User:
        if current_user.role not in allowed_roles and current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"权限不足,需要以下角色之一: {', '.join([r.value for r in allowed_roles])}",
            )
        return current_user

    return role_checker


def require_permission(*required_permissions: Permission):
    """权限检查装饰器 - 需要拥有任意一个指定权限"""

    async def permission_checker(current_user: User = Depends(get_current_active_user)) -> User:
        # 管理员拥有所有权限
        if current_user.role == UserRole.ADMIN:
            return current_user

        # 检查用户是否拥有任意一个所需权限
        if not has_any_permission(current_user.role, list(required_permissions)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"权限不足,需要以下权限之一: {', '.join([p.value for p in required_permissions])}",
            )
        return current_user

    return permission_checker


def require_all_permissions(*required_permissions: Permission):
    """权限检查装饰器 - 需要拥有所有指定权限"""

    async def permission_checker(current_user: User = Depends(get_current_active_user)) -> User:
        # 管理员拥有所有权限
        if current_user.role == UserRole.ADMIN:
            return current_user

        # 检查用户是否拥有所有所需权限
        for perm in required_permissions:
            if not has_permission(current_user.role, perm):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"权限不足,缺少权限: {perm.value}",
                )
        return current_user

    return permission_checker


async def get_current_tenant(
    current_user: User = Depends(get_current_active_user),
) -> str:
    """
    FastAPI 依赖：从当前登录用户提取租户ID（store_id）

    用法:
        tenant_id: str = Depends(get_current_tenant)
    """
    from .tenant_context import TenantContext

    store_id = getattr(current_user, "store_id", None)
    if not store_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前用户未关联门店，无法确定租户上下文",
        )
    TenantContext.set_current_tenant(store_id)
    return store_id
