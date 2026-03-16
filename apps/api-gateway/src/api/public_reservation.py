"""
客户自助预订公开API — 无需登录
H5页面通过手机号+验证码认证后，使用 X-Phone-Token 访问
"""

from datetime import date, datetime, time
from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..middleware.public_rate_limiter import check_ip_rate_limit, check_sms_rate_limit
from ..services.public_reservation_service import public_reservation_service
from ..services.sms_service import sms_service

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/public", tags=["public_reservation"])


# ── Pydantic Models ──


class SendCodeRequest(BaseModel):
    phone: str = Field(..., min_length=11, max_length=11, description="手机号")


class VerifyCodeRequest(BaseModel):
    phone: str = Field(..., min_length=11, max_length=11)
    code: str = Field(..., min_length=6, max_length=6)


class CreateBookingRequest(BaseModel):
    store_id: str
    customer_name: str = Field(..., min_length=1, max_length=50)
    party_size: int = Field(..., ge=1, le=100)
    reservation_date: date
    reservation_time: time
    reservation_type: str = "regular"
    table_type: Optional[str] = None
    special_requests: Optional[str] = Field(None, max_length=500)
    dietary_restrictions: Optional[str] = Field(None, max_length=255)


class BookingResponse(BaseModel):
    id: str
    store_id: str
    customer_name: str
    customer_phone: str
    party_size: int
    reservation_date: date
    reservation_time: time
    reservation_type: str
    status: str
    table_type: Optional[str] = None
    special_requests: Optional[str] = None
    created_at: Optional[datetime] = None


def _to_booking_response(r) -> BookingResponse:
    return BookingResponse(
        id=str(r.id),
        store_id=r.store_id,
        customer_name=r.customer_name,
        customer_phone=r.customer_phone,
        party_size=r.party_size,
        reservation_date=r.reservation_date,
        reservation_time=r.reservation_time,
        reservation_type=r.reservation_type.value if hasattr(r.reservation_type, "value") else str(r.reservation_type),
        status=r.status.value if hasattr(r.status, "value") else str(r.status),
        table_type=r.room_name,
        special_requests=r.special_requests,
        created_at=r.created_at,
    )


# ── Helper: get DB without tenant isolation ──


def _get_public_db():
    return get_db(enable_tenant_isolation=False)


async def _get_phone_from_token(x_phone_token: str = Header(..., alias="X-Phone-Token")) -> str:
    """从 X-Phone-Token Header 提取手机号"""
    phone = await public_reservation_service.get_phone_by_token(x_phone_token)
    if not phone:
        raise HTTPException(status_code=401, detail="Token 无效或已过期，请重新验证手机号")
    return phone


# ── SMS 验证 ──


@router.post("/sms/send-code")
async def send_code(
    req: SendCodeRequest,
    _: None = Depends(check_ip_rate_limit),
):
    """发送短信验证码"""
    await check_sms_rate_limit(req.phone)
    try:
        result = await sms_service.send_code(req.phone)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sms/verify")
async def verify_code(
    req: VerifyCodeRequest,
    _: None = Depends(check_ip_rate_limit),
):
    """验证手机号 → 返回 phone token（24h有效）"""
    ok = await sms_service.verify_code(req.phone, req.code)
    if not ok:
        raise HTTPException(status_code=400, detail="验证码错误或已过期")

    token = await public_reservation_service.create_phone_token(req.phone)
    return {"token": token, "expires_in": 86400}


# ── 门店信息 ──


@router.get("/stores")
async def list_stores(
    session: AsyncSession = Depends(_get_public_db),
    _: None = Depends(check_ip_rate_limit),
):
    """获取门店列表（公开信息）"""
    return await public_reservation_service.get_public_stores(session)


@router.get("/stores/{store_id}/availability")
async def get_availability(
    store_id: str,
    target_date: date = Query(..., description="查询日期"),
    session: AsyncSession = Depends(_get_public_db),
    _: None = Depends(check_ip_rate_limit),
):
    """查询门店可用时段"""
    return await public_reservation_service.get_store_availability(session, store_id, target_date)


# ── 预订操作（需 X-Phone-Token） ──


@router.post("/reservations", response_model=BookingResponse, status_code=201)
async def create_reservation(
    req: CreateBookingRequest,
    phone: str = Depends(_get_phone_from_token),
    session: AsyncSession = Depends(_get_public_db),
):
    """创建预订"""
    try:
        r = await public_reservation_service.create_public_reservation(
            session=session,
            phone=phone,
            store_id=req.store_id,
            customer_name=req.customer_name,
            party_size=req.party_size,
            reservation_date=req.reservation_date,
            reservation_time=req.reservation_time,
            reservation_type=req.reservation_type,
            table_type=req.table_type,
            special_requests=req.special_requests,
            dietary_restrictions=req.dietary_restrictions,
        )
        return _to_booking_response(r)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/reservations", response_model=List[BookingResponse])
async def my_reservations(
    phone: str = Depends(_get_phone_from_token),
    session: AsyncSession = Depends(_get_public_db),
):
    """查看我的预订"""
    reservations = await public_reservation_service.lookup_reservations(session, phone)
    return [_to_booking_response(r) for r in reservations]


@router.post("/reservations/{reservation_id}/cancel", response_model=BookingResponse)
async def cancel_reservation(
    reservation_id: str,
    phone: str = Depends(_get_phone_from_token),
    session: AsyncSession = Depends(_get_public_db),
):
    """取消预订"""
    try:
        r = await public_reservation_service.cancel_reservation(session, reservation_id, phone)
        return _to_booking_response(r)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
