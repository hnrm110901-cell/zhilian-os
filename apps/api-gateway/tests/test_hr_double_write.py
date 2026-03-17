"""Tests for HR double-write service."""
import os
import uuid
from datetime import date
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/test")
os.environ.setdefault("APP_ENV", "test")

from src.services.hr.double_write_service import DoubleWriteService


def _make_employee(
    emp_id="EMP_DW_001",
    store_id="STORE001",
    name="李四",
    phone="13900139000",
    email="lisi@test.com",
    position="chef",
    skills=None,
    training_completed=None,
    hire_date=None,
    is_active=True,
    preferences=None,
):
    """Build a mock Employee ORM object."""
    emp = MagicMock()
    emp.id = emp_id
    emp.store_id = store_id
    emp.name = name
    emp.phone = phone
    emp.email = email
    emp.position = position
    emp.skills = skills or []
    emp.training_completed = training_completed or []
    emp.hire_date = hire_date or date(2025, 6, 1)
    emp.is_active = is_active
    emp.preferences = preferences or {}
    return emp


def _mock_scalar_one_or_none(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _mock_scalars_all(rows):
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    return result


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_on_employee_created_success(mock_session):
    """on_employee_created inserts person + assignment + contract + id_map."""
    emp = _make_employee()

    call_log = []
    async def fake_execute(stmt, params=None):
        sql_text = getattr(stmt, 'text', str(stmt))
        call_log.append(sql_text)
        if "org_node_id" in sql_text and "stores" in sql_text:
            return _mock_scalar_one_or_none("ORG_NODE_001")
        if "employee_id_map" in sql_text and "SELECT" in sql_text:
            return _mock_scalar_one_or_none(None)
        if "skill_nodes" in sql_text:
            return _mock_scalars_all([])
        return MagicMock()

    mock_session.execute = AsyncMock(side_effect=fake_execute)

    svc = DoubleWriteService(session=mock_session)
    result = await svc.on_employee_created(emp)

    assert result is True
    # Should have INSERT into persons, employment_assignments, employment_contracts, employee_id_map
    insert_sqls = [s for s in call_log if "INSERT" in s]
    assert len(insert_sqls) >= 4


@pytest.mark.asyncio
async def test_on_employee_created_no_org_node(mock_session):
    """If store has no org_node_id, double-write is skipped (returns False)."""
    emp = _make_employee()

    async def fake_execute(stmt, params=None):
        sql_text = getattr(stmt, 'text', str(stmt))
        if "org_node_id" in sql_text and "stores" in sql_text:
            return _mock_scalar_one_or_none(None)
        if "employee_id_map" in sql_text and "SELECT" in sql_text:
            return _mock_scalar_one_or_none(None)
        return MagicMock()

    mock_session.execute = AsyncMock(side_effect=fake_execute)

    svc = DoubleWriteService(session=mock_session)
    result = await svc.on_employee_created(emp)

    assert result is False


@pytest.mark.asyncio
async def test_on_employee_created_already_exists(mock_session):
    """If employee_id_map entry exists, skip (idempotent)."""
    emp = _make_employee()

    async def fake_execute(stmt, params=None):
        sql_text = getattr(stmt, 'text', str(stmt))
        if "employee_id_map" in sql_text and "SELECT" in sql_text:
            return _mock_scalar_one_or_none(uuid.uuid4())
        if "org_node_id" in sql_text and "stores" in sql_text:
            return _mock_scalar_one_or_none("ORG_NODE_001")
        return MagicMock()

    mock_session.execute = AsyncMock(side_effect=fake_execute)

    svc = DoubleWriteService(session=mock_session)
    result = await svc.on_employee_created(emp)

    assert result is True  # not an error, just already synced


@pytest.mark.asyncio
async def test_on_employee_created_exception_is_silent(mock_session):
    """Exception in double-write does NOT propagate — returns False."""
    emp = _make_employee()
    mock_session.execute = AsyncMock(side_effect=Exception("DB boom"))

    svc = DoubleWriteService(session=mock_session)
    result = await svc.on_employee_created(emp)

    assert result is False  # silent failure


@pytest.mark.asyncio
async def test_on_employee_updated_name_sync(mock_session):
    """Updating name propagates to persons table."""
    emp = _make_employee(name="王五_updated")
    person_id = uuid.uuid4()

    call_log = []
    async def fake_execute(stmt, params=None):
        sql_text = getattr(stmt, 'text', str(stmt))
        call_log.append((sql_text, params))
        if "employee_id_map" in sql_text and "SELECT" in sql_text:
            row = MagicMock()
            row.person_id = person_id
            row.assignment_id = uuid.uuid4()
            return MagicMock(fetchone=MagicMock(return_value=row))
        return MagicMock()

    mock_session.execute = AsyncMock(side_effect=fake_execute)

    svc = DoubleWriteService(session=mock_session)
    result = await svc.on_employee_updated(emp)

    assert result is True
    update_sqls = [s for s, _ in call_log if "UPDATE" in s and "persons" in s]
    assert len(update_sqls) >= 1


@pytest.mark.asyncio
async def test_on_employee_updated_is_active_false(mock_session):
    """Deactivating employee sets assignment status to 'ended'."""
    emp = _make_employee(is_active=False)
    person_id = uuid.uuid4()
    assignment_id = uuid.uuid4()

    call_log = []
    async def fake_execute(stmt, params=None):
        sql_text = getattr(stmt, 'text', str(stmt))
        call_log.append((sql_text, params))
        if "employee_id_map" in sql_text and "SELECT" in sql_text:
            row = MagicMock()
            row.person_id = person_id
            row.assignment_id = assignment_id
            return MagicMock(fetchone=MagicMock(return_value=row))
        return MagicMock()

    mock_session.execute = AsyncMock(side_effect=fake_execute)

    svc = DoubleWriteService(session=mock_session)
    result = await svc.on_employee_updated(emp)

    assert result is True
    update_sqls = [s for s, _ in call_log if "UPDATE" in s and "employment_assignments" in s]
    assert len(update_sqls) >= 1


@pytest.mark.asyncio
async def test_on_employee_updated_no_id_map_entry(mock_session):
    """If employee has no id_map entry, update is a no-op (returns False)."""
    emp = _make_employee()

    async def fake_execute(stmt, params=None):
        sql_text = getattr(stmt, 'text', str(stmt))
        if "employee_id_map" in sql_text and "SELECT" in sql_text:
            return MagicMock(fetchone=MagicMock(return_value=None))
        return MagicMock()

    mock_session.execute = AsyncMock(side_effect=fake_execute)

    svc = DoubleWriteService(session=mock_session)
    result = await svc.on_employee_updated(emp)

    assert result is False


@pytest.mark.asyncio
async def test_on_employee_updated_exception_is_silent(mock_session):
    """on_employee_updated must return False and not raise when _do_update fails."""
    svc = DoubleWriteService(mock_session)
    # Make _do_update raise
    with patch.object(svc, "_do_update", side_effect=RuntimeError("db error")):
        result = await svc.on_employee_updated(MagicMock(id=uuid4(), name="Test"))
    assert result is False
    # Must not raise — test passing IS the assertion
