"""Multi-store API compatibility routes tests."""
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

for _k, _v in {
    "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
    "REDIS_URL": "redis://localhost:6379/0",
    "CELERY_BROKER_URL": "redis://localhost:6379/0",
    "CELERY_RESULT_BACKEND": "redis://localhost:6379/0",
    "SECRET_KEY": "test-secret-key",
    "JWT_SECRET": "test-jwt-secret",
}.items():
    os.environ.setdefault(_k, _v)

from src.api.multi_store import (  # noqa: E402
    CompareStoresRequest,
    get_current_active_user,
    router,
    compare_stores,
    get_performance_ranking_compat,
    get_regional_summary_compat,
    get_stores_compat,
)


@pytest.mark.asyncio
async def test_get_stores_compat_returns_list_shape():
    store = SimpleNamespace(
        id="S001",
        name="岳麓店",
        code="YL01",
        address="长沙市岳麓区",
        city="长沙",
        district="岳麓",
        region="华中",
        status="active",
        is_active=True,
        manager_id="U001",
        area=300,
        seats=120,
        phone="123456",
        created_at=None,
    )

    with patch("src.api.multi_store.store_service.get_stores", new=AsyncMock(return_value=[store])):
        out = await get_stores_compat(
            region=None,
            city=None,
            status=None,
            is_active=None,
            limit=100,
            offset=0,
            current_user=None,
        )

    assert out["total"] == 1
    assert out["stores"][0]["id"] == "S001"
    assert out["stores"][0]["region"] == "华中"


@pytest.mark.asyncio
async def test_compare_stores_accepts_frontend_payload_and_returns_metrics():
    request = CompareStoresRequest(
        store_ids=["S001", "S002"],
        start_date="2026-03-01",
        end_date="2026-03-08",
    )

    service_result = {
        "stores": [
            {"id": "S001", "name": "岳麓店", "region": "华中"},
            {"id": "S002", "name": "芙蓉店", "region": "华中"},
        ],
        "metrics": ["revenue", "orders", "customers"],
        "data": {
            "revenue": {"S001": 100000, "S002": 90000},
            "orders": {"S001": 100, "S002": 80},
            "customers": {"S001": 160, "S002": 130},
        },
    }

    with patch("src.api.multi_store.store_service.compare_stores", new=AsyncMock(return_value=service_result)):
        out = await compare_stores(request, current_user=None)

    assert out["metrics"] == ["revenue", "orders", "customers", "avg_order_value"]
    assert out["start_date"] == "2026-03-01"
    assert out["stores"][0]["metrics"]["revenue"] == 100000
    assert out["stores"][0]["metrics"]["avg_order_value"] == 1000
    assert out["data"]["orders"]["S002"] == 80


@pytest.mark.asyncio
async def test_compare_stores_appends_avg_order_value_when_metrics_missing_and_fallback_computes():
    request = CompareStoresRequest(
        store_ids=["S001", "S002"],
        metrics=["revenue", "orders", "customers"],
        start_date="2026-03-01",
        end_date="2026-03-08",
    )

    service_result = {
        "stores": [
            {"id": "S001", "name": "岳麓店", "region": "华中"},
            {"id": "S002", "name": "芙蓉店", "region": "华中"},
        ],
        "metrics": ["revenue", "orders", "customers", "avg_order_value"],
        "data": {
            "revenue": {"S001": 100000, "S002": 90000},
            "orders": {"S001": 100, "S002": 0},
            "customers": {"S001": 160, "S002": 130},
        },
    }

    with patch("src.api.multi_store.store_service.compare_stores", new=AsyncMock(return_value=service_result)) as mocked:
        out = await compare_stores(request, current_user=None)

    called_metrics = mocked.await_args.args[1]
    assert called_metrics == ["revenue", "orders", "customers", "avg_order_value"]
    assert out["metrics"] == ["revenue", "orders", "customers", "avg_order_value"]
    assert out["stores"][0]["metrics"]["avg_order_value"] == 1000
    assert out["stores"][1]["metrics"]["avg_order_value"] == 0


@pytest.mark.asyncio
async def test_get_regional_summary_compat_aggregates_stats():
    s1 = SimpleNamespace(id="S001")
    s2 = SimpleNamespace(id="S002")

    with patch(
        "src.api.multi_store.store_service.get_stores_by_region",
        new=AsyncMock(return_value={"华中": [s1, s2]}),
    ), patch(
        "src.api.multi_store.store_service.get_store_stats",
        new=AsyncMock(side_effect=[
            {"today_revenue": 100000, "today_orders": 100, "today_customers": 150},
            {"today_revenue": 80000, "today_orders": 90, "today_customers": 120},
        ]),
    ):
        out = await get_regional_summary_compat(current_user=None)

    assert out["regions"][0]["region"] == "华中"
    assert out["regions"][0]["store_count"] == 2
    assert out["regions"][0]["total_revenue"] == 180000
    assert out["regions"][0]["total_orders"] == 190


@pytest.mark.asyncio
async def test_get_performance_ranking_compat_adds_growth_rate_default():
    with patch(
        "src.api.multi_store.store_service.get_performance_ranking",
        new=AsyncMock(return_value=[
            {"store_id": "S001", "store_name": "岳麓店", "region": "华中", "value": 100000, "rank": 1}
        ]),
    ):
        out = await get_performance_ranking_compat(metric="revenue", limit=10, current_user=None)

    assert out["metric"] == "revenue"
    assert out["ranking"][0]["store_id"] == "S001"
    assert out["ranking"][0]["growth_rate"] == 0.0


