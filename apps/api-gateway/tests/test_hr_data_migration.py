"""Tests for HR data migration script (employees → persons/assignments)."""
import os
import uuid
from datetime import date, datetime
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

# Ensure env vars before importing src modules
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/test")
os.environ.setdefault("APP_ENV", "test")

from src.migrations.hr_data_migration import HrDataMigration, MigrationReport


@pytest.fixture
def mock_session():
    """Create a mock AsyncSession that tracks executed SQL."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    # begin_nested() returns an async context manager (savepoint per employee)
    nested_cm = AsyncMock()
    nested_cm.__aenter__ = AsyncMock(return_value=None)
    nested_cm.__aexit__ = AsyncMock(return_value=False)
    session.begin_nested = MagicMock(return_value=nested_cm)
    return session


def _make_employee_row(
    emp_id="EMP001",
    store_id="STORE001",
    name="张三",
    phone="13800138000",
    email="zhangsan@test.com",
    position="waiter",
    skills=None,
    training_completed=None,
    hire_date=None,
    is_active=True,
    preferences=None,
):
    """Build a mock Row object that looks like an employees table row."""
    row = MagicMock()
    row.id = emp_id
    row.store_id = store_id
    row.name = name
    row.phone = phone
    row.email = email
    row.position = position
    row.skills = skills or ["服务技能"]
    row.training_completed = training_completed or []
    row.hire_date = hire_date or date(2025, 6, 1)
    row.is_active = is_active
    row.preferences = preferences or {}
    # Make it subscriptable like a Row
    row._mapping = {
        "id": row.id,
        "store_id": row.store_id,
        "name": row.name,
        "phone": row.phone,
        "email": row.email,
        "position": row.position,
        "skills": row.skills,
        "training_completed": row.training_completed,
        "hire_date": row.hire_date,
        "is_active": row.is_active,
        "preferences": row.preferences,
    }
    return row


def _mock_scalars_all(rows):
    """Helper: mock session.execute().scalars().all() pattern (single-column queries)."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    return result


def _mock_fetchall(rows):
    """Helper: mock session.execute().fetchall() pattern (multi-column queries)."""
    result = MagicMock()
    result.fetchall.return_value = rows
    return result


