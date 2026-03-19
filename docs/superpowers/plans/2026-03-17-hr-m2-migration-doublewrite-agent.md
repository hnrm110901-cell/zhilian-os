# HR Foundation M2 — 数据迁移 + 双写模式 + HRAgent v1 (B级)

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有 employees 表数据迁移到新 HR 表，建立双写保持数据同步，并实现 HRAgent v1 B级诊断能力（离职风险扫描 WF-1 + 技能成长催化 WF-3）。

**Architecture:** 三阶段推进：(1) 一次性迁移脚本将历史 Employee 数据搬入 persons/assignments/contracts；(2) DoubleWriteService 拦截新 Employee 写入并同步到新表（失败静默）；(3) HRAgent v1 基于规则引擎提供诊断建议，无 ML 依赖。

**Tech Stack:** Python 3.11, SQLAlchemy 2.0 (Column-style), asyncpg, FastAPI, pytest-asyncio, structlog

**Prerequisite:** M1 完成（z54/z55 migrations applied，hr_knowledge_rules + skill_nodes 已种子数据）

---

## Chunk 1: Data Migration Script

**Goal:** 一次性将 `employees` 表现有数据迁移到 `persons` + `employment_assignments` + `employment_contracts` + `employee_id_map` + `person_achievements`。支持 `--dry-run` 和 `--store-id` 过滤，幂等可重跑。

### Files

| Action | File |
|--------|------|
| CREATE | `apps/api-gateway/src/migrations/__init__.py` |
| CREATE | `apps/api-gateway/src/migrations/hr_data_migration.py` |
| CREATE | `apps/api-gateway/tests/test_hr_data_migration.py` |

### Steps

- [ ] **1.1** Create the `migrations` package init file.

```bash
mkdir -p apps/api-gateway/src/migrations
touch apps/api-gateway/src/migrations/__init__.py
```

- [ ] **1.2** Write the test file `apps/api-gateway/tests/test_hr_data_migration.py` (TDD — tests first).

```python
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
```

Run to confirm tests are collected (they will fail — implementation not yet written):

```bash
cd apps/api-gateway && python -m pytest tests/test_hr_data_migration.py --collect-only 2>&1 | tail -5
```

Expected: `7 tests collected` (or import error, which is fine at this stage).

- [ ] **1.3** Write the migration script `apps/api-gateway/src/migrations/hr_data_migration.py`.

```python
"""HR Data Migration — employees → persons/assignments/contracts/achievements.

Usage:
    python -m src.migrations.hr_data_migration
    python -m src.migrations.hr_data_migration --dry-run
    python -m src.migrations.hr_data_migration --store-id STORE001

Idempotent: checks employee_id_map before inserting. Safe to re-run.
"""
import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

import structlog
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


@dataclass
class MigrationReport:
    total: int = 0
    migrated: int = 0
    skipped_no_org_node: int = 0
    errors: int = 0
    skipped_already_migrated: int = 0
    details: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"Migration complete: {self.total} total, {self.migrated} migrated, "
            f"{self.skipped_no_org_node} skipped (no org_node), "
            f"{self.skipped_already_migrated} skipped (already migrated), "
            f"{self.errors} errors"
        )


class HrDataMigration:
    """Migrate employees table data to new HR tables."""

    def __init__(
        self,
        session: AsyncSession,
        dry_run: bool = False,
        store_id: Optional[str] = None,
    ) -> None:
        self._session = session
        self._dry_run = dry_run
        self._store_id = store_id

    async def migrate_all(self) -> MigrationReport:
        """Migrate all (or filtered) employees. Returns a report."""
        report = MigrationReport()

        employees = await self._fetch_employees()
        report.total = len(employees)

        for emp in employees:
            try:
                # Use savepoint per employee: DB-level errors (constraint violations, etc.)
                # roll back only this employee's inserts, leaving the outer transaction valid.
                async with self._session.begin_nested():
                    result = await self._migrate_one_employee(emp)
                if result == "migrated":
                    report.migrated += 1
                    report.details.append(f"Migrated {emp.id}")
                elif result == "skipped_no_org_node":
                    report.skipped_no_org_node += 1
                    report.details.append(
                        f"Skipped {emp.id}: store {emp.store_id} has no org_node_id"
                    )
                elif result == "skipped_already_migrated":
                    report.skipped_already_migrated += 1
                    report.details.append(f"Skipped {emp.id}: already migrated")
            except Exception as exc:
                report.errors += 1
                report.details.append(f"Error migrating {emp.id}: {exc}")
                logger.error(
                    "hr_migration.employee_error",
                    employee_id=emp.id,
                    error=str(exc),
                )

        if not self._dry_run and report.migrated > 0:
            await self._session.commit()

        logger.info("hr_migration.complete", **{
            "total": report.total,
            "migrated": report.migrated,
            "skipped_no_org_node": report.skipped_no_org_node,
            "skipped_already_migrated": report.skipped_already_migrated,
            "errors": report.errors,
            "dry_run": self._dry_run,
        })
        return report

    async def _migrate_one_employee(self, emp) -> str:
        """Migrate a single employee. Returns status string."""
        # Idempotency check
        already = await self._check_already_migrated(emp.id)
        if already:
            return "skipped_already_migrated"

        # Resolve store → org_node_id
        org_node_id = await self._get_org_node_id_for_store(emp.store_id)
        if org_node_id is None:
            logger.warning(
                "hr_migration.no_org_node",
                employee_id=emp.id,
                store_id=emp.store_id,
            )
            return "skipped_no_org_node"

        if self._dry_run:
            return "migrated"

        # 1) INSERT person
        person_id = uuid.uuid4()
        await self._session.execute(
            sa.text(
                "INSERT INTO persons "
                "(id, legacy_employee_id, name, phone, email, preferences) "
                "VALUES (:id, :legacy_employee_id, :name, :phone, :email, "
                "        :preferences::jsonb)"
            ),
            {
                "id": str(person_id),
                "legacy_employee_id": emp.id,
                "name": emp.name,
                "phone": emp.phone,
                "email": emp.email,
                "preferences": json.dumps(emp.preferences or {}),
            },
        )

        # 2) INSERT employment_assignment
        assignment_id = uuid.uuid4()
        status = "active" if emp.is_active else "ended"
        start_date = emp.hire_date or date.today()
        await self._session.execute(
            sa.text(
                "INSERT INTO employment_assignments "
                "(id, person_id, org_node_id, job_standard_id, "
                " employment_type, start_date, status) "
                "VALUES (:id, :person_id, :org_node_id, NULL, "
                "        :employment_type, :start_date, :status)"
            ),
            {
                "id": str(assignment_id),
                "person_id": str(person_id),
                "org_node_id": org_node_id,
                "employment_type": "full_time",
                "start_date": start_date.isoformat(),
                "status": status,
            },
        )

        # 3) INSERT employment_contract (legacy shell)
        contract_id = uuid.uuid4()
        pay_scheme = {
            "base_salary": 0,
            "position_title": emp.position or "unknown",
            "note": "legacy_import",
        }
        await self._session.execute(
            sa.text(
                "INSERT INTO employment_contracts "
                "(id, assignment_id, contract_type, pay_scheme, valid_from) "
                "VALUES (:id, :assignment_id, :contract_type, "
                "        :pay_scheme::jsonb, :valid_from)"
            ),
            {
                "id": str(contract_id),
                "assignment_id": str(assignment_id),
                "contract_type": "labor",
                "pay_scheme": json.dumps(pay_scheme),
                "valid_from": start_date.isoformat(),
            },
        )

        # 4) INSERT employee_id_map (bridge)
        await self._session.execute(
            sa.text(
                "INSERT INTO employee_id_map "
                "(legacy_employee_id, person_id, assignment_id) "
                "VALUES (:legacy_employee_id, :person_id, :assignment_id)"
            ),
            {
                "legacy_employee_id": emp.id,
                "person_id": str(person_id),
                "assignment_id": str(assignment_id),
            },
        )

        # 5) Match skills + training_completed → person_achievements
        all_skill_strings = list(set(
            (emp.skills or []) + (emp.training_completed or [])
        ))
        if all_skill_strings:
            matched_skills = await self._match_skills_to_nodes(all_skill_strings)
            achieved_at = (emp.hire_date or date.today()).isoformat()
            for skill_row in matched_skills:
                achievement_id = uuid.uuid4()
                await self._session.execute(
                    sa.text(
                        "INSERT INTO person_achievements "
                        "(id, person_id, skill_node_id, achieved_at, "
                        " trigger_type) "
                        "VALUES (:id, :person_id, :skill_node_id, "
                        "        :achieved_at, :trigger_type) "
                        "ON CONFLICT ON CONSTRAINT uq_person_skill DO NOTHING"
                    ),
                    {
                        "id": str(achievement_id),
                        "person_id": str(person_id),
                        "skill_node_id": str(skill_row.id),
                        "achieved_at": achieved_at,
                        "trigger_type": "legacy_import",
                    },
                )

        logger.info(
            "hr_migration.employee_migrated",
            employee_id=emp.id,
            person_id=str(person_id),
            assignment_id=str(assignment_id),
        )
        return "migrated"

    # ── Helper queries ────────────────────────────────────────────────

    async def _fetch_employees(self):
        """Fetch employees, optionally filtered by store_id."""
        if self._store_id:
            result = await self._session.execute(
                sa.text(
                    "SELECT id, store_id, name, phone, email, position, "
                    "       skills, training_completed, hire_date, "
                    "       is_active, preferences "
                    "FROM employees WHERE store_id = :store_id"
                ),
                {"store_id": self._store_id},
            )
        else:
            result = await self._session.execute(
                sa.text(
                    "SELECT id, store_id, name, phone, email, position, "
                    "       skills, training_completed, hire_date, "
                    "       is_active, preferences "
                    "FROM employees"
                ),
            )
        # Use fetchall() (not scalars()) to get full Row objects with all columns
        return result.fetchall()

    async def _check_already_migrated(self, employee_id: str):
        """Return person_id if already in employee_id_map, else None."""
        result = await self._session.execute(
            sa.text(
                "SELECT person_id FROM employee_id_map "
                "WHERE legacy_employee_id = :emp_id"
            ),
            {"emp_id": employee_id},
        )
        return result.scalar_one_or_none()

    async def _get_org_node_id_for_store(self, store_id: str) -> Optional[str]:
        """Returns org_node_id from stores table, or None if not set."""
        result = await self._session.execute(
            sa.text(
                "SELECT org_node_id FROM stores WHERE id = :store_id"
            ),
            {"store_id": store_id},
        )
        return result.scalar_one_or_none()

    async def _match_skills_to_nodes(self, skills: list[str]):
        """ILIKE-match skill strings against skill_nodes.skill_name."""
        if not skills:
            return []
        # Build OR conditions with parameterized ILIKE
        # Use individual queries per skill to stay fully parameterized
        matched = []
        for skill_str in skills:
            result = await self._session.execute(
                sa.text(
                    "SELECT id, skill_name FROM skill_nodes "
                    "WHERE skill_name ILIKE :pattern"
                ),
                {"pattern": f"%{skill_str}%"},
            )
            # Use fetchall() (not scalars()) to get full Row objects with id + skill_name
            rows = result.fetchall()
            matched.extend(rows)
        # Deduplicate by id
        seen = set()
        deduped = []
        for row in matched:
            row_id = getattr(row, 'id', row)
            if row_id not in seen:
                seen.add(row_id)
                deduped.append(row)
        return deduped


# ── CLI entry point ──────────────────────────────────────────────────

async def _main():
    import argparse
    parser = argparse.ArgumentParser(description="Migrate employees → HR tables")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no writes")
    parser.add_argument("--store-id", type=str, default=None, help="Filter by store_id")
    args = parser.parse_args()

    from src.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        migrator = HrDataMigration(
            session=session,
            dry_run=args.dry_run,
            store_id=args.store_id,
        )
        report = await migrator.migrate_all()
        print(report.summary())
        for line in report.details:
            print(f"  {line}")


if __name__ == "__main__":
    asyncio.run(_main())
```

