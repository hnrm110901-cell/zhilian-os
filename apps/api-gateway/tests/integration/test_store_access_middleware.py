"""
Tests for src/middleware/store_access.py — store ID validation middleware.
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.responses import JSONResponse

from src.middleware.store_access import (
    StoreAccessMiddleware,
    get_user_accessible_stores,
    validate_store_access_sync,
)


def _middleware():
    return StoreAccessMiddleware(app=MagicMock())


def _request(path="/api/v1/orders", method="GET", query_params=None,
             path_params=None, body=None, user=None):
    """Create a mock request."""
    req = MagicMock()
    req.url.path = path
    req.method = method
    req.query_params = query_params or {}
    req.path_params = path_params or {}
    req.state = MagicMock()
    if user is not None:
        req.state.user = user
    else:
        req.state.user = None
    if body is not None:
        req.body = AsyncMock(return_value=body if isinstance(body, bytes) else json.dumps(body).encode())
    else:
        req.body = AsyncMock(return_value=b"")
    return req


# ===========================================================================
# _should_skip_validation
# ===========================================================================
class TestShouldSkipValidation:
    def test_health_path_skipped(self):
        m = _middleware()
        assert m._should_skip_validation("/health") is True

    def test_docs_path_skipped(self):
        m = _middleware()
        assert m._should_skip_validation("/docs") is True

    def test_auth_login_skipped(self):
        m = _middleware()
        assert m._should_skip_validation("/auth/login") is True

    def test_api_path_not_skipped(self):
        m = _middleware()
        assert m._should_skip_validation("/api/v1/orders") is False

    def test_redoc_path_skipped(self):
        m = _middleware()
        assert m._should_skip_validation("/redoc") is True

    def test_openapi_json_skipped(self):
        m = _middleware()
        assert m._should_skip_validation("/openapi.json") is True

    def test_metrics_path_skipped(self):
        m = _middleware()
        assert m._should_skip_validation("/metrics") is True

    def test_auth_register_skipped(self):
        m = _middleware()
        assert m._should_skip_validation("/auth/register") is True

    def test_health_subpath_skipped(self):
        m = _middleware()
        # startswith check means /health/live is also skipped
        assert m._should_skip_validation("/health/live") is True

    def test_root_path_not_skipped(self):
        m = _middleware()
        assert m._should_skip_validation("/") is False

    def test_stores_path_not_skipped(self):
        m = _middleware()
        assert m._should_skip_validation("/stores/S1/orders") is False


# ===========================================================================
# _validate_store_access
# ===========================================================================
class TestValidateStoreAccess:
    @pytest.mark.asyncio
    async def test_no_user_returns_false(self):
        m = _middleware()
        req = _request()
        req.state.user = None
        result = await m._validate_store_access(req, "S1")
        assert result is False

    @pytest.mark.asyncio
    async def test_super_admin_returns_true(self):
        m = _middleware()
        req = _request(user={"role": "super_admin", "store_id": "S_OTHER"})
        result = await m._validate_store_access(req, "S1")
        assert result is True

    @pytest.mark.asyncio
    async def test_system_admin_returns_true(self):
        m = _middleware()
        req = _request(user={"role": "system_admin"})
        result = await m._validate_store_access(req, "S1")
        assert result is True

    @pytest.mark.asyncio
    async def test_user_stores_list_contains_store(self):
        m = _middleware()
        req = _request(user={"role": "waiter", "stores": ["S1", "S2"]})
        result = await m._validate_store_access(req, "S1")
        assert result is True

    @pytest.mark.asyncio
    async def test_user_stores_list_not_contains_store(self):
        m = _middleware()
        req = _request(user={"role": "waiter", "stores": ["S2", "S3"]})
        result = await m._validate_store_access(req, "S1")
        assert result is False

    @pytest.mark.asyncio
    async def test_user_store_id_matches(self):
        m = _middleware()
        req = _request(user={"role": "waiter", "store_id": "S1"})
        result = await m._validate_store_access(req, "S1")
        assert result is True

    @pytest.mark.asyncio
    async def test_user_store_id_mismatch_returns_false(self):
        m = _middleware()
        req = _request(user={"role": "waiter", "store_id": "S99"})
        result = await m._validate_store_access(req, "S1")
        assert result is False

    @pytest.mark.asyncio
    async def test_user_no_store_info_returns_false(self):
        m = _middleware()
        req = _request(user={"role": "waiter"})
        result = await m._validate_store_access(req, "S1")
        assert result is False

    @pytest.mark.asyncio
    async def test_user_stores_list_takes_precedence_over_store_id(self):
        # When stores list is present and non-empty it is used for the check
        m = _middleware()
        req = _request(user={"role": "waiter", "stores": ["S2"], "store_id": "S1"})
        # S1 is NOT in stores list — should be denied even though store_id matches
        result = await m._validate_store_access(req, "S1")
        assert result is False


# ===========================================================================
# _extract_store_id
# ===========================================================================
class TestExtractStoreId:
    @pytest.mark.asyncio
    async def test_from_query_params(self):
        m = _middleware()
        req = _request(query_params={"store_id": "QS1"})
        result = await m._extract_store_id(req)
        assert result == "QS1"

    @pytest.mark.asyncio
    async def test_from_path_params(self):
        m = _middleware()
        req = _request(path_params={"store_id": "PS1"})
        result = await m._extract_store_id(req)
        assert result == "PS1"

    @pytest.mark.asyncio
    async def test_query_params_take_precedence_over_path_params(self):
        m = _middleware()
        req = _request(query_params={"store_id": "QS1"}, path_params={"store_id": "PS1"})
        result = await m._extract_store_id(req)
        assert result == "QS1"

    @pytest.mark.asyncio
    async def test_from_post_body(self):
        m = _middleware()
        req = _request(method="POST", body={"store_id": "BS1"})
        result = await m._extract_store_id(req)
        assert result == "BS1"

    @pytest.mark.asyncio
    async def test_from_put_body(self):
        m = _middleware()
        req = _request(method="PUT", body={"store_id": "BS1"})
        result = await m._extract_store_id(req)
        assert result == "BS1"

    @pytest.mark.asyncio
    async def test_from_patch_body(self):
        m = _middleware()
        req = _request(method="PATCH", body={"store_id": "BS1"})
        result = await m._extract_store_id(req)
        assert result == "BS1"

    @pytest.mark.asyncio
    async def test_post_non_json_body_returns_none(self):
        m = _middleware()
        req = _request(method="POST")
        req.body = AsyncMock(return_value=b"not-json")
        result = await m._extract_store_id(req)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_no_store_id_returns_none(self):
        m = _middleware()
        req = _request(method="GET")
        result = await m._extract_store_id(req)
        assert result is None

    @pytest.mark.asyncio
    async def test_body_exception_returns_none(self):
        m = _middleware()
        req = _request(method="POST")
        req.body = AsyncMock(side_effect=RuntimeError("body read error"))
        result = await m._extract_store_id(req)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_body_not_read(self):
        # For GET requests the body is never read; body mock not called
        m = _middleware()
        req = _request(method="GET")
        body_mock = AsyncMock(return_value=b'{"store_id": "BS1"}')
        req.body = body_mock
        result = await m._extract_store_id(req)
        assert result is None
        body_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_post_body_missing_store_id_key(self):
        m = _middleware()
        req = _request(method="POST", body={"other_field": "value"})
        result = await m._extract_store_id(req)
        assert result is None

    @pytest.mark.asyncio
    async def test_post_empty_body_returns_none(self):
        m = _middleware()
        req = _request(method="POST")
        req.body = AsyncMock(return_value=b"")
        result = await m._extract_store_id(req)
        assert result is None


# ===========================================================================
# _extract_brand_id
# ===========================================================================
class TestExtractBrandId:
    @pytest.mark.asyncio
    async def test_from_query_params(self):
        m = _middleware()
        req = _request(query_params={"brand_id": "QB1"})
        result = await m._extract_brand_id(req, {})
        assert result == "QB1"

    @pytest.mark.asyncio
    async def test_from_path_params(self):
        m = _middleware()
        req = _request(path_params={"brand_id": "PB1"})
        result = await m._extract_brand_id(req, {})
        assert result == "PB1"

    @pytest.mark.asyncio
    async def test_from_post_body(self):
        m = _middleware()
        req = _request(method="POST", body={"brand_id": "BB1"})
        result = await m._extract_brand_id(req, {})
        assert result == "BB1"

    @pytest.mark.asyncio
    async def test_from_put_body(self):
        m = _middleware()
        req = _request(method="PUT", body={"brand_id": "BB1"})
        result = await m._extract_brand_id(req, {})
        assert result == "BB1"

    @pytest.mark.asyncio
    async def test_no_brand_returns_none(self):
        m = _middleware()
        req = _request()
        result = await m._extract_brand_id(req, {})
        assert result is None

    @pytest.mark.asyncio
    async def test_query_takes_precedence_over_path(self):
        m = _middleware()
        req = _request(query_params={"brand_id": "QB1"}, path_params={"brand_id": "PB1"})
        result = await m._extract_brand_id(req, {})
        assert result == "QB1"

    @pytest.mark.asyncio
    async def test_get_body_not_read_for_brand(self):
        m = _middleware()
        req = _request(method="GET")
        body_mock = AsyncMock(return_value=b'{"brand_id": "BB1"}')
        req.body = body_mock
        result = await m._extract_brand_id(req, {})
        assert result is None
        body_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_post_non_json_body_returns_none(self):
        m = _middleware()
        req = _request(method="POST")
        req.body = AsyncMock(return_value=b"not-json")
        result = await m._extract_brand_id(req, {})
        assert result is None

    @pytest.mark.asyncio
    async def test_body_exception_returns_none(self):
        m = _middleware()
        req = _request(method="POST")
        req.body = AsyncMock(side_effect=RuntimeError("body read error"))
        result = await m._extract_brand_id(req, {})
        assert result is None


# ===========================================================================
# get_user_accessible_stores
# ===========================================================================
class TestGetUserAccessibleStores:
    def test_super_admin_returns_wildcard(self):
        result = get_user_accessible_stores({"role": "super_admin"})
        assert result == ["*"]

    def test_system_admin_returns_wildcard(self):
        result = get_user_accessible_stores({"role": "system_admin"})
        assert result == ["*"]

    def test_user_stores_list_returned(self):
        result = get_user_accessible_stores({"role": "waiter", "stores": ["S1", "S2"]})
        assert result == ["S1", "S2"]

    def test_user_store_id_returned_as_list(self):
        result = get_user_accessible_stores({"role": "waiter", "store_id": "S99"})
        assert result == ["S99"]

    def test_no_stores_returns_empty(self):
        result = get_user_accessible_stores({"role": "waiter"})
        assert result == []

    def test_empty_stores_list_falls_back_to_store_id(self):
        # An empty list is falsy, so should fall back to store_id
        result = get_user_accessible_stores({"role": "waiter", "stores": [], "store_id": "S1"})
        assert result == ["S1"]

    def test_no_role_no_stores_returns_empty(self):
        result = get_user_accessible_stores({})
        assert result == []


# ===========================================================================
# validate_store_access_sync
# ===========================================================================
class TestValidateStoreAccessSync:
    def test_super_admin_allowed(self):
        assert validate_store_access_sync({"role": "super_admin"}, "ANY") is True

    def test_system_admin_allowed(self):
        assert validate_store_access_sync({"role": "system_admin"}, "ANY") is True

    def test_matching_store_allowed(self):
        assert validate_store_access_sync({"role": "waiter", "store_id": "S1"}, "S1") is True

    def test_non_matching_store_denied(self):
        assert validate_store_access_sync({"role": "waiter", "store_id": "S1"}, "S2") is False

    def test_stores_list_match_allowed(self):
        assert validate_store_access_sync({"role": "waiter", "stores": ["S1", "S2"]}, "S2") is True

    def test_stores_list_no_match_denied(self):
        assert validate_store_access_sync({"role": "waiter", "stores": ["S1", "S2"]}, "S3") is False

    def test_no_store_info_denied(self):
        assert validate_store_access_sync({"role": "waiter"}, "S1") is False


# ===========================================================================
# dispatch: excluded paths
# ===========================================================================
class TestDispatchExcludedPaths:
    @pytest.mark.asyncio
    async def test_health_skips_validation(self):
        m = _middleware()
        req = _request(path="/health")
        call_next = AsyncMock(return_value=MagicMock())
        await m.dispatch(req, call_next)
        call_next.assert_awaited_once_with(req)

    @pytest.mark.asyncio
    async def test_docs_skips_validation(self):
        m = _middleware()
        req = _request(path="/docs")
        call_next = AsyncMock(return_value=MagicMock())
        await m.dispatch(req, call_next)
        call_next.assert_awaited_once_with(req)

    @pytest.mark.asyncio
    async def test_auth_login_skips_validation(self):
        m = _middleware()
        req = _request(path="/auth/login")
        call_next = AsyncMock(return_value=MagicMock())
        await m.dispatch(req, call_next)
        call_next.assert_awaited_once_with(req)


# ===========================================================================
# dispatch: store access denied
# ===========================================================================
class TestDispatchStoreAccessDenied:
    @pytest.mark.asyncio
    async def test_unauthorized_store_access_returns_403(self):
        m = _middleware()
        req = _request(
            path="/api/v1/orders",
            query_params={"store_id": "S_OTHER"},
            user={"role": "waiter", "store_id": "S1"},
        )
        call_next = AsyncMock(return_value=MagicMock())
        response = await m.dispatch(req, call_next)
        assert isinstance(response, JSONResponse)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_403_response_contains_error_code(self):
        m = _middleware()
        req = _request(
            path="/api/v1/orders",
            query_params={"store_id": "S_OTHER"},
            user={"role": "waiter", "store_id": "S1"},
        )
        call_next = AsyncMock(return_value=MagicMock())
        response = await m.dispatch(req, call_next)
        body = json.loads(response.body)
        assert body["error_code"] == "STORE_ACCESS_DENIED"
        assert body["store_id"] == "S_OTHER"

    @pytest.mark.asyncio
    async def test_no_user_with_store_id_in_query_returns_403(self):
        m = _middleware()
        req = _request(
            path="/api/v1/orders",
            query_params={"store_id": "S1"},
        )
        req.state.user = None
        call_next = AsyncMock(return_value=MagicMock())
        response = await m.dispatch(req, call_next)
        assert isinstance(response, JSONResponse)
        assert response.status_code == 403


# ===========================================================================
# dispatch: brand access denied
# ===========================================================================
class TestDispatchBrandAccessDenied:
    @pytest.mark.asyncio
    async def test_cross_brand_access_returns_403(self):
        m = _middleware()
        # Set both store_id (matching) and brand_id (mismatching) in query
        req = _request(
            path="/api/v1/orders",
            user={"role": "waiter", "store_id": "S1", "brand_id": "B1"},
        )
        req.query_params = {"store_id": "S1", "brand_id": "B_OTHER"}
        call_next = AsyncMock(return_value=MagicMock())
        response = await m.dispatch(req, call_next)
        assert isinstance(response, JSONResponse)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_403_response_contains_brand_error_code(self):
        m = _middleware()
        req = _request(
            path="/api/v1/orders",
            user={"role": "waiter", "store_id": "S1", "brand_id": "B1"},
        )
        req.query_params = {"store_id": "S1", "brand_id": "B_OTHER"}
        call_next = AsyncMock(return_value=MagicMock())
        response = await m.dispatch(req, call_next)
        body = json.loads(response.body)
        assert body["error_code"] == "BRAND_ACCESS_DENIED"
        assert body["brand_id"] == "B_OTHER"

    @pytest.mark.asyncio
    async def test_super_admin_not_blocked_on_cross_brand(self):
        m = _middleware()
        req = _request(
            path="/api/v1/orders",
            user={"role": "super_admin", "brand_id": "B1"},
        )
        req.query_params = {"brand_id": "B_OTHER"}
        call_next = AsyncMock(return_value=MagicMock())
        response = await m.dispatch(req, call_next)
        # super_admin bypasses brand check — call_next must have been called
        call_next.assert_awaited_once()


# ===========================================================================
# dispatch: no store_id, proceeds normally
# ===========================================================================
class TestDispatchNoStoreId:
    @pytest.mark.asyncio
    async def test_no_store_id_calls_next(self):
        m = _middleware()
        req = _request(path="/api/v1/menu")  # no store_id anywhere
        req.state.user = None
        call_next = AsyncMock(return_value=MagicMock())
        await m.dispatch(req, call_next)
        call_next.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_store_id_in_request_but_user_has_store_id_calls_next(self):
        # User's own store_id is injected as store_id; since it matches, call_next
        m = _middleware()
        req = _request(path="/api/v1/menu", user={"role": "waiter", "store_id": "S1"})
        # No store_id in query/path/body — dispatch will use user.store_id
        call_next = AsyncMock(return_value=MagicMock())
        await m.dispatch(req, call_next)
        call_next.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_authorized_store_access_calls_next(self):
        m = _middleware()
        req = _request(
            path="/api/v1/orders",
            query_params={"store_id": "S1"},
            user={"role": "waiter", "store_id": "S1"},
        )
        call_next = AsyncMock(return_value=MagicMock())
        await m.dispatch(req, call_next)
        call_next.assert_awaited_once()


# ===========================================================================
# dispatch: exception handling
# ===========================================================================
class TestDispatchException:
    @pytest.mark.asyncio
    async def test_exception_in_middleware_calls_next(self):
        m = _middleware()
        req = _request(path="/api/v1/orders")
        # Make _extract_store_id raise
        m._extract_store_id = AsyncMock(side_effect=RuntimeError("unexpected"))
        call_next = AsyncMock(return_value=MagicMock())
        await m.dispatch(req, call_next)
        call_next.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_exception_clears_tenant_context(self):
        from src.core.tenant_context import TenantContext
        m = _middleware()
        req = _request(path="/api/v1/orders")
        m._extract_store_id = AsyncMock(side_effect=RuntimeError("boom"))
        call_next = AsyncMock(return_value=MagicMock())
        await m.dispatch(req, call_next)
        # Context must be cleared even after an exception
        assert TenantContext.get_current_tenant() is None


# ===========================================================================
# dispatch: brand context set (lines 102-107)
# ===========================================================================
class TestDispatchBrandContextSet:
    @pytest.mark.asyncio
    async def test_brand_id_in_user_calls_set_current_brand(self):
        """Lines 102-105: user has brand_id, no cross-brand request → set_current_brand called."""
        from src.core.tenant_context import TenantContext
        m = _middleware()
        req = _request(
            path="/api/v1/orders",
            user={"role": "waiter", "store_id": "S1", "brand_id": "B1"},
        )
        call_next = AsyncMock(return_value=MagicMock())
        with patch.object(TenantContext, "set_current_brand") as mock_set:
            await m.dispatch(req, call_next)
        mock_set.assert_called_once_with("B1")

    @pytest.mark.asyncio
    async def test_set_current_brand_value_error_is_swallowed(self):
        """Lines 106-107: ValueError from set_current_brand is swallowed → call_next still called."""
        from src.core.tenant_context import TenantContext
        m = _middleware()
        req = _request(
            path="/api/v1/orders",
            user={"role": "waiter", "store_id": "S1", "brand_id": "B1"},
        )
        call_next = AsyncMock(return_value=MagicMock())
        with patch.object(TenantContext, "set_current_brand", side_effect=ValueError("invalid brand")):
            await m.dispatch(req, call_next)
        call_next.assert_awaited_once()
        assert TenantContext.get_current_brand() is None
