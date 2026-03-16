"""
Reward & Penalty Models -- 奖惩管理
奖励/罚款记录，与薪酬自动关联
"""

import enum
import uuid

from sqlalchemy import Column, Date
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID

from .base import Base, TimestampMixin


class RewardPenaltyType(str, enum.Enum):
    """奖惩类型"""

    REWARD = "reward"  # 奖励
    PENALTY = "penalty"  # 罚款


class RewardPenaltyCategory(str, enum.Enum):
    """奖惩分类"""

    # 奖励类
    SERVICE_EXCELLENCE = "service_excellence"  # 服务之星
    SALES_CHAMPION = "sales_champion"  # 销售冠军
    ZERO_WASTE = "zero_waste"  # 零损耗奖
    INNOVATION = "innovation"  # 创新奖
    ATTENDANCE_PERFECT = "attendance_perfect"  # 全勤奖
    TEAM_CONTRIBUTION = "team_contribution"  # 团队贡献奖
    CUSTOMER_PRAISE = "customer_praise"  # 顾客表扬
    # 罚款类
    FOOD_SAFETY = "food_safety"  # 食品安全违规
    HYGIENE = "hygiene"  # 卫生违规
    DISCIPLINE = "discipline"  # 纪律违规
    CUSTOMER_COMPLAINT = "customer_complaint"  # 顾客投诉
    EQUIPMENT_DAMAGE = "equipment_damage"  # 设备损坏
    WASTE_EXCESS = "waste_excess"  # 超额损耗
    OTHER = "other"  # 其他


class RewardPenaltyStatus(str, enum.Enum):
    """审批状态"""

    PENDING = "pending"  # 待审批
    APPROVED = "approved"  # 已批准
    REJECTED = "rejected"  # 已驳回
    CANCELLED = "cancelled"  # 已取消


class RewardPenaltyRecord(Base, TimestampMixin):
    """
    奖惩记录。
    审批通过后自动计入当月工资单。
    所有金额单位：分。
    """

    __tablename__ = "reward_penalty_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=False, index=True)
    employee_id = Column(String(50), ForeignKey("employees.id"), nullable=False, index=True)

    rp_type = Column(
        SAEnum(RewardPenaltyType, name="reward_penalty_type_enum"),
        nullable=False,
        index=True,
    )
    category = Column(
        SAEnum(RewardPenaltyCategory, name="reward_penalty_category_enum"),
        nullable=False,
    )
    status = Column(
        SAEnum(RewardPenaltyStatus, name="reward_penalty_status_enum"),
        nullable=False,
        default=RewardPenaltyStatus.PENDING,
    )

    # 金额（分）—— 奖励为正，罚款为正（type区分方向）
    amount_fen = Column(Integer, nullable=False, default=0)

    # 关联月份（计入哪个月的工资）
    pay_month = Column(String(7), nullable=True, index=True)  # YYYY-MM

    # 事件信息
    incident_date = Column(Date, nullable=False)
    description = Column(Text, nullable=False)
    evidence = Column(JSON, nullable=True)  # 附件/照片URL列表

    # 审批
    submitted_by = Column(String(100), nullable=True)
    approved_by = Column(String(100), nullable=True)
    approved_at = Column(Date, nullable=True)
    reject_reason = Column(Text, nullable=True)

    remark = Column(Text, nullable=True)

    def __repr__(self):
        return (
            f"<RewardPenaltyRecord(employee='{self.employee_id}', "
            f"type='{self.rp_type}', amount={self.amount_fen / 100:.2f}yuan)>"
        )
