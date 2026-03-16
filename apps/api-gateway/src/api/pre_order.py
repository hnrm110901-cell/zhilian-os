"""
预排菜 API — P0 补齐（易订PRO 1.10 菜品管理 + 脑图"预排菜"能力）

支持预订关联菜品：
- 为预订添加/修改/删除预排菜
- 确认预排菜（锁定不可更改）
- 查看预订的菜品清单和预估消费
- 厨房视图：查看当日需要备料的预排菜汇总
"""

import uuid
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.dish import Dish
from ..models.reservation import Reservation, ReservationStatus
from ..models.reservation_pre_order import PreOrderStatus, ReservationPreOrder
from ..models.user import User

router = APIRouter()


# ── Request / Response Models ─────────────────────────────────────


class AddPreOrderItem(BaseModel):
    dish_id: Optional[str] = None  # 可选，若无则手写菜名
    dish_name: str
    unit_price: int  # 单价（分）
    quantity: int = 1
    taste_note: Optional[str] = None  # 口味：少盐/加辣
    serving_size: Optional[str] = None  # 规格：大份/小份


class BatchAddPreOrderRequest(BaseModel):
    reservation_id: str
    store_id: str
    items: List[AddPreOrderItem]


class UpdatePreOrderItemRequest(BaseModel):
    quantity: Optional[int] = None
    taste_note: Optional[str] = None
    serving_size: Optional[str] = None


def _to_dict(item: ReservationPreOrder) -> Dict[str, Any]:
    return {
        "id": str(item.id),
        "reservation_id": item.reservation_id,
        "dish_id": str(item.dish_id) if item.dish_id else None,
        "dish_name": item.dish_name,
        "dish_code": item.dish_code,
        "unit_price": item.unit_price,
        "quantity": item.quantity,
        "subtotal": item.subtotal,
        "taste_note": item.taste_note,
        "serving_size": item.serving_size,
        "status": item.status.value if hasattr(item.status, "value") else str(item.status),
        "is_locked": item.is_locked,
        "sort_order": item.sort_order,
    }


# ── 查看预排菜 ───────────────────────────────────────────────────