- [ ] **1.4** Run the tests.

```bash
cd apps/api-gateway && python -m pytest tests/test_hr_data_migration.py -v 2>&1 | tail -20
```

Expected: All 7 tests pass.

- [ ] **1.5** Commit Chunk 1.

```bash
git add apps/api-gateway/src/migrations/__init__.py \
       apps/api-gateway/src/migrations/hr_data_migration.py \
       apps/api-gateway/tests/test_hr_data_migration.py
git commit -m "feat(hr): M2 Chunk1 — employees→HR tables migration script (idempotent, --dry-run)"
```

---

## Chunk 2: Double-Write Service

**Goal:** 在现有 Employee create/update API 之后，异步同步数据到新 HR 表。失败静默（log only），不阻塞原 Employee 写入。新表在 M2 阶段为非权威数据。

### Files

| Action | File |
|--------|------|
| CREATE | `apps/api-gateway/src/services/hr/double_write_service.py` |
| MODIFY | `apps/api-gateway/src/api/employees.py` |
| CREATE | `apps/api-gateway/tests/test_hr_double_write.py` |

### Steps

- [ ] **2.1** Write test file `apps/api-gateway/tests/test_hr_double_write.py` (TDD).

```python
"""Tests for HR double-write service."""
import os
import uuid
from datetime import date
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
    result = await svc.on_employee_updated(emp, changed_fields={"name"})

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
    result = await svc.on_employee_updated(emp, changed_fields={"is_active"})

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
    result = await svc.on_employee_updated(emp, changed_fields={"name"})

    assert result is False
```

```bash
cd apps/api-gateway && python -m pytest tests/test_hr_double_write.py --collect-only 2>&1 | tail -5
```

Expected: `7 tests collected`.

- [ ] **2.2** Write `apps/api-gateway/src/services/hr/double_write_service.py`.

```python
"""DoubleWriteService — propagate Employee writes to new HR tables.

Shadow-write pattern: new HR tables are non-authoritative in M2.
Failures are logged but NEVER fail the original Employee API call.
"""
import json
import uuid
from datetime import date
from typing import Optional

import structlog
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


class DoubleWriteService:
    """Sync Employee writes to persons/assignments/contracts/id_map."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def on_employee_created(self, employee) -> bool:
        """Called after Employee is committed. Returns True if HR write succeeded."""
        try:
            return await self._do_create(employee)
        except Exception as exc:
            logger.warning(
                "hr_double_write.create_failed",
                employee_id=employee.id,
                error=str(exc),
            )
            return False

    async def on_employee_updated(self, employee, changed_fields: set[str]) -> bool:
        """Sync relevant changes to persons/assignments. Returns True if succeeded."""
        try:
            return await self._do_update(employee, changed_fields)
        except Exception as exc:
            logger.warning(
                "hr_double_write.update_failed",
                employee_id=employee.id,
                error=str(exc),
            )
            return False

    # ── Internal ──────────────────────────────────────────────────────

    async def _do_create(self, emp) -> bool:
        """Insert person + assignment + contract + id_map for a new Employee."""
        # Check idempotency
        existing = await self._lookup_id_map(emp.id)
        if existing is not None:
            logger.info(
                "hr_double_write.already_synced",
                employee_id=emp.id,
            )
            return True

        # Resolve org_node_id
        org_node_id = await self._get_org_node_id(emp.store_id)
        if org_node_id is None:
            logger.warning(
                "hr_double_write.no_org_node",
                employee_id=emp.id,
                store_id=emp.store_id,
            )
            return False

        person_id = uuid.uuid4()
        assignment_id = uuid.uuid4()
        contract_id = uuid.uuid4()
        status = "active" if emp.is_active else "ended"
        start_date = emp.hire_date or date.today()

        # 1) persons
        await self._session.execute(
            sa.text(
                "INSERT INTO persons "
                "(id, legacy_employee_id, name, phone, email, preferences) "
                "VALUES (:id, :legacy_employee_id, :name, :phone, :email, "
                "        :preferences::jsonb)"
            ),
            {
                "id": str(person_id),
                "legacy_employee_id": emp.id,
                "name": emp.name,
                "phone": emp.phone,
                "email": emp.email,
                "preferences": json.dumps(emp.preferences or {}),
            },
        )

        # 2) employment_assignments
        await self._session.execute(
            sa.text(
                "INSERT INTO employment_assignments "
                "(id, person_id, org_node_id, job_standard_id, "
                " employment_type, start_date, status) "
                "VALUES (:id, :person_id, :org_node_id, NULL, "
                "        :employment_type, :start_date, :status)"
            ),
            {
                "id": str(assignment_id),
                "person_id": str(person_id),
                "org_node_id": org_node_id,
                "employment_type": "full_time",
                "start_date": start_date.isoformat(),
                "status": status,
            },
        )

        # 3) employment_contracts
        pay_scheme = {
            "base_salary": 0,
            "position_title": emp.position or "unknown",
            "note": "double_write",
        }
        await self._session.execute(
            sa.text(
                "INSERT INTO employment_contracts "
                "(id, assignment_id, contract_type, pay_scheme, valid_from) "
                "VALUES (:id, :assignment_id, :contract_type, "
                "        :pay_scheme::jsonb, :valid_from)"
            ),
            {
                "id": str(contract_id),
                "assignment_id": str(assignment_id),
                "contract_type": "labor",
                "pay_scheme": json.dumps(pay_scheme),
                "valid_from": start_date.isoformat(),
            },
        )

        # 4) employee_id_map
        await self._session.execute(
            sa.text(
                "INSERT INTO employee_id_map "
                "(legacy_employee_id, person_id, assignment_id) "
                "VALUES (:legacy_employee_id, :person_id, :assignment_id)"
            ),
            {
                "legacy_employee_id": emp.id,
                "person_id": str(person_id),
                "assignment_id": str(assignment_id),
            },
        )

        # 5) Match skills → achievements (best-effort)
        all_skill_strings = list(set(
            (emp.skills or []) + (emp.training_completed or [])
        ))
        for skill_str in all_skill_strings:
            result = await self._session.execute(
                sa.text(
                    "SELECT id FROM skill_nodes "
                    "WHERE skill_name ILIKE :pattern"
                ),
                {"pattern": f"%{skill_str}%"},
            )
            skill_rows = result.scalars().all()
            achieved_at = (emp.hire_date or date.today()).isoformat()
            for skill_id in skill_rows:
                await self._session.execute(
                    sa.text(
                        "INSERT INTO person_achievements "
                        "(id, person_id, skill_node_id, achieved_at, trigger_type) "
                        "VALUES (:id, :person_id, :skill_node_id, "
                        "        :achieved_at, :trigger_type) "
                        "ON CONFLICT ON CONSTRAINT uq_person_skill DO NOTHING"
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "person_id": str(person_id),
                        "skill_node_id": str(skill_id),
                        "achieved_at": achieved_at,
                        "trigger_type": "double_write",
                    },
                )

        # Commit HR writes so they actually persist
        await self._session.commit()

        logger.info(
            "hr_double_write.created",
            employee_id=emp.id,
            person_id=str(person_id),
        )
        return True

    async def _do_update(self, emp, changed_fields: set[str]) -> bool:
        """Propagate Employee field changes to HR tables."""
        id_map = await self._lookup_id_map_full(emp.id)
        if id_map is None:
            logger.info(
                "hr_double_write.no_id_map_for_update",
                employee_id=emp.id,
            )
            return False

        person_id = id_map.person_id
        assignment_id = id_map.assignment_id

        # Sync person-level fields — use individual UPDATE per field (no f-string SQL)
        person_fields = changed_fields & {"name", "phone", "email", "preferences"}
        if "name" in person_fields:
            await self._session.execute(
                sa.text(
                    "UPDATE persons SET name = :name, updated_at = NOW() "
                    "WHERE id = :person_id"
                ),
                {"name": emp.name, "person_id": str(person_id)},
            )
        if "phone" in person_fields:
            await self._session.execute(
                sa.text(
                    "UPDATE persons SET phone = :phone, updated_at = NOW() "
                    "WHERE id = :person_id"
                ),
                {"phone": emp.phone, "person_id": str(person_id)},
            )
        if "email" in person_fields:
            await self._session.execute(
                sa.text(
                    "UPDATE persons SET email = :email, updated_at = NOW() "
                    "WHERE id = :person_id"
                ),
                {"email": emp.email, "person_id": str(person_id)},
            )
        if "preferences" in person_fields:
            await self._session.execute(
                sa.text(
                    "UPDATE persons SET preferences = :preferences::jsonb, "
                    "updated_at = NOW() WHERE id = :person_id"
                ),
                {
                    "preferences": json.dumps(emp.preferences or {}),
                    "person_id": str(person_id),
                },
            )

        # Sync assignment-level fields
        if "is_active" in changed_fields:
            new_status = "active" if emp.is_active else "ended"
            await self._session.execute(
                sa.text(
                    "UPDATE employment_assignments "
                    "SET status = :status "
                    "WHERE id = :assignment_id"
                ),
                {
                    "status": new_status,
                    "assignment_id": str(assignment_id),
                },
            )

        # Sync position → contract pay_scheme
        if "position" in changed_fields:
            pay_scheme = {
                "base_salary": 0,
                "position_title": emp.position or "unknown",
                "note": "double_write_update",
            }
            await self._session.execute(
                sa.text(
                    "UPDATE employment_contracts "
                    "SET pay_scheme = :pay_scheme::jsonb "
                    "WHERE assignment_id = :assignment_id"
                ),
                {
                    "pay_scheme": json.dumps(pay_scheme),
                    "assignment_id": str(assignment_id),
                },
            )

        # Commit HR writes so they actually persist
        await self._session.commit()

        logger.info(
            "hr_double_write.updated",
            employee_id=emp.id,
            changed_fields=list(changed_fields),
        )
        return True

    # ── Helpers ───────────────────────────────────────────────────────

    async def _lookup_id_map(self, employee_id: str):
        """Return person_id if in id_map, else None."""
        result = await self._session.execute(
            sa.text(
                "SELECT person_id FROM employee_id_map "
                "WHERE legacy_employee_id = :emp_id"
            ),
            {"emp_id": employee_id},
        )
        return result.scalar_one_or_none()

    async def _lookup_id_map_full(self, employee_id: str):
        """Return full id_map row (person_id + assignment_id), or None."""
        result = await self._session.execute(
            sa.text(
                "SELECT person_id, assignment_id FROM employee_id_map "
                "WHERE legacy_employee_id = :emp_id"
            ),
            {"emp_id": employee_id},
        )
        return result.fetchone()

    async def _get_org_node_id(self, store_id: str) -> Optional[str]:
        result = await self._session.execute(
            sa.text("SELECT org_node_id FROM stores WHERE id = :store_id"),
            {"store_id": store_id},
        )
        return result.scalar_one_or_none()
```

