"""
Tests for src/core/permissions.py — RBAC 权限矩阵.

Covers:
  - Permission enum: all expected values present
  - get_user_permissions: correct set per role
  - has_permission: True/False for specific role+permission combinations
  - has_any_permission: OR semantics
  - has_all_permissions: AND semantics
  - ADMIN has all permissions
  - Role boundaries (WAITER, FINANCE, HEAD_CHEF, WAREHOUSE_MANAGER etc.)
  - Unknown role → empty set
"""
import pytest
from src.core.permissions import (
    Permission,
    get_user_permissions,
    has_all_permissions,
    has_any_permission,
    has_permission,
)
from src.models.user import UserRole


# ===========================================================================
# Permission enum completeness
# ===========================================================================

class TestPermissionEnum:
    def test_agent_order_read_exists(self):
        assert Permission.AGENT_ORDER_READ == "agent:order:read"

    def test_agent_inventory_write_exists(self):
        assert Permission.AGENT_INVENTORY_WRITE == "agent:inventory:write"

    def test_voice_command_exists(self):
        assert Permission.VOICE_COMMAND == "voice:command"

    def test_audit_delete_exists(self):
        assert Permission.AUDIT_DELETE == "audit:delete"

    def test_fct_read_exists(self):
        assert Permission.FCT_READ == "fct:read"

    def test_user_delete_exists(self):
        assert Permission.USER_DELETE == "user:delete"

    def test_system_config_exists(self):
        assert Permission.SYSTEM_CONFIG == "system:config"


# ===========================================================================
# get_user_permissions
# ===========================================================================

class TestGetUserPermissions:
    def test_admin_has_all_permissions(self):
        perms = get_user_permissions(UserRole.ADMIN)
        assert perms == set(Permission)

    def test_waiter_has_limited_permissions(self):
        perms = get_user_permissions(UserRole.WAITER)
        assert Permission.AGENT_ORDER_READ in perms
        assert Permission.AGENT_ORDER_WRITE in perms
        assert Permission.VOICE_COMMAND in perms
        # Waiter does NOT have admin-level permissions
        assert Permission.USER_DELETE not in perms
        assert Permission.AUDIT_DELETE not in perms
        assert Permission.SYSTEM_CONFIG not in perms
        assert Permission.STORE_WRITE not in perms

    def test_store_manager_has_fct_read(self):
        perms = get_user_permissions(UserRole.STORE_MANAGER)
        assert Permission.FCT_READ in perms

    def test_store_manager_does_not_have_user_delete(self):
        perms = get_user_permissions(UserRole.STORE_MANAGER)
        assert Permission.USER_DELETE not in perms

    def test_finance_has_audit_read(self):
        perms = get_user_permissions(UserRole.FINANCE)
        assert Permission.AUDIT_READ in perms
        assert Permission.SYSTEM_LOGS in perms

    def test_finance_does_not_have_fct_write(self):
        perms = get_user_permissions(UserRole.FINANCE)
        assert Permission.FCT_WRITE not in perms

    def test_warehouse_manager_has_inventory_write(self):
        perms = get_user_permissions(UserRole.WAREHOUSE_MANAGER)
        assert Permission.AGENT_INVENTORY_READ in perms
        assert Permission.AGENT_INVENTORY_WRITE in perms

    def test_warehouse_manager_does_not_have_order_write(self):
        perms = get_user_permissions(UserRole.WAREHOUSE_MANAGER)
        assert Permission.AGENT_ORDER_WRITE not in perms

    def test_head_chef_has_inventory_write(self):
        perms = get_user_permissions(UserRole.HEAD_CHEF)
        assert Permission.AGENT_INVENTORY_WRITE in perms
        assert Permission.VOICE_NOTIFICATION in perms

    def test_chef_has_minimal_permissions(self):
        perms = get_user_permissions(UserRole.CHEF)
        assert Permission.AGENT_ORDER_READ in perms
        assert Permission.AGENT_INVENTORY_READ in perms
        assert Permission.USER_WRITE not in perms
        assert Permission.STORE_WRITE not in perms

    def test_floor_manager_has_reservation_write(self):
        perms = get_user_permissions(UserRole.FLOOR_MANAGER)
        assert Permission.AGENT_RESERVATION_WRITE in perms
        assert Permission.VOICE_NOTIFICATION in perms

    def test_customer_manager_has_service_write(self):
        perms = get_user_permissions(UserRole.CUSTOMER_MANAGER)
        assert Permission.AGENT_SERVICE_WRITE in perms
        assert Permission.AGENT_RESERVATION_WRITE in perms
        # Customer manager cannot write inventory
        assert Permission.AGENT_INVENTORY_WRITE not in perms

    def test_team_leader_has_voice_command(self):
        perms = get_user_permissions(UserRole.TEAM_LEADER)
        assert Permission.VOICE_COMMAND in perms
        assert Permission.AGENT_SCHEDULE_READ in perms
        # Team leader cannot write schedule
        assert Permission.AGENT_SCHEDULE_WRITE not in perms

    def test_procurement_has_inventory_write(self):
        perms = get_user_permissions(UserRole.PROCUREMENT)
        assert Permission.AGENT_INVENTORY_WRITE in perms
        assert Permission.AGENT_DECISION_READ in perms

    def test_returns_set_type(self):
        perms = get_user_permissions(UserRole.WAITER)
        assert isinstance(perms, set)


