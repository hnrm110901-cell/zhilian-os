"""
客户归属与风控模型 — Phase P1 (客必得能力)
客户归属追踪 + 离职交接 + 流失预警
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from .base import Base, TimestampMixin

# ═══════════════════════════════════════════════════════════════
#  客户归属
# ═══════════════════════════════════════════════════════════════


class TransferReason(str, enum.Enum):
    """交接原因"""

    RESIGNATION = "resignation"  # 离职
    REORG = "reorg"  # 组织调整
    MANUAL = "manual"  # 手动转移
    AUTO_BALANCE = "auto_balance"  # 自动均衡


class CustomerOwnership(Base, TimestampMixin):
    """客户归属记录（防止人走客走）"""

    __tablename__ = "customer_ownerships"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)

    # 客户
    customer_phone = Column(String(20), nullable=False, index=True)
    customer_name = Column(String(100), nullable=False)

    # 归属
    owner_employee_id = Column(String(50), ForeignKey("employees.id"), nullable=False, index=True)
    assigned_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    # 交接
    transferred_from = Column(String(50), nullable=True)  # 前归属人ID
    transferred_at = Column(DateTime, nullable=True)
    transfer_reason = Column(Enum(TransferReason), nullable=True)
    transfer_notes = Column(Text, nullable=True)

    # 客户价值
    total_visits = Column(Integer, default=0)
    total_spent = Column(Integer, default=0)  # 累计消费(分)
    last_visit_at = Column(DateTime, nullable=True)
    customer_level = Column(String(20), nullable=True)  # VIP/GOLD/SILVER/NORMAL

    __table_args__ = (
        Index("idx_ownership_store_active", "store_id", "is_active"),
        Index("idx_ownership_employee", "owner_employee_id", "is_active"),
        Index("idx_ownership_phone", "customer_phone", "store_id"),
    )


# ═══════════════════════════════════════════════════════════════
#  客户流失预警
# ═══════════════════════════════════════════════════════════════


class RiskLevel(str, enum.Enum):
    """风险等级"""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RiskType(str, enum.Enum):
    """风险类型"""

    DORMANT = "dormant"  # 沉睡(>30天未消费)
    DECLINING = "declining"  # 消费频次下降
    COMPETITOR_LOST = "competitor_lost"  # 疑似流失到竞对
    NEGATIVE_FEEDBACK = "negative_feedback"  # 差评/投诉


class CustomerRiskAlert(Base, TimestampMixin):
    """客户流失预警"""

    __tablename__ = "customer_risk_alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)

    # 客户
    customer_phone = Column(String(20), nullable=False, index=True)
    customer_name = Column(String(100), nullable=False)

    # 风险评估
    risk_level = Column(Enum(RiskLevel), nullable=False, index=True)
    risk_type = Column(Enum(RiskType), nullable=False)
    risk_score = Column(Float, nullable=True)  # 0~1
    last_visit_days = Column(Integer, nullable=False)  # 距上次消费天数

    # AI分析
    predicted_churn_probability = Column(Float, nullable=True)  # 流失概率
    suggested_action = Column(Text, nullable=True)  # AI建议的挽回动作
    suggested_offer = Column(String(200), nullable=True)  # 建议优惠 "满200减50"

    # 执行追踪
    action_taken = Column(Boolean, default=False, nullable=False)
    action_taken_at = Column(DateTime, nullable=True)
    action_by = Column(String(50), nullable=True)  # 执行人
    action_result = Column(Text, nullable=True)  # 执行结果
    is_resolved = Column(Boolean, default=False, nullable=False)

    __table_args__ = (
        Index("idx_risk_store_level", "store_id", "risk_level"),
        Index("idx_risk_unresolved", "store_id", "is_resolved"),
    )
