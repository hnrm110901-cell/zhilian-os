"""
Payroll Models — 薪酬管理
薪资结构、月度工资单、个税申报
"""
import enum
import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Numeric, Boolean, Date, DateTime,
    Text, ForeignKey, Enum as SAEnum, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSON

from .base import Base, TimestampMixin


# ── Enums ──────────────────────────────────────────────────

class PayrollStatus(str, enum.Enum):
    DRAFT = "draft"             # 草稿（计算中）
    CONFIRMED = "confirmed"     # 已确认（待发放）
    PAID = "paid"               # 已发放
    CANCELLED = "cancelled"     # 已作废


class SalaryType(str, enum.Enum):
    MONTHLY = "monthly"         # 月薪
    HOURLY = "hourly"           # 时薪
    DAILY = "daily"             # 日薪


class TaxStatus(str, enum.Enum):
    PENDING = "pending"         # 待申报
    DECLARED = "declared"       # 已申报
    PAID = "paid"               # 已缴纳


# ── 1. 薪资结构 ────────────────────────────────────────────

class SalaryStructure(Base, TimestampMixin):
    """
    员工薪资方案：定义基本工资、岗位补贴、绩效系数等。
    一个员工同时只有一个生效的薪资方案。
    """
    __tablename__ = "salary_structures"
    __table_args__ = (
        UniqueConstraint("employee_id", "is_active", name="uq_salary_active"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=False, index=True)
    employee_id = Column(String(50), ForeignKey("employees.id"), nullable=False, index=True)

    salary_type = Column(
        SAEnum(SalaryType, name="salary_type"),
        nullable=False,
        default=SalaryType.MONTHLY,
    )

    # 基本薪资（单位：分）
    base_salary_fen = Column(Integer, nullable=False, default=0)
    # 岗位补贴（分）
    position_allowance_fen = Column(Integer, nullable=False, default=0)
    # 餐补（分）
    meal_allowance_fen = Column(Integer, nullable=False, default=0)
    # 交通补贴（分）
    transport_allowance_fen = Column(Integer, nullable=False, default=0)

    # 时薪/日薪（分），salary_type=hourly/daily 时使用
    hourly_rate_fen = Column(Integer, nullable=True)

    # 绩效系数（0.0-2.0，默认1.0）
    performance_coefficient = Column(Numeric(4, 2), nullable=False, default=1.0)

    # 社保公积金（个人部分，分）
    social_insurance_fen = Column(Integer, nullable=False, default=0)
    housing_fund_fen = Column(Integer, nullable=False, default=0)

    # 专项附加扣除（分/月）
    special_deduction_fen = Column(Integer, nullable=False, default=0)

    is_active = Column(Boolean, default=True, nullable=False)
    effective_date = Column(Date, nullable=False)
    expire_date = Column(Date, nullable=True)
    approved_by = Column(String(100), nullable=True)
    remark = Column(Text, nullable=True)

    def __repr__(self):
        return (
            f"<SalaryStructure(employee='{self.employee_id}', "
            f"base={self.base_salary_fen/100:.2f}yuan, active={self.is_active})>"
        )


# ── 2. 月度工资单 ──────────────────────────────────────────

class PayrollRecord(Base, TimestampMixin):
    """
    月度工资单：每月为每个员工生成一条。
    所有金额单位：分（fen），展示时 /100 转元。
    """
    __tablename__ = "payroll_records"
    __table_args__ = (
        UniqueConstraint("store_id", "employee_id", "pay_month", name="uq_payroll_month"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=False, index=True)
    employee_id = Column(String(50), ForeignKey("employees.id"), nullable=False, index=True)
    pay_month = Column(String(7), nullable=False, index=True)  # YYYY-MM

    status = Column(
        SAEnum(PayrollStatus, name="payroll_status"),
        nullable=False,
        default=PayrollStatus.DRAFT,
    )

    # ── 应发 ──
    base_salary_fen = Column(Integer, nullable=False, default=0)
    position_allowance_fen = Column(Integer, nullable=False, default=0)
    meal_allowance_fen = Column(Integer, nullable=False, default=0)
    transport_allowance_fen = Column(Integer, nullable=False, default=0)
    performance_bonus_fen = Column(Integer, nullable=False, default=0)  # 绩效奖金
    overtime_pay_fen = Column(Integer, nullable=False, default=0)       # 加班费
    commission_fen = Column(Integer, nullable=False, default=0)         # 提成
    reward_fen = Column(Integer, nullable=False, default=0)             # 奖励
    other_bonus_fen = Column(Integer, nullable=False, default=0)        # 其他奖金
    gross_salary_fen = Column(Integer, nullable=False, default=0)       # 应发合计

    # ── 扣款 ──
    absence_deduction_fen = Column(Integer, nullable=False, default=0)  # 缺勤扣款
    late_deduction_fen = Column(Integer, nullable=False, default=0)     # 迟到扣款
    penalty_fen = Column(Integer, nullable=False, default=0)            # 罚款
    social_insurance_fen = Column(Integer, nullable=False, default=0)   # 社保个人
    housing_fund_fen = Column(Integer, nullable=False, default=0)       # 公积金个人
    tax_fen = Column(Integer, nullable=False, default=0)                # 个税
    other_deduction_fen = Column(Integer, nullable=False, default=0)    # 其他扣款
    total_deduction_fen = Column(Integer, nullable=False, default=0)    # 扣款合计

    # ── 实发 ──
    net_salary_fen = Column(Integer, nullable=False, default=0)         # 实发工资

    # ── 考勤统计 ──
    attendance_days = Column(Numeric(5, 1), nullable=True)     # 出勤天数
    absence_days = Column(Numeric(5, 1), nullable=True)        # 缺勤天数
    late_count = Column(Integer, nullable=True)                 # 迟到次数
    overtime_hours = Column(Numeric(6, 1), nullable=True)       # 加班时数
    leave_days = Column(Numeric(5, 1), nullable=True)           # 请假天数

    # ── 计算明细（JSON，审计用）──
    calculation_detail = Column(JSON, nullable=True)

    # ── 规则快照（JSON，审计溯源：记录算薪时使用的业务规则） ──
    rule_snapshot = Column(JSON, nullable=True)

    paid_at = Column(DateTime, nullable=True)
    confirmed_by = Column(String(100), nullable=True)
    remark = Column(Text, nullable=True)

    def __repr__(self):
        return (
            f"<PayrollRecord(employee='{self.employee_id}', "
            f"month='{self.pay_month}', net={self.net_salary_fen/100:.2f}yuan)>"
        )


# ── 3. 个税申报记录 ────────────────────────────────────────

class TaxDeclaration(Base, TimestampMixin):
    """
    员工个税计算记录（累计预扣法）。
    每月一条，记录累计收入、累计扣除、累计税额、本月应纳税额。
    """
    __tablename__ = "tax_declarations"
    __table_args__ = (
        UniqueConstraint("employee_id", "tax_month", name="uq_tax_month"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=False, index=True)
    employee_id = Column(String(50), ForeignKey("employees.id"), nullable=False, index=True)
    tax_month = Column(String(7), nullable=False, index=True)  # YYYY-MM

    status = Column(
        SAEnum(TaxStatus, name="tax_declaration_status"),
        nullable=False,
        default=TaxStatus.PENDING,
    )

    # 本月数据（分）
    monthly_income_fen = Column(Integer, nullable=False, default=0)           # 本月应税收入
    monthly_social_deduction_fen = Column(Integer, nullable=False, default=0) # 本月社保公积金扣除
    monthly_special_deduction_fen = Column(Integer, nullable=False, default=0)# 本月专项附加扣除

    # 累计数据（分）— 累计预扣法核心
    cumulative_income_fen = Column(Integer, nullable=False, default=0)         # 累计收入
    cumulative_deduction_fen = Column(Integer, nullable=False, default=0)      # 累计扣除（起征点+社保+专项）
    cumulative_taxable_income_fen = Column(Integer, nullable=False, default=0) # 累计应纳税所得额
    cumulative_tax_fen = Column(Integer, nullable=False, default=0)            # 累计应纳税额
    cumulative_prepaid_tax_fen = Column(Integer, nullable=False, default=0)    # 累计已预扣税额

    # 本月应扣税额（分）= 累计应纳税额 - 累计已预扣税额
    current_month_tax_fen = Column(Integer, nullable=False, default=0)

    # 适用税率和速算扣除数
    tax_rate_pct = Column(Numeric(5, 2), nullable=True)    # 适用税率 %
    quick_deduction_fen = Column(Integer, nullable=True)    # 速算扣除数（分）

    declared_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return (
            f"<TaxDeclaration(employee='{self.employee_id}', "
            f"month='{self.tax_month}', tax={self.current_month_tax_fen/100:.2f}yuan)>"
        )
