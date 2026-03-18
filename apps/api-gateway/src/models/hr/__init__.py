"""HR domain models — persons, assignments, contracts, lifecycle processes."""
from .person import Person
from .employment_assignment import EmploymentAssignment
from .employment_contract import EmploymentContract
from .employee_id_map import EmployeeIdMap
from .attendance_rule import AttendanceRule
from .kpi_template import KpiTemplate
from .onboarding_process import OnboardingProcess
from .onboarding_checklist_item import OnboardingChecklistItem
from .offboarding_process import OffboardingProcess
from .transfer_process import TransferProcess

__all__ = [
    "Person",
    "EmploymentAssignment",
    "EmploymentContract",
    "EmployeeIdMap",
    "AttendanceRule",
    "KpiTemplate",
    "OnboardingProcess",
    "OnboardingChecklistItem",
    "OffboardingProcess",
    "TransferProcess",
]
