"""
权限管理模块
定义角色权限和访问控制规则
"""
from typing import List, Set, Dict
from enum import Enum

from ..models.user import UserRole


class Permission(str, Enum):
    """系统权限枚举"""
    # Agent访问权限
    AGENT_SCHEDULE_READ = "agent:schedule:read"
    AGENT_SCHEDULE_WRITE = "agent:schedule:write"

    AGENT_ORDER_READ = "agent:order:read"
    AGENT_ORDER_WRITE = "agent:order:write"

    AGENT_INVENTORY_READ = "agent:inventory:read"
    AGENT_INVENTORY_WRITE = "agent:inventory:write"

    AGENT_SERVICE_READ = "agent:service:read"
    AGENT_SERVICE_WRITE = "agent:service:write"

    AGENT_TRAINING_READ = "agent:training:read"
    AGENT_TRAINING_WRITE = "agent:training:write"

    AGENT_DECISION_READ = "agent:decision:read"
    AGENT_DECISION_WRITE = "agent:decision:write"

    AGENT_RESERVATION_READ = "agent:reservation:read"
    AGENT_RESERVATION_WRITE = "agent:reservation:write"

    # 用户管理权限
    USER_READ = "user:read"
    USER_WRITE = "user:write"
    USER_DELETE = "user:delete"

    # 门店管理权限
    STORE_READ = "store:read"
    STORE_WRITE = "store:write"
    STORE_DELETE = "store:delete"

    # 系统配置权限
    SYSTEM_CONFIG = "system:config"
    SYSTEM_LOGS = "system:logs"


