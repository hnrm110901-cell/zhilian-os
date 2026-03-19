"""
Agent 配置管理 Service — CRUD + 批量初始化
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.agent_config import AgentConfig

# 默认 Agent 配置模板
DEFAULT_CONFIGS: dict[str, dict] = {
    "daily_report": {
        "push_time": "07:30",
        "channels": ["wechat"],
        "recipients": [],
        "include_sections": ["revenue", "traffic", "food_cost", "anomalies"],
    },
    "inventory_alert": {
        "low_stock_threshold_pct": 20,
        "expiry_days_before": 3,
        "check_time": "10:00",
        "channels": ["wechat"],
    },
    "reconciliation": {
        "threshold_pct": 2.0,
        "schedule": "daily",
        "run_time": "03:00",
        "sources": ["pos", "inventory", "procurement"],
        "auto_alert": True,
    },
    "member_lifecycle": {
        "churn_days": 90,
        "birthday_days_before": 3,
        "rfm_enabled": True,
        "rfm_segments": ["high_value", "at_risk", "lost"],
    },
    "revenue_anomaly": {
        "check_interval_minutes": 15,
        "threshold_std": 2.0,
        "channels": ["wechat"],
    },
    "prep_suggestion": {
        "generate_time": "16:00",
        "safety_factor": 1.1,
        "auto_push": False,
    },
}


async def init_brand_agents(session: AsyncSession, brand_id: str) -> list[dict]:
    """为新品牌初始化全部默认 Agent 配置"""
    created = []
    for agent_type, default_cfg in DEFAULT_CONFIGS.items():
        existing = await session.execute(
            select(AgentConfig).where(
                AgentConfig.brand_id == brand_id,
                AgentConfig.agent_type == agent_type,
            )
        )
        if existing.scalar_one_or_none():
            continue

        cfg = AgentConfig(
            id=f"AGCFG_{uuid.uuid4().hex[:8].upper()}",
            brand_id=brand_id,
            agent_type=agent_type,
            is_enabled=False,
            config=default_cfg,
            description=_type_label(agent_type),
        )
        session.add(cfg)
        created.append({"id": cfg.id, "agent_type": agent_type})

    await session.flush()
    return created


async def list_brand_agents(session: AsyncSession, brand_id: str) -> list[dict]:
    """列出品牌所有 Agent 配置"""
    result = await session.execute(
        select(AgentConfig).where(AgentConfig.brand_id == brand_id).order_by(AgentConfig.agent_type)
    )
    configs = result.scalars().all()

    # 如果品牌还没有配置，自动初始化
    if not configs:
        await init_brand_agents(session, brand_id)
        await session.commit()
        result = await session.execute(
            select(AgentConfig).where(AgentConfig.brand_id == brand_id).order_by(AgentConfig.agent_type)
        )
        configs = result.scalars().all()

    return [_to_dict(c) for c in configs]


async def get_agent_config(session: AsyncSession, brand_id: str, agent_type: str) -> Optional[dict]:
    """获取单个 Agent 配置"""
    result = await session.execute(
        select(AgentConfig).where(
            AgentConfig.brand_id == brand_id,
            AgentConfig.agent_type == agent_type,
        )
    )
    cfg = result.scalar_one_or_none()
    return _to_dict(cfg) if cfg else None


async def update_agent_config(
    session: AsyncSession,
    brand_id: str,
    agent_type: str,
    *,
    is_enabled: Optional[bool] = None,
    config: Optional[dict] = None,
) -> Optional[dict]:
    """更新 Agent 配置"""
    result = await session.execute(
        select(AgentConfig).where(
            AgentConfig.brand_id == brand_id,
            AgentConfig.agent_type == agent_type,
        )
    )
    cfg = result.scalar_one_or_none()
    if not cfg:
        return None

    if is_enabled is not None:
        cfg.is_enabled = is_enabled
    if config is not None:
        # 合并更新，保留未传入的字段
        merged = {**(cfg.config or {}), **config}
        cfg.config = merged

    cfg.updated_at = datetime.utcnow()
    await session.flush()
    return _to_dict(cfg)


async def toggle_agent(session: AsyncSession, brand_id: str, agent_type: str) -> Optional[dict]:
    """切换 Agent 启用/停用"""
    result = await session.execute(
        select(AgentConfig).where(
            AgentConfig.brand_id == brand_id,
            AgentConfig.agent_type == agent_type,
        )
    )
    cfg = result.scalar_one_or_none()
    if not cfg:
        return None

    cfg.is_enabled = not cfg.is_enabled
    cfg.updated_at = datetime.utcnow()
    await session.flush()
    return _to_dict(cfg)


def _to_dict(cfg: AgentConfig) -> dict:
    return {
        "id": cfg.id,
        "brand_id": cfg.brand_id,
        "agent_type": cfg.agent_type,
        "agent_label": _type_label(cfg.agent_type),
        "is_enabled": cfg.is_enabled,
        "config": cfg.config or {},
        "description": cfg.description,
        "created_at": cfg.created_at.isoformat() if cfg.created_at else None,
        "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None,
    }


def _type_label(agent_type: str) -> str:
    labels = {
        "daily_report": "经营日报",
        "inventory_alert": "库存预警",
        "reconciliation": "三源对账",
        "member_lifecycle": "会员生命周期",
        "revenue_anomaly": "营收异常检测",
        "prep_suggestion": "智能备料建议",
    }
    return labels.get(agent_type, agent_type)
