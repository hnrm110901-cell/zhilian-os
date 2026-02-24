"""
事件溯源 API
查询 Neural System 事件的完整处理链路
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import Optional
from datetime import datetime, timedelta

from ..core.database import get_db
from ..models.neural_event_log import NeuralEventLog, EventProcessingStatus

router = APIRouter(prefix="/api/v1/event-sourcing", tags=["event_sourcing"])


@router.get("/events/{store_id}")
async def list_events(
    store_id: str,
    event_type: Optional[str] = Query(None, description="过滤事件类型"),
    status: Optional[EventProcessingStatus] = Query(None, description="过滤处理状态"),
    hours: int = Query(24, ge=1, le=720, description="查询最近N小时"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """列出门店的神经事件处理记录（最近N小时）"""
    since = datetime.utcnow() - timedelta(hours=hours)
    conditions = [
        NeuralEventLog.store_id == store_id,
        NeuralEventLog.queued_at >= since,
    ]
    if event_type:
        conditions.append(NeuralEventLog.event_type == event_type)
    if status:
        conditions.append(NeuralEventLog.processing_status == status)

    result = await db.execute(
        select(NeuralEventLog)
        .where(and_(*conditions))
        .order_by(NeuralEventLog.queued_at.desc())
        .limit(limit)
        .offset(offset)
    )
    events = result.scalars().all()
    return {"store_id": store_id, "total": len(events), "events": [e.to_dict() for e in events]}


@router.get("/events/{store_id}/{event_id}")
async def get_event(
    store_id: str,
    event_id: str,
    db: AsyncSession = Depends(get_db),
):
    """获取单个事件的完整处理链路"""
    log = await db.get(NeuralEventLog, event_id)
    if not log or log.store_id != store_id:
        raise HTTPException(status_code=404, detail="Event not found")
    return log.to_dict()


@router.get("/stats/{store_id}")
async def event_stats(
    store_id: str,
    hours: int = Query(24, ge=1, le=720),
    db: AsyncSession = Depends(get_db),
):
    """门店事件处理统计（各状态计数）"""
    from sqlalchemy import func
    since = datetime.utcnow() - timedelta(hours=hours)
    result = await db.execute(
        select(NeuralEventLog.processing_status, func.count().label("count"))
        .where(and_(
            NeuralEventLog.store_id == store_id,
            NeuralEventLog.queued_at >= since,
        ))
        .group_by(NeuralEventLog.processing_status)
    )
    rows = result.all()
    stats = {row.processing_status.value: row.count for row in rows}
    total = sum(stats.values())
    return {"store_id": store_id, "hours": hours, "total": total, "by_status": stats}
