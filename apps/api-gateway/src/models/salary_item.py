"""
Salary Item Models — 薪酬项定义与明细
支持106项薪酬公式的定义、计算和记录
"""

import uuid

from sqlalchemy import Boolean, Column, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSON, UUID

from .base import Base, TimestampMixin


class SalaryItemDefinition(Base, TimestampMixin):
    """
    薪酬项定义（品牌/门店级）
    每个薪酬项定义一个计算公式，按 calc_order 顺序执行
    """

    __tablename__ = "salary_item_definitions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(String(50), nullable=False, index=True)
    store_id = Column(String(50), nullable=True, index=True)  # NULL=品牌通用

    item_name = Column(String(100), nullable=False)  # 应发工资/实发工资/绩效标准/工龄补贴...
    item_code = Column(String(50), nullable=True)  # 薪酬项编码
    item_category = Column(String(30), nullable=False)  # income/deduction/subsidy/tax/attendance/system
    calc_order = Column(Integer, nullable=False, default=50)  # 计算顺序（1-99）
    formula = Column(Text, nullable=True)  # 公式表达式
    formula_type = Column(String(20), default="expression")  # expression/condition/fixed/lookup
    decimal_places = Column(Integer, default=2)
    is_active = Column(Boolean, default=True, nullable=False)
    effective_month = Column(String(7), nullable=True)  # 生效月份 YYYY-MM
    expire_month = Column(String(7), nullable=True)
    remark = Column(Text, nullable=True)

    def __repr__(self):
        return f"<SalaryItemDefinition(name='{self.item_name}', order={self.calc_order})>"


class SalaryItemRecord(Base, TimestampMixin):
    """
    员工月度薪酬项明细
    每个员工每月每个薪酬项一条记录
    """

    __tablename__ = "salary_item_records"
    __table_args__ = (UniqueConstraint("employee_id", "pay_month", "item_id", name="uq_salary_item_month"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=False, index=True)
    employee_id = Column(String(50), nullable=False, index=True)
    pay_month = Column(String(7), nullable=False, index=True)  # YYYY-MM
    item_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    item_name = Column(String(100), nullable=False)  # 冗余方便查询
    item_category = Column(String(30), nullable=False)
    amount_fen = Column(Integer, nullable=False, default=0)  # 金额（分）
    formula_snapshot = Column(Text, nullable=True)  # 计算时的公式快照
    calc_inputs = Column(JSON, nullable=True)  # 计算时的输入参数快照

    def __repr__(self):
        return f"<SalaryItemRecord(emp='{self.employee_id}', item='{self.item_name}', amount={self.amount_fen})>"