- [ ] **2.3** Modify `apps/api-gateway/src/api/employees.py` to call DoubleWriteService after create/update.

Add the following after the existing `await session.commit()` + `await session.refresh(emp)` in the `create_employee` endpoint (line ~114):

```python
    # --- HR double-write (shadow, non-blocking) ---
    try:
        from src.services.hr.double_write_service import DoubleWriteService
        dw = DoubleWriteService(session=session)
        await dw.on_employee_created(emp)
    except Exception as exc:
        logger.warning("hr_double_write.create_hook_failed", employee_id=emp.id, error=str(exc))
```

Add similar hook in `update_employee` endpoint (after line ~138):

```python
    # --- HR double-write (shadow, non-blocking) ---
    changed = set(req.model_dump(exclude_none=True).keys())
    try:
        from src.services.hr.double_write_service import DoubleWriteService
        dw = DoubleWriteService(session=session)
        await dw.on_employee_updated(emp, changed_fields=changed)
    except Exception as exc:
        logger.warning("hr_double_write.update_hook_failed", employee_id=emp.id, error=str(exc))
```

- [ ] **2.4** Run the tests.

```bash
cd apps/api-gateway && python -m pytest tests/test_hr_double_write.py -v 2>&1 | tail -20
```

Expected: All 7 tests pass.

- [ ] **2.5** Update `apps/api-gateway/src/services/hr/__init__.py` to export DoubleWriteService.

```python
"""HR domain services."""
from .seed_service import HrSeedService
from .double_write_service import DoubleWriteService

__all__ = ["HrSeedService", "DoubleWriteService"]
```

- [ ] **2.6** Commit Chunk 2.

```bash
git add apps/api-gateway/src/services/hr/double_write_service.py \
       apps/api-gateway/src/services/hr/__init__.py \
       apps/api-gateway/src/api/employees.py \
       apps/api-gateway/tests/test_hr_double_write.py
git commit -m "feat(hr): M2 Chunk2 — DoubleWriteService + Employee API hooks (shadow-write)"
```

---

## Chunk 3: HR Knowledge + Retention Risk + Skill Gap Services

**Goal:** 实现三个 HR 领域服务：(1) HrKnowledgeService 查询规则和技能图谱；(2) RetentionRiskService 计算离职风险分（WF-1）并推送告警；(3) SkillGapService 推荐下一技能（WF-3）。

### Files

| Action | File |
|--------|------|
| CREATE | `apps/api-gateway/src/services/hr/knowledge_service.py` |
| CREATE | `apps/api-gateway/src/services/hr/retention_risk_service.py` |
| CREATE | `apps/api-gateway/src/services/hr/skill_gap_service.py` |
| CREATE | `apps/api-gateway/tests/test_hr_knowledge_service.py` |
| CREATE | `apps/api-gateway/tests/test_hr_retention_risk_service.py` |

### Steps

- [ ] **3.1** Write test file `apps/api-gateway/tests/test_hr_knowledge_service.py` (TDD).

```python
"""Tests for HrKnowledgeService."""
import os
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/test")
os.environ.setdefault("APP_ENV", "test")

from src.services.hr.knowledge_service import HrKnowledgeService


def _mock_scalars_all(rows):
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    return result


def _mock_fetchall(rows):
    result = MagicMock()
    result.fetchall.return_value = rows
    return result


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_query_rules_all(mock_session):
    """Query all active rules."""
    rule = MagicMock()
    rule._mapping = {
        "id": uuid.uuid4(),
        "rule_type": "sop",
        "category": "turnover",
        "condition": {"tenure_days_lt": 90},
        "action": {"recommend": "mentor_assign"},
        "confidence": 0.85,
    }
    mock_session.execute = AsyncMock(return_value=_mock_fetchall([rule]))

    svc = HrKnowledgeService(session=mock_session)
    rules = await svc.query_rules()

    assert len(rules) == 1
    mock_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_query_rules_with_category_filter(mock_session):
    """Filter rules by category."""
    mock_session.execute = AsyncMock(return_value=_mock_fetchall([]))

    svc = HrKnowledgeService(session=mock_session)
    rules = await svc.query_rules(category="scheduling")

    assert rules == []
    # Verify category filter was used in query
    call_args = mock_session.execute.call_args
    params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("params", {})
    assert params.get("category") == "scheduling"


@pytest.mark.asyncio
async def test_get_skills_for_person(mock_session):
    """Get achieved skill names for a person."""
    person_id = uuid.uuid4()
    row1 = MagicMock()
    row1.skill_name = "服务沟通"
    row2 = MagicMock()
    row2.skill_name = "库存管理"
    mock_session.execute = AsyncMock(return_value=_mock_fetchall([row1, row2]))

    svc = HrKnowledgeService(session=mock_session)
    skills = await svc.get_skills_for_person(person_id)

    assert skills == ["服务沟通", "库存管理"]


@pytest.mark.asyncio
async def test_get_next_skill_for_person(mock_session):
    """Returns highest-revenue-lift unachieved skill in category."""
    person_id = uuid.uuid4()

    call_count = 0
    async def fake_execute(stmt, params=None):
        nonlocal call_count
        call_count += 1
        sql_text = getattr(stmt, 'text', str(stmt))
        # First call: get achieved skill IDs
        if "person_achievements" in sql_text:
            return _mock_scalars_all([])
        # Second call: get unskilled nodes ordered by revenue lift
        if "skill_nodes" in sql_text:
            node = MagicMock()
            node._mapping = {
                "id": uuid.uuid4(),
                "skill_name": "高级服务",
                "estimated_revenue_lift": 500.00,
                "category": "service",
            }
            return _mock_fetchall([node])
        return MagicMock()

    mock_session.execute = AsyncMock(side_effect=fake_execute)

    svc = HrKnowledgeService(session=mock_session)
    result = await svc.get_next_skill_for_person(person_id, target_category="service")

    assert result is not None
    assert result["skill_name"] == "高级服务"


@pytest.mark.asyncio
async def test_get_next_skill_all_achieved(mock_session):
    """Returns None when all skills in category are achieved."""
    person_id = uuid.uuid4()
    node_id = uuid.uuid4()

    async def fake_execute(stmt, params=None):
        sql_text = getattr(stmt, 'text', str(stmt))
        if "person_achievements" in sql_text:
            return _mock_scalars_all([node_id])
        if "skill_nodes" in sql_text:
            return _mock_fetchall([])  # no unskilled nodes left
        return MagicMock()

    mock_session.execute = AsyncMock(side_effect=fake_execute)

    svc = HrKnowledgeService(session=mock_session)
    result = await svc.get_next_skill_for_person(person_id, target_category="service")

    assert result is None
```

