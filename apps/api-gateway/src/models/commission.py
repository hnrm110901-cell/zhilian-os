"""
Commission Models -- 提成管理
提成规则配置 + 提成记录
"""

import enum
import uuid

from sqlalchemy import Boolean, Column, Date
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSON, UUID

from .base import Base, TimestampMixin


class CommissionType(str, enum.Enum):
    """提成类型"""

    SALES_AMOUNT = "sales_amount"  # 按营业额
    DISH_COUNT = "dish_count"  # 按菜品销量
    SERVICE_FEE = "service_fee"  # 按服务费（宴会/包间）
    MEMBERSHIP = "membership"  # 会员转化提成
    CUSTOM = "custom"  # 自定义


class CommissionCalcMethod(str, enum.Enum):
    """计算方式"""

    FIXED_PER_UNIT = "fixed_per_unit"  # 每单/每份固定金额
    PERCENTAGE = "percentage"  # 按比例
    TIERED = "tiered"  # 阶梯式


class CommissionRule(Base, TimestampMixin):
    """
    提成规则配置。
    支持门店级/岗位级个性化规则。
    """

    __tablename__ = "commission_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=False, index=True)
    name = Column(String(100), nullable=False)  # 规则名称

    commission_type = Column(
        SAEnum(CommissionType, name="commission_type_enum"),
        nullable=False,
    )
    calc_method = Column(
        SAEnum(CommissionCalcMethod, name="commission_calc_method_enum"),
        nullable=False,
    )

    # 适用范围
    applicable_positions = Column(JSON, nullable=True)  # ["waiter","chef"] 为空=全岗位
    applicable_employee_ids = Column(JSON, nullable=True)  # 指定员工，为空=全员

    # 固定金额（分/单位）—— FIXED_PER_UNIT 时使用
    fixed_amount_fen = Column(Integer, default=0)

    # 提成比例（%）—— PERCENTAGE 时使用
    rate_pct = Column(Numeric(6, 3), default=0)  # 如 2.5%

    # 阶梯规则（JSON）—— TIERED 时使用
    # 格式: [{"min": 0, "max": 50000, "rate_pct": 1.0}, {"min": 50000, "max": 100000, "rate_pct": 1.5}]
    tiered_rules = Column(JSON, nullable=True)

    # 计算基数过滤（关联菜品/品类）
    target_dish_ids = Column(JSON, nullable=True)  # 关联菜品ID
    target_categories = Column(JSON, nullable=True)  # 关联品类

    is_active = Column(Boolean, default=True, nullable=False)
    effective_date = Column(Date, nullable=False)
    expire_date = Column(Date, nullable=True)
    remark = Column(Text, nullable=True)

    def __repr__(self):
        return f"<CommissionRule(name='{self.name}', type='{self.commission_type}')>"


class CommissionRecord(Base, TimestampMixin):
    """
    提成记录：每月计算后生成。
    所有金额单位：分。
    """

    __tablename__ = "commission_records"
    __table_args__ = (
        UniqueConstraint(
            "employee_id",
            "pay_month",
            "rule_id",
            name="uq_commission_month_rule",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=False, index=True)
    employee_id = Column(String(50), ForeignKey("employees.id"), nullable=False, index=True)
    pay_month = Column(String(7), nullable=False, index=True)  # YYYY-MM
    rule_id = Column(UUID(as_uuid=True), ForeignKey("commission_rules.id"), nullable=False)

    # 计算基数
    base_amount_fen = Column(Integer, default=0)  # 计算基数（营业额/销量等）
    base_quantity = Column(Integer, default=0)  # 数量基数（份数/单数）

    # 提成金额
    commission_fen = Column(Integer, nullable=False, default=0)

    # 计算明细
    calculation_detail = Column(JSON, nullable=True)
    remark = Column(Text, nullable=True)

    def __repr__(self):
        return (
            f"<CommissionRecord(employee='{self.employee_id}', "
            f"month='{self.pay_month}', amount={self.commission_fen / 100:.2f}yuan)>"
        )
