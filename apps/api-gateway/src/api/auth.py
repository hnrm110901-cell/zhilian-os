"""
Authentication API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional

from ..models.user import User, UserRole
from ..services.auth_service import AuthService
from ..core.dependencies import get_current_active_user, require_role

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


@router.post("/login")
async def login(request: LoginRequest):
    """
    用户登录
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

    token_data = await auth_service.create_access_token_for_user(user)
    return token_data


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