- [ ] **3.2** Write test file `apps/api-gateway/tests/test_hr_retention_risk_service.py` (TDD).

```python
"""Tests for RetentionRiskService."""
import os
import uuid
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/test")
os.environ.setdefault("APP_ENV", "test")

from src.services.hr.retention_risk_service import RetentionRiskService


def _mock_scalar_one_or_none(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _mock_scalar(value):
    result = MagicMock()
    result.scalar.return_value = value
    return result


def _mock_fetchall(rows):
    result = MagicMock()
    result.fetchall.return_value = rows
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
async def test_compute_risk_new_hire_no_achievements(mock_session):
    """New hire (<90 days) with no achievements → higher risk."""
    assignment_id = uuid.uuid4()

    async def fake_execute(stmt, params=None):
        sql_text = getattr(stmt, 'text', str(stmt))
        # start_date query
        if "start_date" in sql_text and "employment_assignments" in sql_text:
            return _mock_scalar_one_or_none(date.today() - timedelta(days=30))
        # achievement count
        if "person_achievements" in sql_text and "COUNT" in sql_text:
            return _mock_scalar(0)
        # person_id lookup
        if "person_id" in sql_text and "employment_assignments" in sql_text:
            return _mock_scalar_one_or_none(uuid.uuid4())
        # existing retention signal
        if "retention_signals" in sql_text and "SELECT" in sql_text:
            return _mock_scalar_one_or_none(None)
        return MagicMock()

    mock_session.execute = AsyncMock(side_effect=fake_execute)

    svc = RetentionRiskService(session=mock_session)
    score = await svc.compute_risk_for_assignment(assignment_id, session=mock_session)

    # new_hire(0.2) + no_achievements(0.2) + baseline(0.3) = 0.7
    assert 0.6 <= score <= 0.8


@pytest.mark.asyncio
async def test_compute_risk_veteran_with_skills(mock_session):
    """Veteran (>90 days) with achievements → lower risk."""
    assignment_id = uuid.uuid4()

    async def fake_execute(stmt, params=None):
        sql_text = getattr(stmt, 'text', str(stmt))
        if "start_date" in sql_text and "employment_assignments" in sql_text:
            return _mock_scalar_one_or_none(date.today() - timedelta(days=200))
        if "person_achievements" in sql_text and "COUNT" in sql_text:
            return _mock_scalar(3)
        if "person_id" in sql_text and "employment_assignments" in sql_text:
            return _mock_scalar_one_or_none(uuid.uuid4())
        if "retention_signals" in sql_text and "SELECT" in sql_text:
            return _mock_scalar_one_or_none(None)
        return MagicMock()

    mock_session.execute = AsyncMock(side_effect=fake_execute)

    svc = RetentionRiskService(session=mock_session)
    score = await svc.compute_risk_for_assignment(assignment_id, session=mock_session)

    # baseline(0.3) only, no new_hire, has achievements
    assert 0.2 <= score <= 0.4


@pytest.mark.asyncio
async def test_compute_risk_with_existing_signal(mock_session):
    """Existing retention signal blends into score."""
    assignment_id = uuid.uuid4()

    async def fake_execute(stmt, params=None):
        sql_text = getattr(stmt, 'text', str(stmt))
        if "start_date" in sql_text and "employment_assignments" in sql_text:
            return _mock_scalar_one_or_none(date.today() - timedelta(days=200))
        if "person_achievements" in sql_text and "COUNT" in sql_text:
            return _mock_scalar(2)
        if "person_id" in sql_text and "employment_assignments" in sql_text:
            return _mock_scalar_one_or_none(uuid.uuid4())
        if "retention_signals" in sql_text and "SELECT" in sql_text:
            return _mock_scalar_one_or_none(0.6)
        return MagicMock()

    mock_session.execute = AsyncMock(side_effect=fake_execute)

    svc = RetentionRiskService(session=mock_session)
    score = await svc.compute_risk_for_assignment(assignment_id, session=mock_session)

    # baseline(0.3) + existing_signal(0.6 * 0.5 = 0.3) = 0.6
    assert 0.5 <= score <= 0.7


@pytest.mark.asyncio
async def test_scan_store_returns_high_risk(mock_session):
    """scan_store returns list of high-risk assignments."""
    org_node_id = "ORG_NODE_001"
    assignment_id = uuid.uuid4()
    person_id = uuid.uuid4()

    assignment_row = MagicMock()
    assignment_row.id = assignment_id
    assignment_row.person_id = person_id
    assignment_row.start_date = date.today() - timedelta(days=30)

    async def fake_execute(stmt, params=None):
        sql_text = getattr(stmt, 'text', str(stmt))
        # Fetch active assignments for store
        if "employment_assignments" in sql_text and "org_node_id" in sql_text and "SELECT" in sql_text and "INSERT" not in sql_text and "UPDATE" not in sql_text:
            if "start_date" in sql_text and "COUNT" not in sql_text and "person_id" not in sql_text:
                return _mock_scalar_one_or_none(assignment_row.start_date)
            if "person_id" in sql_text and "COUNT" not in sql_text:
                return _mock_scalar_one_or_none(person_id)
            return _mock_fetchall([assignment_row])
        if "person_achievements" in sql_text and "COUNT" in sql_text:
            return _mock_scalar(0)
        if "retention_signals" in sql_text and "SELECT" in sql_text:
            return _mock_scalar_one_or_none(None)
        # INSERT/UPDATE retention_signals
        if "retention_signals" in sql_text:
            return MagicMock()
        # person name lookup
        if "persons" in sql_text:
            return _mock_scalar_one_or_none("张三")
        return MagicMock()

    mock_session.execute = AsyncMock(side_effect=fake_execute)

    svc = RetentionRiskService(session=mock_session)
    high_risk, total_scanned = await svc.scan_store(org_node_id)

    assert isinstance(high_risk, list)
    assert isinstance(total_scanned, int)


@pytest.mark.asyncio
@patch("src.services.hr.retention_risk_service.wechat_service")
async def test_run_wf1_pushes_wechat(mock_wechat, mock_session):
    """WF-1 pushes WeChat alerts for high-risk employees."""
    org_node_id = "ORG_NODE_001"

    # Patch scan_store to return (high_risk_list, total_scanned)
    svc = RetentionRiskService(session=mock_session)

    with patch.object(svc, "scan_store", return_value=(
        [{"assignment_id": str(uuid.uuid4()), "person_name": "张三",
          "risk_score": 0.85, "risk_factors": {"new_hire": True}}],
        3,  # 3 total active assignments scanned, 1 is high-risk
    )):
        result = await svc.run_wf1_for_store(org_node_id)

    assert result["high_risk"] == 1
    assert result["scanned"] == 3
    mock_wechat.send_text_message.assert_called_once()
```

- [ ] **3.3** Write `apps/api-gateway/src/services/hr/knowledge_service.py`.

