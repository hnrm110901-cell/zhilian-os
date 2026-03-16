"""
全链路闭环 API — 暴露 lifecycle_bridge 能力为 REST 端点

供前端/管理端调用：
- 客户360生命周期视图（老客弹屏）
- 手动触发宴会采购桥接
- 手动触发订单→CDP闭环
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from src.core.database import get_db
from src.core.dependencies import get_current_user
from src.services.lifecycle_bridge import (
    get_customer_lifecycle_view,
    on_order_completed,
    prepare_order_from_reservation,
    trigger_procurement_from_beo,
)

router = APIRouter(prefix="/api/v1/lifecycle", tags=["lifecycle"])


# ── 客户360生命周期视图 ──────────────────────────────────


@router.get("/customer-view")
async def customer_lifecycle_view(
    phone: str = Query(..., description="客户手机号"),
    store_id: str = Query(..., description="门店ID"),
    current_user: dict = Depends(get_current_user),
):
    """
    客户全生命周期视图 — 一次性返回客户在预订/订单/CDP/旅程四大系统中的全部状态。

    用途：老客到店弹屏、客户360画像、销售跟单参考。
    """
    async for session in get_db():
        view = await get_customer_lifecycle_view(session, phone, store_id)
        return view


# ── 手动触发桥接 ──────────────────────────────────────────


class ManualOrderBridgeRequest(BaseModel):
    reservation_id: str


@router.post("/bridge/reservation-to-order")
async def manual_reservation_to_order(
    body: ManualOrderBridgeRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    手动触发预订→订单桥接（Bridge 1）。

    通常在到店签到时自动触发，此端点用于补偿/重试。
    """
    async for session in get_db():
        try:
            result = await prepare_order_from_reservation(session, body.reservation_id)
            await session.commit()
            return result
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))


class ManualCDPBridgeRequest(BaseModel):
    order_id: str


@router.post("/bridge/order-to-cdp")
async def manual_order_to_cdp(
    body: ManualCDPBridgeRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    手动触发订单→CDP闭环（Bridge 3）。

    通常在订单完成时自动触发，此端点用于补偿/重试/批量回补。
    """
    async for session in get_db():
        try:
            result = await on_order_completed(session, body.order_id)
            await session.commit()
            return result
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
