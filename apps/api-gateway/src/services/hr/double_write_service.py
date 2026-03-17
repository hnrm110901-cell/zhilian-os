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

    async def on_employee_updated(self, employee) -> bool:
        """Sync relevant changes to persons/assignments. Returns True if succeeded."""
        try:
            return await self._do_update(employee)
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
                "hr_double_write.already_exists",
                employee_id=emp.id,
            )
            return True

        # Get org_node_id from employee's store
        org_node_id = await self._get_org_node_for_employee(emp)
        if org_node_id is None:
            logger.warning(
                "hr_double_write.no_org_node",
                employee_id=emp.id,
                store_id=emp.store_id,
            )
            return False

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

        # 3) INSERT employment_contract
        contract_id = uuid.uuid4()
        pay_scheme = {
            "base_salary": 0,
            "position_title": emp.position or "unknown",
            "note": "double_write_create",
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

        # 4) INSERT employee_id_map
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

        # 5) Match skills → person_achievements (best-effort, SELECT id single-column)
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

    async def _do_update(self, emp) -> bool:
        """Propagate Employee field changes to HR tables (always checks all relevant fields)."""
        id_map = await self._lookup_id_map_full(emp.id)
        if id_map is None:
            logger.info(
                "hr_double_write.no_id_map_for_update",
                employee_id=emp.id,
            )
            return False

        person_id = id_map.person_id
        assignment_id = id_map.assignment_id

        # Sync person-level fields — always update all non-None fields
        if emp.name is not None:
            await self._session.execute(
                sa.text(
                    "UPDATE persons SET name = :name, updated_at = NOW() "
                    "WHERE id = :person_id"
                ),
                {"name": emp.name, "person_id": str(person_id)},
            )
        if emp.phone is not None:
            await self._session.execute(
                sa.text(
                    "UPDATE persons SET phone = :phone, updated_at = NOW() "
                    "WHERE id = :person_id"
                ),
                {"phone": emp.phone, "person_id": str(person_id)},
            )
        if emp.email is not None:
            await self._session.execute(
                sa.text(
                    "UPDATE persons SET email = :email, updated_at = NOW() "
                    "WHERE id = :person_id"
                ),
                {"email": emp.email, "person_id": str(person_id)},
            )
        if emp.preferences is not None:
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
        # department: Employee model does not expose this field; skipped

        # Sync assignment-level fields
        if emp.is_active is not None:
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
        if emp.position is not None:
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
        """Return Row with person_id + assignment_id, or None."""
        result = await self._session.execute(
            sa.text(
                "SELECT person_id, assignment_id FROM employee_id_map "
                "WHERE legacy_employee_id = :emp_id"
            ),
            {"emp_id": employee_id},
        )
        return result.fetchone()

    async def _get_org_node_for_employee(self, emp) -> Optional[str]:
        """Return org_node_id for the employee's store, or None."""
        result = await self._session.execute(
            sa.text(
                "SELECT org_node_id FROM stores WHERE id = :store_id"
            ),
            {"store_id": emp.store_id},
        )
        return result.scalar_one_or_none()
