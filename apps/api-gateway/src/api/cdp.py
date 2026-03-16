"""
CDP API — Consumer Data Platform 统一消费者身份管理

Sprint 1: 身份解析 + 回填 + 统计
Sprint 2: RFM 重算 + 企微通道 + 偏差校验
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.core.dependencies import get_current_user
from src.services.identity_resolution_service import identity_resolution_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/cdp", tags=["CDP"])


# ── Request / Response Schemas ──────────────────────────────────────


class ResolveRequest(BaseModel):
    phone: str
    store_id: Optional[str] = None
    wechat_openid: Optional[str] = None
    wechat_unionid: Optional[str] = None
    pos_member_id: Optional[str] = None
    source: str = "manual"
    display_name: Optional[str] = None


class MergeRequest(BaseModel):
    winner_id: str
    loser_id: str


class BackfillRequest(BaseModel):
    store_id: str
    batch_size: int = 500


# ── Endpoints ───────────────────────────────────────────────────────


@router.post("/resolve")
async def resolve_consumer(
    req: ResolveRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """解析或创建统一消费者身份，返回 consumer_id"""
    try:
        consumer_id = await identity_resolution_service.resolve(
            db,
            req.phone,
            store_id=req.store_id,
            wechat_openid=req.wechat_openid,
            wechat_unionid=req.wechat_unionid,
            pos_member_id=req.pos_member_id,
            source=req.source,
            display_name=req.display_name,
        )
        await db.commit()
        return {"consumer_id": str(consumer_id)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/consumer/{consumer_id}")
async def get_consumer(
    consumer_id: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取消费者详情"""
    import uuid

    try:
        cid = uuid.UUID(consumer_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid consumer_id")

    consumer = await identity_resolution_service.get_consumer(db, cid)
    if not consumer:
        raise HTTPException(status_code=404, detail="consumer not found")

    return {
        "consumer_id": str(consumer.id),
        "primary_phone": consumer.primary_phone,
        "display_name": consumer.display_name,
        "gender": consumer.gender,
        "birth_date": str(consumer.birth_date) if consumer.birth_date else None,
        "wechat_openid": consumer.wechat_openid,
        "wechat_unionid": consumer.wechat_unionid,
        "wechat_nickname": consumer.wechat_nickname,
        "total_order_count": consumer.total_order_count,
        "total_order_amount_yuan": round((consumer.total_order_amount_fen or 0) / 100, 2),
        "total_reservation_count": consumer.total_reservation_count,
        "first_order_at": consumer.first_order_at.isoformat() if consumer.first_order_at else None,
        "last_order_at": consumer.last_order_at.isoformat() if consumer.last_order_at else None,
        "rfm_recency_days": consumer.rfm_recency_days,
        "rfm_frequency": consumer.rfm_frequency,
        "rfm_monetary_yuan": round((consumer.rfm_monetary_fen or 0) / 100, 2),
        "tags": consumer.tags or [],
        "is_merged": consumer.is_merged,
        "source": consumer.source,
        "created_at": consumer.created_at.isoformat() if consumer.created_at else None,
    }


@router.get("/lookup")
async def lookup_by_phone(
    phone: str = Query(..., min_length=1),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """按手机号查找消费者"""
    consumer = await identity_resolution_service.get_consumer_by_phone(db, phone)
    if not consumer:
        return {"found": False, "consumer_id": None}
    return {"found": True, "consumer_id": str(consumer.id)}


@router.post("/merge")
async def merge_consumers(
    req: MergeRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """合并两个消费者身份（loser → winner）"""
    import uuid

    try:
        winner = uuid.UUID(req.winner_id)
        loser = uuid.UUID(req.loser_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid UUID")

    try:
        result_id = await identity_resolution_service.merge(db, winner, loser)
        await db.commit()
        return {"merged_consumer_id": str(result_id)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/backfill/orders")
async def backfill_orders(
    req: BackfillRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """回填指定门店存量订单的 consumer_id"""
    result = await identity_resolution_service.backfill_orders(
        db,
        req.store_id,
        batch_size=req.batch_size,
    )
    await db.commit()
    return result


@router.post("/backfill/reservations")
async def backfill_reservations(
    req: BackfillRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """回填指定门店存量预订的 consumer_id"""
    result = await identity_resolution_service.backfill_reservations(
        db,
        req.store_id,
        batch_size=req.batch_size,
    )
    await db.commit()
    return result


@router.post("/refresh/{consumer_id}")
async def refresh_profile(
    consumer_id: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """刷新消费者聚合统计"""
    import uuid

    try:
        cid = uuid.UUID(consumer_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid consumer_id")

    await identity_resolution_service.refresh_profile(db, cid)
    await db.commit()
    return {"status": "ok"}


@router.get("/stats")
async def get_cdp_stats(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """CDP 基础统计"""
    return await identity_resolution_service.get_stats(db)


@router.get("/fill-rate")
async def get_fill_rate(
    store_id: Optional[str] = Query(None),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    consumer_id 填充率（Sprint 1 KPI: >= 80%）

    返回 orders/reservations/queues 各表的填充率
    """
    from src.services.cdp_sync_service import cdp_sync_service

    return await cdp_sync_service.get_fill_rate(db, store_id=store_id)


# ── Sprint 2: RFM 重算 + 企微通道 ──────────────────────────────────


class RFMRecalcRequest(BaseModel):
    store_id: Optional[str] = None


class MemberBackfillRequest(BaseModel):
    store_id: Optional[str] = None
    batch_size: int = 500


class BatchSendRequest(BaseModel):
    store_id: str
    rfm_levels: List[str] = ["S4", "S5"]
    message_type: str = "text"
    content: str
    limit: int = 100
    dry_run: bool = True


class TagSendRequest(BaseModel):
    store_id: str
    tags: List[str]
    message_type: str = "text"
    content: str
    limit: int = 100
    dry_run: bool = True


@router.post("/rfm/recalculate")
async def rfm_recalculate(
    req: RFMRecalcRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """基于 consumer_id 重算全量 RFM（Sprint 2）"""
    from src.services.cdp_rfm_service import cdp_rfm_service

    result = await cdp_rfm_service.recalculate_all(db, store_id=req.store_id)
    await db.commit()
    return result


@router.get("/rfm/deviation")
async def rfm_deviation(
    store_id: Optional[str] = Query(None),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """RFM 偏差率（Sprint 2 KPI: < 5%）"""
    from src.services.cdp_rfm_service import cdp_rfm_service

    return await cdp_rfm_service.compute_deviation(db, store_id=store_id)


@router.post("/backfill/members")
async def backfill_members(
    req: MemberBackfillRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """将 PrivateDomainMember 链接到 ConsumerIdentity（按 customer_id=phone 匹配）"""
    from src.services.cdp_rfm_service import cdp_rfm_service

    result = await cdp_rfm_service.backfill_members(
        db,
        store_id=req.store_id,
        batch_size=req.batch_size,
    )
    await db.commit()
    return result


@router.post("/wechat/batch-send")
async def wechat_batch_send(
    req: BatchSendRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """按 RFM 等级批量发送企微消息（默认 dry_run=True 仅预估）"""
    from src.services.cdp_wechat_channel import cdp_wechat_channel

    result = await cdp_wechat_channel.batch_send_by_rfm(
        db,
        req.store_id,
        req.rfm_levels,
        req.message_type,
        req.content,
        limit=req.limit,
        dry_run=req.dry_run,
    )
    if not req.dry_run:
        await db.commit()
    return result


@router.post("/wechat/tag-send")
async def wechat_tag_send(
    req: TagSendRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """按标签定向推送企微消息"""
    from src.services.cdp_wechat_channel import cdp_wechat_channel

    result = await cdp_wechat_channel.batch_send_by_tags(
        db,
        req.store_id,
        req.tags,
        req.message_type,
        req.content,
        limit=req.limit,
        dry_run=req.dry_run,
    )
    if not req.dry_run:
        await db.commit()
    return result


@router.get("/wechat/channel-stats")
async def wechat_channel_stats(
    store_id: Optional[str] = Query(None),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """企微通道统计：openid覆盖率 + CDP链接率"""
    from src.services.cdp_wechat_channel import cdp_wechat_channel

    return await cdp_wechat_channel.get_channel_stats(db, store_id=store_id)
