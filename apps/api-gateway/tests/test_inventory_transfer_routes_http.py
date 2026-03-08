"""Inventory transfer HTTP route tests."""
import os
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

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

from src.api.inventory import router, get_current_active_user, get_db  # noqa: E402
from src.models.decision_log import DecisionStatus  # noqa: E402


class _ScalarOneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _ScalarsAllResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return self._values


class _FakeSession:
    def __init__(self, execute_results):
        self._execute_results = list(execute_results)
        self.added = []

    async def execute(self, _stmt):
        return self._execute_results.pop(0)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        return None


def _build_client(session: _FakeSession) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(id="u-1", role="store_manager")

    async def _override_db():
        return session

    app.dependency_overrides[get_db] = _override_db
    return TestClient(app)


def test_create_transfer_request_route_returns_pending():
    source_item = SimpleNamespace(
        id="inv-src-1",
        store_id="S001",
        name="鸡腿",
        unit="kg",
        current_quantity=50.0,
    )
    target_item = SimpleNamespace(
        id="inv-tgt-1",
        store_id="S002",
        name="鸡腿",
        unit="kg",
        current_quantity=8.0,
    )
    session = _FakeSession([
        _ScalarOneResult(source_item),
        _ScalarOneResult(target_item),
    ])

    with patch(
        "src.api.inventory.approval_service.create_approval_request",
        new=AsyncMock(return_value=SimpleNamespace(id="dec-1")),
    ):
        client = _build_client(session)
        response = client.post(
            "/api/v1/inventory/transfer-request?store_id=S001",
            json={
                "source_item_id": "inv-src-1",
                "target_store_id": "S002",
                "target_item_id": "inv-tgt-1",
                "quantity": 8,
                "reason": "晚高峰调货",
            },
        )

    assert response.status_code == 201
    data = response.json()
    assert data["decision_id"] == "dec-1"
    assert data["status"] == "pending_approval"
    assert data["transfer"]["target_store_id"] == "S002"


def test_create_transfer_request_rejects_non_positive_quantity():
    session = _FakeSession([])
    client = _build_client(session)

    response = client.post(
        "/api/v1/inventory/transfer-request?store_id=S001",
        json={
            "source_item_id": "inv-src-1",
            "target_store_id": "S002",
            "quantity": 0,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "调货数量必须大于0"


def test_create_transfer_request_rejects_same_source_and_target_store():
    session = _FakeSession([])
    client = _build_client(session)

    response = client.post(
        "/api/v1/inventory/transfer-request?store_id=S001",
        json={
            "source_item_id": "inv-src-1",
            "target_store_id": "S001",
            "quantity": 2,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "目标门店不能与来源门店相同"


def test_list_transfer_requests_route_filters_status():
    row1 = SimpleNamespace(
        id="dec-1",
        store_id="S001",
        ai_suggestion={"source_store_id": "S001", "target_store_id": "S002", "item_name": "鸡腿", "quantity": 8},
        decision_status=DecisionStatus.PENDING,
        manager_feedback=None,
        created_at=datetime(2026, 3, 8, 9, 0, 0),
        approved_at=None,
        executed_at=None,
    )
    row2 = SimpleNamespace(
        id="dec-2",
        store_id="S001",
        ai_suggestion={"source_store_id": "S001", "target_store_id": "S003", "item_name": "牛肉", "quantity": 5},
        decision_status=DecisionStatus.REJECTED,
        manager_feedback="不通过",
        created_at=datetime(2026, 3, 8, 10, 0, 0),
        approved_at=datetime(2026, 3, 8, 10, 5, 0),
        executed_at=None,
    )
    session = _FakeSession([_ScalarsAllResult([row1, row2])])
    client = _build_client(session)

    response = client.get("/api/v1/inventory/transfer-requests?store_id=S001&status=pending&limit=30")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["decision_id"] == "dec-1"
    assert data["items"][0]["status"] == "pending"


def test_approve_transfer_request_route_executes():
    decision = SimpleNamespace(
        id="dec-1",
        decision_status=DecisionStatus.PENDING,
        ai_suggestion={"source_item_id": "inv-src-1", "target_item_id": "inv-tgt-1", "quantity": 8},
        approval_chain=[],
    )
    source_item = SimpleNamespace(id="inv-src-1", store_id="S001", current_quantity=20.0)
    target_item = SimpleNamespace(id="inv-tgt-1", store_id="S002", current_quantity=3.0)
    session = _FakeSession([
        _ScalarOneResult(decision),
        _ScalarOneResult(source_item),
        _ScalarOneResult(target_item),
    ])
    client = _build_client(session)

    response = client.post(
        "/api/v1/inventory/transfer-requests/dec-1/approve",
        json={"manager_feedback": "同意"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["status"] == "executed"
    assert data["source_new_quantity"] == 12.0
    assert data["target_new_quantity"] == 11.0


def test_reject_transfer_request_route_marks_rejected():
    decision = SimpleNamespace(
        id="dec-1",
        decision_status=DecisionStatus.PENDING,
        approval_chain=[],
    )
    session = _FakeSession([_ScalarOneResult(decision)])
    client = _build_client(session)

    response = client.post(
        "/api/v1/inventory/transfer-requests/dec-1/reject",
        json={"manager_feedback": "本店库存不足"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["status"] == "rejected"


def test_approve_transfer_request_route_rejects_non_pending_decision():
    decision = SimpleNamespace(
        id="dec-1",
        decision_status=DecisionStatus.REJECTED,
        ai_suggestion={"source_item_id": "inv-src-1", "target_item_id": "inv-tgt-1", "quantity": 8},
        approval_chain=[],
    )
    session = _FakeSession([_ScalarOneResult(decision)])
    client = _build_client(session)

    response = client.post(
        "/api/v1/inventory/transfer-requests/dec-1/approve",
        json={"manager_feedback": "同意"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "仅待审批的调货申请可批准"


def test_inventory_single_segment_static_get_routes_precede_dynamic_item_route():
    get_paths = []
    for route in router.routes:
        methods = getattr(route, "methods", set()) or set()
        if "GET" not in methods:
            continue
        get_paths.append(route.path)

    assert "/inventory/{item_id}" in get_paths
    dynamic_index = get_paths.index("/inventory/{item_id}")

    single_segment_static_paths = []
    for path in get_paths:
        if not path.startswith("/inventory/"):
            continue
        suffix = path[len("/inventory/") :]
        if "{" in suffix:
            continue
        if "/" in suffix:
            continue
        single_segment_static_paths.append(path)

    assert "/inventory/transfer-requests" in single_segment_static_paths
    for static_path in single_segment_static_paths:
        assert get_paths.index(static_path) < dynamic_index