@router.get("/api/v1/pre-orders/{reservation_id}")
async def get_pre_orders(
    reservation_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """查看预订的预排菜列表"""
    result = await session.execute(
        select(ReservationPreOrder)
        .where(
            and_(
                ReservationPreOrder.reservation_id == reservation_id,
                ReservationPreOrder.status != PreOrderStatus.CANCELLED,
            )
        )
        .order_by(ReservationPreOrder.sort_order)
    )
    items = result.scalars().all()

    total_amount = sum(i.subtotal for i in items)
    return {
        "reservation_id": reservation_id,
        "items": [_to_dict(i) for i in items],
        "total_items": len(items),
        "total_amount": total_amount,
        "total_amount_yuan": round(total_amount / 100, 2),
    }


# ── 添加预排菜 ───────────────────────────────────────────────────


@router.post("/api/v1/pre-orders", status_code=201)
async def add_pre_orders(
    req: BatchAddPreOrderRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """批量添加预排菜"""
    # 验证预订存在
    res_result = await session.execute(select(Reservation).where(Reservation.id == req.reservation_id))
    reservation = res_result.scalar_one_or_none()
    if not reservation:
        raise HTTPException(status_code=404, detail="预订不存在")

    # 检查预订是否已完成/取消
    if reservation.status in (ReservationStatus.COMPLETED, ReservationStatus.CANCELLED, ReservationStatus.NO_SHOW):
        raise HTTPException(status_code=400, detail=f"预订状态为{reservation.status.value}，不可添加预排菜")

    # 检查是否有已锁定的预排菜
    locked_result = await session.execute(
        select(func.count()).where(
            and_(
                ReservationPreOrder.reservation_id == req.reservation_id,
                ReservationPreOrder.is_locked == True,
            )
        )
    )
    if locked_result.scalar() > 0:
        raise HTTPException(status_code=400, detail="预排菜已锁定确认，不可新增")

    # 获取现有最大排序号
    max_sort_result = await session.execute(
        select(func.max(ReservationPreOrder.sort_order)).where(ReservationPreOrder.reservation_id == req.reservation_id)
    )
    max_sort = max_sort_result.scalar() or 0

    created_items = []
    for idx, item in enumerate(req.items):
        # 如有dish_id，补充菜品编码
        dish_code = None
        if item.dish_id:
            dish_result = await session.execute(select(Dish).where(Dish.id == item.dish_id))
            dish = dish_result.scalar_one_or_none()
            if dish:
                dish_code = dish.code

        pre_order = ReservationPreOrder(
            id=uuid.uuid4(),
            reservation_id=req.reservation_id,
            store_id=req.store_id,
            dish_id=item.dish_id,
            dish_name=item.dish_name,
            dish_code=dish_code,
            unit_price=item.unit_price,
            quantity=item.quantity,
            subtotal=item.unit_price * item.quantity,
            taste_note=item.taste_note,
            serving_size=item.serving_size,
            status=PreOrderStatus.DRAFT,
            sort_order=max_sort + idx + 1,
        )
        session.add(pre_order)
        created_items.append(pre_order)

    await session.commit()
    for i in created_items:
        await session.refresh(i)

    return {
        "reservation_id": req.reservation_id,
        "added": len(created_items),
        "items": [_to_dict(i) for i in created_items],
    }


# ── 修改预排菜 ───────────────────────────────────────────────────


@router.patch("/api/v1/pre-orders/items/{item_id}")
async def update_pre_order_item(
    item_id: str,
    req: UpdatePreOrderItemRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """修改预排菜项（数量/口味/规格）"""
    result = await session.execute(select(ReservationPreOrder).where(ReservationPreOrder.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="预排菜项不存在")

    if item.is_locked:
        raise HTTPException(status_code=400, detail="预排菜已锁定，不可修改")

    if req.quantity is not None:
        item.quantity = req.quantity
        item.subtotal = item.unit_price * req.quantity
    if req.taste_note is not None:
        item.taste_note = req.taste_note
    if req.serving_size is not None:
        item.serving_size = req.serving_size

    await session.commit()
    await session.refresh(item)
    return _to_dict(item)


# ── 删除预排菜 ───────────────────────────────────────────────────


@router.delete("/api/v1/pre-orders/items/{item_id}")
async def delete_pre_order_item(
    item_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """删除预排菜项"""
    result = await session.execute(select(ReservationPreOrder).where(ReservationPreOrder.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="预排菜项不存在")

    if item.is_locked:
        raise HTTPException(status_code=400, detail="预排菜已锁定，不可删除")

    item.status = PreOrderStatus.CANCELLED
    await session.commit()
    return {"message": f"已删除预排菜【{item.dish_name}】"}


# ── 确认/锁定预排菜 ──────────────────────────────────────────────


@router.post("/api/v1/pre-orders/{reservation_id}/confirm")
async def confirm_pre_orders(
    reservation_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """确认并锁定预排菜（确认后不可更改）"""
    result = await session.execute(
        select(ReservationPreOrder).where(
            and_(
                ReservationPreOrder.reservation_id == reservation_id,
                ReservationPreOrder.status == PreOrderStatus.DRAFT,
            )
        )
    )
    items = result.scalars().all()

    if not items:
        raise HTTPException(status_code=400, detail="没有待确认的预排菜")

    for item in items:
        item.status = PreOrderStatus.CONFIRMED
        item.is_locked = True

    await session.commit()

    total_amount = sum(i.subtotal for i in items)
    return {
        "reservation_id": reservation_id,
        "confirmed_items": len(items),
        "total_amount": total_amount,
        "total_amount_yuan": round(total_amount / 100, 2),
        "message": f"已确认{len(items)}项预排菜，共¥{total_amount / 100:.2f}",
    }


# ── 厨房备料视图 ─────────────────────────────────────────────────


@router.get("/api/v1/pre-orders/kitchen-prep/{store_id}")
async def get_kitchen_prep_summary(
    store_id: str,
    prep_date: date = Query(..., description="备料日期"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    厨房备料汇总 — 按菜品聚合当日所有已确认预排菜的总量。

    用于厨房提前准备食材、半成品。
    """
    # 查找当日已确认预订的预排菜
    query = (
        select(
            ReservationPreOrder.dish_name,
            ReservationPreOrder.dish_code,
            ReservationPreOrder.serving_size,
            func.sum(ReservationPreOrder.quantity).label("total_qty"),
            func.count(ReservationPreOrder.reservation_id.distinct()).label("order_count"),
        )
        .join(Reservation, Reservation.id == ReservationPreOrder.reservation_id)
        .where(
            and_(
                ReservationPreOrder.store_id == store_id,
                Reservation.reservation_date == prep_date,
                ReservationPreOrder.status.in_(
                    [
                        PreOrderStatus.CONFIRMED,
                        PreOrderStatus.PREPARING,
                    ]
                ),
                Reservation.status.in_(
                    [
                        ReservationStatus.PENDING,
                        ReservationStatus.CONFIRMED,
                        ReservationStatus.ARRIVED,
                        ReservationStatus.SEATED,
                    ]
                ),
            )
        )
        .group_by(
            ReservationPreOrder.dish_name,
            ReservationPreOrder.dish_code,
            ReservationPreOrder.serving_size,
        )
        .order_by(func.sum(ReservationPreOrder.quantity).desc())
    )

    result = await session.execute(query)
    rows = result.all()

    dishes = []
    for r in rows:
        dishes.append(
            {
                "dish_name": r.dish_name,
                "dish_code": r.dish_code,
                "serving_size": r.serving_size,
                "total_quantity": int(r.total_qty),
                "order_count": int(r.order_count),
            }
        )

    return {
        "store_id": store_id,
        "prep_date": prep_date.isoformat(),
        "dishes": dishes,
        "total_dish_types": len(dishes),
        "total_portions": sum(d["total_quantity"] for d in dishes),
    }
