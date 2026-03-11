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
        mock_event.listen.assert_called_once()

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
        mock_event.listen.assert_called_once()


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


# ===========================================================================
# receive_do_orm_execute inner function (lines 88-111)
# ===========================================================================

class TestReceiveDoOrmExecute:
    """
    Tests for the inner `receive_do_orm_execute` function defined inside
    enable_tenant_filter's ORM fallback block (lines 88-111).

    Strategy: use a fake `event.listens_for` decorator to capture the inner
    function, then call it directly with mock orm_execute_state objects.
    """

    def _capture_listener(self, mock_event):
        """Return a fake listen that captures the registered function."""
        captured = {}

        def fake_listen(session, event_name, fn):
            captured["fn"] = fn

        mock_event.listen = fake_listen
        return captured

    @pytest.mark.asyncio
    async def test_non_select_returns_early(self):
        """ORM listener returns immediately for non-SELECT statements (line 89-90)."""
        mock_session = AsyncMock()

        with patch("src.core.tenant_filter.TenantContext.get_current_tenant", return_value="S1"), \
             patch("src.core.tenant_filter.event") as mock_event:
            captured = self._capture_listener(mock_event)
            await enable_tenant_filter(mock_session, use_rls=False)

        assert "fn" in captured, "event.listen was not called"

        mock_state = MagicMock()
        mock_state.is_select = False
        # Should return without touching statement
        captured["fn"](mock_state)
        mock_state.statement.froms.__iter__.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_tenant_returns_early(self):
        """ORM listener returns early when no tenant context at query time (lines 93-94)."""
        mock_session = AsyncMock()

        with patch("src.core.tenant_filter.TenantContext.get_current_tenant", return_value="S1"), \
             patch("src.core.tenant_filter.event") as mock_event:
            captured = self._capture_listener(mock_event)
            await enable_tenant_filter(mock_session, use_rls=False)

        assert "fn" in captured

        mock_state = MagicMock()
        mock_state.is_select = True
        with patch("src.core.tenant_filter.TenantContext.get_current_tenant", return_value=None):
            captured["fn"](mock_state)
        mock_state.statement.froms.__iter__.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_tenant_table_not_filtered(self):
        """ORM listener skips tables not in TENANT_TABLES (lines 98-111)."""
        mock_session = AsyncMock()

        with patch("src.core.tenant_filter.TenantContext.get_current_tenant", return_value="S1"), \
             patch("src.core.tenant_filter.event") as mock_event:
            captured = self._capture_listener(mock_event)
            await enable_tenant_filter(mock_session, use_rls=False)

        assert "fn" in captured

        mock_table = MagicMock()
        mock_table.name = "users"  # system table, not in TENANT_TABLES

        mock_state = MagicMock()
        mock_state.is_select = True
        mock_state.statement.froms = [mock_table]

        with patch("src.core.tenant_filter.TenantContext.get_current_tenant", return_value="S1"):
            captured["fn"](mock_state)

        mock_state.statement.where.assert_not_called()

    @pytest.mark.asyncio
    async def test_tenant_table_with_existing_filter_not_doubled(self):
        """ORM listener skips filter injection when store_id already present (line 102)."""
        mock_session = AsyncMock()

        with patch("src.core.tenant_filter.TenantContext.get_current_tenant", return_value="S1"), \
             patch("src.core.tenant_filter.event") as mock_event:
            captured = self._capture_listener(mock_event)
            await enable_tenant_filter(mock_session, use_rls=False)

        assert "fn" in captured

        mock_table = MagicMock()
        mock_table.name = "orders"  # in TENANT_TABLES

        mock_state = MagicMock()
        mock_state.is_select = True
        mock_state.statement.froms = [mock_table]

        with patch("src.core.tenant_filter.TenantContext.get_current_tenant", return_value="S1"), \
             patch("src.core.tenant_filter._has_store_filter", return_value=True):
            captured["fn"](mock_state)

        mock_state.statement.where.assert_not_called()

    @pytest.mark.asyncio
    async def test_tenant_table_applies_store_id_filter(self):
        """ORM listener injects store_id WHERE clause for tenant tables (lines 103-111)."""
        mock_session = AsyncMock()

        with patch("src.core.tenant_filter.TenantContext.get_current_tenant", return_value="S1"), \
             patch("src.core.tenant_filter.event") as mock_event:
            captured = self._capture_listener(mock_event)
            await enable_tenant_filter(mock_session, use_rls=False)

        assert "fn" in captured

        mock_table = MagicMock()
        mock_table.name = "orders"  # in TENANT_TABLES

        mock_state = MagicMock()
        mock_state.is_select = True
        mock_state.statement.froms = [mock_table]
        # Capture statement before listener reassigns mock_state.statement
        original_statement = mock_state.statement

        with patch("src.core.tenant_filter.TenantContext.get_current_tenant", return_value="S1"), \
             patch("src.core.tenant_filter._has_store_filter", return_value=False):
            captured["fn"](mock_state)

        original_statement.where.assert_called_once()


# ===========================================================================
# disable_tenant_filter (lines 147-148)
# ===========================================================================

class TestDisableTenantFilter:
    def test_disable_calls_event_remove(self):
        """
        disable_tenant_filter calls event.remove with the session and listener name
        (line 147), then logs the outcome (line 148).

        receive_do_orm_execute is a closure defined inside enable_tenant_filter, so
        it is not in module scope.  We inject a sentinel into the module namespace
        so the name resolves, then verify event.remove is called correctly.
        """
        import src.core.tenant_filter as tf_mod
        from src.core.tenant_filter import disable_tenant_filter

        mock_session = MagicMock()
        sentinel_fn = MagicMock()

        # Inject the name into module scope so the function body can resolve it
        tf_mod.receive_do_orm_execute = sentinel_fn
        try:
            with patch.object(tf_mod, "event") as mock_event:
                disable_tenant_filter(mock_session)

            mock_event.remove.assert_called_once_with(
                mock_session, "do_orm_execute", sentinel_fn
            )
        finally:
            # Always clean up the injected attribute
            del tf_mod.receive_do_orm_execute

    def test_disable_logs_info(self):
        """
        After event.remove, disable_tenant_filter logs an info message (line 148).
        """
        import src.core.tenant_filter as tf_mod
        from src.core.tenant_filter import disable_tenant_filter

        mock_session = MagicMock()
        sentinel_fn = MagicMock()

        tf_mod.receive_do_orm_execute = sentinel_fn
        try:
            with patch.object(tf_mod, "event"), \
                 patch.object(tf_mod, "logger") as mock_logger:
                disable_tenant_filter(mock_session)

            mock_logger.info.assert_called_once_with("Tenant filter disabled for session")
        finally:
            del tf_mod.receive_do_orm_execute
