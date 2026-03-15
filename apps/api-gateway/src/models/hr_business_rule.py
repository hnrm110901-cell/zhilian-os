"""
HR业务规则配置 — 替代硬编码的扣款/补贴/奖金规则
支持按 品牌→门店→岗位 三级配置继承
"""
import enum
import uuid

from sqlalchemy import Column, String, Integer, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID, JSON

from .base import Base, TimestampMixin


class RuleCategory(str, enum.Enum):
    """规则类别"""
    ATTENDANCE_PENALTY = "attendance_penalty"   # 考勤扣款
    SENIORITY_SUBSIDY = "seniority_subsidy"    # 工龄补贴
    OVERTIME_RATE = "overtime_rate"             # 加班倍数
    FULL_ATTENDANCE = "full_attendance"         # 全勤奖
    MEAL_SUBSIDY = "meal_subsidy"              # 餐补
    TRANSPORT_SUBSIDY = "transport_subsidy"     # 交通补贴
    HOUSING_SUBSIDY = "housing_subsidy"         # 住房补贴
    POSITION_ALLOWANCE = "position_allowance"   # 岗位津贴
    OTHER = "other"


class HRBusinessRule(Base, TimestampMixin):
    """
    HR业务规则配置表

    rules_json 结构示例:

    attendance_penalty:
        {"late_per_time_fen": 5000, "absent_per_day_fen": 20000,
         "early_leave_per_time_fen": 3000}

    seniority_subsidy:
        {"tiers": [
            {"min_months": 13, "max_months": 24, "amount_fen": 5000},
            {"min_months": 24, "max_months": 36, "amount_fen": 10000},
            {"min_months": 36, "max_months": 48, "amount_fen": 15000},
            {"min_months": 48, "max_months": 99999, "amount_fen": 20000}
        ]}

    overtime_rate:
        {"weekday": 1.5, "weekend": 2.0, "holiday": 3.0}

    full_attendance:
        {"enabled": true, "bonus_fen": 30000}

    meal_subsidy:
        {"per_day_fen": 1500, "workday_only": true}

    position_allowance:
        {"manager": 200000, "chef_head": 150000, "senior_waiter": 50000}
    """
    __tablename__ = "hr_business_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(String(50), nullable=False, index=True)
    store_id = Column(String(50), nullable=True)          # NULL = 品牌通用
    position = Column(String(50), nullable=True)           # NULL = 所有岗位
    employment_type = Column(String(30), nullable=True)    # NULL = 所有用工类型

    category = Column(String(50), nullable=False, index=True)  # RuleCategory value
    rule_name = Column(String(100), nullable=False)            # 人类可读名称
    rules_json = Column(JSON, nullable=False)                  # 规则详情

    priority = Column(Integer, default=0)       # 优先级（高优先）
    is_active = Column(Boolean, default=True)
    description = Column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<HRBusinessRule {self.rule_name} "
            f"category={self.category} brand={self.brand_id} "
            f"store={self.store_id}>"
        )
