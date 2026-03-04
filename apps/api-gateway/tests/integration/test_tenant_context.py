"""
Tests for src/core/tenant_context.py — tenant and brand context management.

Covers:
  - get/set/clear/require_tenant
  - get/set/clear/require_brand
  - with_tenant decorator (async and sync functions)
"""
import pytest
from unittest.mock import AsyncMock

from src.core.tenant_context import TenantContext, with_tenant


class TestTenantContextStoreTier:
    def setup_method(self):
        TenantContext.clear_current_tenant()

    def teardown_method(self):
        TenantContext.clear_current_tenant()

    def test_get_returns_none_initially(self):
        assert TenantContext.get_current_tenant() is None

    def test_set_and_get(self):
        TenantContext.set_current_tenant("S1")
        assert TenantContext.get_current_tenant() == "S1"

    def test_clear_resets_to_none(self):
        TenantContext.set_current_tenant("S1")
        TenantContext.clear_current_tenant()
        assert TenantContext.get_current_tenant() is None

    def test_require_tenant_returns_when_set(self):
        TenantContext.set_current_tenant("STORE99")
        result = TenantContext.require_tenant()
        assert result == "STORE99"

    def test_require_tenant_raises_when_not_set(self):
        with pytest.raises(RuntimeError, match="Tenant context not set"):
            TenantContext.require_tenant()

    def test_set_empty_raises(self):
        with pytest.raises(ValueError, match="store_id cannot be empty"):
            TenantContext.set_current_tenant("")


class TestTenantContextBrandTier:
    def setup_method(self):
        TenantContext.clear_current_brand()

    def teardown_method(self):
        TenantContext.clear_current_brand()

    def test_get_brand_returns_none_initially(self):
        assert TenantContext.get_current_brand() is None

    def test_set_and_get_brand(self):
        TenantContext.set_current_brand("B1")
        assert TenantContext.get_current_brand() == "B1"

    def test_clear_brand_resets_to_none(self):
        TenantContext.set_current_brand("B1")
        TenantContext.clear_current_brand()
        assert TenantContext.get_current_brand() is None

    def test_require_brand_returns_when_set(self):
        TenantContext.set_current_brand("BRAND99")
        result = TenantContext.require_brand()
        assert result == "BRAND99"

    def test_require_brand_raises_when_not_set(self):
        with pytest.raises(RuntimeError, match="Brand context not set"):
            TenantContext.require_brand()

    def test_set_brand_empty_raises(self):
        with pytest.raises(ValueError, match="brand_id cannot be empty"):
            TenantContext.set_current_brand("")


class TestWithTenantDecorator:
    def teardown_method(self):
        TenantContext.clear_current_tenant()

    @pytest.mark.asyncio
    async def test_async_function_sets_and_clears_tenant(self):
        @with_tenant("STORE_ASYNC")
        async def async_fn():
            return TenantContext.get_current_tenant()

        result = await async_fn()
        assert result == "STORE_ASYNC"
        # After call, context is cleared
        assert TenantContext.get_current_tenant() is None

    @pytest.mark.asyncio
    async def test_async_function_clears_on_exception(self):
        @with_tenant("STORE_ERR")
        async def async_err():
            raise ValueError("oops")

        with pytest.raises(ValueError):
            await async_err()
        assert TenantContext.get_current_tenant() is None

    def test_sync_function_sets_and_clears_tenant(self):
        @with_tenant("STORE_SYNC")
        def sync_fn():
            return TenantContext.get_current_tenant()

        result = sync_fn()
        assert result == "STORE_SYNC"
        assert TenantContext.get_current_tenant() is None

    def test_sync_function_clears_on_exception(self):
        @with_tenant("STORE_SYNC_ERR")
        def sync_err():
            raise ValueError("sync oops")

        with pytest.raises(ValueError):
            sync_err()
        assert TenantContext.get_current_tenant() is None
