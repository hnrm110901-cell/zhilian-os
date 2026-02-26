"""
Orders API - 订单管理REST接口
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime, date

from src.core.dependencies import get_current_user
from fastapi import Depends
from src.services.order_service import OrderService

router = APIRouter(prefix="/orders", tags=["orders"])


class OrderItemIn(BaseModel):
    item_id: str
    item_name: str
    quantity: int
    unit_price: int  # 分
    notes: Optional[str] = None
    customizations: Optional[Dict[str, Any]] = {}


class CreateOrderRequest(BaseModel):
    store_id: str
    table_number: str
    items: List[OrderItemIn]
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    notes: Optional[str] = None
    discount_amount: Optional[int] = 0


class UpdateStatusRequest(BaseModel):
    status: str
    notes: Optional[str] = None


class AddItemsRequest(BaseModel):
    items: List[OrderItemIn]


class CancelOrderRequest(BaseModel):
    reason: Optional[str] = None


@router.get("/today-overview")
async def today_overview(
    store_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    """今日订单概览"""
    svc = OrderService(store_id)
    today = date.today().isoformat()
    stats = await svc.get_order_statistics(start_date=today, end_date=today)
    orders = await svc.list_orders(start_date=today, end_date=today, limit=200)

    active = [o for o in orders if o["status"] in ("pending", "confirmed", "preparing", "ready", "served")]
    return {
        "stats": stats,
        "active_orders": active,
        "active_count": len(active),
    }


@router.get("/statistics")
async def get_statistics(
    store_id: str = Query(...),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """订单统计"""
    svc = OrderService(store_id)
    stats = await svc.get_order_statistics(start_date=start_date, end_date=end_date)
    return stats


@router.get("")
async def list_orders(
    store_id: str = Query(...),
    status: Optional[str] = Query(None),
    table_number: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    current_user: dict = Depends(get_current_user),
):
    """查询订单列表"""
    svc = OrderService(store_id)
    orders = await svc.list_orders(
        status=status,
        table_number=table_number,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )
    return {"orders": orders, "total": len(orders)}


@router.post("")
async def create_order(
    body: CreateOrderRequest,
    current_user: dict = Depends(get_current_user),
):
    """创建订单"""
    svc = OrderService(body.store_id)
    items = [i.dict() for i in body.items]
    try:
        order = await svc.create_order(
            table_number=body.table_number,
            items=items,
            customer_name=body.customer_name,
            customer_phone=body.customer_phone,
            notes=body.notes,
            discount_amount=body.discount_amount or 0,
        )
        return order
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{order_id}")
async def get_order(
    order_id: str,
    current_user: dict = Depends(get_current_user),
):
    """获取订单详情"""
    svc = OrderService()
    order = await svc.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    return order


@router.patch("/{order_id}/status")
async def update_status(
    order_id: str,
    body: UpdateStatusRequest,
    current_user: dict = Depends(get_current_user),
):
    """更新订单状态"""
    valid = {"pending", "confirmed", "preparing", "ready", "served", "completed", "cancelled"}
    if body.status not in valid:
        raise HTTPException(status_code=400, detail=f"无效状态: {body.status}")
    svc = OrderService()
    try:
        order = await svc.update_order_status(order_id, body.status, body.notes)
        return order
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{order_id}/items")
async def add_items(
    order_id: str,
    body: AddItemsRequest,
    current_user: dict = Depends(get_current_user),
):
    """追加订单菜品"""
    svc = OrderService()
    try:
        order = await svc.add_items(order_id, [i.dict() for i in body.items])
        return order
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{order_id}/cancel")
async def cancel_order(
    order_id: str,
    body: CancelOrderRequest,
    current_user: dict = Depends(get_current_user),
):
    """取消订单"""
    svc = OrderService()
    try:
        order = await svc.cancel_order(order_id, body.reason)
        return order
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
