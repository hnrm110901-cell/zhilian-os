"""
权限矩阵模块 — 13 种角色 × 资源 × 操作
封装只读查询，供 roles API 使用
"""

from typing import Dict, List, Set

from ..models.user import UserRole
from .permissions import ROLE_PERMISSIONS, Permission, get_user_permissions

ROLE_LABELS: Dict[str, str] = {
    UserRole.ADMIN: "系统管理员",
    UserRole.STORE_MANAGER: "店长",
    UserRole.ASSISTANT_MANAGER: "店长助理",
    UserRole.FLOOR_MANAGER: "楼面经理",
    UserRole.CUSTOMER_MANAGER: "客户经理",
    UserRole.TEAM_LEADER: "领班",
    UserRole.WAITER: "服务员",
    UserRole.HEAD_CHEF: "厨师长",
    UserRole.STATION_MANAGER: "档口负责人",
    UserRole.CHEF: "厨师",
    UserRole.WAREHOUSE_MANAGER: "库管",
    UserRole.FINANCE: "财务",
    UserRole.PROCUREMENT: "采购",
}

# 资源分组，用于前端矩阵展示
RESOURCE_GROUPS: Dict[str, List[str]] = {
    "Agent调度": [
        Permission.AGENT_SCHEDULE_READ,
        Permission.AGENT_SCHEDULE_WRITE,
    ],
    "Agent订单": [
        Permission.AGENT_ORDER_READ,
        Permission.AGENT_ORDER_WRITE,
    ],
    "Agent库存": [
        Permission.AGENT_INVENTORY_READ,
        Permission.AGENT_INVENTORY_WRITE,
    ],
    "Agent决策": [
        Permission.AGENT_DECISION_READ,
        Permission.AGENT_DECISION_WRITE,
    ],
    "Agent绩效": [
        Permission.AGENT_PERFORMANCE_READ,
        Permission.AGENT_PERFORMANCE_WRITE,
    ],
    "用户管理": [
        Permission.USER_READ,
        Permission.USER_WRITE,
        Permission.USER_DELETE,
    ],
    "门店管理": [
        Permission.STORE_READ,
        Permission.STORE_WRITE,
    ],
    "语音设备": [
        Permission.VOICE_DEVICE_READ,
        Permission.VOICE_DEVICE_WRITE,
        Permission.VOICE_COMMAND,
    ],
}


def get_matrix() -> Dict:
    """返回角色权限矩阵，格式：{role: {label, permissions: [...]}}"""
    matrix = {}
    for role in UserRole:
        perms = get_user_permissions(role)
        matrix[role.value] = {
            "label": ROLE_LABELS.get(role, role.value),
            "permissions": [p.value for p in perms],
        }
    return matrix


def get_all_permissions() -> List[Dict]:
    """返回所有权限列表（按资源分组）"""
    result = []
    seen: Set[str] = set()
    for group, perms in RESOURCE_GROUPS.items():
        for p in perms:
            if p not in seen:
                result.append({"group": group, "value": p.value, "label": p.value})
                seen.add(p)
    # 剩余未分组权限
    for p in Permission:
        if p not in seen:
            result.append({"group": "其他", "value": p.value, "label": p.value})
    return result
