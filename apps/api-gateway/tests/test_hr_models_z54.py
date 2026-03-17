"""Unit tests for z54 HR core models — no DB required."""
import uuid
import pytest
from src.models.hr.person import Person
from src.models.hr.employment_assignment import EmploymentAssignment
from src.models.hr.employment_contract import EmploymentContract
from src.models.hr.employee_id_map import EmployeeIdMap
from src.models.hr.attendance_rule import AttendanceRule
from src.models.hr.kpi_template import KpiTemplate


def test_person_tablename():
    assert Person.__tablename__ == "persons"


def test_person_has_required_columns():
    cols = {c.name for c in Person.__table__.columns}
    assert {"id", "legacy_employee_id", "name", "phone", "email",
            "preferences", "created_at", "updated_at"}.issubset(cols)


def test_person_id_is_uuid():
    from sqlalchemy.dialects.postgresql import UUID
    col = Person.__table__.columns["id"]
    assert isinstance(col.type, UUID)


def test_employment_assignment_tablename():
    assert EmploymentAssignment.__tablename__ == "employment_assignments"


def test_employment_assignment_has_required_columns():
    cols = {c.name for c in EmploymentAssignment.__table__.columns}
    assert {"id", "person_id", "org_node_id", "employment_type",
            "start_date", "status"}.issubset(cols)


def test_employment_contract_has_pay_scheme_jsonb():
    from sqlalchemy.dialects.postgresql import JSONB
    col = EmploymentContract.__table__.columns["pay_scheme"]
    assert isinstance(col.type, JSONB)


def test_employee_id_map_pk_is_string():
    col = EmployeeIdMap.__table__.columns["legacy_employee_id"]
    from sqlalchemy import String
    assert isinstance(col.type, String)
    assert col.primary_key is True


def test_all_models_importable():
    from src.models.hr import (
        Person, EmploymentAssignment, EmploymentContract,
        EmployeeIdMap, AttendanceRule, KpiTemplate,
    )
    assert all([Person, EmploymentAssignment, EmploymentContract,
                EmployeeIdMap, AttendanceRule, KpiTemplate])
