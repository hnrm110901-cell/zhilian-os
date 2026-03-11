"""
BusinessIntelAgent 数据模型 — Phase 12
经营智能体：DecisionAgent + KPIAgent + OrderAgent 合并

L1 主数据层:  BizMetricSnapshot  — 门店日粒度指标快照
L2 交易层:    RevenueAlert       — 营收异常预警事件
L3 分析层:    KpiScorecard       — KPI健康度评分卡
L4 预警层:    OrderForecast      — 订单量预测
L5 智能层:    BizDecision        — 综合经营决策（Top3建议）
日志层:       BizIntelLog        — Agent执行日志
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, Text, Date, DateTime,
    Numeric, JSON, ForeignKey, Index,
)
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.orm import relationship

from .base import Base

# ─────────────────────────────────────────────
# 枚举
# ─────────────────────────────────────────────

AnomalyLevelEnum = PgEnum(
    "normal", "warning", "critical", "severe",
    name="anomaly_level_enum", create_type=False,
)

KpiStatusEnum = PgEnum(
    "excellent", "on_track", "at_risk", "off_track",
    name="kpi_status_enum", create_type=False,
)

DecisionPriorityEnum = PgEnum(
    "p0", "p1", "p2", "p3",
    name="decision_priority_enum", create_type=False,
)

ScenarioTypeEnum = PgEnum(
    "peak_revenue", "revenue_slump", "cost_overrun",
    "staff_shortage", "inventory_crisis", "normal_ops",
    name="scenario_type_enum", create_type=False,
)

BizIntelAgentTypeEnum = PgEnum(
    "revenue_anomaly", "kpi_scorecard", "order_forecast",
    "biz_insight", "scenario_match",
    name="biz_intel_agent_type_enum", create_type=False,
)

DecisionStatusEnum = PgEnum(
    "pending", "accepted", "rejected", "executed",
    name="biz_decision_status_enum", create_type=False,
)


# ─────────────────────────────────────────────
# L1 主数据层
# ─────────────────────────────────────────────

class BizMetricSnapshot(Base):
    """
    L1 — 门店日粒度指标快照
    每天记录一次，作为各Agent分析的基础数据源
    """
    __tablename__ = "biz_metric_snapshots"

    id             = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    brand_id       = Column(String(36), nullable=False, index=True)
    store_id       = Column(String(36), nullable=False, index=True)
    snapshot_date  = Column(Date, nullable=False, index=True)

    # 营收维度
    revenue_yuan          = Column(Numeric(14, 2), nullable=False, default=0)
    expected_revenue_yuan = Column(Numeric(14, 2), nullable=True)
    revenue_deviation_pct = Column(Float, nullable=True)       # 实际/预期偏差%
    order_count           = Column(Integer, nullable=False, default=0)
    avg_order_value_yuan  = Column(Numeric(10, 2), nullable=True)
    table_turnover_rate   = Column(Float, nullable=True)       # 翻台率

    # 成本维度
    food_cost_yuan        = Column(Numeric(14, 2), nullable=True)
    food_cost_ratio       = Column(Float, nullable=True)       # 食材成本率
    labor_cost_yuan       = Column(Numeric(14, 2), nullable=True)
    labor_cost_ratio      = Column(Float, nullable=True)       # 人力成本率
    gross_profit_yuan     = Column(Numeric(14, 2), nullable=True)
    gross_profit_ratio    = Column(Float, nullable=True)

    # 运营维度
    customer_count        = Column(Integer, nullable=True)
    complaint_count       = Column(Integer, nullable=True, default=0)
    staff_count           = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_biz_snapshot_brand_store_date", "brand_id", "store_id", "snapshot_date"),
    )


# ─────────────────────────────────────────────
# L2 交易层
# ─────────────────────────────────────────────

class RevenueAlert(Base):
    """
    L2 — 营收异常预警事件
    由 RevenueAnomalyAgent 生成
    """
    __tablename__ = "revenue_alerts"

    id             = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    brand_id       = Column(String(36), nullable=False, index=True)
    store_id       = Column(String(36), nullable=False, index=True)
    alert_date     = Column(Date, nullable=False, index=True)

    anomaly_level         = Column(AnomalyLevelEnum, nullable=False)
    actual_revenue_yuan   = Column(Numeric(14, 2), nullable=False)
    expected_revenue_yuan = Column(Numeric(14, 2), nullable=False)
    deviation_pct         = Column(Float, nullable=False)       # 正=超预期，负=不及预期
    impact_yuan           = Column(Numeric(14, 2), nullable=False, default=0)  # ¥影响金额

    root_causes     = Column(JSON, nullable=True)               # ["peak_hour_miss", "dish_oos"]
    recommended_action = Column(Text, nullable=True)
    ai_insight      = Column(Text, nullable=True)               # Claude生成的洞察
    confidence      = Column(Float, nullable=True, default=0.8)

    is_resolved     = Column(Boolean, nullable=False, default=False)
    resolved_at     = Column(DateTime, nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_revenue_alert_brand_store_date", "brand_id", "store_id", "alert_date"),
    )


# ─────────────────────────────────────────────
# L3 分析层
# ─────────────────────────────────────────────

class KpiScorecard(Base):
    """
    L3 — KPI健康度评分卡
    由 KpiScorecardAgent 生成，聚合多维KPI
    """
    __tablename__ = "kpi_scorecards"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    brand_id     = Column(String(36), nullable=False, index=True)
    store_id     = Column(String(36), nullable=False, index=True)
    period       = Column(String(7), nullable=False, index=True)  # "2026-03"

    # 综合健康度
    overall_health_score  = Column(Float, nullable=False)         # 0-100
    revenue_score         = Column(Float, nullable=True)
    cost_score            = Column(Float, nullable=True)
    efficiency_score      = Column(Float, nullable=True)
    quality_score         = Column(Float, nullable=True)

    # 分项汇总
    kpi_items             = Column(JSON, nullable=True)           # [{kpi_id, name, value, target, achievement_pct, status}]
    at_risk_count         = Column(Integer, nullable=False, default=0)
    off_track_count       = Column(Integer, nullable=False, default=0)

    improvement_priorities = Column(JSON, nullable=True)          # [{"kpi": ..., "action": ..., "impact_yuan": ...}]
    ai_insight             = Column(Text, nullable=True)
    confidence             = Column(Float, nullable=True, default=0.85)

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_kpi_scorecard_brand_store_period", "brand_id", "store_id", "period"),
    )


# ─────────────────────────────────────────────
# L4 预警层
# ─────────────────────────────────────────────

class OrderForecast(Base):
    """
    L4 — 订单量/营收预测
    由 OrderForecastAgent 生成，支持3/7/14/30天预测
    """
    __tablename__ = "order_forecasts"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    brand_id     = Column(String(36), nullable=False, index=True)
    store_id     = Column(String(36), nullable=False, index=True)
    forecast_date = Column(Date, nullable=False)                   # 预测生成日期
    horizon_days  = Column(Integer, nullable=False, default=7)     # 预测天数

    # 预测结果
    predicted_orders       = Column(Integer, nullable=False)
    predicted_revenue_yuan = Column(Numeric(14, 2), nullable=False)
    lower_bound_yuan       = Column(Numeric(14, 2), nullable=True) # 置信区间下界
    upper_bound_yuan       = Column(Numeric(14, 2), nullable=True) # 置信区间上界
    trend_slope            = Column(Float, nullable=True)          # 日均增长趋势

    # 历史参照
    avg_daily_orders_7d    = Column(Float, nullable=True)
    avg_daily_revenue_7d   = Column(Numeric(14, 2), nullable=True)
    day_of_week_factors    = Column(JSON, nullable=True)           # {0: 1.2, 6: 0.8} 星期因子

    ai_insight  = Column(Text, nullable=True)
    confidence  = Column(Float, nullable=True, default=0.75)
    created_at  = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_order_forecast_brand_store_date", "brand_id", "store_id", "forecast_date"),
    )


# ─────────────────────────────────────────────
# L5 智能层
# ─────────────────────────────────────────────

class BizDecision(Base):
    """
    L5 — 综合经营决策（Top3建议）
    由 BizInsightAgent 生成，整合营收/KPI/订单三维数据
    """
    __tablename__ = "biz_decisions"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    brand_id     = Column(String(36), nullable=False, index=True)
    store_id     = Column(String(36), nullable=False, index=True)
    decision_date = Column(Date, nullable=False, index=True)

    # Top3建议
    recommendations   = Column(JSON, nullable=False)             # [{rank, title, action, expected_saving_yuan, confidence, urgency_hours, category}]
    total_saving_yuan = Column(Numeric(14, 2), nullable=False, default=0)  # ¥总预期节省
    priority          = Column(DecisionPriorityEnum, nullable=False, default="p1")

    # 决策上下文
    data_sources      = Column(JSON, nullable=True)              # 使用的数据来源
    scenario_type     = Column(ScenarioTypeEnum, nullable=True)  # 当前经营场景
    ai_insight        = Column(Text, nullable=True)

    # 采纳追踪
    status            = Column(DecisionStatusEnum, nullable=False, default="pending")
    accepted_rank     = Column(Integer, nullable=True)           # 店长采纳的建议序号
    accepted_at       = Column(DateTime, nullable=True)
    outcome_yuan      = Column(Numeric(14, 2), nullable=True)    # 实际产生的¥收益（T+1填写）
    confidence        = Column(Float, nullable=True, default=0.80)
    created_at        = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_biz_decision_brand_store_date", "brand_id", "store_id", "decision_date"),
    )


# ─────────────────────────────────────────────
# 场景识别
# ─────────────────────────────────────────────

class ScenarioRecord(Base):
    """
    场景识别记录
    由 ScenarioMatchAgent 生成，支持历史案例匹配
    """
    __tablename__ = "scenario_records"

    id            = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    brand_id      = Column(String(36), nullable=False, index=True)
    store_id      = Column(String(36), nullable=False, index=True)
    record_date   = Column(Date, nullable=False, index=True)

    scenario_type       = Column(ScenarioTypeEnum, nullable=False)
    scenario_score      = Column(Float, nullable=True)           # 场景匹配强度 0-1
    key_signals         = Column(JSON, nullable=True)            # [{signal, value, threshold}]
    historical_matches  = Column(JSON, nullable=True)            # [{date, store_id, similarity, outcome_yuan}]
    recommended_playbook = Column(JSON, nullable=True)           # [{step, action, owner}]
    ai_insight          = Column(Text, nullable=True)
    confidence          = Column(Float, nullable=True, default=0.75)
    created_at          = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_scenario_brand_store_date", "brand_id", "store_id", "record_date"),
    )


# ─────────────────────────────────────────────
# 日志层
# ─────────────────────────────────────────────

class BizIntelLog(Base):
    """Agent执行日志"""
    __tablename__ = "biz_intel_logs"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    brand_id    = Column(String(36), nullable=False, index=True)
    agent_type  = Column(BizIntelAgentTypeEnum, nullable=False)
    input_params  = Column(JSON, nullable=True)
    output_summary = Column(JSON, nullable=True)
    saving_yuan   = Column(Numeric(14, 2), nullable=True, default=0)
    duration_ms   = Column(Integer, nullable=True)
    success       = Column(Boolean, nullable=False, default=True)
    created_at    = Column(DateTime, default=datetime.utcnow, index=True)
