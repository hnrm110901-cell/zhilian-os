"""EmploymentAssignment — 在岗关系（Person × OrgNode × 岗位）"""
import uuid
from sqlalchemy import Column, String, Date, ForeignKey, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID
from ..base import Base


class EmploymentAssignment(Base):
    __tablename__ = "employment_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    person_id = Column(UUID(as_uuid=True),
                       ForeignKey("persons.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    org_node_id = Column(String(64),
                         ForeignKey("org_nodes.id", ondelete="RESTRICT"),
                         nullable=False, index=True)
    # 引用job_standards.id，无强FK（跨模块，避免循环依赖）
    job_standard_id = Column(UUID(as_uuid=True), nullable=True)
    employment_type = Column(String(30), nullable=False,
                             comment="full_time/hourly/outsourced/dispatched/partner")
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    status = Column(String(20), nullable=False, default="active",
                    server_default="'active'",
                    comment="active/ended/suspended")
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                        nullable=False)

    def __repr__(self) -> str:
        return (f"<EmploymentAssignment(id={self.id}, "
                f"person_id={self.person_id}, status={self.status!r})>")
