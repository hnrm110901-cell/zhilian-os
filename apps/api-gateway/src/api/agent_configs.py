"""
Agent 配置管理 API — 品牌级 Agent 启停 / 参数配置
仅 ADMIN 可用
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.core.dependencies import require_role
from src.models.user import User, UserRole
from src.services import agent_config_service

router = APIRouter(prefix="/agent-configs", tags=["agent-configs"])


class UpdateAgentConfigRequest(BaseModel):
    is_enabled: Optional[bool] = None
    config: Optional[dict] = None


@router.get("/{brand_id}")
async def list_brand_agents(
    brand_id: str,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """列出品牌所有 Agent 配置（不存在则自动初始化默认配置）"""
    return await agent_config_service.list_brand_agents(session, brand_id)


@router.get("/{brand_id}/{agent_type}")
async def get_agent_config(
    brand_id: str,
    agent_type: str,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """获取单个 Agent 配置详情"""
    cfg = await agent_config_service.get_agent_config(session, brand_id, agent_type)
    if not cfg:
        raise HTTPException(status_code=404, detail="Agent 配置不存在")
    return cfg


@router.put("/{brand_id}/{agent_type}")
async def update_agent_config(
    brand_id: str,
    agent_type: str,
    req: UpdateAgentConfigRequest,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """更新 Agent 配置（参数合并更新，未传入的字段保留原值）"""
    result = await agent_config_service.update_agent_config(
        session,
        brand_id,
        agent_type,
        is_enabled=req.is_enabled,
        config=req.config,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Agent 配置不存在")
    await session.commit()
    return result


@router.post("/{brand_id}/{agent_type}/toggle")
async def toggle_agent(
    brand_id: str,
    agent_type: str,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """切换 Agent 启用/停用"""
    result = await agent_config_service.toggle_agent(session, brand_id, agent_type)
    if not result:
        raise HTTPException(status_code=404, detail="Agent 配置不存在")
    await session.commit()
    return result


@router.post("/{brand_id}/init")
async def init_brand_agents(
    brand_id: str,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """为品牌初始化全部默认 Agent 配置"""
    created = await agent_config_service.init_brand_agents(session, brand_id)
    await session.commit()
    return {"brand_id": brand_id, "created": created}