```python
"""HrKnowledgeService — Rule retrieval + skill graph traversal for HRAgent v1."""
import uuid
from typing import Optional

import structlog
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


class HrKnowledgeService:
    """Query HR knowledge rules and skill graph."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def query_rules(
        self,
        category: Optional[str] = None,
        rule_type: Optional[str] = None,
    ) -> list[dict]:
        """Fetch active hr_knowledge_rules, optionally filtered."""
        if category and rule_type:
            result = await self._session.execute(
                sa.text(
                    "SELECT id, rule_type, category, condition, action, "
                    "       expected_impact, confidence, industry_source "
                    "FROM hr_knowledge_rules "
                    "WHERE is_active = true AND category = :category "
                    "  AND rule_type = :rule_type "
                    "ORDER BY confidence DESC"
                ),
                {"category": category, "rule_type": rule_type},
            )
        elif category:
            result = await self._session.execute(
                sa.text(
                    "SELECT id, rule_type, category, condition, action, "
                    "       expected_impact, confidence, industry_source "
                    "FROM hr_knowledge_rules "
                    "WHERE is_active = true AND category = :category "
                    "ORDER BY confidence DESC"
                ),
                {"category": category},
            )
        elif rule_type:
            result = await self._session.execute(
                sa.text(
                    "SELECT id, rule_type, category, condition, action, "
                    "       expected_impact, confidence, industry_source "
                    "FROM hr_knowledge_rules "
                    "WHERE is_active = true AND rule_type = :rule_type "
                    "ORDER BY confidence DESC"
                ),
                {"rule_type": rule_type},
            )
        else:
            result = await self._session.execute(
                sa.text(
                    "SELECT id, rule_type, category, condition, action, "
                    "       expected_impact, confidence, industry_source "
                    "FROM hr_knowledge_rules "
                    "WHERE is_active = true "
                    "ORDER BY confidence DESC"
                ),
            )

        rows = result.fetchall()
        return [
            {
                "id": str(row._mapping["id"]) if hasattr(row, '_mapping') else str(row.id),
                "rule_type": row._mapping.get("rule_type", "") if hasattr(row, '_mapping') else row.rule_type,
                "category": row._mapping.get("category") if hasattr(row, '_mapping') else row.category,
                "condition": row._mapping.get("condition", {}) if hasattr(row, '_mapping') else row.condition,
                "action": row._mapping.get("action", {}) if hasattr(row, '_mapping') else row.action,
                "confidence": row._mapping.get("confidence", 0) if hasattr(row, '_mapping') else row.confidence,
            }
            for row in rows
        ]

    async def get_skills_for_person(self, person_id: uuid.UUID) -> list[str]:
        """Return skill_names the person has achieved."""
        result = await self._session.execute(
            sa.text(
                "SELECT sn.skill_name "
                "FROM person_achievements pa "
                "JOIN skill_nodes sn ON sn.id = pa.skill_node_id "
                "WHERE pa.person_id = :person_id "
                "ORDER BY pa.achieved_at DESC"
            ),
            {"person_id": str(person_id)},
        )
        rows = result.fetchall()
        return [row.skill_name for row in rows]

    async def get_next_skill_for_person(
        self,
        person_id: uuid.UUID,
        target_category: str = "service",
    ) -> Optional[dict]:
        """Return the highest-revenue-lift unachieved skill in category.

        Returns None if person has all skills in category.
        """
        # Get already-achieved skill IDs
        achieved_result = await self._session.execute(
            sa.text(
                "SELECT skill_node_id FROM person_achievements "
                "WHERE person_id = :person_id"
            ),
            {"person_id": str(person_id)},
        )
        achieved_ids = achieved_result.scalars().all()

        # Find unskilled nodes in category, ordered by revenue lift
        if achieved_ids:
            # Build safe parameterized exclusion
            placeholders = ", ".join(f":excl_{i}" for i in range(len(achieved_ids)))
            params = {
                "category": target_category,
                **{f"excl_{i}": str(aid) for i, aid in enumerate(achieved_ids)},
            }
            result = await self._session.execute(
                sa.text(
                    f"SELECT id, skill_name, estimated_revenue_lift, category "
                    f"FROM skill_nodes "
                    f"WHERE category = :category "
                    f"  AND id NOT IN ({placeholders}) "
                    f"ORDER BY COALESCE(estimated_revenue_lift, 0) DESC "
                    f"LIMIT 1"
                ),
                params,
            )
        else:
            result = await self._session.execute(
                sa.text(
                    "SELECT id, skill_name, estimated_revenue_lift, category "
                    "FROM skill_nodes "
                    "WHERE category = :category "
                    "ORDER BY COALESCE(estimated_revenue_lift, 0) DESC "
                    "LIMIT 1"
                ),
                {"category": target_category},
            )

        rows = result.fetchall()
        if not rows:
            return None

        row = rows[0]
        return {
            "id": str(row._mapping["id"]) if hasattr(row, '_mapping') else str(row.id),
            "skill_name": row._mapping.get("skill_name", "") if hasattr(row, '_mapping') else row.skill_name,
            "estimated_revenue_lift": float(
                row._mapping.get("estimated_revenue_lift", 0) if hasattr(row, '_mapping')
                else (row.estimated_revenue_lift or 0)
            ),
            "category": row._mapping.get("category", "") if hasattr(row, '_mapping') else row.category,
        }
```

- [ ] **3.4** Write `apps/api-gateway/src/services/hr/retention_risk_service.py`.

```python
"""RetentionRiskService — rule-based retention risk scoring + WF-1 store scan.

B级 implementation: simple heuristic scoring, no ML.
Score formula: min(1.0, baseline + new_hire_factor + no_achievement_factor + existing_signal_blend)
"""
import uuid
from datetime import date, timedelta
from typing import Optional

import structlog
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# Lazy import to avoid circular import at module level
wechat_service = None


def _get_wechat_service():
    global wechat_service
    if wechat_service is None:
        from src.services.wechat_service import wechat_service as _ws
        wechat_service = _ws
    return wechat_service


_BASELINE_RISK = 0.3
_NEW_HIRE_BONUS = 0.2       # <90 days tenure
_NO_ACHIEVEMENT_BONUS = 0.2  # zero person_achievements
_EXISTING_SIGNAL_WEIGHT = 0.5
_HIGH_RISK_THRESHOLD = 0.70


class RetentionRiskService:
    """Compute and manage retention risk signals."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def compute_risk_for_assignment(
        self,
        assignment_id: uuid.UUID,
        session: Optional[AsyncSession] = None,
    ) -> float:
        """Rule-based risk score 0.0-1.0.

        Formula: min(1.0, 0.3 + new_hire*0.2 + no_achievements*0.2 + existing_signal*0.5)
        """
        s = session or self._session

        # Get start_date
        start_result = await s.execute(
            sa.text(
                "SELECT start_date FROM employment_assignments "
                "WHERE id = :aid"
            ),
            {"aid": str(assignment_id)},
        )
        start_date = start_result.scalar_one_or_none()
        if start_date is None:
            return 0.0

        # Get person_id
        pid_result = await s.execute(
            sa.text(
                "SELECT person_id FROM employment_assignments "
                "WHERE id = :aid"
            ),
            {"aid": str(assignment_id)},
        )
        person_id = pid_result.scalar_one_or_none()

        score = _BASELINE_RISK

        # New hire factor
        if start_date and (date.today() - start_date).days < 90:
            score += _NEW_HIRE_BONUS

        # Achievement factor
        if person_id:
            ach_result = await s.execute(
                sa.text(
                    "SELECT COUNT(*) FROM person_achievements "
                    "WHERE person_id = :pid"
                ),
                {"pid": str(person_id)},
            )
            ach_count = ach_result.scalar() or 0
            if ach_count == 0:
                score += _NO_ACHIEVEMENT_BONUS

        # Existing signal blend
        sig_result = await s.execute(
            sa.text(
                "SELECT risk_score FROM retention_signals "
                "WHERE assignment_id = :aid "
                "ORDER BY computed_at DESC LIMIT 1"
            ),
            {"aid": str(assignment_id)},
        )
        existing_score = sig_result.scalar_one_or_none()
        if existing_score is not None:
            score += float(existing_score) * _EXISTING_SIGNAL_WEIGHT

        return min(1.0, score)

    async def scan_store(self, org_node_id: str) -> tuple[list[dict], int]:
        """WF-1: compute risk for all active assignments in store.

        Returns (high_risk_list, total_scanned_count).
        high_risk_list: entries with score > 0.70.
        total_scanned_count: all active assignments processed.
        Writes/updates retention_signals for each assignment.
        """
        # Get active assignments
        assign_result = await self._session.execute(
            sa.text(
                "SELECT ea.id, ea.person_id, ea.start_date "
                "FROM employment_assignments ea "
                "WHERE ea.org_node_id = :org_node_id "
                "  AND ea.status = 'active'"
            ),
            {"org_node_id": org_node_id},
        )
        assignments = assign_result.fetchall()

        high_risk = []
        for row in assignments:
            aid = row.id if hasattr(row, 'id') else row[0]
            person_id = row.person_id if hasattr(row, 'person_id') else row[1]

            risk_score = await self.compute_risk_for_assignment(
                uuid.UUID(str(aid)), session=self._session
            )

            risk_factors = {
                "computed_by": "rule_based_v1",
                "threshold": _HIGH_RISK_THRESHOLD,
            }

            # Insert new retention_signal row (history tracking: ORDER BY computed_at DESC LIMIT 1
            # in compute_risk_for_assignment always reads the latest).
            await self._session.execute(
                sa.text(
                    "INSERT INTO retention_signals "
                    "(id, assignment_id, risk_score, risk_factors, "
                    " intervention_status, computed_at) "
                    "VALUES (:id, :aid, :score, :factors::jsonb, "
                    "        'pending', NOW())"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "aid": str(aid),
                    "score": risk_score,
                    "factors": __import__("json").dumps(risk_factors),
                },
            )

            if risk_score >= _HIGH_RISK_THRESHOLD:
                # Look up person name
                name_result = await self._session.execute(
                    sa.text("SELECT name FROM persons WHERE id = :pid"),
                    {"pid": str(person_id)},
                )
                person_name = name_result.scalar_one_or_none() or "未知"

                high_risk.append({
                    "assignment_id": str(aid),
                    "person_id": str(person_id),
                    "person_name": person_name,
                    "risk_score": round(risk_score, 2),
                    "risk_factors": risk_factors,
                })

        await self._session.commit()

        total_scanned = len(assignments)
        logger.info(
            "hr_retention.scan_complete",
            org_node_id=org_node_id,
            total_scanned=total_scanned,
            high_risk_count=len(high_risk),
        )
        return high_risk, total_scanned

    async def run_wf1_for_store(self, org_node_id: str) -> dict:
        """Full WF-1: scan → push WeChat alerts for high-risk.

        Returns {scanned: int, high_risk: int, alerted: int}.
        """
        high_risk, total_scanned = await self.scan_store(org_node_id)

        alerted = 0
        for entry in high_risk:
            try:
                ws = _get_wechat_service()
                message = (
                    f"【离职风险预警】\n"
                    f"员工: {entry['person_name']}\n"
                    f"风险分: {entry['risk_score']}\n"
                    f"建议: 安排1对1面谈，了解诉求，预期挽留可避免¥{3000:.2f}招聘成本"
                )
                await ws.send_text_message(content=message)
                alerted += 1
            except Exception as exc:
                logger.warning(
                    "hr_retention.wechat_alert_failed",
                    person_name=entry["person_name"],
                    error=str(exc),
                )

        return {
            "scanned": total_scanned,
            "high_risk": len(high_risk),
            "alerted": alerted,
        }
```

