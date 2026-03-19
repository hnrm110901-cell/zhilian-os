"""
EmployeeJobBinding — 员工与岗位标准绑定
记录员工当前及历史岗位绑定关系。
employee_id 使用 String，因为 Employee 可能来自外部系统。
"""
from sqlalchemy import Column, String, Boolean, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from .base import Base, TimestampMixin


class EmployeeJobBinding(Base, TimestampMixin):
    """员工岗位绑定表"""
    __tablename__ = "employee_job_bindings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 员工信息（String，兼容外部系统ID）
    employee_id = Column(String(64), nullable=False, index=True)
    employee_name = Column(String(128))   # 冗余存储，方便查询
    store_id = Column(String(64), nullable=False, index=True)

    # 岗位关联
    job_standard_id = Column(UUID(as_uuid=True), ForeignKey("job_standards.id"), nullable=False)
    job_code = Column(String(64), nullable=False)    # 冗余存储
    job_name = Column(String(128))                   # 冗余存储

    # 绑定时间
    bound_at = Column(DateTime, nullable=False)
    unbound_at = Column(DateTime)                    # 解绑时间，null 表示当前在职

    is_active = Column(Boolean, default=True, nullable=False)
    bound_by = Column(String(64))    # 操作人
    notes = Column(Text)

    # 关联
    job_standard = relationship("JobStandard")

    def __repr__(self):
        return f"<EmployeeJobBinding(employee_id='{self.employee_id}', job_code='{self.job_code}', is_active={self.is_active})>"
