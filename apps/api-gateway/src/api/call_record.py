"""
来电记录 + 路线发送 API — P2 补齐（易订PRO 1.5路线发送 + 1.15来电记录）

来电记录：
- 存储电话呼入/呼出记录
- 关联客户档案（自动识别老客）
- 支持 CTI 系统 Webhook 接入

路线发送：
- 为预订客户生成门店导航链接
- 通过短信/企微推送到店路线
"""

import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.user import User

router = APIRouter()


# ══════════════════════════════════════════════════════════════════
# 来电记录（内存存储，生产环境迁移到数据库）
# ══════════════════════════════════════════════════════════════════

_call_records: List[Dict[str, Any]] = []


class CallRecordRequest(BaseModel):
    store_id: str
    caller_phone: str
    call_direction: str = "inbound"  # inbound(来电) / outbound(去电)
    caller_name: Optional[str] = None
    duration_seconds: Optional[int] = None
    recording_url: Optional[str] = None
    notes: Optional[str] = None
    cti_source: Optional[str] = None  # CTI系统来源标识


@router.post("/api/v1/call-records", status_code=201)
async def create_call_record(
    req: CallRecordRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """记录来电/去电（支持CTI Webhook调用）"""
    # 尝试识别老客
    customer_info = await _identify_customer(session, req.caller_phone, req.store_id)

    record = {
        "id": str(uuid.uuid4()),
        "store_id": req.store_id,
        "caller_phone": req.caller_phone,
        "caller_name": req.caller_name or customer_info.get("name"),
        "call_direction": req.call_direction,
        "duration_seconds": req.duration_seconds,
        "recording_url": req.recording_url,
        "notes": req.notes,
        "cti_source": req.cti_source,
        "customer_recognized": customer_info.get("recognized", False),
        "customer_level": customer_info.get("level"),
        "total_visits": customer_info.get("total_visits", 0),
        "created_at": datetime.utcnow().isoformat(),
    }
    _call_records.append(record)
    return record


@router.get("/api/v1/call-records")
async def list_call_records(
    store_id: str = Query(...),
    days: int = Query(7, description="查询最近N天"),
    caller_phone: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """查询来电记录"""
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()

    records = [
        r
        for r in _call_records
        if r["store_id"] == store_id and r["created_at"] >= since and (not caller_phone or r["caller_phone"] == caller_phone)
    ]

    return {
        "store_id": store_id,
        "total": len(records),
        "records": sorted(records, key=lambda x: x["created_at"], reverse=True)[:100],
    }


@router.post("/api/v1/call-records/webhook")
async def cti_webhook(
    payload: Dict[str, Any],
    session: AsyncSession = Depends(get_db),
):
    """
    CTI 系统 Webhook 入口。

    接收第三方电话系统的来电推送事件。
    格式灵活，自动归一化存储。
    """
    req = CallRecordRequest(
        store_id=payload.get("store_id", "unknown"),
        caller_phone=payload.get("caller", payload.get("phone", "")),
        call_direction=payload.get("direction", "inbound"),
        caller_name=payload.get("name"),
        duration_seconds=payload.get("duration"),
        recording_url=payload.get("recording_url"),
        cti_source=payload.get("source", "external_cti"),
    )

    customer_info = await _identify_customer(session, req.caller_phone, req.store_id)

    record = {
        "id": str(uuid.uuid4()),
        "store_id": req.store_id,
        "caller_phone": req.caller_phone,
        "caller_name": req.caller_name or customer_info.get("name"),
        "call_direction": req.call_direction,
        "duration_seconds": req.duration_seconds,
        "recording_url": req.recording_url,
        "cti_source": req.cti_source,
        "customer_recognized": customer_info.get("recognized", False),
        "customer_level": customer_info.get("level"),
        "raw_payload": payload,
        "created_at": datetime.utcnow().isoformat(),
    }
    _call_records.append(record)
    return {"status": "ok", "record_id": record["id"]}


async def _identify_customer(session: AsyncSession, phone: str, store_id: str) -> Dict[str, Any]:
    """来电自动识别客户档案"""
    try:
        from sqlalchemy import and_, select

        from ..models.customer_ownership import CustomerOwnership

        result = await session.execute(
            select(CustomerOwnership).where(
                and_(
                    CustomerOwnership.customer_phone == phone,
                    CustomerOwnership.store_id == store_id,
                    CustomerOwnership.is_active == True,
                )
            )
        )
        ownership = result.scalar_one_or_none()
        if ownership:
            return {
                "recognized": True,
                "name": ownership.customer_name,
                "level": ownership.customer_level,
                "total_visits": ownership.total_visits,
                "total_spent": ownership.total_spent,
            }
    except Exception:
        pass

    return {"recognized": False}


# ══════════════════════════════════════════════════════════════════
# 路线发送（到店导航）
# ══════════════════════════════════════════════════════════════════


class SendRouteRequest(BaseModel):
    reservation_id: str
    channel: str = "sms"  # sms / wechat


@router.post("/api/v1/reservations/{reservation_id}/send-route")
async def send_route(
    reservation_id: str,
    req: SendRouteRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    向预订客户发送门店导航路线。

    生成腾讯/高德地图导航链接，通过短信或企微推送。
    """
    from sqlalchemy import select

    from ..models.reservation import Reservation
    from ..models.store import Store

    # 获取预订信息
    res_result = await session.execute(select(Reservation).where(Reservation.id == reservation_id))
    r = res_result.scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="预订不存在")

    # 获取门店信息
    store_result = await session.execute(select(Store).where(Store.id == r.store_id))
    store = store_result.scalar_one_or_none()

    store_name = store.name if store else r.store_id
    store_address = store.address if store and hasattr(store, "address") else ""

    # 生成导航链接（腾讯地图URI Scheme）
    # 生产环境应从 store 表读取经纬度
    nav_url = f"https://apis.map.qq.com/uri/v1/routeplan?type=drive&to={store_name}&tocoord=0,0&referer=tunxiangos"
    if store_address:
        nav_url = f"https://apis.map.qq.com/uri/v1/search?keyword={store_address}&referer=tunxiangos"

    message = (
        f"【{store_name}】\n"
        f"您的预订：{r.reservation_date} {r.reservation_time.strftime('%H:%M')}，{r.party_size}位\n"
        f"导航路线：{nav_url}\n"
        f"地址：{store_address}"
    )

    # 发送通知（fire-and-forget）
    sent = False
    try:
        if req.channel == "sms":
            from ..services.sms_service import sms_service

            await sms_service.send_sms(r.customer_phone, message)
            sent = True
        elif req.channel == "wechat":
            from ..services.wechat_trigger_service import wechat_trigger_service

            await wechat_trigger_service.trigger(
                "route.sent",
                {
                    "customer_phone": r.customer_phone,
                    "store_name": store_name,
                    "nav_url": nav_url,
                },
            )
            sent = True
    except Exception:
        pass

    return {
        "reservation_id": reservation_id,
        "customer_phone": r.customer_phone[:3] + "****" + r.customer_phone[-4:],
        "channel": req.channel,
        "nav_url": nav_url,
        "store_address": store_address,
        "message_sent": sent,
    }
