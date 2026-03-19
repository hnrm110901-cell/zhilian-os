"""EmployeeIdMap — 迁移桥接表（旧String PK → 新UUID）。临时表，M4阶段删除。"""
from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from ..base import Base


class EmployeeIdMap(Base):
    __tablename__ = "employee_id_map"

    legacy_employee_id = Column(String(50), primary_key=True,
                                comment="原employees.id，如EMP001")
    person_id = Column(UUID(as_uuid=True),
                       ForeignKey("persons.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    assignment_id = Column(UUID(as_uuid=True),
                           ForeignKey("employment_assignments.id", ondelete="CASCADE"),
                           nullable=False, index=True)

    def __repr__(self) -> str:
        return f"<EmployeeIdMap({self.legacy_employee_id!r} → {self.person_id})>"
