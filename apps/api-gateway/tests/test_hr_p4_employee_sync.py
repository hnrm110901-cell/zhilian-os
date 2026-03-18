"""P4 Employee Sync tests — EmployeeSyncService

All tests use mocked AsyncSession — no real database required.
"""
import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.hr.employee_sync_service import EmployeeSyncService

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_scalar_result(value):
    """Mock result whose scalar_one_or_none() returns value."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = value
    return mock_result


def _make_person(person_id=None, name="张三", phone="13800000001"):
    p = MagicMock()
    p.id = person_id or uuid.uuid4()
    p.name = name
    p.phone = phone
    return p


def _make_id_map(legacy_id="POS001", person_id=None, assignment_id=None):
    m = MagicMock()
    m.legacy_employee_id = legacy_id
    m.person_id = person_id or uuid.uuid4()
    m.assignment_id = assignment_id or uuid.uuid4()
    return m


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEmployeeSyncService:

    async def test_sync_new_employee_created(self):
        """new ext_id + active → Person + Assignment + IdMap created"""
        session = AsyncMock()
        # First execute: EmployeeIdMap lookup → not found
        # Second execute (flush side): handled by flush mock
        session.execute = AsyncMock(return_value=_make_scalar_result(None))
        session.flush = AsyncMock()
        session.add = MagicMock()

        svc = EmployeeSyncService()
        result = await svc.sync_from_pos(
            store_org_node_id="store-001",
            pos_employees=[
                {"external_id": "POS001", "name": "李四", "phone": "13900000001", "status": "active"},
            ],
            session=session,
        )

        assert result["created"] == 1
        assert result["total_processed"] == 1
        # Person + Assignment + IdMap = 3 adds
        assert session.add.call_count == 3

    async def test_sync_existing_unchanged(self):
        """same name/phone → unchanged count"""
        person = _make_person(name="张三", phone="13800000001")
        id_map = _make_id_map(legacy_id="POS001", person_id=person.id)

        session = AsyncMock()
        # Call 1: EmployeeIdMap lookup → found
        # Call 2: Person lookup → found with same data
        session.execute = AsyncMock(side_effect=[
            _make_scalar_result(id_map),
            _make_scalar_result(person),
        ])
        session.flush = AsyncMock()

        svc = EmployeeSyncService()
        result = await svc.sync_from_pos(
            store_org_node_id="store-001",
            pos_employees=[
                {"external_id": "POS001", "name": "张三", "phone": "13800000001", "status": "active"},
            ],
            session=session,
        )

        assert result["unchanged"] == 1
        assert result["updated"] == 0
        assert result["created"] == 0

    async def test_sync_existing_updated(self):
        """name changed → updated count"""
        person = _make_person(name="张三旧", phone="13800000001")
        id_map = _make_id_map(legacy_id="POS001", person_id=person.id)

        session = AsyncMock()
        session.execute = AsyncMock(side_effect=[
            _make_scalar_result(id_map),
            _make_scalar_result(person),
        ])
        session.flush = AsyncMock()

        svc = EmployeeSyncService()
        result = await svc.sync_from_pos(
            store_org_node_id="store-001",
            pos_employees=[
                {"external_id": "POS001", "name": "张三新", "phone": "13800000001", "status": "active"},
            ],
            session=session,
        )

        assert result["updated"] == 1
        assert person.name == "张三新"

    async def test_sync_terminated(self):
        """status=inactive with existing map → assignment ended"""
        id_map = _make_id_map(legacy_id="POS001")

        session = AsyncMock()
        # Call 1: EmployeeIdMap lookup → found
        # Call 2: update statement execution
        session.execute = AsyncMock(side_effect=[
            _make_scalar_result(id_map),
            MagicMock(),  # update result
        ])
        session.flush = AsyncMock()

        svc = EmployeeSyncService()
        result = await svc.sync_from_pos(
            store_org_node_id="store-001",
            pos_employees=[
                {"external_id": "POS001", "name": "张三", "status": "inactive"},
            ],
            session=session,
        )

        assert result["terminated"] == 1
        # The second execute call should be the UPDATE statement
        assert session.execute.call_count == 2

    async def test_sync_empty_external_id_skipped(self):
        """no external_id → skip"""
        session = AsyncMock()
        session.flush = AsyncMock()

        svc = EmployeeSyncService()
        result = await svc.sync_from_pos(
            store_org_node_id="store-001",
            pos_employees=[
                {"name": "无ID员工", "status": "active"},
                {"external_id": "", "name": "空ID员工", "status": "active"},
            ],
            session=session,
        )

        assert result["created"] == 0
        assert result["total_processed"] == 2
        # No execute calls since all skipped
        session.execute.assert_not_called()

    async def test_sync_inactive_new_skipped(self):
        """new + inactive → skip (don't create)"""
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_make_scalar_result(None))
        session.flush = AsyncMock()

        svc = EmployeeSyncService()
        result = await svc.sync_from_pos(
            store_org_node_id="store-001",
            pos_employees=[
                {"external_id": "POS999", "name": "离职员工", "status": "inactive"},
            ],
            session=session,
        )

        assert result["created"] == 0
        assert result["unchanged"] == 1
        # No add calls since we skip inactive new employees
        session.add.assert_not_called()

    async def test_sync_returns_correct_counts(self):
        """verify result dict with mixed operations"""
        person_existing = _make_person(name="王五", phone="13700000001")
        id_map_existing = _make_id_map(legacy_id="POS002", person_id=person_existing.id)
        id_map_terminate = _make_id_map(legacy_id="POS003")

        session = AsyncMock()
        session.execute = AsyncMock(side_effect=[
            # Employee 1 (POS001): new → not found
            _make_scalar_result(None),
            # Employee 2 (POS002): existing, unchanged → found map, then found person
            _make_scalar_result(id_map_existing),
            _make_scalar_result(person_existing),
            # Employee 3 (POS003): terminate → found map, then update
            _make_scalar_result(id_map_terminate),
            MagicMock(),  # update result
        ])
        session.flush = AsyncMock()
        session.add = MagicMock()

        svc = EmployeeSyncService()
        result = await svc.sync_from_pos(
            store_org_node_id="store-001",
            pos_employees=[
                {"external_id": "POS001", "name": "新人", "status": "active"},
                {"external_id": "POS002", "name": "王五", "phone": "13700000001", "status": "active"},
                {"external_id": "POS003", "name": "离职者", "status": "inactive"},
            ],
            session=session,
        )

        assert result["created"] == 1
        assert result["unchanged"] == 1
        assert result["terminated"] == 1
        assert result["total_processed"] == 3
        assert result["store"] == "store-001"

    async def test_sync_single_store_stub(self):
        """stub returns note about unimplemented API"""
        session = AsyncMock()

        svc = EmployeeSyncService()
        result = await svc.sync_single_store(
            store_org_node_id="store-001",
            adapter_type="pinzhi",
            session=session,
        )

        assert result["total_processed"] == 0
        assert "not yet implemented" in result["note"]
        assert "pinzhi" in result["note"]

    async def test_sync_phone_update_only_when_provided(self):
        """phone only updated when new phone is provided (not None)"""
        person = _make_person(name="赵六", phone="13600000001")
        id_map = _make_id_map(legacy_id="POS004", person_id=person.id)

        session = AsyncMock()
        session.execute = AsyncMock(side_effect=[
            _make_scalar_result(id_map),
            _make_scalar_result(person),
        ])
        session.flush = AsyncMock()

        svc = EmployeeSyncService()
        # phone=None → should not update phone, name same → unchanged
        result = await svc.sync_from_pos(
            store_org_node_id="store-001",
            pos_employees=[
                {"external_id": "POS004", "name": "赵六", "status": "active"},
            ],
            session=session,
        )

        assert result["unchanged"] == 1
        assert person.phone == "13600000001"  # phone unchanged
