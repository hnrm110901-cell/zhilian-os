"""
Daily Summary tables — 每日营业/损耗/经营汇总
"""

import uuid

from sqlalchemy import Boolean, Column, Date, Integer, Numeric, String, Time, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

from .base import Base, TimestampMixin


class DailyRevenueSummary(Base, TimestampMixin):
    """每日营业汇总"""

    __tablename__ = "daily_revenue_summary"
    __table_args__ = (UniqueConstraint("store_id", "biz_date"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=False, index=True)
    biz_date = Column(Date, nullable=False)
    order_count = Column(Integer, nullable=False)
    guest_count = Column(Integer)
    dine_in_count = Column(Integer)
    takeout_count = Column(Integer)
    gross_revenue_fen = Column(Integer, nullable=False)
    discount_total_fen = Column(Integer)
    net_revenue_fen = Column(Integer, nullable=False)
    platform_commission_fen = Column(Integer)
    avg_ticket_fen = Column(Integer)
    table_turnover_rate = Column(Numeric(5, 2))
    peak_hour_start = Column(Time)
    peak_hour_end = Column(Time)
    weather = Column(String(20))
    is_holiday = Column(Boolean)


class DailyWasteSummary(Base, TimestampMixin):
    """每日损耗汇总"""

    __tablename__ = "daily_waste_summary"
    __table_args__ = (UniqueConstraint("store_id", "biz_date"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=False, index=True)
    biz_date = Column(Date, nullable=False)
    total_waste_cost_fen = Column(Integer, nullable=False)
    total_waste_events = Column(Integer, nullable=False)
    waste_rate_pct = Column(Numeric(5, 2))
    top_waste_ingredient = Column(String(100))
    top_waste_cost_fen = Column(Integer)
    preventable_cost_fen = Column(Integer)
    root_cause_dist = Column(JSONB)  # {"staff_error":4,"spoilage":2}


class DailyPnlSummary(Base, TimestampMixin):
    """经营日报（每日损益汇总）"""

    __tablename__ = "daily_pnl_summary"
    __table_args__ = (UniqueConstraint("store_id", "biz_date"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=False, index=True)
    biz_date = Column(Date, nullable=False)
    # 收入
    gross_revenue_fen = Column(Integer, nullable=False)
    discount_fen = Column(Integer)
    net_revenue_fen = Column(Integer, nullable=False)
    # 成本
    food_cost_fen = Column(Integer, nullable=False)
    food_cost_pct = Column(Numeric(5, 2))
    labor_cost_fen = Column(Integer, nullable=False)
    labor_cost_pct = Column(Numeric(5, 2))
    rent_cost_fen = Column(Integer)
    utility_cost_fen = Column(Integer)
    platform_fee_fen = Column(Integer)
    packaging_cost_fen = Column(Integer)
    waste_cost_fen = Column(Integer)
    other_cost_fen = Column(Integer)
    # 利润
    gross_profit_fen = Column(Integer)
    gross_profit_pct = Column(Numeric(5, 2))
    operating_profit_fen = Column(Integer)
    operating_profit_pct = Column(Numeric(5, 2))
