"""
事件溯源 API
查询 Neural System 事件的完整处理链路
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import Optional
from datetime import datetime, timedelta
import structlog

from ..core.database import get_db
from ..models.neural_event_log import NeuralEventLog, EventProcessingStatus

logger = structlog.get_logger()
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


@router.post("/replay/{event_id}")
async def replay_event(
    event_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    重放事件 — 将已完成或失败的事件重置为 PENDING，重新入队处理。

    适用于：修复 bug 后对失败事件批量重试，或对历史事件重新应用新逻辑。
    """
    log = await db.get(NeuralEventLog, event_id)
    if not log:
        raise HTTPException(status_code=404, detail="Event not found")

    if log.processing_status == EventProcessingStatus.PROCESSING:
        raise HTTPException(status_code=409, detail="Event is currently being processed")

    prev_status = log.processing_status
    log.processing_status = EventProcessingStatus.PENDING
    log.started_at         = None
    log.processed_at       = None
    log.error_message      = None
    log.retry_count        = (log.retry_count or 0) + 1

    await db.commit()

    logger.info(
        "event_replayed",
        event_id=event_id,
        store_id=log.store_id,
        prev_status=prev_status,
        retry_count=log.retry_count,
    )

    return {
        "event_id":      event_id,
        "store_id":      log.store_id,
        "event_type":    log.event_type,
        "prev_status":   prev_status,
        "new_status":    EventProcessingStatus.PENDING,
        "retry_count":   log.retry_count,
        "replayed_at":   datetime.utcnow().isoformat(),
    }


@router.get("/snapshot/{store_id}")
async def event_snapshot(
    store_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    事件流快照 — 返回门店当前事件流的统计快照，包含：
    - 各状态计数（总体 + 最近 24 小时）
    - 最常见的 event_type Top-5
    - 平均处理时长
    - 待处理 / 失败事件列表（各最多 5 条）
    """
    from sqlalchemy import func, case

    now   = datetime.utcnow()
    h24   = now - timedelta(hours=24)

    # ── 全量状态分布 ──
    all_stats_result = await db.execute(
        select(NeuralEventLog.processing_status, func.count().label("cnt"))
        .where(NeuralEventLog.store_id == store_id)
        .group_by(NeuralEventLog.processing_status)
    )
    all_stats = {r.processing_status.value: r.cnt for r in all_stats_result.all()}

    # ── 最近 24h 状态分布 ──
    recent_stats_result = await db.execute(
        select(NeuralEventLog.processing_status, func.count().label("cnt"))
        .where(and_(NeuralEventLog.store_id == store_id, NeuralEventLog.queued_at >= h24))
        .group_by(NeuralEventLog.processing_status)
    )
    recent_stats = {r.processing_status.value: r.cnt for r in recent_stats_result.all()}

    # ── Top-5 event_type ──
    type_result = await db.execute(
        select(NeuralEventLog.event_type, func.count().label("cnt"))
        .where(NeuralEventLog.store_id == store_id)
        .group_by(NeuralEventLog.event_type)
        .order_by(func.count().desc())
        .limit(5)
    )
    top_types = [{"event_type": r.event_type, "count": r.cnt} for r in type_result.all()]

    # ── 平均处理时长（秒） ──
    avg_result = await db.execute(
        select(
            func.avg(
                func.extract("epoch", NeuralEventLog.processed_at) -
                func.extract("epoch", NeuralEventLog.started_at)
            )
        ).where(
            and_(
                NeuralEventLog.store_id == store_id,
                NeuralEventLog.processed_at.isnot(None),
                NeuralEventLog.started_at.isnot(None),
            )
        )
    )
    avg_processing_s = round(float(avg_result.scalar() or 0), 2)

    # ── 待处理 + 失败事件样本 ──
    pending_result = await db.execute(
        select(NeuralEventLog)
        .where(and_(
            NeuralEventLog.store_id == store_id,
            NeuralEventLog.processing_status == EventProcessingStatus.PENDING,
        ))
        .order_by(NeuralEventLog.queued_at.asc())
        .limit(5)
    )
    pending_events = [e.to_dict() for e in pending_result.scalars().all()]

    failed_result = await db.execute(
        select(NeuralEventLog)
        .where(and_(
            NeuralEventLog.store_id == store_id,
            NeuralEventLog.processing_status == EventProcessingStatus.FAILED,
        ))
        .order_by(NeuralEventLog.queued_at.desc())
        .limit(5)
    )
    failed_events = [e.to_dict() for e in failed_result.scalars().all()]

    return {
        "store_id":            store_id,
        "snapshot_at":         now.isoformat(),
        "all_time":            all_stats,
        "last_24h":            recent_stats,
        "top_event_types":     top_types,
        "avg_processing_secs": avg_processing_s,
        "pending_sample":      pending_events,
        "failed_sample":       failed_events,
    }


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
