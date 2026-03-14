"""
Agent OKR 模型 — P1 统一量化日志
跨所有 Agent 的决策响应日志，支持采纳率/准确率/¥影响追踪

PPT 定义的 OKR：
  BusinessIntelAgent: 决策建议采纳率>70%, 预测准确度±5%以内
  OpsFlowAgent:       库存预警命中率>90%, 订单异常响应<5分钟
  PeopleAgent:        排班人效提升>15%, 人力成本率↓≥2pp
  MarketingAgent:     营销ROI>3:1, 复购周期缩短>20%
  BanquetAgent:       签约率>40%, 线索响应<2小时
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


AgentNameEnum = ENUM(
    "business_intel", "ops_flow", "people", "marketing",
    "banquet", "dish_rd", "supplier", "compliance", "ops", "fct",
    name="agent_okr_agent_name_enum", create_type=True,
)

AgentResponseStatusEnum = ENUM(
    "pending",    # 已推送，待决策
    "adopted",    # 用户接受建议
    "rejected",   # 用户拒绝建议
    "auto",       # 系统自动执行
    "expired",    # 超时未响应
    name="agent_response_status_enum", create_type=True,
)


class AgentResponseLog(Base):
    """
    Agent 决策响应日志（统一量化日志）
    每次 Agent 输出建议 → 记录一条，用户响应后更新状态和实际效果
    """
    __tablename__ = "agent_response_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    brand_id = Column(String(36), nullable=False)
    store_id = Column(String(36), nullable=False)
    agent_name = Column(AgentNameEnum, nullable=False)
    action_type = Column(String(100), nullable=False)  # 如 "order_anomaly", "restock_plan"
    # 建议内容
    recommendation_summary = Column(Text, nullable=True)
    recommendation_yuan = Column(Numeric(14, 2), nullable=True)  # 建议预期¥影响
    confidence = Column(Float, nullable=True)
    priority = Column(String(10), nullable=True)  # P0/P1/P2/P3
    # 用户响应
    status = Column(AgentResponseStatusEnum, nullable=False, server_default="pending")
    responded_at = Column(DateTime, nullable=True)
    response_latency_seconds = Column(Integer, nullable=True)  # 从推送到响应的秒数
    # 实际结果（采纳后回填）
    actual_outcome_yuan = Column(Numeric(14, 2), nullable=True)  # 实际¥效果
    prediction_error_pct = Column(Float, nullable=True)          # |预测-实际|/实际
    outcome_verified = Column(Boolean, server_default="false")
    outcome_verified_at = Column(DateTime, nullable=True)
    # 元数据
    source_record_id = Column(String(36), nullable=True)  # 关联的原始记录ID
    extra_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_agent_resp_agent_store", "agent_name", "store_id"),
        Index("idx_agent_resp_status", "status", "created_at"),
        Index("idx_agent_resp_created", "created_at"),
    )


class AgentOKRSnapshot(Base):
    """
    Agent OKR 快照（每日/每周聚合）
    记录每个 Agent 的 KPI 达成情况，供趋势分析
    """
    __tablename__ = "agent_okr_snapshots"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    brand_id = Column(String(36), nullable=False)
    store_id = Column(String(36), nullable=True)   # NULL = 全品牌汇总
    agent_name = Column(AgentNameEnum, nullable=False)
    period = Column(String(10), nullable=False)    # "2026-03-12" 或 "2026-W11"
    period_type = Column(String(5), nullable=False, server_default="day")  # "day"|"week"
    # 通用指标
    total_recommendations = Column(Integer, nullable=False, server_default="0")
    adopted_count = Column(Integer, nullable=False, server_default="0")
    rejected_count = Column(Integer, nullable=False, server_default="0")
    adoption_rate = Column(Float, nullable=True)      # adopted / (adopted+rejected)
    avg_confidence = Column(Float, nullable=True)
    total_impact_yuan = Column(Numeric(14, 2), nullable=True)
    actual_impact_yuan = Column(Numeric(14, 2), nullable=True)
    avg_prediction_error_pct = Column(Float, nullable=True)
    avg_response_latency_seconds = Column(Integer, nullable=True)
    # OKR达成标志（基于PPT定义）
    okr_adoption_met = Column(Boolean, nullable=True)    # 采纳率目标是否达成
    okr_accuracy_met = Column(Boolean, nullable=True)    # 准确率目标是否达成
    okr_latency_met = Column(Boolean, nullable=True)     # 响应时效是否达成
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_okr_snap_agent_period", "agent_name", "period"),
        Index("idx_okr_snap_brand_period", "brand_id", "period"),
    )
