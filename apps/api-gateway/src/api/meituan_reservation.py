"""
美团/大众点评预订渠道API
- Webhook接收美团预订推送（签名验证）
- 本地状态同步到美团
"""

import hashlib
import hmac
import os
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.user import User
from ..services.meituan_reservation_service import meituan_reservation_service

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/meituan/reservation", tags=["meituan_reservation"])

WEBHOOK_SECRET = os.getenv("MEITUAN_RESERVATION_WEBHOOK_SECRET", "")


def _verify_signature(body: bytes, signature: Optional[str]) -> bool:
    """HMAC-SHA256 签名验证"""
    if not WEBHOOK_SECRET:
        return True
    if not signature:
        return False
    expected = hmac.new(
        WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature.removeprefix("sha256="))


class SyncStatusRequest(BaseModel):
    reservation_id: str
    action: str  # confirm | cancel | no_show


@router.post("/webhook")
async def receive_reservation_webhook(
    request: Request,
    x_meituan_signature: Optional[str] = Header(default=None, alias="X-Meituan-Signature"),
):
    """
    接收美团预订推送

    美团/大众点评预订创建、修改、取消时推送到此接口。
    使用 HMAC-SHA256 签名验证。

    推送格式:
    {
        "event_type": "reservation.created" | "reservation.updated" | "reservation.cancelled",
        "store_id": "meituan_poi_id",
        "reservation_id": "mt_rsv_123456",
        "customer_name": "张三",
        "customer_phone": "13800138000",
        "party_size": 4,
        "reservation_date": "2026-03-15",
        "reservation_time": "18:00",
        "table_type": "包厢",
        "special_requests": "靠窗位置",
        "status": "confirmed",
        "source": "meituan" | "dianping",
        "raw": { ... }
    }
    """
    body = await request.body()

    if not _verify_signature(body, x_meituan_signature):
        raise HTTPException(status_code=401, detail="签名验证失败")

    data = await request.json()
    event_type = data.get("event_type", "reservation.created")

    try:
        result = await meituan_reservation_service.handle_webhook(event_type, data)
        return {"success": True, **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("meituan_reservation_webhook_error", error=str(e), event_type=event_type)
        raise HTTPException(status_code=500, detail="处理失败")


@router.post("/sync-status")
async def sync_status_to_meituan(
    req: SyncStatusRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    将本地状态同步到美团

    在屯象OS中确认/取消/标记no-show后，推回美团平台。
    """
    try:
        result = await meituan_reservation_service.sync_to_meituan(session, req.reservation_id, req.action)
        return {"success": True, **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/test")
async def test_webhook_endpoint():
    """连通性测试"""
    return {
        "status": "ok",
        "service": "meituan_reservation",
        "signature_required": bool(WEBHOOK_SECRET),
    }
