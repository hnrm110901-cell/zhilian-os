"""
BFF 会员画像 — P1 到店识客

GET  /api/v1/bff/member-profile/{store_id}/{phone}  — 聚合画像
GET  /api/v1/bff/today-reservations/{store_id}       — 今日预订列表
"""

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.dependencies import get_db, get_current_user, validate_store_brand
from ..models.user import User
from ..services.member_profile_aggregator import member_profile_aggregator

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/api/v1/bff/member-profile",
    tags=["BFF-会员画像"],
)


_CACHE_TTL = 300  # 5分钟


async def _cache_get(key: str):
    """Redis 缓存读取（失败静默返回 None）"""
    try:
        from ..core.redis_client import redis_client
        import json
        val = await redis_client.get(key)
        return json.loads(val) if val else None
    except Exception:
        return None


async def _cache_set(key: str, data: dict):
    """Redis 缓存写入"""
    try:
        from ..core.redis_client import redis_client
        import json
        await redis_client.setex(key, _CACHE_TTL, json.dumps(data, default=str))
    except Exception:
        pass


@router.get("/{store_id}/{phone}", summary="获取会员画像")
async def get_member_profile(
    store_id: str,
    phone: str,
    include_ai: bool = Query(default=True, description="是否生成AI话术"),
    refresh: bool = Query(default=False, description="强制刷新缓存"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    聚合多源会员画像：身份+偏好+资产+里程碑+AI话术。
    每个子源独立失败，降级返回 null。
    Redis 缓存 5 分钟，?refresh=true 强制刷新。
    """
    await validate_store_brand(store_id, current_user)

    cache_key = f"member_profile:{store_id}:{phone}"
    if not refresh:
        cached = await _cache_get(cache_key)
        if cached:
            return cached

    profile = await member_profile_aggregator.aggregate(
        db=db,
        phone=phone.strip(),
        store_id=store_id,
        include_ai_script=include_ai,
    )

    # 清理内部字段（以 _ 开头的）
    identity = profile.get("identity")
    if identity:
        # 把 dietary_restrictions 移到 preferences
        dietary = identity.pop("_dietary_restrictions", [])
        profile["identity"] = {
            k: v for k, v in identity.items() if not k.startswith("_")
        }
        prefs = profile.get("preferences")
        if prefs and dietary:
            prefs["dietary_restrictions"] = dietary

    await _cache_set(cache_key, profile)
    return profile