def test_static_count_route_not_captured_by_dynamic_store_id_route():
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/multi-store")
    app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(id="u1", role="admin")

    with patch("src.api.multi_store.store_service.get_store_count", new=AsyncMock(return_value=7)), patch(
        "src.api.multi_store.store_service.get_store", new=AsyncMock(return_value=None)
    ):
        client = TestClient(app)
        response = client.get("/api/v1/multi-store/count")

    assert response.status_code == 200
    assert response.json()["count"] == 7


def test_static_stores_route_not_captured_by_dynamic_store_id_route():
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/multi-store")
    app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(id="u1", role="admin")

    store = SimpleNamespace(
        id="S001",
        name="岳麓店",
        code="YL01",
        address="长沙市岳麓区",
        city="长沙",
        district="岳麓",
        region="华中",
        status="active",
        is_active=True,
        manager_id="U001",
        area=300,
        seats=120,
        phone="123456",
        created_at=None,
    )

    with patch("src.api.multi_store.store_service.get_stores", new=AsyncMock(return_value=[store])), patch(
        "src.api.multi_store.store_service.get_store", new=AsyncMock(return_value=None)
    ):
        client = TestClient(app)
        response = client.get("/api/v1/multi-store/stores")

    assert response.status_code == 200
    assert response.json()["stores"][0]["id"] == "S001"


def test_static_list_route_not_captured_by_dynamic_store_id_route():
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/multi-store")
    app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(id="u1", role="admin")

    store = SimpleNamespace(
        id="S001",
        name="岳麓店",
        code="YL01",
        address="长沙市岳麓区",
        city="长沙",
        district="岳麓",
        region="华中",
        status="active",
        is_active=True,
        manager_id="U001",
        area=300,
        seats=120,
        phone="123456",
        created_at=None,
    )

    with patch("src.api.multi_store.store_service.get_stores", new=AsyncMock(return_value=[store])), patch(
        "src.api.multi_store.store_service.get_store", new=AsyncMock(return_value=None)
    ):
        client = TestClient(app)
        response = client.get("/api/v1/multi-store/list")

    assert response.status_code == 200
    assert response.json()["stores"][0]["id"] == "S001"


def test_static_performance_ranking_route_not_captured_by_dynamic_store_id_route():
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/multi-store")
    app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(id="u1", role="admin")

    with patch(
        "src.api.multi_store.store_service.get_performance_ranking",
        new=AsyncMock(return_value=[{"store_id": "S001", "store_name": "岳麓店", "region": "华中", "value": 100000, "rank": 1}]),
    ), patch("src.api.multi_store.store_service.get_store", new=AsyncMock(return_value=None)):
        client = TestClient(app)
        response = client.get("/api/v1/multi-store/performance-ranking?metric=revenue&limit=10")

    assert response.status_code == 200
    assert response.json()["ranking"][0]["store_id"] == "S001"
    assert response.json()["ranking"][0]["growth_rate"] == 0.0


def test_static_regional_summary_route_not_captured_by_dynamic_store_id_route():
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/multi-store")
    app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(id="u1", role="admin")

    s1 = SimpleNamespace(id="S001")
    with patch(
        "src.api.multi_store.store_service.get_stores_by_region",
        new=AsyncMock(return_value={"华中": [s1]}),
    ), patch(
        "src.api.multi_store.store_service.get_store_stats",
        new=AsyncMock(return_value={"today_revenue": 100000, "today_orders": 100, "today_customers": 150}),
    ), patch("src.api.multi_store.store_service.get_store", new=AsyncMock(return_value=None)):
        client = TestClient(app)
        response = client.get("/api/v1/multi-store/regional-summary")

    assert response.status_code == 200
    assert response.json()["regions"][0]["region"] == "华中"


def test_dynamic_store_id_route_declared_after_all_static_get_routes():
    get_routes = []
    for route in router.routes:
        methods = getattr(route, "methods", set()) or set()
        if "GET" not in methods:
            continue
        get_routes.append(route.path)

    assert "/{store_id}" in get_routes
    dynamic_index = get_routes.index("/{store_id}")

    # 约束：任何新增静态 GET 路由都必须在 /{store_id} 前声明，防止被动态路由吞掉。
    static_get_routes = [path for path in get_routes if "{" not in path]
    for static_path in static_get_routes:
        assert get_routes.index(static_path) < dynamic_index, f"static route {static_path} must be before /{{store_id}}"


def test_single_segment_static_get_routes_are_all_before_dynamic_store_id_route():
    get_routes = []
    for route in router.routes:
        methods = getattr(route, "methods", set()) or set()
        if "GET" not in methods:
            continue
        get_routes.append(route.path)

    assert "/{store_id}" in get_routes
    dynamic_index = get_routes.index("/{store_id}")

    single_segment_static = []
    for path in get_routes:
        if "{" in path:
            continue
        if path == "/":
            continue
        if path.count("/") != 1:
            continue
        single_segment_static.append(path)

    for static_path in single_segment_static:
        assert get_routes.index(static_path) < dynamic_index, f"single-segment static route {static_path} must be before /{{store_id}}"
