"""
预订单/锁位单 API — P1 补齐（易订PRO 脑图"预订单/锁位单"能力）

生成预订确认凭证：
- 预订单（含客户信息、桌台、时间、预排菜）
- 锁位单（宴会场地锁定确认）
- 支持分享链接 + JSON数据（前端渲染PDF/图片）
"""

import hashlib
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.reservation import Reservation, ReservationStatus
from ..models.reservation_pre_order import PreOrderStatus, ReservationPreOrder
from ..models.user import User

router = APIRouter()


@router.get("/api/v1/reservations/{reservation_id}/receipt")
async def generate_receipt(
    reservation_id: str,
    receipt_type: str = Query("reservation", description="单据类型: reservation(预订单) / lock(锁位单)"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    生成预订单/锁位单数据（前端可渲染为PDF/图片/H5分享页）。

    返回完整的预订信息 + 预排菜清单 + 分享token。
    """
    result = await session.execute(select(Reservation).where(Reservation.id == reservation_id))
    r = result.scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="预订不存在")

    # 生成短链token（基于reservation_id的确定性哈希，幂等）
    share_token = hashlib.sha256(f"receipt:{reservation_id}:{r.store_id}".encode()).hexdigest()[:16]

    # 获取预排菜
    pre_order_result = await session.execute(
        select(ReservationPreOrder)
        .where(
            and_(
                ReservationPreOrder.reservation_id == reservation_id,
                ReservationPreOrder.status != PreOrderStatus.CANCELLED,
            )
        )
        .order_by(ReservationPreOrder.sort_order)
    )
    pre_orders = pre_order_result.scalars().all()

    pre_order_items = []
    pre_order_total = 0
    for po in pre_orders:
        pre_order_items.append(
            {
                "dish_name": po.dish_name,
                "quantity": po.quantity,
                "unit_price_yuan": round(po.unit_price / 100, 2),
                "subtotal_yuan": round(po.subtotal / 100, 2),
                "taste_note": po.taste_note,
                "serving_size": po.serving_size,
            }
        )
        pre_order_total += po.subtotal

    # 构建单据数据
    receipt = {
        "receipt_type": receipt_type,
        "receipt_title": "预订确认单" if receipt_type == "reservation" else "场地锁位单",
        "receipt_number": f"RCT-{reservation_id}",
        "share_token": share_token,
        "generated_at": datetime.utcnow().isoformat(),
        # 预订信息
        "reservation_id": str(r.id),
        "store_id": r.store_id,
        "status": r.status.value if hasattr(r.status, "value") else str(r.status),
        # 客户信息
        "customer_name": r.customer_name,
        "customer_phone": _mask_phone(r.customer_phone),
        "party_size": r.party_size,
        # 时间地点
        "reservation_date": r.reservation_date.isoformat() if r.reservation_date else None,
        "reservation_time": r.reservation_time.strftime("%H:%M") if r.reservation_time else None,
        "table_number": r.table_number,
        "room_name": r.room_name,
        # 类型
        "reservation_type": r.reservation_type.value if hasattr(r.reservation_type, "value") else str(r.reservation_type),
        # 特殊需求
        "special_requests": r.special_requests,
        "dietary_restrictions": r.dietary_restrictions,
        # 金额
        "estimated_budget_yuan": round(r.estimated_budget / 100, 2) if r.estimated_budget else None,
        "deposit_paid_yuan": round(r.deposit_paid / 100, 2) if r.deposit_paid else None,
        # 预排菜
        "pre_order_items": pre_order_items,
        "pre_order_total_yuan": round(pre_order_total / 100, 2),
        # 备注
        "notes": r.notes,
    }

    # 锁位单额外信息
    if receipt_type == "lock":
        receipt["lock_info"] = {
            "room_locked_at": r.room_locked_at.isoformat() if r.room_locked_at else None,
            "signed_at": r.signed_at.isoformat() if r.signed_at else None,
            "banquet_stage": r.banquet_stage,
            "banquet_details": r.banquet_details,
        }

    return receipt


def _mask_phone(phone: str) -> str:
    """手机号脱敏：138****0001"""
    if phone and len(phone) >= 7:
        return phone[:3] + "****" + phone[-4:]
    return phone or ""


@router.get("/api/v1/reservations/{reservation_id}/receipt/share-data")
async def get_share_data(
    reservation_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    获取分享用的精简数据（用于微信分享卡片 / 短信链接）。

    仅包含：门店+时间+人数+桌号，不含敏感信息。
    """
    result = await session.execute(select(Reservation).where(Reservation.id == reservation_id))
    r = result.scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="预订不存在")

    share_token = hashlib.sha256(f"receipt:{reservation_id}:{r.store_id}".encode()).hexdigest()[:16]

    return {
        "share_token": share_token,
        "title": f"预订确认 - {r.reservation_date.isoformat()} {r.reservation_time.strftime('%H:%M')}",
        "description": f"{r.party_size}位 · {r.table_number or r.room_name or '待分配'}",
        "reservation_date": r.reservation_date.isoformat(),
        "reservation_time": r.reservation_time.strftime("%H:%M"),
        "party_size": r.party_size,
        "table_number": r.table_number,
        "room_name": r.room_name,
        "status": r.status.value if hasattr(r.status, "value") else str(r.status),
    }
