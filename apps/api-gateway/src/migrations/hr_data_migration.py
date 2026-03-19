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
from datetime import date
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
        # Use individual queries per skill to stay fully parameterized
        # N+1 accepted: migration runs once offline; not a latency-sensitive path
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