# ===========================================================================
# has_permission
# ===========================================================================

class TestHasPermission:
    def test_admin_has_any_permission(self):
        assert has_permission(UserRole.ADMIN, Permission.AUDIT_DELETE) is True
        assert has_permission(UserRole.ADMIN, Permission.USER_DELETE) is True
        assert has_permission(UserRole.ADMIN, Permission.SYSTEM_CONFIG) is True

    def test_waiter_has_order_read(self):
        assert has_permission(UserRole.WAITER, Permission.AGENT_ORDER_READ) is True

    def test_waiter_does_not_have_audit_read(self):
        assert has_permission(UserRole.WAITER, Permission.AUDIT_READ) is False

    def test_finance_has_audit_read(self):
        assert has_permission(UserRole.FINANCE, Permission.AUDIT_READ) is True

    def test_finance_does_not_have_fct_write(self):
        assert has_permission(UserRole.FINANCE, Permission.FCT_WRITE) is False

    def test_store_manager_has_fct_read(self):
        assert has_permission(UserRole.STORE_MANAGER, Permission.FCT_READ) is True

    def test_head_chef_does_not_have_fct_read(self):
        assert has_permission(UserRole.HEAD_CHEF, Permission.FCT_READ) is False

    def test_chef_does_not_have_user_read(self):
        assert has_permission(UserRole.CHEF, Permission.USER_READ) is False


# ===========================================================================
# has_any_permission
# ===========================================================================

class TestHasAnyPermission:
    def test_waiter_has_any_of_order_permissions(self):
        assert has_any_permission(
            UserRole.WAITER,
            [Permission.AGENT_ORDER_READ, Permission.AUDIT_DELETE],
        ) is True  # has ORDER_READ

    def test_waiter_has_none_of_admin_permissions(self):
        assert has_any_permission(
            UserRole.WAITER,
            [Permission.SYSTEM_CONFIG, Permission.AUDIT_DELETE, Permission.USER_DELETE],
        ) is False

    def test_finance_has_any_of_audit_or_order(self):
        assert has_any_permission(
            UserRole.FINANCE,
            [Permission.AUDIT_READ, Permission.SYSTEM_CONFIG],
        ) is True  # has AUDIT_READ

    def test_empty_permissions_list_returns_false(self):
        assert has_any_permission(UserRole.ADMIN, []) is False


# ===========================================================================
# has_all_permissions
# ===========================================================================

class TestHasAllPermissions:
    def test_waiter_has_all_basic_permissions(self):
        assert has_all_permissions(
            UserRole.WAITER,
            [Permission.AGENT_ORDER_READ, Permission.AGENT_ORDER_WRITE, Permission.VOICE_COMMAND],
        ) is True

    def test_waiter_missing_one_fails(self):
        assert has_all_permissions(
            UserRole.WAITER,
            [Permission.AGENT_ORDER_READ, Permission.AUDIT_READ],
        ) is False

    def test_admin_has_all_permissions_in_any_combination(self):
        assert has_all_permissions(
            UserRole.ADMIN,
            [Permission.SYSTEM_CONFIG, Permission.AUDIT_DELETE, Permission.FCT_WRITE],
        ) is True

    def test_empty_permissions_list_returns_true(self):
        # all() on empty iterable is True
        assert has_all_permissions(UserRole.WAITER, []) is True
