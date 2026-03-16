"""
Agent 配置模型 — 每个品牌可独立配置各类 Agent 的推送规则和参数
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from .base import Base


class AgentConfig(Base):
    """品牌级 Agent 配置（一个品牌 × 一个 agent_type 唯一）"""

    __tablename__ = "agent_configs"

    id = Column(String(50), primary_key=True, default=lambda: f"AGCFG_{uuid.uuid4().hex[:8].upper()}")
    brand_id = Column(String(50), nullable=False, index=True)
    agent_type = Column(String(50), nullable=False, index=True)
    # agent_type 可选值:
    #   daily_report     — 经营日报推送
    #   inventory_alert  — 库存预警
    #   reconciliation   — 三源对账
    #   member_lifecycle — 会员生命周期
    #   revenue_anomaly  — 营收异常检测
    #   prep_suggestion  — 智能备料建议

    is_enabled = Column(Boolean, default=True, nullable=False)
    config = Column(JSONB, default=dict, nullable=False)
    # config 结构因 agent_type 而异，示例：
    # daily_report:     {"push_time": "07:30", "channels": ["wechat", "sms"], "recipients": ["user_id_1"]}
    # inventory_alert:  {"low_stock_threshold": 20, "expiry_days_before": 3, "channels": ["wechat"]}
    # reconciliation:   {"threshold_pct": 2.0, "schedule": "daily", "sources": ["pos", "inventory", "procurement"]}
    # member_lifecycle: {"churn_days": 90, "birthday_days_before": 3, "rfm_enabled": true}

    description = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        # 每个品牌每种 agent 只能有一条配置
        __import__("sqlalchemy").UniqueConstraint("brand_id", "agent_type", name="uq_agent_config_brand_type"),
    )
