"""HR domain models — persons, assignments, contracts."""
from .person import Person
from .employment_assignment import EmploymentAssignment
from .employment_contract import EmploymentContract
from .employee_id_map import EmployeeIdMap
from .attendance_rule import AttendanceRule
from .kpi_template import KpiTemplate

__all__ = [
    "Person",
    "EmploymentAssignment",
    "EmploymentContract",
    "EmployeeIdMap",
    "AttendanceRule",
    "KpiTemplate",
]