# 角色权限映射
ROLE_PERMISSIONS: Dict[UserRole, Set[Permission]] = {
    # 系统管理员 - 拥有所有权限
    UserRole.ADMIN: set(Permission),

    # 店长 - 拥有门店所有运营权限
    UserRole.STORE_MANAGER: {
        Permission.AGENT_SCHEDULE_READ,
        Permission.AGENT_SCHEDULE_WRITE,
        Permission.AGENT_ORDER_READ,
        Permission.AGENT_ORDER_WRITE,
        Permission.AGENT_INVENTORY_READ,
        Permission.AGENT_INVENTORY_WRITE,
        Permission.AGENT_SERVICE_READ,
        Permission.AGENT_SERVICE_WRITE,
        Permission.AGENT_TRAINING_READ,
        Permission.AGENT_TRAINING_WRITE,
        Permission.AGENT_DECISION_READ,
        Permission.AGENT_DECISION_WRITE,
        Permission.AGENT_RESERVATION_READ,
        Permission.AGENT_RESERVATION_WRITE,
        Permission.USER_READ,
        Permission.USER_WRITE,
        Permission.STORE_READ,
        Permission.SYSTEM_LOGS,
    },

    # 店长助理 - 协助店长管理
    UserRole.ASSISTANT_MANAGER: {
        Permission.AGENT_SCHEDULE_READ,
        Permission.AGENT_SCHEDULE_WRITE,
        Permission.AGENT_ORDER_READ,
        Permission.AGENT_ORDER_WRITE,
        Permission.AGENT_INVENTORY_READ,
        Permission.AGENT_SERVICE_READ,
        Permission.AGENT_SERVICE_WRITE,
        Permission.AGENT_TRAINING_READ,
        Permission.AGENT_DECISION_READ,
        Permission.AGENT_RESERVATION_READ,
        Permission.AGENT_RESERVATION_WRITE,
        Permission.USER_READ,
        Permission.STORE_READ,
    },

    # 楼面经理 - 前厅运营管理
    UserRole.FLOOR_MANAGER: {
        Permission.AGENT_SCHEDULE_READ,
        Permission.AGENT_ORDER_READ,
        Permission.AGENT_ORDER_WRITE,
        Permission.AGENT_SERVICE_READ,
        Permission.AGENT_SERVICE_WRITE,
        Permission.AGENT_TRAINING_READ,
        Permission.AGENT_RESERVATION_READ,
        Permission.AGENT_RESERVATION_WRITE,
        Permission.USER_READ,
    },

    # 客户经理 - 客户关系和预订管理
    UserRole.CUSTOMER_MANAGER: {
        Permission.AGENT_ORDER_READ,
        Permission.AGENT_SERVICE_READ,
        Permission.AGENT_SERVICE_WRITE,
        Permission.AGENT_RESERVATION_READ,
        Permission.AGENT_RESERVATION_WRITE,
        Permission.AGENT_DECISION_READ,
    },

    # 领班 - 前厅基层管理
    UserRole.TEAM_LEADER: {
        Permission.AGENT_SCHEDULE_READ,
        Permission.AGENT_ORDER_READ,
        Permission.AGENT_ORDER_WRITE,
        Permission.AGENT_SERVICE_READ,
        Permission.AGENT_RESERVATION_READ,
        Permission.AGENT_TRAINING_READ,
    },

    # 服务员 - 基础服务操作
    UserRole.WAITER: {
        Permission.AGENT_ORDER_READ,
        Permission.AGENT_ORDER_WRITE,
        Permission.AGENT_SERVICE_READ,
        Permission.AGENT_RESERVATION_READ,
    },

    # 厨师长 - 后厨全面管理
    UserRole.HEAD_CHEF: {
        Permission.AGENT_SCHEDULE_READ,
        Permission.AGENT_SCHEDULE_WRITE,
        Permission.AGENT_ORDER_READ,
        Permission.AGENT_INVENTORY_READ,
        Permission.AGENT_INVENTORY_WRITE,
        Permission.AGENT_TRAINING_READ,
        Permission.AGENT_DECISION_READ,
        Permission.USER_READ,
    },

    # 档口负责人 - 档口运营管理
    UserRole.STATION_MANAGER: {
        Permission.AGENT_SCHEDULE_READ,
        Permission.AGENT_ORDER_READ,
        Permission.AGENT_INVENTORY_READ,
        Permission.AGENT_TRAINING_READ,
    },

    # 厨师 - 基础后厨操作
    UserRole.CHEF: {
        Permission.AGENT_ORDER_READ,
        Permission.AGENT_INVENTORY_READ,
    },

    # 库管 - 库存管理
    UserRole.WAREHOUSE_MANAGER: {
        Permission.AGENT_INVENTORY_READ,
        Permission.AGENT_INVENTORY_WRITE,
        Permission.AGENT_DECISION_READ,
        Permission.STORE_READ,
    },

    # 财务 - 财务数据访问
    UserRole.FINANCE: {
        Permission.AGENT_ORDER_READ,
        Permission.AGENT_INVENTORY_READ,
        Permission.AGENT_DECISION_READ,
        Permission.STORE_READ,
        Permission.SYSTEM_LOGS,
    },

    # 采购 - 采购和库存
    UserRole.PROCUREMENT: {
        Permission.AGENT_INVENTORY_READ,
        Permission.AGENT_INVENTORY_WRITE,
        Permission.AGENT_DECISION_READ,
    },
}


def get_user_permissions(role: UserRole) -> Set[Permission]:
    """获取用户角色的所有权限"""
    return ROLE_PERMISSIONS.get(role, set())


def has_permission(role: UserRole, permission: Permission) -> bool:
    """检查角色是否拥有指定权限"""
    user_permissions = get_user_permissions(role)
    return permission in user_permissions


def has_any_permission(role: UserRole, permissions: List[Permission]) -> bool:
    """检查角色是否拥有任意一个指定权限"""
    user_permissions = get_user_permissions(role)
    return any(perm in user_permissions for perm in permissions)


def has_all_permissions(role: UserRole, permissions: List[Permission]) -> bool:
    """检查角色是否拥有所有指定权限"""
    user_permissions = get_user_permissions(role)
    return all(perm in user_permissions for perm in permissions)
