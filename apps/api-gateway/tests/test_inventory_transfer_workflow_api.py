import os
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException

for _k, _v in {
    "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
    "REDIS_URL": "redis://localhost:6379/0",
    "CELERY_BROKER_URL": "redis://localhost:6379/0",
    "CELERY_RESULT_BACKEND": "redis://localhost:6379/0",
    "SECRET_KEY": "test-secret-key",
    "JWT_SECRET": "test-jwt-secret",
}.items():
    os.environ.setdefault(_k, _v)

from src.models.decision_log import DecisionStatus
from src.models.inventory import TransactionType
from src.api.inventory import (
    TransferRequestBody,
    TransferApprovalBody,
    TransferRejectBody,
    create_transfer_request,
    list_transfer_requests,
    approve_transfer_request,
    reject_transfer_request,
)


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


@pytest.mark.asyncio
async def test_create_transfer_request_success():
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
        current_quantity=10.0,
    )

    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            _ScalarOneResult(source_item),
            _ScalarOneResult(target_item),
        ]
    )

    with patch(
        "src.api.inventory.approval_service.create_approval_request",
        new=AsyncMock(return_value=SimpleNamespace(id="dec-1")),
    ):
        out = await create_transfer_request(
            req=TransferRequestBody(
                source_item_id="inv-src-1",
                target_store_id="S002",
                quantity=8.0,
                reason="晚高峰门店缺货",
            ),
            store_id="S001",
            session=session,
            current_user=SimpleNamespace(id="u-1"),
        )

    assert out["decision_id"] == "dec-1"
    assert out["status"] == "pending_approval"
    assert out["transfer"]["source_store_id"] == "S001"
    assert out["transfer"]["target_store_id"] == "S002"
    assert out["transfer"]["quantity"] == 8.0


@pytest.mark.asyncio
async def test_create_transfer_request_insufficient_stock():
    source_item = SimpleNamespace(
        id="inv-src-1",
        store_id="S001",
        name="鸡腿",
        unit="kg",
        current_quantity=2.0,
    )
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[_ScalarOneResult(source_item)])

    with pytest.raises(HTTPException) as ex:
        await create_transfer_request(
            req=TransferRequestBody(
                source_item_id="inv-src-1",
                target_store_id="S002",
                quantity=8.0,
            ),
            store_id="S001",
            session=session,
            current_user=SimpleNamespace(id="u-1"),
        )

    assert ex.value.status_code == 400
    assert "库存不足" in ex.value.detail


@pytest.mark.asyncio
async def test_list_transfer_requests_filters_status_and_store():
    row1 = SimpleNamespace(
        id="dec-1",
        store_id="S001",
        ai_suggestion={
            "source_store_id": "S001",
            "target_store_id": "S002",
            "source_item_id": "inv-src-1",
            "target_item_id": "inv-tgt-1",
            "item_name": "鸡腿",
            "quantity": 8.0,
            "unit": "kg",
            "reason": "调货",
        },
        decision_status=DecisionStatus.PENDING,
        manager_feedback=None,
        created_at=datetime(2026, 3, 8, 9, 0, 0),
        approved_at=None,
        executed_at=None,
    )
    row2 = SimpleNamespace(
        id="dec-2",
        store_id="S003",
        ai_suggestion={
            "source_store_id": "S003",
            "target_store_id": "S004",
            "source_item_id": "inv-src-2",
            "target_item_id": "inv-tgt-2",
            "item_name": "牛肉",
            "quantity": 5.0,
            "unit": "kg",
            "reason": "调货",
        },
        decision_status=DecisionStatus.REJECTED,
        manager_feedback="不通过",
        created_at=datetime(2026, 3, 8, 10, 0, 0),
        approved_at=datetime(2026, 3, 8, 10, 5, 0),
        executed_at=None,
    )

    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarsAllResult([row1, row2]))

    out = await list_transfer_requests(
        store_id="S001",
        status="pending",
        limit=50,
        session=session,
        current_user=SimpleNamespace(id="u-1"),
    )

    assert out["total"] == 1
    assert out["items"][0]["decision_id"] == "dec-1"
    assert out["items"][0]["status"] == "pending"


