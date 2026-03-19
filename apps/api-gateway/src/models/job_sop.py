"""
JobSOP — 岗位操作标准（SOP步骤）
每个岗位可拥有多个场景SOP，包含结构化步骤。
"""
from sqlalchemy import Column, String, Integer, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from .base import Base, TimestampMixin


class JobSOP(Base, TimestampMixin):
    """岗位SOP操作标准表"""
    __tablename__ = "job_sops"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_standard_id = Column(UUID(as_uuid=True), ForeignKey("job_standards.id"), nullable=False, index=True)

    # SOP分类：pre_shift/during_service/peak_hour/post_shift/handover/emergency
    sop_type = Column(String(32), nullable=False)
    sop_name = Column(String(128), nullable=False)

    # 步骤列表：[{step_no: int, action: str, standard: str, check_point: str}]
    steps = Column(JSON, nullable=False)

    duration_minutes = Column(Integer)       # 预计时长（分钟）
    responsible_role = Column(String(64))    # 执行角色
    sort_order = Column(Integer, default=0)

    # 关联
    job_standard = relationship("JobStandard", back_populates="sops")

    def __repr__(self):
        return f"<JobSOP(sop_name='{self.sop_name}', sop_type='{self.sop_type}')>"
