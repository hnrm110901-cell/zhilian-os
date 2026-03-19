"""BFF 发券 + ROI — P2"""

import structlog
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID

from ..core.dependencies import get_db, get_current_user, validate_store_brand
from ..models.user import User
from ..models.service_voucher import ServiceVoucherTemplate
from ..models.consumer_identity import ConsumerIdentity
from ..services.coupon_distribution_service import coupon_distribution_service
from ..services.coupon_roi_service import coupon_roi_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/bff/member-profile", tags=["BFF-发券"])


class DistributeCouponRequest(BaseModel):
    consumer_id: str
    coupon_source: str  # weishenghuo | service_voucher
    coupon_id: str
    coupon_name: Optional[str] = ""
    coupon_value_fen: Optional[int] = 0
    phone: Optional[str] = None


@router.get("/{store_id}/available-coupons/{consumer_id}", summary="可用券列表")
async def available_coupons(
    store_id: str,
    consumer_id: str,
    phone: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """聚合微生活券 + 屯象服务券模板，返回可选券列表"""
    await validate_store_brand(store_id, current_user)
    brand_id = current_user.brand_id or ""
    coupons: List[dict] = []

    # 1) 微生活券 — 需要手机号查 card_no
    if phone:
        try:
            from ..services.member_service import member_service
            member = await member_service.query_member(mobile=phone)
            card_no = (member or {}).get("card_no", "")
            if card_no:
                wsh_list = await member_service.coupon_list(card_no=card_no, store_id=store_id)
                for c in (wsh_list or []):
                    coupons.append({
                        "id": str(c.get("coupon_id", "")),
                        "name": c.get("coupon_name", "未命名券"),
                        "source": "weishenghuo",
                        "value_display": c.get("value_display", ""),
                        "expires": c.get("end_time", ""),
                    })
        except Exception as e:
            logger.warning("微生活券查询失败", error=str(e))

    # 2) 屯象服务券模板
    try:
        stmt = select(ServiceVoucherTemplate).where(
            ServiceVoucherTemplate.brand_id == brand_id,
            ServiceVoucherTemplate.is_active.is_(True),
        )
        result = await db.execute(stmt)
        templates = result.scalars().all()
        for t in templates:
            coupons.append({
                "id": str(t.id),
                "name": t.name,
                "source": "service_voucher",
                "value_display": t.description or t.voucher_type,
                "expires": "",
            })
    except Exception as e:
        logger.warning("服务券模板查询失败", error=str(e))

    return {"coupons": coupons}


@router.post("/{store_id}/distribute-coupon", summary="发券")
async def distribute_coupon(
    store_id: str,
    req: DistributeCouponRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """发放优惠券（微生活券透传 或 屯象服务券）"""
    await validate_store_brand(store_id, current_user)
    distributed_by = current_user.id
    brand_id = current_user.brand_id or ""

    if req.coupon_source == "weishenghuo":
        if not req.phone:
            return {"success": False, "error": "微生活券需要手机号"}
        return await coupon_distribution_service.distribute_weishenghuo_coupon(
            db=db, consumer_id=UUID(req.consumer_id), store_id=store_id,
            brand_id=brand_id, coupon_id=req.coupon_id,
            coupon_name=req.coupon_name or "", coupon_value_fen=req.coupon_value_fen or 0,
            distributed_by=distributed_by, phone=req.phone,
        )
    elif req.coupon_source == "service_voucher":
        return await coupon_distribution_service.distribute_service_voucher(
            db=db, template_id=UUID(req.coupon_id),
            consumer_id=UUID(req.consumer_id), store_id=store_id,
            brand_id=brand_id, distributed_by=distributed_by,
        )
    else:
        return {"success": False, "error": f"未知券来源: {req.coupon_source}"}


@router.post("/{store_id}/confirm-service-voucher/{voucher_id}", summary="确认服务券核销")
async def confirm_service_voucher(
    store_id: str,
    voucher_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """员工确认服务券已送达"""
    await validate_store_brand(store_id, current_user)
    confirmed_by = current_user.id
    return await coupon_distribution_service.confirm_service_voucher(
        db=db, voucher_id=UUID(voucher_id), confirmed_by=confirmed_by,
    )


@router.get("/{store_id}/coupon-roi", summary="发券ROI查询")
async def query_coupon_roi(
    store_id: str,
    start_date: str = Query(..., description="开始日期 YYYY-MM-DD"),
    end_date: str = Query(..., description="结束日期 YYYY-MM-DD"),
    staff_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查询发券 ROI 汇总 + 日趋势"""
    await validate_store_brand(store_id, current_user)
    from datetime import date as _date
    sd = _date.fromisoformat(start_date)
    ed = _date.fromisoformat(end_date)
    sid = UUID(staff_id) if staff_id else None
    return await coupon_roi_service.query_roi(
        db=db, store_id=store_id, brand_id=current_user.brand_id or "",
        start_date=sd, end_date=ed, staff_id=sid,
    )


@router.get("/{store_id}/coupon-roi/leaderboard", summary="发券员工排行榜")
async def coupon_staff_leaderboard(
    store_id: str,
    start_date: str = Query(..., description="开始日期 YYYY-MM-DD"),
    end_date: str = Query(..., description="结束日期 YYYY-MM-DD"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """员工发券效果排行"""
    await validate_store_brand(store_id, current_user)
    from datetime import date as _date
    sd = _date.fromisoformat(start_date)
    ed = _date.fromisoformat(end_date)
    return {
        "leaderboard": await coupon_roi_service.staff_leaderboard(
            db=db, store_id=store_id, brand_id=current_user.brand_id or "",
            start_date=sd, end_date=ed,
        )
    }
