"""
Agent Memory Bus API - Agent共享记忆总线API

Provides visibility into the per-store agent memory stream so ops can
inspect what agents have been finding and sharing with each other.
"""
from fastapi import APIRouter, Depends, Query
from typing import Optional

from src.core.dependencies import get_current_user
from src.models.user import User

router = APIRouter(prefix="/api/v1/agent-memory")


@router.get("/{store_id}")
async def get_agent_memory(
    store_id: str,
    last_n: int = Query(20, ge=1, le=100, description="返回最近N条记录"),
    agent: Optional[str] = Query(None, description="按Agent类型过滤: decision/inventory/schedule/order/kpi"),
    current_user: User = Depends(get_current_user),
):
    """
    查看门店Agent共享记忆流

    返回该门店所有Agent最近发布的发现，按时间倒序排列。
    可按Agent类型过滤。

    用途:
    - 了解各Agent当前关注的问题
    - 调试Agent协作是否正常
    - 审计AI决策依据
    """
    from src.services.agent_memory_bus import agent_memory_bus

    findings = await agent_memory_bus.subscribe(
        store_id=store_id,
        last_n=last_n,
        agent_filter=agent,
    )
    stream_len = await agent_memory_bus.stream_length(store_id)

    return {
        "store_id": store_id,
        "stream_length": stream_len,
        "returned": len(findings),
        "findings": findings,
    }


@router.delete("/{store_id}")
async def clear_agent_memory(
    store_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    清空门店Agent记忆流（仅用于测试/调试）
    """
    from src.services.agent_memory_bus import agent_memory_bus
    from src.services.redis_cache_service import redis_cache

    key = f"agent:stream:{store_id}"
    await redis_cache.delete(key)

    return {"store_id": store_id, "cleared": True}
