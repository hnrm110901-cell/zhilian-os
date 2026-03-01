"""
Tests for src/core/tenant_filter.py — SQLAlchemy 租户隔离过滤器.

Covers:
  - TENANT_TABLES / SYSTEM_TABLES set membership
  - _has_store_filter: None whereclause → False; containing "store_id" → True
  - enable_tenant_filter: no tenant context → early return (no SQL)
  - enable_tenant_filter: with tenant context + use_rls=True → executes set_config
  - enable_tenant_filter: RLS exception → falls back to ORM filter
  - TenantFilterContext: __aenter__ calls enable_tenant_filter
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.tenant_filter import (
    SYSTEM_TABLES,
    TENANT_TABLES,
    TenantFilterContext,
    _has_store_filter,
    enable_tenant_filter,
)


# ===========================================================================
# Table set membership
# ===========================================================================

class TestTableSets:
    def test_orders_is_tenant_table(self):
        assert "orders" in TENANT_TABLES

    def test_order_items_is_tenant_table(self):
        assert "order_items" in TENANT_TABLES

    def test_inventory_items_is_tenant_table(self):
        assert "inventory_items" in TENANT_TABLES

    def test_schedules_is_tenant_table(self):
        assert "schedules" in TENANT_TABLES

    def test_financial_records_is_tenant_table(self):
        assert "financial_records" in TENANT_TABLES

    def test_users_is_system_table(self):
        assert "users" in SYSTEM_TABLES

    def test_stores_is_system_table(self):
        assert "stores" in SYSTEM_TABLES

    def test_roles_is_system_table(self):
        assert "roles" in SYSTEM_TABLES

    def test_audit_logs_is_system_table(self):
        assert "audit_logs" in SYSTEM_TABLES

    def test_tenant_tables_not_overlap_system_tables(self):
        assert TENANT_TABLES.isdisjoint(SYSTEM_TABLES)


# ===========================================================================
# _has_store_filter
# ===========================================================================

class TestHasStoreFilter:
    def test_no_whereclause_returns_false(self):
        stmt = MagicMock()
        stmt.whereclause = None
        assert _has_store_filter(stmt) is False

    def test_missing_whereclause_attr_returns_false(self):
        stmt = MagicMock(spec=[])  # no attributes at all
        assert _has_store_filter(stmt) is False

    def test_whereclause_containing_store_id_returns_true(self):
        stmt = MagicMock()
        stmt.whereclause = "orders.store_id = :store_id_1"
        assert _has_store_filter(stmt) is True

    def test_whereclause_without_store_id_returns_false(self):
        stmt = MagicMock()
        stmt.whereclause = "orders.status = 'completed'"
        assert _has_store_filter(stmt) is False

    def test_case_insensitive_store_id(self):
        stmt = MagicMock()
        stmt.whereclause = "STORE_ID = 'S1'"
        assert _has_store_filter(stmt) is True


# ===========================================================================
# enable_tenant_filter — no tenant context
# ===========================================================================

class TestEnableTenantFilterNoContext:
    @pytest.mark.asyncio
    async def test_no_tenant_context_returns_early(self):
        """When TenantContext has no current tenant, nothing is executed."""
        mock_session = AsyncMock()

        with patch("src.core.tenant_filter.TenantContext.get_current_tenant", return_value=None):
            await enable_tenant_filter(mock_session)

        mock_session.execute.assert_not_awaited()


# ===========================================================================
# enable_tenant_filter — RLS path
# ===========================================================================

class TestEnableTenantFilterRLS:
    @pytest.mark.asyncio
    async def test_with_tenant_context_executes_set_config(self):
        """RLS path: executes set_config SQL with correct tenant_id."""
        mock_session = AsyncMock()

        with patch("src.core.tenant_filter.TenantContext.get_current_tenant", return_value="STORE-001"):
            await enable_tenant_filter(mock_session, use_rls=True)

        # Should have executed exactly one statement (the set_config call)
        mock_session.execute.assert_awaited_once()
        call_args = mock_session.execute.call_args
        # The first arg is a text() expression; verify the params dict
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("params", {})
        # The bound params should include tenant_id
        assert "tenant_id" in str(call_args)

    @pytest.mark.asyncio
    async def test_rls_failure_falls_back_to_orm(self):
        """
        If set_config raises, use_rls is set to False and ORM filter install is attempted.
        Production note: event.listens_for requires a real SQLAlchemy session; here we
        patch the event module to avoid that constraint in unit tests.
        """
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=Exception("DB error"))

        with patch("src.core.tenant_filter.TenantContext.get_current_tenant", return_value="S1"), \
             patch("src.core.tenant_filter.event") as mock_event:
            await enable_tenant_filter(mock_session, use_rls=True)

        # The ORM fallback path should have tried to attach a listener
        mock_event.listens_for.assert_called_once()

    @pytest.mark.asyncio
    async def test_use_rls_false_skips_set_config(self):
        """When use_rls=False, skip the RLS SQL and install ORM event listener."""
        mock_session = AsyncMock()

        with patch("src.core.tenant_filter.TenantContext.get_current_tenant", return_value="S1"), \
             patch("src.core.tenant_filter.event") as mock_event:
            await enable_tenant_filter(mock_session, use_rls=False)

        # No execute call for set_config
        mock_session.execute.assert_not_awaited()
        # ORM event listener should be attached
        mock_event.listens_for.assert_called_once()


# ===========================================================================
# TenantFilterContext
# ===========================================================================

class TestTenantFilterContext:
    @pytest.mark.asyncio
    async def test_aenter_calls_enable_tenant_filter(self):
        mock_session = AsyncMock()

        with patch("src.core.tenant_filter.enable_tenant_filter", new=AsyncMock()) as mock_enable, \
             patch("src.core.tenant_filter.disable_tenant_filter"):
            async with TenantFilterContext(mock_session, enable=True) as session:
                pass
            mock_enable.assert_awaited_once_with(mock_session)

    @pytest.mark.asyncio
    async def test_aenter_disabled_skips_enable(self):
        mock_session = AsyncMock()

        with patch("src.core.tenant_filter.enable_tenant_filter", new=AsyncMock()) as mock_enable, \
             patch("src.core.tenant_filter.disable_tenant_filter"):
            async with TenantFilterContext(mock_session, enable=False) as session:
                pass
            mock_enable.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_aenter_returns_session(self):
        mock_session = AsyncMock()

        with patch("src.core.tenant_filter.enable_tenant_filter", new=AsyncMock()), \
             patch("src.core.tenant_filter.disable_tenant_filter"):
            async with TenantFilterContext(mock_session) as s:
                assert s is mock_session
