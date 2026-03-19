"""
宴会销控模型 — Phase P2 (宴荟佳能力)
档期管理 · 吉日等级 · 销售漏斗 · 竞对分析 · 动态定价
"""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Column, Date, DateTime, Enum, Float, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID

from .base import Base, TimestampMixin

# ═══════════════════════════════════════════════════════════════
#  档期吉日配置
# ═══════════════════════════════════════════════════════════════


class AuspiciousLevel(str, enum.Enum):
    """吉日等级"""

    S = "S"  # 超级吉日（如情人节、中秋）
    A = "A"  # 一级吉日（双数好日子）
    B = "B"  # 二级吉日
    NORMAL = "normal"  # 普通日
    OFF_PEAK = "off_peak"  # 淡季日


class DateBookingStatus(str, enum.Enum):
    """档期状态"""

    AVAILABLE = "available"  # 可售
    LOCKED = "locked"  # 锁定（客户意向中）
    SOLD = "sold"  # 已售
    BLOCKED = "blocked"  # 不可用（装修/休息）


class BanquetDateConfig(Base, TimestampMixin):
    """宴会档期配置（日历级别）"""

    __tablename__ = "banquet_date_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)
    hall_id = Column(String(50), nullable=True)  # 可为空=全店通用

    # 日期
    target_date = Column(Date, nullable=False, index=True)

    # 吉日等级
    auspicious_level = Column(Enum(AuspiciousLevel), default=AuspiciousLevel.NORMAL, nullable=False)
    price_multiplier = Column(Numeric(4, 2), default=1.00)  # 价格系数: S=1.5, A=1.3, B=1.1

    # 状态
    booking_status = Column(Enum(DateBookingStatus), default=DateBookingStatus.AVAILABLE, nullable=False, index=True)
    locked_by_reservation_id = Column(String(50), nullable=True)
    locked_at = Column(DateTime, nullable=True)
    lock_expires_at = Column(DateTime, nullable=True)  # 锁定过期时间

    # 容量
    max_tables = Column(Integer, nullable=True)  # 最大桌数
    booked_tables = Column(Integer, default=0)  # 已预订桌数

    # 备注
    notes = Column(Text, nullable=True)  # "情人节特别档期"

    __table_args__ = (
        Index("idx_date_config_store_date", "store_id", "target_date"),
        Index("idx_date_config_status", "store_id", "booking_status"),
    )


# ═══════════════════════════════════════════════════════════════
#  销售漏斗
# ═══════════════════════════════════════════════════════════════


class FunnelStage(str, enum.Enum):
    """销售阶段（复用已有BanquetStage概念，扩展跟进细节）"""

    LEAD = "lead"  # 线索
    INTENT = "intent"  # 意向
    ROOM_LOCK = "room_lock"  # 锁厅
    NEGOTIATION = "negotiation"  # 议价
    SIGNED = "signed"  # 签约
    PREPARATION = "preparation"  # 筹备
    COMPLETED = "completed"  # 完成
    LOST = "lost"  # 输单


class SalesFunnelRecord(Base, TimestampMixin):
    """销售漏斗记录"""

    __tablename__ = "sales_funnel_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)
    reservation_id = Column(String(50), nullable=True, index=True)

    # 客户信息
    customer_name = Column(String(100), nullable=False)
    customer_phone = Column(String(20), nullable=False, index=True)
    event_type = Column(String(30), nullable=True)  # wedding/birthday/corporate

    # 漏斗阶段
    current_stage = Column(Enum(FunnelStage), default=FunnelStage.LEAD, nullable=False, index=True)
    entered_stage_at = Column(DateTime, default=datetime.utcnow)
    stage_duration_hours = Column(Integer, default=0)  # 在当前阶段停留时长

    # 归属
    owner_employee_id = Column(String(50), nullable=True, index=True)

    # 跟进
    follow_up_count = Column(Integer, default=0)
    last_follow_up_at = Column(DateTime, nullable=True)
    next_follow_up_at = Column(DateTime, nullable=True)
    follow_up_notes = Column(JSON, default=list)  # [{time, note, by}]

    # AI 预测
    conversion_probability = Column(Float, nullable=True)  # 0~1
    estimated_value = Column(Integer, default=0)  # 预估金额(分)

    # 输单分析
    lost_reason = Column(Text, nullable=True)
    lost_to_competitor = Column(String(100), nullable=True)

    # 关联
    target_date = Column(Date, nullable=True)  # 目标宴会日期
    target_hall = Column(String(100), nullable=True)
    table_count = Column(Integer, nullable=True)

    __table_args__ = (
        Index("idx_funnel_store_stage", "store_id", "current_stage"),
        Index("idx_funnel_employee", "owner_employee_id", "current_stage"),
    )


# ═══════════════════════════════════════════════════════════════
#  竞对分析
# ═══════════════════════════════════════════════════════════════


class BanquetCompetitor(Base, TimestampMixin):
    """宴会竞对"""

    __tablename__ = "banquet_competitors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)

    # 竞对信息
    competitor_name = Column(String(100), nullable=False)
    competitor_address = Column(String(200), nullable=True)
    competitor_price_min = Column(Integer, nullable=True)  # 最低价(分/桌)
    competitor_price_max = Column(Integer, nullable=True)  # 最高价(分/桌)
    competitor_hall_count = Column(Integer, nullable=True)  # 厅数

    # 竞争数据
    lost_deals_count = Column(Integer, default=0)  # 输给该竞对的单数
    won_deals_count = Column(Integer, default=0)  # 从该竞对赢来的单数
    common_lost_reasons = Column(JSON, default=list)  # ["价格高", "场地小"]

    # 情报
    notes = Column(Text, nullable=True)
    last_updated = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index("idx_competitor_store", "store_id"),)
