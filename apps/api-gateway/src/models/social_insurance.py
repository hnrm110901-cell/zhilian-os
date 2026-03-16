"""
Social Insurance Config -- 社保公积金配置
区域化五险一金费率 + 员工参保方案
"""

import enum
import uuid

from sqlalchemy import Boolean, Column, Date
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSON, UUID

from .base import Base, TimestampMixin


class SocialInsuranceConfig(Base, TimestampMixin):
    """
    区域社保公积金费率配置。
    每个城市/地区一条配置，包含五险一金的企业和个人费率。
    """

    __tablename__ = "social_insurance_configs"
    __table_args__ = (UniqueConstraint("region_code", "effective_year", name="uq_si_region_year"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    region_code = Column(String(20), nullable=False, index=True)  # 如 "430100"（长沙）
    region_name = Column(String(50), nullable=False)  # 如 "长沙市"
    effective_year = Column(Integer, nullable=False)  # 生效年度

    # 缴费基数上下限（分/月）
    base_floor_fen = Column(Integer, nullable=False, default=0)  # 最低缴费基数
    base_ceiling_fen = Column(Integer, nullable=False, default=0)  # 最高缴费基数

    # ── 五险费率（%，存两位小数） ──
    # 养老保险
    pension_employer_pct = Column(Numeric(5, 2), default=16.0)  # 企业 16%
    pension_employee_pct = Column(Numeric(5, 2), default=8.0)  # 个人 8%

    # 医疗保险
    medical_employer_pct = Column(Numeric(5, 2), default=8.0)  # 企业 8%
    medical_employee_pct = Column(Numeric(5, 2), default=2.0)  # 个人 2%

    # 失业保险
    unemployment_employer_pct = Column(Numeric(5, 2), default=0.7)  # 企业 0.7%
    unemployment_employee_pct = Column(Numeric(5, 2), default=0.3)  # 个人 0.3%

    # 工伤保险（仅企业缴）
    injury_employer_pct = Column(Numeric(5, 2), default=0.4)  # 企业 0.2-1.9%

    # 生育保险（仅企业缴，部分地区已合并医疗）
    maternity_employer_pct = Column(Numeric(5, 2), default=0.0)  # 企业

    # ── 住房公积金（%） ──
    housing_fund_employer_pct = Column(Numeric(5, 2), default=8.0)  # 企业 5-12%
    housing_fund_employee_pct = Column(Numeric(5, 2), default=8.0)  # 个人 5-12%

    is_active = Column(Boolean, default=True, nullable=False)
    remark = Column(Text, nullable=True)

    def __repr__(self):
        return f"<SocialInsuranceConfig(region='{self.region_name}', year={self.effective_year})>"


class EmployeeSocialInsurance(Base, TimestampMixin):
    """
    员工参保方案。
    关联区域配置，记录个人缴费基数。
    """

    __tablename__ = "employee_social_insurances"
    __table_args__ = (UniqueConstraint("employee_id", "effective_year", name="uq_emp_si_year"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=False, index=True)
    employee_id = Column(String(50), ForeignKey("employees.id"), nullable=False, index=True)

    # 关联区域配置
    config_id = Column(UUID(as_uuid=True), ForeignKey("social_insurance_configs.id"), nullable=False)
    effective_year = Column(Integer, nullable=False)

    # 个人缴费基数（分/月） —— 在 base_floor 和 base_ceiling 之间
    personal_base_fen = Column(Integer, nullable=False, default=0)

    # 是否参保各项（部分岗位可能不参某些险种）
    has_pension = Column(Boolean, default=True)
    has_medical = Column(Boolean, default=True)
    has_unemployment = Column(Boolean, default=True)
    has_injury = Column(Boolean, default=True)
    has_maternity = Column(Boolean, default=True)
    has_housing_fund = Column(Boolean, default=True)

    # 公积金个性化比例（覆盖区域默认值）
    housing_fund_pct_override = Column(Numeric(5, 2), nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)
    remark = Column(Text, nullable=True)

    def __repr__(self):
        return f"<EmployeeSocialInsurance(employee='{self.employee_id}', " f"base={self.personal_base_fen / 100:.0f}yuan)>"
