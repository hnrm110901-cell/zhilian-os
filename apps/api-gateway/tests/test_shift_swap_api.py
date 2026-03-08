import json
import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.api.employees import (
    ShiftSwapApprovalRequest,
    ShiftSwapRequestCreate,
    approve_shift_swap_request,
    create_shift_swap_request,
    list_shift_swap_requests,
)
from src.models.schedule import Schedule, Shift
from src.models.store import Store
from src.models.task import Task, TaskStatus


@pytest.mark.asyncio
async def test_create_shift_swap_request_success():
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    requester = SimpleNamespace(id="E1", store_id="S1", name="张三", skills=["cashier"], is_active=True)
    target = SimpleNamespace(id="E2", store_id="S1", name="李四", skills=["cashier"], is_active=True)

    shift_id = uuid.uuid4()
    schedule_id = uuid.uuid4()
    shift = SimpleNamespace(id=shift_id, schedule_id=schedule_id, employee_id="E1", position="cashier")
    schedule = SimpleNamespace(id=schedule_id, store_id="S1", schedule_date=date(2026, 3, 8))
    manager_id = uuid.uuid4()
    store = SimpleNamespace(id="S1", manager_id=manager_id)

    async def _get(model, key):
        if model is Shift and key == shift_id:
            return shift
        if model is Schedule and key == schedule_id:
            return schedule
        if model is Store and key == "S1":
            return store
        return None

    session.get.side_effect = _get

    with patch("src.api.employees.EmployeeRepository.get_by_id", new=AsyncMock(side_effect=[requester, target])):
        with patch("src.api.employees.wechat_service.send_text_message", new=AsyncMock(return_value={"errcode": 0})):
            response = await create_shift_swap_request(
                employee_id="E1",
                req=ShiftSwapRequestCreate(shift_id=str(shift_id), target_employee_id="E2", reason="临时有事"),
                session=session,
                current_user=SimpleNamespace(id=uuid.uuid4()),
            )

    assert response["status"] == TaskStatus.PENDING
    session.add.assert_called_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_shift_swap_request_skill_mismatch():
    session = AsyncMock()
    requester = SimpleNamespace(id="E1", store_id="S1", name="张三", skills=["cashier"], is_active=True)
    target = SimpleNamespace(id="E2", store_id="S1", name="李四", skills=["chef"], is_active=True)

    shift_id = uuid.uuid4()
    schedule_id = uuid.uuid4()
    shift = SimpleNamespace(id=shift_id, schedule_id=schedule_id, employee_id="E1", position="cashier")
    schedule = SimpleNamespace(id=schedule_id, store_id="S1", schedule_date=date(2026, 3, 8))

    async def _get(model, key):
        if model is Shift and key == shift_id:
            return shift
        if model is Schedule and key == schedule_id:
            return schedule
        return None

    session.get.side_effect = _get

    with patch("src.api.employees.EmployeeRepository.get_by_id", new=AsyncMock(side_effect=[requester, target])):
        with pytest.raises(HTTPException) as exc:
            await create_shift_swap_request(
                employee_id="E1",
                req=ShiftSwapRequestCreate(shift_id=str(shift_id), target_employee_id="E2", reason="临时有事"),
                session=session,
                current_user=SimpleNamespace(id=uuid.uuid4()),
            )

    assert exc.value.status_code == 400
    assert "技能不匹配" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_approve_shift_swap_request_success():
    session = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    request_id = uuid.uuid4()
    shift_id = uuid.uuid4()
    manager_id = uuid.uuid4()

    task = SimpleNamespace(
        id=request_id,
        category="shift_swap",
        status=TaskStatus.PENDING,
        store_id="S1",
        content=json.dumps({"shift_id": str(shift_id), "from_employee_id": "E1", "to_employee_id": "E2"}),
        result=None,
        completed_at=None,
    )
    store = SimpleNamespace(id="S1", manager_id=manager_id)
    shift = SimpleNamespace(id=shift_id, employee_id="E1")

    async def _get(model, key):
        if model is Task and key == request_id:
            return task
        if model is Store and key == "S1":
            return store
        if model is Shift and key == shift_id:
            return shift
        return None

    session.get.side_effect = _get

    with patch("src.api.employees.wechat_service.send_text_message", new=AsyncMock(return_value={"errcode": 0})):
        response = await approve_shift_swap_request(
            request_id=str(request_id),
            req=ShiftSwapApprovalRequest(approved=True, comment="同意"),
            session=session,
            current_user=SimpleNamespace(id=manager_id),
        )

    assert response["approved"] is True
    assert shift.employee_id == "E2"
    assert task.status == TaskStatus.COMPLETED
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_approve_shift_swap_request_forbidden_non_manager():
    session = AsyncMock()
    request_id = uuid.uuid4()

    task = SimpleNamespace(
        id=request_id,
        category="shift_swap",
        status=TaskStatus.PENDING,
        store_id="S1",
        content=json.dumps({"shift_id": str(uuid.uuid4()), "from_employee_id": "E1", "to_employee_id": "E2"}),
    )
    store = SimpleNamespace(id="S1", manager_id=uuid.uuid4())

    async def _get(model, key):
        if model is Task and key == request_id:
            return task
        if model is Store and key == "S1":
            return store
        return None

    session.get.side_effect = _get

    with pytest.raises(HTTPException) as exc:
        await approve_shift_swap_request(
            request_id=str(request_id),
            req=ShiftSwapApprovalRequest(approved=False, comment="不同意"),
            session=session,
            current_user=SimpleNamespace(id=uuid.uuid4()),
        )

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_list_shift_swap_requests():
    session = AsyncMock()

    task = SimpleNamespace(
        id=uuid.uuid4(),
        title="换班申请",
        status=TaskStatus.PENDING,
        store_id="S1",
        created_at=None,
        completed_at=None,
        content=json.dumps({"from_employee_id": "E1", "to_employee_id": "E2"}),
        result=None,
    )

    result_obj = MagicMock()
    result_obj.scalars.return_value.all.return_value = [task]
    session.execute = AsyncMock(return_value=result_obj)

    response = await list_shift_swap_requests(
        store_id="S1",
        status=None,
        session=session,
        current_user=SimpleNamespace(id=uuid.uuid4()),
    )

    assert response["store_id"] == "S1"
    assert response["total"] == 1
    assert response["items"][0]["content"]["from_employee_id"] == "E1"
