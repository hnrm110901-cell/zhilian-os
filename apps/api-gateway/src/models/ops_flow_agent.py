"""
OpsFlowAgent Models — Phase 13
运营流程体：订单异常 / 库存预警 / 菜品质检 / 出品链联动告警 / 综合优化

核心创新：OpsChainEvent + OpsChainLinkage 实现「1个事件→3层联动」
表命名：ops_flow_* 前缀，避免与现有表冲突
OKR:
  - 库存预警命中率 >90%
  - 菜品质检覆盖率 >80%
  - 订单异常响应 <5分钟
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, Column, DateTime, Float, Index,
    Integer, Numeric, String, Text, func,
)
from sqlalchemy.dialects.postgresql import ENUM, JSON

from .base import Base


# ── PG Enums ──────────────────────────────────────────────────────────────────

OpsFlowAgentTypeEnum = ENUM(
    "chain_alert", "order_anomaly", "inventory_intel",
    "quality_inspection", "ops_optimize",
    name="ops_flow_agent_type_enum", create_type=True,
)

OpsChainEventTypeEnum = ENUM(
    "order_anomaly", "inventory_low", "quality_fail",
    "order_spike", "inventory_expiry", "quality_pattern",
    name="ops_chain_event_type_enum", create_type=True,
)

OpsChainEventSeverityEnum = ENUM(
    "info", "warning", "critical",
    name="ops_chain_event_severity_enum", create_type=True,
)

OpsOrderAnomalyTypeEnum = ENUM(
    "refund_spike", "complaint_rate", "delivery_timeout",
    "revenue_drop", "cancel_surge", "avg_order_drop",
    name="ops_order_anomaly_type_enum", create_type=True,
)

OpsInventoryAlertTypeEnum = ENUM(
    "low_stock", "expiry_risk", "stockout_predicted",
    "overstock", "restock_overdue",
    name="ops_inventory_alert_type_enum", create_type=True,
)

OpsQualityStatusEnum = ENUM(
    "pass", "warning", "fail",
    name="ops_quality_status_enum", create_type=True,
)

OpsDecisionStatusEnum = ENUM(
    "pending", "accepted", "rejected", "auto_executed",
    name="ops_decision_status_enum", create_type=True,
)


# ── L1: 出品链触发事件（联动中枢）───────────────────────────────────────────────

class OpsChainEvent(Base):
    """出品链触发事件 — 任何层（订单/库存/质检）的异常都先写这张表，再触发联动"""
    __tablename__ = "ops_flow_chain_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    brand_id = Column(String(36), nullable=False)
    store_id = Column(String(36), nullable=False)
    event_type = Column(OpsChainEventTypeEnum, nullable=False)
    severity = Column(OpsChainEventSeverityEnum, nullable=False, server_default="warning")
    source_layer = Column(String(20), nullable=False)   # "order" | "inventory" | "quality"
    source_record_id = Column(String(36), nullable=True) # 原始记录ID
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    impact_yuan = Column(Numeric(14, 2), nullable=True)  # 预估¥影响
    event_data = Column(JSON, nullable=True)             # 事件详情
    linkage_triggered = Column(Boolean, server_default="false")  # 是否已触发联动
    linkage_count = Column(Integer, server_default="0")          # 触发联动层数
    resolved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_ops_chain_event_store_type", "store_id", "event_type"),
        Index("idx_ops_chain_event_created", "created_at"),
    )


# ── L2: 联动触发记录（核心新表）──────────────────────────────────────────────────

class OpsChainLinkage(Base):
    """出品链联动触发记录 — 记录「1个事件→触发了哪些层的响应」"""
    __tablename__ = "ops_flow_chain_linkages"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    trigger_event_id = Column(String(36), nullable=False)   # OpsChainEvent.id
    trigger_layer = Column(String(20), nullable=False)      # 触发源层
    target_layer = Column(String(20), nullable=False)       # 被触发层
    target_action = Column(String(100), nullable=False)     # 执行的检查/动作
    target_record_id = Column(String(36), nullable=True)    # 产生的新记录ID
    result_summary = Column(Text, nullable=True)
    impact_yuan = Column(Numeric(14, 2), nullable=True)
    executed_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_ops_linkage_event", "trigger_event_id"),
    )


# ── L3: 订单异常记录 ───────────────────────────────────────────────────────────

class OpsOrderAnomaly(Base):
    """订单层异常分析结果"""
    __tablename__ = "ops_flow_order_anomalies"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    brand_id = Column(String(36), nullable=False)
    store_id = Column(String(36), nullable=False)
    anomaly_type = Column(OpsOrderAnomalyTypeEnum, nullable=False)
    time_period = Column(String(20), nullable=False, server_default="today")
    # 指标数据
    current_value = Column(Float, nullable=True)
    baseline_value = Column(Float, nullable=True)
    deviation_pct = Column(Float, nullable=True)           # 偏差百分比
    estimated_revenue_loss_yuan = Column(Numeric(14, 2), nullable=True)
    # AI分析
    root_cause = Column(Text, nullable=True)
    recommendations = Column(JSON, nullable=True)          # [str]
    ai_insight = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True, server_default="0.80")
    # 联动
    chain_event_id = Column(String(36), nullable=True)     # 触发的OpsChainEvent.id
    order_count = Column(Integer, nullable=True)
    affected_dish_ids = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_ops_order_anomaly_store", "store_id", "created_at"),
    )


# ── L4: 库存预警记录 ───────────────────────────────────────────────────────────

class OpsInventoryAlert(Base):
    """库存层预警分析结果"""
    __tablename__ = "ops_flow_inventory_alerts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    brand_id = Column(String(36), nullable=False)
    store_id = Column(String(36), nullable=False)
    alert_type = Column(OpsInventoryAlertTypeEnum, nullable=False)
    dish_id = Column(String(36), nullable=True)
    dish_name = Column(String(100), nullable=True)
    # 库存数据
    current_qty = Column(Integer, nullable=True)
    safety_qty = Column(Integer, nullable=True)           # 安全库存量
    predicted_stockout_hours = Column(Float, nullable=True)  # 预计几小时后售罄
    restock_qty_recommended = Column(Integer, nullable=True)
    estimated_loss_yuan = Column(Numeric(14, 2), nullable=True)
    # AI分析
    risk_level = Column(String(20), nullable=False, server_default="medium")  # low/medium/high/critical
    recommendations = Column(JSON, nullable=True)
    ai_insight = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True, server_default="0.85")
    # 联动
    chain_event_id = Column(String(36), nullable=True)
    resolved = Column(Boolean, server_default="false")
    resolved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_ops_inv_alert_store_dish", "store_id", "dish_id"),
        Index("idx_ops_inv_alert_unresolved", "store_id", "resolved"),
    )


# ── L5: 质检记录 ───────────────────────────────────────────────────────────────

class OpsQualityRecord(Base):
    """质检层检测结果（整合 QualityAgent）"""
    __tablename__ = "ops_flow_quality_records"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    brand_id = Column(String(36), nullable=False)
    store_id = Column(String(36), nullable=False)
    dish_id = Column(String(36), nullable=True)
    dish_name = Column(String(100), nullable=False)
    # 质检结果
    quality_score = Column(Float, nullable=False)          # 0-100
    status = Column(OpsQualityStatusEnum, nullable=False)
    issues = Column(JSON, nullable=True)                   # [{severity, description, category}]
    suggestions = Column(JSON, nullable=True)
    image_url = Column(String(500), nullable=True)
    # AI分析
    ai_insight = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)
    # 联动
    chain_event_id = Column(String(36), nullable=True)     # 若质检失败触发的联动事件
    alert_sent = Column(Boolean, server_default="false")   # 是否已推送企微告警
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_ops_quality_store_date", "store_id", "created_at"),
        Index("idx_ops_quality_status", "store_id", "status"),
    )


# ── L6: 综合优化决策 ───────────────────────────────────────────────────────────

class OpsFlowDecision(Base):
    """OpsOptimizeAgent 生成的跨层综合优化建议"""
    __tablename__ = "ops_flow_decisions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    brand_id = Column(String(36), nullable=False)
    store_id = Column(String(36), nullable=False)
    decision_title = Column(String(200), nullable=False)
    priority = Column(String(10), nullable=False, server_default="P2")  # P0/P1/P2/P3
    # 涉及层
    involves_order = Column(Boolean, server_default="false")
    involves_inventory = Column(Boolean, server_default="false")
    involves_quality = Column(Boolean, server_default="false")
    # 量化影响
    estimated_revenue_impact_yuan = Column(Numeric(14, 2), nullable=True)
    estimated_cost_saving_yuan = Column(Numeric(14, 2), nullable=True)
    # 建议内容
    recommendations = Column(JSON, nullable=True)          # [{layer, action, expected_yuan, timeline}]
    reasoning = Column(Text, nullable=True)
    ai_insight = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True, server_default="0.80")
    # 状态
    status = Column(OpsDecisionStatusEnum, nullable=False, server_default="pending")
    accepted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_ops_decision_store_priority", "store_id", "priority"),
    )


# ── L7: Agent 调用日志 ─────────────────────────────────────────────────────────

class OpsFlowAgentLog(Base):
    """OpsFlowAgent 调用记录（量化日志，支持OKR追踪）"""
    __tablename__ = "ops_flow_agent_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    brand_id = Column(String(36), nullable=False)
    agent_type = Column(OpsFlowAgentTypeEnum, nullable=False)
    input_params = Column(JSON, nullable=True)
    output_summary = Column(JSON, nullable=True)
    impact_yuan = Column(Numeric(14, 2), nullable=True)
    duration_ms = Column(Integer, nullable=True)
    success = Column(Boolean, nullable=False, server_default="true")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_ops_log_agent_type", "agent_type", "created_at"),
    )
