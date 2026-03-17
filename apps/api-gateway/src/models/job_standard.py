"""
JobStandard — 连锁餐饮岗位标准库
行业知识本体：岗位 → 职责 → SOP → KPI基线
"""
from sqlalchemy import Column, String, Integer, Boolean, Text, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from .base import Base, TimestampMixin


class JobStandard(Base, TimestampMixin):
    """连锁餐饮岗位标准表"""
    __tablename__ = "job_standards"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # 岗位标识
    job_code = Column(String(64), unique=True, nullable=False, index=True)  # e.g. "store_manager"
    job_name = Column(String(128), nullable=False)                          # 店长
    job_level = Column(String(32), nullable=False)                          # hq/region/store/support/kitchen
    job_category = Column(String(64), nullable=False)                       # management/front_of_house/back_of_house/support_dept

    # 组织关系
    report_to_role = Column(String(256))   # 汇报对象描述
    manages_roles = Column(String(256))    # 管辖角色描述

    # 岗位内容
    job_objective = Column(Text)           # 岗位目标
    responsibilities = Column(JSON)        # 核心职责列表 [str]
    daily_tasks = Column(JSON)             # 日重点工作 [str]
    weekly_tasks = Column(JSON)            # 周重点工作 [str]
    monthly_tasks = Column(JSON)           # 月重点工作 [str]

    # KPI基线
    kpi_targets = Column(JSON)             # [{name, description, unit}]

    # 任职资格
    experience_years_min = Column(Integer, default=0)   # 最低工作年限
    education_requirement = Column(String(64))          # 学历要求
    skill_requirements = Column(JSON)                   # 技能要求 [str]

    # 管理参考
    common_issues = Column(JSON)           # 常见问题 [str]
    industry_category = Column(String(64), default="通用")  # 行业分类

    # 元数据
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0)
    created_by = Column(String(64), default="system")

    # 关联
    sops = relationship("JobSOP", back_populates="job_standard", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<JobStandard(job_code='{self.job_code}', job_name='{self.job_name}', level='{self.job_level}')>"