- [ ] **3.5** Write `apps/api-gateway/src/services/hr/skill_gap_service.py`.

```python
"""SkillGapService — per-person skill gap analysis + next-skill recommendation (WF-3)."""
import uuid
from typing import Optional

import structlog
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from .knowledge_service import HrKnowledgeService

logger = structlog.get_logger()


class SkillGapService:
    """Analyze skill gaps and recommend next skill with revenue impact."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._knowledge = HrKnowledgeService(session=session)

    async def analyze_person(self, person_id: uuid.UUID) -> dict:
        """Full skill gap analysis for a single person.

        Returns:
            {
                "person_id": str,
                "achieved_skills": [...],
                "next_recommended": {...} | None,
                "total_potential_yuan": float,
            }
        """
        achieved = await self._knowledge.get_skills_for_person(person_id)

        # Try each standard category
        best_next = None
        total_potential = 0.0
        for category in ("service", "kitchen", "management", "compliance"):
            next_skill = await self._knowledge.get_next_skill_for_person(
                person_id, target_category=category
            )
            if next_skill:
                lift = next_skill.get("estimated_revenue_lift", 0) or 0
                total_potential += float(lift)
                if best_next is None or float(lift) > float(
                    best_next.get("estimated_revenue_lift", 0) or 0
                ):
                    best_next = next_skill

        return {
            "person_id": str(person_id),
            "achieved_skills": achieved,
            "next_recommended": best_next,
            "total_potential_yuan": round(total_potential, 2),
        }

    async def analyze_store(self, org_node_id: str) -> list[dict]:
        """Analyze skill gaps for all active employees in a store.

        Returns list of per-person gap analyses.
        """
        result = await self._session.execute(
            sa.text(
                "SELECT ea.person_id "
                "FROM employment_assignments ea "
                "WHERE ea.org_node_id = :org_node_id "
                "  AND ea.status = 'active'"
            ),
            {"org_node_id": org_node_id},
        )
        person_ids = result.scalars().all()

        analyses = []
        for pid in person_ids:
            try:
                analysis = await self.analyze_person(uuid.UUID(str(pid)))
                analyses.append(analysis)
            except Exception as exc:
                logger.warning(
                    "hr_skill_gap.person_analysis_failed",
                    person_id=str(pid),
                    error=str(exc),
                )

        return analyses
```

- [ ] **3.6** Update `apps/api-gateway/src/services/hr/__init__.py`.

```python
"""HR domain services."""
from .seed_service import HrSeedService
from .double_write_service import DoubleWriteService
from .knowledge_service import HrKnowledgeService
from .retention_risk_service import RetentionRiskService
from .skill_gap_service import SkillGapService

__all__ = [
    "HrSeedService",
    "DoubleWriteService",
    "HrKnowledgeService",
    "RetentionRiskService",
    "SkillGapService",
]
```

- [ ] **3.7** Run all Chunk 3 tests.

```bash
cd apps/api-gateway && python -m pytest tests/test_hr_knowledge_service.py tests/test_hr_retention_risk_service.py -v 2>&1 | tail -20
```

Expected: All tests pass.

- [ ] **3.8** Commit Chunk 3.

```bash
git add apps/api-gateway/src/services/hr/knowledge_service.py \
       apps/api-gateway/src/services/hr/retention_risk_service.py \
       apps/api-gateway/src/services/hr/skill_gap_service.py \
       apps/api-gateway/src/services/hr/__init__.py \
       apps/api-gateway/tests/test_hr_knowledge_service.py \
       apps/api-gateway/tests/test_hr_retention_risk_service.py
git commit -m "feat(hr): M2 Chunk3 — KnowledgeService + RetentionRiskService(WF-1) + SkillGapService(WF-3)"
```

---

## Chunk 4: HRAgent v1 (B级) + REST API

**Goal:** 实现 HRAgent v1 规则驱动诊断（离职风险 WF-1 + 技能差距 WF-3），REST API 注册到 FastAPI main app。

### Files

| Action | File |
|--------|------|
| CREATE | `apps/api-gateway/src/agents/hr_agent.py` |
| CREATE | `apps/api-gateway/src/api/hr.py` |
| MODIFY | `apps/api-gateway/src/main.py` |
| CREATE | `apps/api-gateway/tests/test_hr_agent_v1.py` |

### Steps

- [ ] **4.1** Write test file `apps/api-gateway/tests/test_hr_agent_v1.py` (TDD).

```python
"""Tests for HRAgent v1 (B级 rule-based)."""
import os
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/test")
os.environ.setdefault("APP_ENV", "test")

from src.agents.hr_agent import HRAgentV1, HRDiagnosis


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_diagnose_retention_risk(mock_session):
    """Intent 'retention_risk' calls RetentionRiskService.scan_store."""
    agent = HRAgentV1()

    with patch("src.agents.hr_agent.RetentionRiskService") as MockRRS:
        mock_rrs = AsyncMock()
        # scan_store returns (high_risk_list, total_scanned)
        mock_rrs.scan_store.return_value = (
            [
                {
                    "assignment_id": str(uuid.uuid4()),
                    "person_name": "张三",
                    "risk_score": 0.85,
                    "risk_factors": {"new_hire": True},
                }
            ],
            1,
        )
        MockRRS.return_value = mock_rrs

        with patch("src.agents.hr_agent.HrKnowledgeService") as MockKS:
            mock_ks = AsyncMock()
            mock_ks.query_rules.return_value = [
                {"rule_type": "alert", "category": "turnover",
                 "action": {"recommend": "mentor_assign"}, "confidence": 0.8}
            ]
            MockKS.return_value = mock_ks

            diagnosis = await agent.diagnose(
                "retention_risk",
                store_id="STORE001",
                session=mock_session,
            )

    assert isinstance(diagnosis, HRDiagnosis)
    assert diagnosis.intent == "retention_risk"
    assert len(diagnosis.high_risk_persons) == 1
    assert diagnosis.high_risk_persons[0]["person_name"] == "张三"
    assert len(diagnosis.recommendations) >= 1


@pytest.mark.asyncio
async def test_diagnose_skill_gaps(mock_session):
    """Intent 'skill_gaps' calls SkillGapService.analyze_store."""
    agent = HRAgentV1()

    with patch("src.agents.hr_agent.SkillGapService") as MockSGS:
        mock_sgs = AsyncMock()
        mock_sgs.analyze_store.return_value = [
            {
                "person_id": str(uuid.uuid4()),
                "achieved_skills": ["服务沟通"],
                "next_recommended": {
                    "skill_name": "高级服务",
                    "estimated_revenue_lift": 500.00,
                },
                "total_potential_yuan": 500.00,
            }
        ]
        MockSGS.return_value = mock_sgs

        diagnosis = await agent.diagnose(
            "skill_gaps",
            store_id="STORE001",
            session=mock_session,
        )

    assert diagnosis.intent == "skill_gaps"
    assert len(diagnosis.recommendations) >= 1
    # Recommendations should include yuan impact
    assert any(
        r.get("expected_yuan", 0) > 0 for r in diagnosis.recommendations
    )


@pytest.mark.asyncio
async def test_diagnose_unknown_intent(mock_session):
    """Unknown intent returns error diagnosis."""
    agent = HRAgentV1()
    diagnosis = await agent.diagnose(
        "unknown_intent",
        store_id="STORE001",
        session=mock_session,
    )
    assert diagnosis.intent == "unknown_intent"
    assert "不支持" in diagnosis.summary


@pytest.mark.asyncio
async def test_diagnose_retention_empty_store(mock_session):
    """Empty store returns diagnosis with no high-risk persons."""
    agent = HRAgentV1()

    with patch("src.agents.hr_agent.RetentionRiskService") as MockRRS:
        mock_rrs = AsyncMock()
        mock_rrs.scan_store.return_value = ([], 0)  # (high_risk_list, total_scanned)
        MockRRS.return_value = mock_rrs

        with patch("src.agents.hr_agent.HrKnowledgeService") as MockKS:
            mock_ks = AsyncMock()
            mock_ks.query_rules.return_value = []
            MockKS.return_value = mock_ks

            diagnosis = await agent.diagnose(
                "retention_risk",
                store_id="STORE001",
                session=mock_session,
            )

    assert diagnosis.high_risk_persons == []
    assert "无高风险" in diagnosis.summary or "0" in diagnosis.summary


@pytest.mark.asyncio
async def test_agent_execute_interface(mock_session):
    """HRAgentV1.execute() follows BaseAgent interface."""
    agent = HRAgentV1()

    with patch.object(agent, "diagnose", return_value=HRDiagnosis(
        intent="retention_risk",
        store_id="STORE001",
        summary="扫描完成",
        recommendations=[],
        high_risk_persons=[],
        generated_at=datetime.utcnow(),
    )):
        with patch("src.agents.hr_agent.AsyncSessionLocal") as MockASL:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            MockASL.return_value = mock_ctx

            response = await agent.execute(
                "retention_risk",
                {"store_id": "STORE001"},
            )

    assert response.success is True
    assert response.data["intent"] == "retention_risk"
```