def _mock_scalar_one_or_none(value):
    """Helper: mock session.execute().scalar_one_or_none()."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _mock_scalar(value):
    """Helper: mock session.execute().scalar()."""
    result = MagicMock()
    result.scalar.return_value = value
    return result


@pytest.mark.asyncio
async def test_migrate_all_basic(mock_session):
    """Migrate one active employee with an org_node_id on its store."""
    emp = _make_employee_row()

    call_count = 0
    async def fake_execute(stmt, params=None):
        nonlocal call_count
        call_count += 1
        sql_str = str(stmt) if not isinstance(stmt, str) else stmt
        sql_text = getattr(stmt, 'text', sql_str)

        # 1) SELECT employees — use _mock_fetchall (multi-column: SELECT id, store_id, ...)
        if "FROM employees" in sql_text and "employee_id_map" not in sql_text:
            return _mock_fetchall([emp])
        # 2) Check already migrated
        if "employee_id_map" in sql_text and "SELECT" in sql_text:
            return _mock_scalar_one_or_none(None)
        # 3) store → org_node_id lookup
        if "org_node_id" in sql_text and "stores" in sql_text:
            return _mock_scalar_one_or_none("ORG_NODE_001")
        # 4) skill ILIKE match — use _mock_fetchall (multi-column: SELECT id, skill_name)
        if "skill_nodes" in sql_text and "ILIKE" in sql_text:
            skill_row = MagicMock()
            skill_row.id = uuid.uuid4()
            skill_row.skill_name = "服务技能"
            return _mock_fetchall([skill_row])
        # 5) INSERTs — return None
        return MagicMock()

    mock_session.execute = AsyncMock(side_effect=fake_execute)

    migrator = HrDataMigration(session=mock_session, dry_run=False)
    report = await migrator.migrate_all()

    assert report.total == 1
    assert report.migrated == 1
    assert report.skipped_no_org_node == 0
    assert report.errors == 0


@pytest.mark.asyncio
async def test_migrate_skips_no_org_node(mock_session):
    """Employee whose store has no org_node_id is skipped."""
    emp = _make_employee_row()

    async def fake_execute(stmt, params=None):
        sql_text = getattr(stmt, 'text', str(stmt))
        if "FROM employees" in sql_text and "employee_id_map" not in sql_text:
            return _mock_fetchall([emp])
        if "employee_id_map" in sql_text and "SELECT" in sql_text:
            return _mock_scalar_one_or_none(None)
        if "org_node_id" in sql_text and "stores" in sql_text:
            return _mock_scalar_one_or_none(None)  # no org_node_id
        return MagicMock()

    mock_session.execute = AsyncMock(side_effect=fake_execute)

    migrator = HrDataMigration(session=mock_session, dry_run=False)
    report = await migrator.migrate_all()

    assert report.total == 1
    assert report.migrated == 0
    assert report.skipped_no_org_node == 1


@pytest.mark.asyncio
async def test_migrate_idempotent_skips_already_migrated(mock_session):
    """If employee_id_map already has the entry, skip it."""
    emp = _make_employee_row()

    async def fake_execute(stmt, params=None):
        sql_text = getattr(stmt, 'text', str(stmt))
        if "FROM employees" in sql_text and "employee_id_map" not in sql_text:
            return _mock_fetchall([emp])
        if "employee_id_map" in sql_text and "SELECT" in sql_text:
            return _mock_scalar_one_or_none(uuid.uuid4())  # already exists
        return MagicMock()

    mock_session.execute = AsyncMock(side_effect=fake_execute)

    migrator = HrDataMigration(session=mock_session, dry_run=False)
    report = await migrator.migrate_all()

    assert report.total == 1
    assert report.migrated == 0
    assert report.skipped_already_migrated == 1


@pytest.mark.asyncio
async def test_dry_run_does_not_commit(mock_session):
    """In dry-run mode, commit is never called."""
    emp = _make_employee_row()

    async def fake_execute(stmt, params=None):
        sql_text = getattr(stmt, 'text', str(stmt))
        if "FROM employees" in sql_text and "employee_id_map" not in sql_text:
            return _mock_fetchall([emp])
        if "employee_id_map" in sql_text and "SELECT" in sql_text:
            return _mock_scalar_one_or_none(None)
        if "org_node_id" in sql_text and "stores" in sql_text:
            return _mock_scalar_one_or_none("ORG_NODE_001")
        if "skill_nodes" in sql_text:
            return _mock_fetchall([])
        return MagicMock()

    mock_session.execute = AsyncMock(side_effect=fake_execute)

    migrator = HrDataMigration(session=mock_session, dry_run=True)
    report = await migrator.migrate_all()

    mock_session.commit.assert_not_called()
    assert report.total == 1


@pytest.mark.asyncio
async def test_migrate_inactive_employee_status_ended(mock_session):
    """Inactive employee gets status='ended' in assignment."""
    emp = _make_employee_row(is_active=False)
    captured_params = {}

    async def fake_execute(stmt, params=None):
        sql_text = getattr(stmt, 'text', str(stmt))
        if "FROM employees" in sql_text and "employee_id_map" not in sql_text:
            return _mock_fetchall([emp])
        if "employee_id_map" in sql_text and "SELECT" in sql_text:
            return _mock_scalar_one_or_none(None)
        if "org_node_id" in sql_text and "stores" in sql_text:
            return _mock_scalar_one_or_none("ORG_NODE_001")
        if "skill_nodes" in sql_text:
            return _mock_fetchall([])
        if "employment_assignments" in sql_text and "INSERT" in sql_text:
            if params:
                captured_params.update(params)
        return MagicMock()

    mock_session.execute = AsyncMock(side_effect=fake_execute)

    migrator = HrDataMigration(session=mock_session, dry_run=False)
    report = await migrator.migrate_all()

    assert report.migrated == 1
    assert captured_params.get("status") == "ended"


@pytest.mark.asyncio
async def test_migrate_with_store_id_filter(mock_session):
    """When store_id filter is set, only that store's employees are fetched."""
    emp = _make_employee_row(store_id="STORE_FILTER")
    captured_sql = []

    async def fake_execute(stmt, params=None):
        sql_text = getattr(stmt, 'text', str(stmt))
        captured_sql.append(sql_text)
        if "FROM employees" in sql_text and "employee_id_map" not in sql_text:
            return _mock_fetchall([emp])
        if "employee_id_map" in sql_text and "SELECT" in sql_text:
            return _mock_scalar_one_or_none(None)
        if "org_node_id" in sql_text and "stores" in sql_text:
            return _mock_scalar_one_or_none("ORG_NODE_FILTER")
        if "skill_nodes" in sql_text:
            return _mock_fetchall([])
        return MagicMock()

    mock_session.execute = AsyncMock(side_effect=fake_execute)

    migrator = HrDataMigration(session=mock_session, dry_run=False, store_id="STORE_FILTER")
    report = await migrator.migrate_all()

    # Verify that the employee SELECT included a store_id filter
    employee_selects = [s for s in captured_sql if "FROM employees" in s and "employee_id_map" not in s]
    assert any("store_id" in s for s in employee_selects)
    assert report.migrated == 1


@pytest.mark.asyncio
async def test_migration_report_dataclass():
    """MigrationReport has correct fields and summary."""
    report = MigrationReport(
        total=10, migrated=7, skipped_no_org_node=2,
        errors=1, skipped_already_migrated=0,
        details=["Migrated EMP001", "Skipped EMP002: no org_node_id"],
    )
    assert report.total == 10
    assert report.migrated == 7
    assert len(report.details) == 2
