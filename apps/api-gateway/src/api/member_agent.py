"""
MemberAgent + BossAgent API — Sprint 3

端点：
  MemberAgent（沉睡唤醒 + VIP保护）:
    GET  /dormant/scan          — 扫描沉睡会员
    POST /dormant/wakeup        — 批量触发唤醒旅程
    GET  /wakeup/metrics        — 唤醒KPI看板
    GET  /vip/alerts            — VIP流失预警

  BossAgent（老板视角经营智能）:
    GET  /boss/brief            — 每日经营速览
    GET  /boss/member-health    — 会员健康仪表盘
    GET  /boss/store-comparison — 跨门店对标
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.core.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/cdp/agent", tags=["CDP-Agent"])


# ── Request Schemas ────────────────────────────────────────────────


class WakeupRequest(BaseModel):
    store_id: str
    min_recency_days: int = 30
    max_count: int = 50
    dry_run: bool = True


# ── MemberAgent Endpoints ─────────────────────────────────────────


@router.get("/dormant/scan")
async def scan_dormant_members(
    store_id: str = Query(...),
    min_recency_days: int = Query(30),
    limit: int = Query(100, le=500),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """扫描沉睡会员列表（按紧急度排序）"""
    from src.services.member_agent_service import member_agent_service

    return await member_agent_service.scan_dormant_members(
        db,
        store_id,
        min_recency_days=min_recency_days,
        limit=limit,
    )


@router.post("/dormant/wakeup")
async def batch_trigger_wakeup(
    req: WakeupRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """批量触发沉睡唤醒旅程（默认 dry_run=True 仅预估）"""
    from src.services.member_agent_service import member_agent_service

    result = await member_agent_service.batch_trigger_wakeup(
        db,
        req.store_id,
        min_recency_days=req.min_recency_days,
        max_count=req.max_count,
        dry_run=req.dry_run,
    )
    if not req.dry_run:
        await db.commit()
    return result


@router.get("/wakeup/metrics")
async def get_wakeup_metrics(
    store_id: str = Query(...),
    days: int = Query(7, le=90),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """唤醒效果指标（Sprint 3 KPI: ≥50条/周）"""
    from src.services.member_agent_service import member_agent_service

    return await member_agent_service.get_wakeup_metrics(db, store_id, days=days)


@router.get("/vip/alerts")
async def get_vip_alerts(
    store_id: str = Query(...),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """S1 高价值客户流失预警"""
    from src.services.member_agent_service import member_agent_service

    return await member_agent_service.get_vip_protection_alerts(db, store_id)


# ── BossAgent Endpoints ───────────────────────────────────────────


@router.get("/boss/brief")
async def get_daily_brief(
    store_id: str = Query(...),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """老板每日经营速览（30秒读懂生意）"""
    from src.services.boss_agent_service import boss_agent_service

    return await boss_agent_service.get_daily_brief(db, store_id)


@router.get("/boss/member-health")
async def get_member_health(
    store_id: Optional[str] = Query(None),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """CDP 会员健康仪表盘"""
    from src.services.boss_agent_service import boss_agent_service

    return await boss_agent_service.get_member_health_dashboard(db, store_id=store_id)


@router.get("/boss/store-comparison")
async def get_store_comparison(
    store_ids: Optional[str] = Query(None, description="逗号分隔的门店ID"),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """跨门店会员健康对标"""
    from src.services.boss_agent_service import boss_agent_service

    ids = store_ids.split(",") if store_ids else None
    return await boss_agent_service.get_multi_store_comparison(db, store_ids=ids)
