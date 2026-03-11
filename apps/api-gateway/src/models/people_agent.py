"""
PeopleAgent Models — Phase 12B
人员智能体：排班优化 / 绩效评分 / 人力成本 / 考勤预警 / 人员配置
表命名：people_* 前缀，避免与现有 schedules / employee_metric_records 冲突
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float, Index,
    Integer, Numeric, String, Text, func,
)
from sqlalchemy.dialects.postgresql import ENUM, JSON

from .base import Base


# ── PG Enums ─────────────────────────────────────────────────────────────────

PeopleAgentTypeEnum = ENUM(
    "shift_optimizer", "performance_score", "labor_cost",
    "attendance_warn", "staffing_plan",
    name="people_agent_type_enum", create_type=False,
)

ShiftStatusEnum = ENUM(
    "draft", "published", "active", "completed", "cancelled",
    name="people_shift_status_enum", create_type=False,
)

PerformanceRatingEnum = ENUM(
    "outstanding", "exceeds", "meets", "below", "unsatisfactory",
    name="people_performance_rating_enum", create_type=False,
)

AttendanceAlertTypeEnum = ENUM(
    "late", "absent", "early_leave", "overtime", "understaffed",
    name="people_attendance_alert_type_enum", create_type=False,
)

StaffingDecisionStatusEnum = ENUM(
    "pending", "accepted", "rejected",
    name="people_staffing_decision_status_enum", create_type=False,
)


# ── L1: 排班优化记录 ──────────────────────────────────────────────────────────

class PeopleShiftRecord(Base):
    """Agent生成的每日排班优化方案"""
    __tablename__ = "people_shift_records"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    brand_id = Column(String(36), nullable=False)
    store_id = Column(String(36), nullable=False)
    shift_date = Column(Date, nullable=False)
    # 优化前/后人数
    required_headcount = Column(Integer, nullable=False, server_default="0")
    scheduled_headcount = Column(Integer, nullable=False, server_default="0")
    coverage_rate = Column(Float, nullable=True)          # 覆盖率 0-1
    # 成本
    estimated_labor_cost_yuan = Column(Numeric(14, 2), nullable=True)
    labor_cost_per_revenue_pct = Column(Float, nullable=True)  # 人力成本率%
    # 排班详情 JSON
    shift_assignments = Column(JSON, nullable=True)            # [{employee_id, shift_type, start, end}]
    optimization_suggestions = Column(JSON, nullable=True)     # [str]
    peak_hours = Column(JSON, nullable=True)                   # ["12:00-13:00", ...]
    status = Column(ShiftStatusEnum, nullable=False, server_default="draft")
    ai_insight = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True, server_default="0.80")
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_people_shift_brand_store_date", "brand_id", "store_id", "shift_date"),
    )


# ── L2: 绩效评分 ─────────────────────────────────────────────────────────────

class PeoplePerformanceScore(Base):
    """员工月度绩效评分（OKR对标）"""
    __tablename__ = "people_performance_scores"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    brand_id = Column(String(36), nullable=False)
    store_id = Column(String(36), nullable=False)
    employee_id = Column(String(36), nullable=False)
    employee_name = Column(String(100), nullable=True)
    role = Column(String(50), nullable=False)
    period = Column(String(7), nullable=False)             # "2026-03"
    # 分项得分
    kpi_scores = Column(JSON, nullable=True)               # [{kpi: str, score: float, weight: float}]
    overall_score = Column(Float, nullable=False)          # 0-100
    rating = Column(PerformanceRatingEnum, nullable=False)
    # 提成
    base_commission_yuan = Column(Numeric(12, 2), nullable=True)
    bonus_commission_yuan = Column(Numeric(12, 2), nullable=True, server_default="0")
    total_commission_yuan = Column(Numeric(12, 2), nullable=True)
    # 改进建议
    improvement_areas = Column(JSON, nullable=True)        # [str]
    ai_insight = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True, server_default="0.85")
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_people_perf_brand_store_emp_period", "brand_id", "store_id", "employee_id", "period"),
    )


# ── L3: 人力成本快照 ─────────────────────────────────────────────────────────

class PeopleLaborCostRecord(Base):
    """门店人力成本周期快照（人效分析）"""
    __tablename__ = "people_labor_cost_records"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    brand_id = Column(String(36), nullable=False)
    store_id = Column(String(36), nullable=False)
    period = Column(String(7), nullable=False)             # "2026-03"
    # 成本结构
    total_labor_cost_yuan = Column(Numeric(14, 2), nullable=False)
    revenue_yuan = Column(Numeric(14, 2), nullable=True)
    labor_cost_ratio = Column(Float, nullable=True)        # %
    target_labor_cost_ratio = Column(Float, nullable=True, server_default="0.28")
    # 效率指标
    revenue_per_employee_yuan = Column(Numeric(12, 2), nullable=True)  # 人效
    avg_headcount = Column(Float, nullable=True)
    overtime_hours = Column(Float, nullable=True, server_default="0")
    overtime_cost_yuan = Column(Numeric(12, 2), nullable=True, server_default="0")
    # 分析
    cost_breakdown = Column(JSON, nullable=True)           # {role: cost_yuan}
    optimization_potential_yuan = Column(Numeric(12, 2), nullable=True)
    ai_insight = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True, server_default="0.80")
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_people_labor_brand_store_period", "brand_id", "store_id", "period"),
    )


# ── L4: 考勤预警 ─────────────────────────────────────────────────────────────

class PeopleAttendanceAlert(Base):
    """考勤异常预警（迟到/缺勤/加班超限）"""
    __tablename__ = "people_attendance_alerts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    brand_id = Column(String(36), nullable=False)
    store_id = Column(String(36), nullable=False)
    employee_id = Column(String(36), nullable=True)
    employee_name = Column(String(100), nullable=True)
    alert_date = Column(Date, nullable=False)
    alert_type = Column(AttendanceAlertTypeEnum, nullable=False)
    severity = Column(String(20), nullable=False, server_default="warning")  # info/warning/critical
    description = Column(Text, nullable=True)
    estimated_impact_yuan = Column(Numeric(12, 2), nullable=True)
    recommended_action = Column(Text, nullable=True)
    is_resolved = Column(Boolean, nullable=False, server_default="false")
    resolved_at = Column(DateTime, nullable=True)
    ai_insight = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_people_alert_brand_store_date", "brand_id", "store_id", "alert_date"),
    )


# ── L5: 人员配置建议 ─────────────────────────────────────────────────────────

class PeopleStaffingDecision(Base):
    """综合人员配置建议（招聘/调岗/裁减）"""
    __tablename__ = "people_staffing_decisions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    brand_id = Column(String(36), nullable=False)
    store_id = Column(String(36), nullable=False)
    decision_date = Column(Date, nullable=False)
    # 决策
    recommendations = Column(JSON, nullable=False)         # [{rank, action, impact_yuan, urgency, role}]
    total_impact_yuan = Column(Numeric(14, 2), nullable=False, server_default="0")
    priority = Column(String(10), nullable=False, server_default="p1")  # p0/p1/p2/p3
    status = Column(StaffingDecisionStatusEnum, nullable=False, server_default="pending")
    accepted_at = Column(DateTime, nullable=True)
    # 支撑数据
    current_headcount = Column(Integer, nullable=True)
    optimal_headcount = Column(Integer, nullable=True)
    headcount_gap = Column(Integer, nullable=True)
    ai_insight = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True, server_default="0.80")
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_people_staffing_brand_store_date", "brand_id", "store_id", "decision_date"),
    )


# ── Log ──────────────────────────────────────────────────────────────────────

class PeopleAgentLog(Base):
    """PeopleAgent调用日志"""
    __tablename__ = "people_agent_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    brand_id = Column(String(36), nullable=False)
    agent_type = Column(PeopleAgentTypeEnum, nullable=False)
    input_params = Column(JSON, nullable=True)
    output_summary = Column(JSON, nullable=True)
    impact_yuan = Column(Numeric(14, 2), nullable=True, server_default="0")
    duration_ms = Column(Integer, nullable=True)
    success = Column(Boolean, nullable=False, server_default="true")
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_people_log_brand_created", "brand_id", "created_at"),
    )