@pytest.mark.asyncio
async def test_list_transfer_requests_accepts_pending_approval_alias():
    row1 = SimpleNamespace(
        id="dec-1",
        store_id="S001",
        ai_suggestion={
            "source_store_id": "S001",
            "target_store_id": "S002",
            "source_item_id": "inv-src-1",
            "target_item_id": "inv-tgt-1",
            "item_name": "鸡腿",
            "quantity": 8.0,
            "unit": "kg",
            "reason": "调货",
        },
        decision_status=DecisionStatus.PENDING,
        manager_feedback=None,
        created_at=datetime(2026, 3, 8, 9, 0, 0),
        approved_at=None,
        executed_at=None,
    )
    row2 = SimpleNamespace(
        id="dec-2",
        store_id="S001",
        ai_suggestion={"source_store_id": "S001", "target_store_id": "S003"},
        decision_status=DecisionStatus.REJECTED,
        manager_feedback="不通过",
        created_at=datetime(2026, 3, 8, 10, 0, 0),
        approved_at=datetime(2026, 3, 8, 10, 5, 0),
        executed_at=None,
    )

    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarsAllResult([row1, row2]))

    out = await list_transfer_requests(
        store_id="S001",
        status="pending_approval",
        limit=50,
        session=session,
        current_user=SimpleNamespace(id="u-1"),
    )

    assert out["total"] == 1
    assert out["items"][0]["decision_id"] == "dec-1"
    assert out["items"][0]["status"] == "pending"


@pytest.mark.asyncio
async def test_list_transfer_requests_returns_empty_for_unknown_status_filter():
    row1 = SimpleNamespace(
        id="dec-1",
        store_id="S001",
        ai_suggestion={"source_store_id": "S001", "target_store_id": "S002"},
        decision_status=DecisionStatus.PENDING,
        manager_feedback=None,
        created_at=datetime(2026, 3, 8, 9, 0, 0),
        approved_at=None,
        executed_at=None,
    )
    row2 = SimpleNamespace(
        id="dec-2",
        store_id="S001",
        ai_suggestion={"source_store_id": "S001", "target_store_id": "S003"},
        decision_status=DecisionStatus.REJECTED,
        manager_feedback="不通过",
        created_at=datetime(2026, 3, 8, 10, 0, 0),
        approved_at=datetime(2026, 3, 8, 10, 5, 0),
        executed_at=None,
    )

    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarsAllResult([row1, row2]))

    out = await list_transfer_requests(
        store_id="S001",
        status="unknown_status",
        limit=50,
        session=session,
        current_user=SimpleNamespace(id="u-1"),
    )

    assert out["total"] == 0
    assert out["items"] == []


@pytest.mark.asyncio
async def test_approve_transfer_request_executes_stock_move_and_transactions():
    decision = SimpleNamespace(
        id="dec-1",
        decision_status=DecisionStatus.PENDING,
        ai_suggestion={
            "source_item_id": "inv-src-1",
            "target_item_id": "inv-tgt-1",
            "quantity": 8.0,
        },
        approval_chain=[],
    )
    source_item = SimpleNamespace(
        id="inv-src-1",
        store_id="S001",
        current_quantity=20.0,
    )
    target_item = SimpleNamespace(
        id="inv-tgt-1",
        store_id="S002",
        current_quantity=3.0,
    )

    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            _ScalarOneResult(decision),
            _ScalarOneResult(source_item),
            _ScalarOneResult(target_item),
        ]
    )
    session.add = Mock()
    session.commit = AsyncMock()

    out = await approve_transfer_request(
        decision_id="dec-1",
        req=TransferApprovalBody(manager_feedback="同意"),
        session=session,
        current_user=SimpleNamespace(id="manager-1"),
    )

    assert out["success"] is True
    assert out["status"] == "executed"
    assert source_item.current_quantity == 12.0
    assert target_item.current_quantity == 11.0
    assert decision.decision_status == DecisionStatus.EXECUTED
    assert decision.manager_feedback == "同意"
    assert len(decision.approval_chain) == 1

    add_calls = session.add.call_args_list
    assert len(add_calls) == 2
    first_txn = add_calls[0].args[0]
    second_txn = add_calls[1].args[0]
    assert first_txn.transaction_type == TransactionType.TRANSFER
    assert second_txn.transaction_type == TransactionType.TRANSFER


@pytest.mark.asyncio
async def test_reject_transfer_request_marks_rejected():
    decision = SimpleNamespace(
        id="dec-1",
        decision_status=DecisionStatus.PENDING,
        approval_chain=[],
    )

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[_ScalarOneResult(decision)])
    session.commit = AsyncMock()

    out = await reject_transfer_request(
        decision_id="dec-1",
        req=TransferRejectBody(manager_feedback="本店库存也紧张"),
        session=session,
        current_user=SimpleNamespace(id="manager-1"),
    )

    assert out["success"] is True
    assert out["status"] == "rejected"
    assert decision.decision_status == DecisionStatus.REJECTED
    assert decision.manager_feedback == "本店库存也紧张"
    assert len(decision.approval_chain) == 1
