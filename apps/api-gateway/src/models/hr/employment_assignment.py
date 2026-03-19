"""EmploymentAssignment — 在岗关系（Person × OrgNode × 岗位）"""
import uuid
from sqlalchemy import Column, Integer, String, Date, ForeignKey, TIMESTAMP, text
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
    position = Column(String(50), nullable=True,
                      comment="岗位名称（厨师/服务员/收银等），z64 补回 Chain-B 字段")
    department = Column(String(50), nullable=True,
                        comment="部门（前厅/后厨/管理）")
    employment_type = Column(String(30), nullable=False,
                             comment="full_time/hourly/outsourced/dispatched/partner")
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    status = Column(String(20), nullable=False, default="active",
                    server_default="'active'",
                    comment="active/ended/suspended")
    # z65 就业属性
    daily_wage_standard_fen = Column(Integer, nullable=True,
                                     comment="日薪标准（分），用于小时工/灵活用工薪资计算")
    work_hour_type = Column(String(30), nullable=True,
                            comment="工时类型：standard/flexible/shift")
    grade_level = Column(String(30), nullable=True, comment="职级")
    # 软引用：入职/离职流程创建 assignment，不反向强FK以避免循环依赖
    onboarding_process_id = Column(UUID(as_uuid=True), nullable=True)
    offboarding_process_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("NOW()"),
                        nullable=False)

    def __repr__(self) -> str:
        return (f"<EmploymentAssignment(id={self.id}, "
                f"person_id={self.person_id}, status={self.status!r})>")