```bash
cd apps/api-gateway && python -m pytest tests/test_hr_agent_v1.py --collect-only 2>&1 | tail -5
```

Expected: `5 tests collected`.

- [ ] **4.2** Write `apps/api-gateway/src/agents/hr_agent.py`.

```python
"""HRAgent v1 — B级规则驱动诊断Agent.

支持意图:
- retention_risk: 离职风险扫描 (WF-1)
- skill_gaps: 技能差距分析 (WF-3)
- staffing: 人力配置诊断 (预留，M3实现)

不含ML预测，纯规则+启发式评分。
"""
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog

from src.core.base_agent import AgentResponse, BaseAgent
from src.core.database import AsyncSessionLocal
from src.services.hr.knowledge_service import HrKnowledgeService
from src.services.hr.retention_risk_service import RetentionRiskService
from src.services.hr.skill_gap_service import SkillGapService

logger = structlog.get_logger()

_SUPPORTED_INTENTS = [
    "retention_risk",
    "skill_gaps",
    "staffing",
]


@dataclass
class HRDiagnosis:
    """Structured output of an HR diagnosis."""
    intent: str
    store_id: str
    summary: str
    recommendations: list[dict] = field(default_factory=list)
    high_risk_persons: list[dict] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        result = asdict(self)
        result["generated_at"] = self.generated_at.isoformat()
        return result


class HRAgentV1(BaseAgent):
    """B级诊断Agent — 规则驱动，不含ML预测。"""

    def __init__(self):
        super().__init__(config={})

    def get_supported_actions(self) -> List[str]:
        return _SUPPORTED_INTENTS

    async def execute(self, action: str, params: Dict[str, Any]) -> AgentResponse:
        """BaseAgent interface: dispatch to diagnose()."""
        start = time.time()
        store_id = params.get("store_id", "")
        logger.info("hr_agent.execute", action=action, store_id=store_id)

        if not store_id:
            return AgentResponse(
                success=False,
                error="缺少必要参数: store_id",
                execution_time=time.time() - start,
            )

        try:
            async with AsyncSessionLocal() as session:
                diagnosis = await self.diagnose(
                    action,
                    store_id=store_id,
                    session=session,
                    person_id=params.get("person_id"),
                )
            return AgentResponse(
                success=True,
                data=diagnosis.to_dict(),
                execution_time=time.time() - start,
            )
        except Exception as exc:
            logger.error("hr_agent.execute_error", action=action, error=str(exc))
            return AgentResponse(
                success=False,
                error=str(exc),
                execution_time=time.time() - start,
            )

    async def diagnose(
        self,
        intent: str,
        store_id: str,
        session=None,
        person_id: Optional[str] = None,
        **kwargs,
    ) -> HRDiagnosis:
        """Main entry point. Routes to appropriate diagnosis method."""
        if intent == "retention_risk":
            return await self._diagnose_retention(store_id, session)
        elif intent == "skill_gaps":
            return await self._diagnose_skill_gaps(store_id, session, person_id)
        elif intent == "staffing":
            return self._diagnose_staffing_placeholder(store_id)
        else:
            return HRDiagnosis(
                intent=intent,
                store_id=store_id,
                summary=f"不支持的诊断意图: {intent}。支持: {', '.join(_SUPPORTED_INTENTS)}",
            )

    async def _diagnose_retention(self, store_id: str, session) -> HRDiagnosis:
        """WF-1: scan store for retention risk, enrich with knowledge rules."""
        # Resolve store → org_node_id
        import sqlalchemy as sa
        org_result = await session.execute(
            sa.text("SELECT org_node_id FROM stores WHERE id = :store_id"),
            {"store_id": store_id},
        )
        org_node_id = org_result.scalar_one_or_none()
        if not org_node_id:
            return HRDiagnosis(
                intent="retention_risk",
                store_id=store_id,
                summary=f"门店 {store_id} 未配置组织节点，无法扫描",
            )

        rrs = RetentionRiskService(session=session)
        high_risk, _ = await rrs.scan_store(org_node_id)

        # Enrich with knowledge rules for recommendations
        ks = HrKnowledgeService(session=session)
        turnover_rules = await ks.query_rules(category="turnover")

        recommendations = []
        for rule in turnover_rules:
            action = rule.get("action", {})
            recommendations.append({
                "action": action.get("recommend", "面谈了解诉求"),
                "expected_yuan": 3000.00,
                "confidence": rule.get("confidence", 0.8),
                "source": "hr_knowledge_rule",
            })

        # If no rules available, provide a default recommendation
        if not recommendations and high_risk:
            recommendations.append({
                "action": "安排1对1面谈，了解离职意向并制定挽留方案",
                "expected_yuan": 3000.00,
                "confidence": 0.7,
                "source": "default_heuristic",
            })

        summary = (
            f"扫描完成：发现 {len(high_risk)} 名高风险员工"
            if high_risk
            else f"扫描完成：无高风险员工（0名超过阈值0.70）"
        )

        return HRDiagnosis(
            intent="retention_risk",
            store_id=store_id,
            summary=summary,
            recommendations=recommendations,
            high_risk_persons=high_risk,
        )

    async def _diagnose_skill_gaps(
        self, store_id: str, session, person_id: Optional[str] = None
    ) -> HRDiagnosis:
        """WF-3: skill gap analysis with revenue impact."""
        import sqlalchemy as sa
        org_result = await session.execute(
            sa.text("SELECT org_node_id FROM stores WHERE id = :store_id"),
            {"store_id": store_id},
        )
        org_node_id = org_result.scalar_one_or_none()
        if not org_node_id:
            return HRDiagnosis(
                intent="skill_gaps",
                store_id=store_id,
                summary=f"门店 {store_id} 未配置组织节点",
            )

        sgs = SkillGapService(session=session)

        if person_id:
            import uuid as uuid_mod
            analyses = [await sgs.analyze_person(uuid_mod.UUID(person_id))]
        else:
            analyses = await sgs.analyze_store(org_node_id)

        recommendations = []
        total_potential = 0.0
        for analysis in analyses:
            next_skill = analysis.get("next_recommended")
            if next_skill:
                lift = float(next_skill.get("estimated_revenue_lift", 0) or 0)
                total_potential += lift
                recommendations.append({
                    "action": f"培训 {next_skill['skill_name']}",
                    "expected_yuan": lift,
                    "confidence": 0.75,
                    "person_id": analysis["person_id"],
                    "source": "skill_gap_analysis",
                })

        summary = (
            f"技能差距分析：{len(analyses)} 人，总潜在提升 "
            f"¥{total_potential:.2f}/月"
        )

        return HRDiagnosis(
            intent="skill_gaps",
            store_id=store_id,
            summary=summary,
            recommendations=recommendations,
        )

    def _diagnose_staffing_placeholder(self, store_id: str) -> HRDiagnosis:
        """Staffing diagnosis placeholder — M3 implementation."""
        return HRDiagnosis(
            intent="staffing",
            store_id=store_id,
            summary="人力配置诊断将在 M3 实现（需要排班数据接入）",
        )
```

- [ ] **4.3** Write `apps/api-gateway/src/api/hr.py`.

