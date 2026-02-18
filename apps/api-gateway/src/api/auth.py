"""
Authentication API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional, List

from ..models.user import User, UserRole
from ..services.auth_service import AuthService
from ..core.dependencies import get_current_active_user, require_role
from ..core.permissions import get_user_permissions

router = APIRouter()
auth_service = AuthService()


# Request/Response models
class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    full_name: str
    role: UserRole
    store_id: Optional[str] = None


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    full_name: Optional[str]
    role: str
    store_id: Optional[str]
    is_active: bool

    class Config:
        from_attributes = True


class UpdateUserRequest(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[UserRole] = None
    store_id: Optional[str] = None
    is_active: Optional[bool] = None


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


@router.post("/login")
async def login(request: LoginRequest):
    """
    用户登录

    使用用户名和密码进行身份验证，成功后返回访问令牌和刷新令牌。

    **认证要求**: 无需认证

    **令牌说明**:
    - `access_token`: 访问令牌，有效期30分钟，用于API请求认证
    - `refresh_token`: 刷新令牌，有效期7天，用于获取新的访问令牌

    **使用方法**:
    1. 保存返回的两个令牌
    2. 在后续API请求中使用访问令牌: `Authorization: Bearer <access_token>`
    3. 访问令牌过期后，使用刷新令牌调用 `/auth/refresh` 获取新令牌

    **示例请求**:
    ```json
    {
        "username": "admin",
        "password": "admin123"
    }
    ```

    **示例响应**:
    ```json
    {
        "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
        "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
        "token_type": "bearer",
        "expires_in": 1800,
        "user": {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "username": "admin",
            "email": "admin@example.com",
            "full_name": "系统管理员",
            "role": "admin",
            "store_id": "STORE_001",
            "is_active": true
        }
    }
    ```

    **错误响应**:
    - `401 Unauthorized`: 用户名或密码错误
    - `403 Forbidden`: 用户已被禁用
    """
    user = await auth_service.authenticate_user(request.username, request.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被禁用",
        )

    token_data = await auth_service.create_tokens_for_user(user)
    return token_data


@router.post("/refresh")
async def refresh_token(request: RefreshTokenRequest):
    """
    刷新访问令牌

    使用刷新令牌获取新的访问令牌，无需重新登录。

    **认证要求**: 无需认证（使用刷新令牌）

    **使用场景**:
    - 访问令牌过期（30分钟后）
    - 前端自动刷新令牌机制
    - 避免频繁要求用户重新登录

    **示例请求**:
    ```json
    {
        "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
    }
    ```

    **示例响应**:
    ```json
    {
        "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
        "token_type": "bearer",
        "expires_in": 1800
    }
    ```

    **错误响应**:
    - `401 Unauthorized`: 刷新令牌无效或已过期
    - `401 Unauthorized`: 用户不存在或已被禁用
    """
    try:
        token_data = await auth_service.refresh_access_token(request.refresh_token)
        return token_data
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="刷新令牌失败",
        )


@router.post("/register", response_model=UserResponse)
async def register(
    request: RegisterRequest,
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.STORE_MANAGER)),
):
    """
    注册新用户 (仅管理员和店长可操作)
    """
    try:
        user = await auth_service.register_user(
            username=request.username,
            email=request.email,
            password=request.password,
            full_name=request.full_name,
            role=request.role,
            store_id=request.store_id,
        )
        return UserResponse(
            id=str(user.id),
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            role=user.role.value,
            store_id=user.store_id,
            is_active=user.is_active,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_active_user)):
    """
    获取当前登录用户信息

    返回当前认证用户的详细信息。

    **认证要求**: 需要有效的访问令牌

    **示例响应**:
    ```json
    {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "username": "admin",
        "email": "admin@example.com",
        "full_name": "系统管理员",
        "role": "admin",
        "store_id": "STORE_001",
        "is_active": true
    }
    ```

    **错误响应**:
    - `401 Unauthorized`: 未提供令牌或令牌无效
    - `403 Forbidden`: 用户已被禁用
    """
    return UserResponse(
        id=str(current_user.id),
        username=current_user.username,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role.value,
        store_id=current_user.store_id,
        is_active=current_user.is_active,
    )


@router.get("/me/permissions")
async def get_current_user_permissions(current_user: User = Depends(get_current_active_user)):
    """
    获取当前用户的权限列表

    返回当前用户角色对应的所有权限。用于前端权限控制和UI元素显示。

    **认证要求**: 需要有效的访问令牌

    **权限类型**:
    - `agent:*:read/write`: Agent操作权限
    - `user:read/write/delete`: 用户管理权限
    - `store:read/write/delete`: 门店管理权限
    - `system:config/logs`: 系统配置权限

    **示例响应**:
    ```json
    {
        "role": "store_manager",
        "permissions": [
            "agent:schedule:read",
            "agent:schedule:write",
            "agent:order:read",
            "agent:order:write",
            "agent:inventory:read",
            "agent:inventory:write",
            "user:read",
            "user:write",
            "store:read"
        ]
    }
    ```

    **错误响应**:
    - `401 Unauthorized`: 未提供令牌或令牌无效
    """
    permissions = get_user_permissions(current_user.role)
    return {
        "role": current_user.role.value,
        "permissions": [perm.value for perm in permissions],
    }


@router.put("/me", response_model=UserResponse)
async def update_current_user(
    request: UpdateUserRequest,
    current_user: User = Depends(get_current_active_user),
):
    """
    更新当前用户信息 (不能修改角色和状态)
    """
    user = await auth_service.update_user(
        user_id=str(current_user.id),
        full_name=request.full_name,
        email=request.email,
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )

    return UserResponse(
        id=str(user.id),
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        role=user.role.value,
        store_id=user.store_id,
        is_active=user.is_active,
    )


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_active_user),
):
    """
    修改密码
    """
    success = await auth_service.change_password(
        user_id=str(current_user.id),
        old_password=request.old_password,
        new_password=request.new_password,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="原密码错误",
        )

    return {"message": "密码修改成功"}


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    request: UpdateUserRequest,
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.STORE_MANAGER)),
):
    """
    更新用户信息 (仅管理员和店长可操作)
    """
    user = await auth_service.update_user(
        user_id=user_id,
        full_name=request.full_name,
        email=request.email,
        role=request.role,
        store_id=request.store_id,
        is_active=request.is_active,
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )

    return UserResponse(
        id=str(user.id),
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        role=user.role.value,
        store_id=user.store_id,
        is_active=user.is_active,
    )
