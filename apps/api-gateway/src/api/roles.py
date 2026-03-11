"""
角色权限管理 API
GET  /api/v1/roles              — 所有角色列表
GET  /api/v1/roles/{role}/permissions — 某角色的权限列表
GET  /api/v1/roles/matrix       — 完整权限矩阵（管理后台用）
GET  /api/v1/roles/permissions  — 所有可用权限枚举
"""
from fastapi import APIRouter, Depends

from ..core.dependencies import get_current_active_user, require_role
from ..core.permission_matrix import get_matrix, get_all_permissions, ROLE_LABELS
from ..core.permissions import get_user_permissions
from ..models.user import User, UserRole

router = APIRouter(prefix="/roles", tags=["roles"])


@router.get("")
async def list_roles(
    _current_user: User = Depends(get_current_active_user),
):
    """返回所有角色列表（含标签）"""
    return [
        {"value": role.value, "label": ROLE_LABELS.get(role, role.value)}
        for role in UserRole
    ]


@router.get("/matrix")
async def get_permission_matrix(
    _current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    """返回完整角色权限矩阵（仅管理员可见）"""
    return get_matrix()


@router.get("/permissions")
async def list_all_permissions(
    _current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    """返回所有可用权限（按资源分组）"""
    return get_all_permissions()


@router.get("/{role}/permissions")
async def get_role_permissions(
    role: UserRole,
    _current_user: User = Depends(get_current_active_user),
):
    """返回指定角色的权限列表"""
    perms = get_user_permissions(role)
    return {
        "role": role.value,
        "label": ROLE_LABELS.get(role, role.value),
        "permissions": [p.value for p in perms],
    }
