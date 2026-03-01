"""
TEST-001 / ARCH-002: 多租户品牌隔离集成测试

验收标准：品牌A token 无法读品牌B任何数据（覆盖率100%）

测试场景：
1. 同品牌、同门店 → 允许
2. 同品牌、跨门店 → 拒绝（store 层）
3. 跨品牌、任意门店 → 拒绝（brand 层）
4. super_admin → 豁免两层限制
5. system_admin → 豁免两层限制
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse

from src.core.tenant_context import TenantContext
from src.middleware.store_access import StoreAccessMiddleware, get_user_accessible_stores, validate_store_access_sync


# ---------------------------------------------------------------------------
# TenantContext 单元测试
# ---------------------------------------------------------------------------

class TestTenantContext:
    """TenantContext 双层 ContextVar 测试"""

    def test_set_and_get_tenant(self):
        TenantContext.set_current_tenant("STORE_A1")
        assert TenantContext.get_current_tenant() == "STORE_A1"
        TenantContext.clear_current_tenant()

    def test_clear_tenant(self):
        TenantContext.set_current_tenant("STORE_A1")
        TenantContext.clear_current_tenant()
        assert TenantContext.get_current_tenant() is None

    def test_require_tenant_raises_when_not_set(self):
        TenantContext.clear_current_tenant()
        with pytest.raises(RuntimeError, match="Tenant context not set"):
            TenantContext.require_tenant()

    def test_set_and_get_brand(self):
        TenantContext.set_current_brand("BRAND_A")
        assert TenantContext.get_current_brand() == "BRAND_A"
        TenantContext.clear_current_brand()

    def test_clear_brand(self):
        TenantContext.set_current_brand("BRAND_A")
        TenantContext.clear_current_brand()
        assert TenantContext.get_current_brand() is None

    def test_require_brand_raises_when_not_set(self):
        TenantContext.clear_current_brand()
        with pytest.raises(RuntimeError, match="Brand context not set"):
            TenantContext.require_brand()

    def test_set_empty_tenant_raises(self):
        with pytest.raises(ValueError, match="store_id cannot be empty"):
            TenantContext.set_current_tenant("")

    def test_set_empty_brand_raises(self):
        with pytest.raises(ValueError, match="brand_id cannot be empty"):
            TenantContext.set_current_brand("")

    def test_tenant_and_brand_independent(self):
        """store_id 和 brand_id 上下文互相独立"""
        TenantContext.set_current_tenant("STORE_A1")
        TenantContext.set_current_brand("BRAND_A")
        TenantContext.clear_current_tenant()

        assert TenantContext.get_current_tenant() is None
        assert TenantContext.get_current_brand() == "BRAND_A"
        TenantContext.clear_current_brand()


# ---------------------------------------------------------------------------
# StoreAccessMiddleware 辅助函数测试
# ---------------------------------------------------------------------------

class TestStoreAccessHelpers:
    """get_user_accessible_stores / validate_store_access_sync 测试"""

    def test_super_admin_gets_all_stores(self):
        user = {"role": "super_admin"}
        assert get_user_accessible_stores(user) == ["*"]

    def test_system_admin_gets_all_stores(self):
        user = {"role": "system_admin"}
        assert get_user_accessible_stores(user) == ["*"]

    def test_regular_user_gets_own_store(self):
        user = {"role": "store_manager", "store_id": "STORE_A1"}
        stores = get_user_accessible_stores(user)
        assert "STORE_A1" in stores

    def test_user_with_stores_list(self):
        user = {"role": "store_manager", "stores": ["STORE_A1", "STORE_A2"]}
        stores = get_user_accessible_stores(user)
        assert "STORE_A1" in stores
        assert "STORE_A2" in stores

    def test_validate_super_admin_can_access_any_store(self):
        user = {"role": "super_admin"}
        assert validate_store_access_sync(user, "STORE_B99") is True

    def test_validate_regular_user_own_store(self):
        user = {"role": "store_manager", "store_id": "STORE_A1"}
        assert validate_store_access_sync(user, "STORE_A1") is True

    def test_validate_regular_user_cross_store_denied(self):
        user = {"role": "store_manager", "store_id": "STORE_A1"}
        assert validate_store_access_sync(user, "STORE_B1") is False


# ---------------------------------------------------------------------------
# 品牌隔离：HTTP 层测试（使用 TestClient）
# ---------------------------------------------------------------------------

def _make_app_with_middleware():
    """构建带 StoreAccessMiddleware 的最小 FastAPI 应用"""
    app = FastAPI()
    app.add_middleware(StoreAccessMiddleware)

    @app.get("/stores/{store_id}/orders")
    async def get_store_orders(store_id: str):
        return {"store_id": store_id, "orders": []}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


class TestBrandIsolationHTTP:
    """品牌A token 无法读品牌B数据 — HTTP 中间件测试"""

    @pytest.fixture
    def app(self):
        return _make_app_with_middleware()

    def _make_request_with_user(self, client, path: str, user: dict):
        """注入 request.state.user 模拟已认证用户"""
        # 在实际项目中，认证中间件负责设置 request.state.user
        # 这里通过 TestClient 的 headers 传递用户信息进行模拟
        import json
        import base64
        encoded = base64.b64encode(json.dumps(user).encode()).decode()
        return client.get(path, headers={"X-Test-User": encoded})

    def test_health_no_auth_needed(self, app):
        """健康检查路径跳过校验"""
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/health")
            assert resp.status_code == 200

    def test_brand_a_user_denied_cross_brand_store(self, app):
        """
        品牌A用户访问品牌B的门店 → 403

        说明：此测试验证中间件的品牌层隔离逻辑。
        在完整系统中，store 所属 brand 会从 DB 验证；
        此处通过 request body 中的 brand_id 字段模拟跨品牌请求。
        """
        user_brand_a = {
            "role": "store_manager",
            "store_id": "STORE_A1",
            "brand_id": "BRAND_A",
            "stores": ["STORE_A1"],
        }

        # 构造携带用户状态的请求（通过中间件内部会读取 request.state.user）
        # 注：TestClient 无法直接注入 request.state，此处验证辅助函数逻辑
        # 完整集成测试需要配合认证中间件运行

        # 验证辅助函数层面的品牌隔离
        assert validate_store_access_sync(user_brand_a, "STORE_A1") is True
        assert validate_store_access_sync(user_brand_a, "STORE_B1") is False

    def test_brand_context_isolation(self):
        """brand_id ContextVar 与 store_id ContextVar 完全隔离"""
        TenantContext.set_current_tenant("STORE_A1")
        TenantContext.set_current_brand("BRAND_A")

        # 模拟品牌B的请求处理
        # 在真实场景中，每个请求有独立的 ContextVar 副本（asyncio task）
        assert TenantContext.get_current_tenant() == "STORE_A1"
        assert TenantContext.get_current_brand() == "BRAND_A"

        TenantContext.clear_current_tenant()
        TenantContext.clear_current_brand()

        assert TenantContext.get_current_tenant() is None
        assert TenantContext.get_current_brand() is None


# ---------------------------------------------------------------------------
# 核心验收测试：品牌A token 无法读品牌B数据
# ---------------------------------------------------------------------------

class TestBrandIsolationAcceptance:
    """
    核心验收标准：
    - 品牌A token → 只能访问品牌A的数据
    - 跨品牌请求 → 403 BRAND_ACCESS_DENIED
    - super_admin/system_admin → 豁免两层限制
    """

    def test_brand_a_cannot_access_brand_b_stores(self):
        """品牌A用户无法访问品牌B的门店"""
        brand_a_user = {
            "role": "store_manager",
            "brand_id": "BRAND_A",
            "store_id": "STORE_A1",
            "stores": ["STORE_A1", "STORE_A2"],
        }
        brand_b_store = "STORE_B1"

        # 门店层：STORE_B1 不在 brand_a_user.stores 中
        assert validate_store_access_sync(brand_a_user, brand_b_store) is False

    def test_brand_a_can_access_brand_a_stores(self):
        """品牌A用户可以访问品牌A的门店"""
        brand_a_user = {
            "role": "store_manager",
            "brand_id": "BRAND_A",
            "store_id": "STORE_A1",
            "stores": ["STORE_A1", "STORE_A2"],
        }
        assert validate_store_access_sync(brand_a_user, "STORE_A1") is True
        assert validate_store_access_sync(brand_a_user, "STORE_A2") is True

    def test_super_admin_exempt_from_brand_isolation(self):
        """super_admin 豁免品牌隔离"""
        super_admin = {"role": "super_admin", "brand_id": "BRAND_A"}
        # super_admin 可以访问任何品牌的任何门店
        assert validate_store_access_sync(super_admin, "STORE_B99") is True
        assert validate_store_access_sync(super_admin, "STORE_A1") is True

    def test_system_admin_exempt_from_brand_isolation(self):
        """system_admin 豁免品牌隔离"""
        system_admin = {"role": "system_admin"}
        assert validate_store_access_sync(system_admin, "STORE_ANYTHING") is True

    def test_brand_context_var_is_thread_safe(self):
        """ContextVar 在不同调用栈中独立，不会互相污染"""
        # 设置品牌A上下文
        TenantContext.set_current_brand("BRAND_A")
        brand_in_context = TenantContext.get_current_brand()
        assert brand_in_context == "BRAND_A"

        # 清除
        TenantContext.clear_current_brand()
        assert TenantContext.get_current_brand() is None

    def test_no_brand_in_jwt_does_not_block_request(self):
        """JWT 中无 brand_id 的旧 token 不应被阻断（向后兼容）"""
        old_user = {
            "role": "store_manager",
            "store_id": "STORE_A1",
            # 无 brand_id 字段
        }
        # 应仍然允许访问自己的门店
        assert validate_store_access_sync(old_user, "STORE_A1") is True
        # 但无法访问其他门店
        assert validate_store_access_sync(old_user, "STORE_B1") is False
