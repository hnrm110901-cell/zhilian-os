"""
私域运营数据库模型
Private Domain Operations Models
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from .base import Base, TimestampMixin


class RFMLevel(str, enum.Enum):
    S1 = "S1"
    S2 = "S2"
    S3 = "S3"
    S4 = "S4"
    S5 = "S5"


class StoreQuadrant(str, enum.Enum):
    BENCHMARK = "benchmark"
    DEFENSIVE = "defensive"
    POTENTIAL = "potential"
    BREAKTHROUGH = "breakthrough"


class SignalType(str, enum.Enum):
    CONSUMPTION = "consumption"
    CHURN_RISK = "churn_risk"
    BAD_REVIEW = "bad_review"
    HOLIDAY = "holiday"
    COMPETITOR = "competitor"
    VIRAL = "viral"


class JourneyType(str, enum.Enum):
    NEW_CUSTOMER = "new_customer"
    VIP_RETENTION = "vip_retention"
    REACTIVATION = "reactivation"
    REVIEW_REPAIR = "review_repair"


class JourneyStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class PrivateDomainMember(Base, TimestampMixin):
    """私域会员档案"""

    __tablename__ = "private_domain_members"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)
    customer_id = Column(String(100), nullable=False, index=True)
    rfm_level = Column(String(5), default=RFMLevel.S3.value, nullable=False)
    store_quadrant = Column(String(20), default=StoreQuadrant.POTENTIAL.value)
    dynamic_tags = Column(JSON, default=list)
    recency_days = Column(Integer, default=0)
    frequency = Column(Integer, default=0)
    monetary = Column(Integer, default=0)  # 分
    last_visit = Column(DateTime, nullable=True)
    risk_score = Column(Float, default=0.0)
    channel_source = Column(String(50), nullable=True)  # 来源渠道
    wechat_openid = Column(String(100), nullable=True)

    # CDP 统一消费者ID（Sprint 2 打通 CDP 地基）
    consumer_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    is_active = Column(Boolean, default=True)
    # RFM 1-5 标准化评分（Sprint 2 CDP RFM 重算）
    r_score = Column(Integer, nullable=True, comment="R评分1-5")
    f_score = Column(Integer, nullable=True, comment="F评分1-5")
    m_score = Column(Integer, nullable=True, comment="M评分1-5")

    rfm_updated_at = Column(DateTime, default=datetime.utcnow)
    birth_date = Column(Date, nullable=True, comment="生日（年月日）")

    __table_args__ = (
        Index("ix_pdm_store_rfm", "store_id", "rfm_level"),
        Index("ix_pdm_store_customer", "store_id", "customer_id", unique=True),
    )


class PrivateDomainSignal(Base, TimestampMixin):
    """信号感知记录"""

    __tablename__ = "private_domain_signals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    signal_id = Column(String(100), unique=True, nullable=False)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)
    customer_id = Column(String(100), nullable=True, index=True)
    signal_type = Column(String(30), nullable=False, index=True)
    description = Column(Text, nullable=False)
    severity = Column(String(20), default="medium")  # low/medium/high/critical
    action_taken = Column(Text, nullable=True)
    triggered_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    resolved_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_pds_store_type", "store_id", "signal_type"),
        Index("ix_pds_triggered", "triggered_at"),
    )


class PrivateDomainJourney(Base, TimestampMixin):
    """用户旅程记录"""

    __tablename__ = "private_domain_journeys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    journey_id = Column(String(100), unique=True, nullable=False)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)
    customer_id = Column(String(100), nullable=False, index=True)
    journey_type = Column(String(30), nullable=False)
    status = Column(String(20), default=JourneyStatus.PENDING.value, nullable=False, index=True)
    current_step = Column(Integer, default=1)
    total_steps = Column(Integer, nullable=False)
    step_history = Column(JSON, default=list)  # 每步执行记录
    started_at = Column(DateTime, default=datetime.utcnow)
    next_action_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_pdj_store_status", "store_id", "status"),
        Index("ix_pdj_customer", "customer_id"),
    )


class StoreQuadrantRecord(Base, TimestampMixin):
    """门店象限历史记录"""

    __tablename__ = "store_quadrant_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)
    quadrant = Column(String(20), nullable=False)
    competition_density = Column(Float, default=0.0)
    member_penetration = Column(Float, default=0.0)
    untapped_potential = Column(Integer, default=0)
    strategy = Column(Text, nullable=True)
    recorded_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (Index("ix_sqr_store_date", "store_id", "recorded_at"),)