```python
"""HR REST API — retention signals, achievements, skill catalog, BFF, diagnose."""
import uuid
from datetime import date
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.user import User

logger = structlog.get_logger()
router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────

class RetentionSignalOut(BaseModel):
    id: str
    assignment_id: str
    risk_score: float
    risk_factors: dict
    intervention_status: str
    computed_at: Optional[str] = None


class AchievementCreateRequest(BaseModel):
    person_id: str
    skill_node_id: str
    achieved_at: Optional[date] = None
    evidence: Optional[str] = None
    trigger_type: str = "manual"


class SkillNodeOut(BaseModel):
    id: str
    skill_name: str
    category: Optional[str] = None
    description: Optional[str] = None
    estimated_revenue_lift: Optional[float] = None


class DiagnoseRequest(BaseModel):
    intent: str
    store_id: str
    person_id: Optional[str] = None


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("/retention-signals")
async def list_retention_signals(
    store_id: str = Query(..., description="门店ID"),
    min_risk: float = Query(0.0, description="最低风险分"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List retention signals for a store, filtered by min risk score."""
    import sqlalchemy as sa

    # Resolve store → org_node_id
    org_result = await session.execute(
        sa.text("SELECT org_node_id FROM stores WHERE id = :store_id"),
        {"store_id": store_id},
    )
    org_node_id = org_result.scalar_one_or_none()
    if not org_node_id:
        raise HTTPException(status_code=404, detail="门店未配置组织节点")

    result = await session.execute(
        sa.text(
            "SELECT rs.id, rs.assignment_id, rs.risk_score, "
            "       rs.risk_factors, rs.intervention_status, rs.computed_at "
            "FROM retention_signals rs "
            "JOIN employment_assignments ea ON ea.id = rs.assignment_id "
            "WHERE ea.org_node_id = :org_node_id "
            "  AND rs.risk_score >= :min_risk "
            "ORDER BY rs.risk_score DESC"
        ),
        {"org_node_id": org_node_id, "min_risk": min_risk},
    )
    rows = result.fetchall()

    return {
        "store_id": store_id,
        "total": len(rows),
        "items": [
            {
                "id": str(row.id),
                "assignment_id": str(row.assignment_id),
                "risk_score": row.risk_score,
                "risk_factors": row.risk_factors,
                "intervention_status": row.intervention_status,
                "computed_at": row.computed_at.isoformat() if row.computed_at else None,
            }
            for row in rows
        ],
    }


@router.post("/achievements", status_code=201)
async def create_achievement(
    req: AchievementCreateRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Record a skill achievement for a person."""
    import sqlalchemy as sa
    import json

    achievement_id = uuid.uuid4()
    achieved_at = req.achieved_at or date.today()

    try:
        await session.execute(
            sa.text(
                "INSERT INTO person_achievements "
                "(id, person_id, skill_node_id, achieved_at, evidence, trigger_type) "
                "VALUES (:id, :person_id, :skill_node_id, :achieved_at, "
                "        :evidence, :trigger_type)"
            ),
            {
                "id": str(achievement_id),
                "person_id": req.person_id,
                "skill_node_id": req.skill_node_id,
                "achieved_at": achieved_at.isoformat(),
                "evidence": req.evidence,
                "trigger_type": req.trigger_type,
            },
        )
        await session.commit()
    except Exception as exc:
        error_str = str(exc)
        if "uq_person_skill" in error_str:
            raise HTTPException(
                status_code=409,
                detail="该员工已拥有此技能认证",
            ) from exc
        raise

    logger.info(
        "hr.achievement_created",
        achievement_id=str(achievement_id),
        person_id=req.person_id,
    )
    return {
        "id": str(achievement_id),
        "person_id": req.person_id,
        "skill_node_id": req.skill_node_id,
        "achieved_at": achieved_at.isoformat(),
    }


@router.get("/skill-nodes")
async def list_skill_nodes(
    category: Optional[str] = Query(None, description="技能类别"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List skill catalog."""
    import sqlalchemy as sa

    if category:
        result = await session.execute(
            sa.text(
                "SELECT id, skill_name, category, description, "
                "       estimated_revenue_lift "
                "FROM skill_nodes "
                "WHERE category = :category "
                "ORDER BY COALESCE(estimated_revenue_lift, 0) DESC"
            ),
            {"category": category},
        )
    else:
        result = await session.execute(
            sa.text(
                "SELECT id, skill_name, category, description, "
                "       estimated_revenue_lift "
                "FROM skill_nodes "
                "ORDER BY COALESCE(estimated_revenue_lift, 0) DESC"
            ),
        )

    rows = result.fetchall()
    return {
        "total": len(rows),
        "items": [
            {
                "id": str(row.id),
                "skill_name": row.skill_name,
                "category": row.category,
                "description": row.description,
                "estimated_revenue_lift": float(row.estimated_revenue_lift)
                    if row.estimated_revenue_lift else None,
            }
            for row in rows
        ],
    }


@router.post("/diagnose")
async def diagnose(
    req: DiagnoseRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Run HRAgent v1 diagnosis."""
    from src.agents.hr_agent import HRAgentV1

    agent = HRAgentV1()
    diagnosis = await agent.diagnose(
        req.intent,
        store_id=req.store_id,
        session=session,
        person_id=req.person_id,
    )
    return diagnosis.to_dict()


@router.get("/bff/sm/{store_id}")
async def bff_sm_hr(
    store_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """BFF首屏: 店长HR视角聚合数据.

    Returns retention risks + skill gaps + pending tasks, all in one call.
    Partial failure → null per section, never blocks entire response.
    """
    from src.agents.hr_agent import HRAgentV1
    agent = HRAgentV1()

    # Retention risk section
    retention = None
    try:
        diag = await agent.diagnose("retention_risk", store_id=store_id, session=session)
        retention = {
            "high_risk_count": len(diag.high_risk_persons),
            "persons": diag.high_risk_persons[:5],
            "recommendations": diag.recommendations[:3],
        }
    except Exception as exc:
        logger.warning("bff_sm_hr.retention_failed", store_id=store_id, error=str(exc))

    # Skill gap section
    skill_gaps = None
    try:
        diag = await agent.diagnose("skill_gaps", store_id=store_id, session=session)
        skill_gaps = {
            "total_potential_yuan": sum(
                r.get("expected_yuan", 0) for r in diag.recommendations
            ),
            "top_recommendations": diag.recommendations[:5],
        }
    except Exception as exc:
        logger.warning("bff_sm_hr.skill_gaps_failed", store_id=store_id, error=str(exc))

    return {
        "store_id": store_id,
        "retention": retention,
        "skill_gaps": skill_gaps,
    }
```

- [ ] **4.4** Modify `apps/api-gateway/src/main.py` to register the HR router.

Add the following import and router registration alongside existing routers:

```python
from src.api import hr
app.include_router(hr.router, prefix="/api/v1/hr", tags=["HR"])
```

- [ ] **4.5** Run all Chunk 4 tests.

```bash
cd apps/api-gateway && python -m pytest tests/test_hr_agent_v1.py -v 2>&1 | tail -20
```

Expected: All 5 tests pass.

- [ ] **4.6** Run ALL M2 tests together to confirm no regressions.

```bash
cd apps/api-gateway && python -m pytest tests/test_hr_data_migration.py tests/test_hr_double_write.py tests/test_hr_knowledge_service.py tests/test_hr_retention_risk_service.py tests/test_hr_agent_v1.py -v 2>&1 | tail -30
```

Expected: All tests pass (approximately 24 tests total).

- [ ] **4.7** Commit Chunk 4.

```bash
git add apps/api-gateway/src/agents/hr_agent.py \
       apps/api-gateway/src/api/hr.py \
       apps/api-gateway/src/main.py \
       apps/api-gateway/tests/test_hr_agent_v1.py
git commit -m "feat(hr): M2 Chunk4 — HRAgent v1 (B级) + REST API + BFF endpoint"
```

---

## Post-Implementation Checklist

After all 4 chunks are committed, verify:

- [ ] **P.1** All 24+ tests pass in a single pytest run.
- [ ] **P.2** `python -m src.migrations.hr_data_migration --dry-run` runs without import errors (will fail at DB connect in dev, that is OK).
- [ ] **P.3** `grep -r "TODO\|FIXME" apps/api-gateway/src/migrations/ apps/api-gateway/src/services/hr/ apps/api-gateway/src/agents/hr_agent.py apps/api-gateway/src/api/hr.py` returns zero results.
- [ ] **P.4** No f-string in `sa.text()` calls (except the UPDATE SET clause in double_write which only uses code-controlled column names, verified safe).
- [ ] **P.5** All JSONB defaults use `default=dict` not `default={}`.
- [ ] **P.6** All timestamps use `TIMESTAMP(timezone=True)`.

---

## File Summary

| File | Action | Chunk | Description |
|------|--------|-------|-------------|
| `src/migrations/__init__.py` | CREATE | 1 | Empty package init |
| `src/migrations/hr_data_migration.py` | CREATE | 1 | CLI migration script (idempotent, --dry-run) |
| `tests/test_hr_data_migration.py` | CREATE | 1 | 7 migration tests |
| `src/services/hr/double_write_service.py` | CREATE | 2 | Shadow-write Employee→HR (silent failures) |
| `src/api/employees.py` | MODIFY | 2 | Add double-write hooks to create/update |
| `tests/test_hr_double_write.py` | CREATE | 2 | 7 double-write tests |
| `src/services/hr/knowledge_service.py` | CREATE | 3 | Rule retrieval + skill graph traversal |
| `src/services/hr/retention_risk_service.py` | CREATE | 3 | WF-1 risk scoring + WeChat alerts |
| `src/services/hr/skill_gap_service.py` | CREATE | 3 | WF-3 per-person gap analysis |
| `src/services/hr/__init__.py` | MODIFY | 2,3 | Export new services |
| `tests/test_hr_knowledge_service.py` | CREATE | 3 | 5 knowledge service tests |
| `tests/test_hr_retention_risk_service.py` | CREATE | 3 | 5 retention risk tests |
| `src/agents/hr_agent.py` | CREATE | 4 | HRAgent v1 B级 (BaseAgent subclass) |
| `src/api/hr.py` | CREATE | 4 | REST API (signals, achievements, skills, BFF, diagnose) |
| `src/main.py` | MODIFY | 4 | Register HR router |
| `tests/test_hr_agent_v1.py` | CREATE | 4 | 5 agent tests |

**Total new files:** 12 | **Modified files:** 3 | **Total tests:** ~24
