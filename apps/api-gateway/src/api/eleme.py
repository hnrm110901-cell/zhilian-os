"""
饿了么集成 API 路由
提供 Webhook 回调、订单管理、菜单同步、门店管理、配送追踪等端点
"""
from datetime import datetime
from typing import Any, Dict, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, func, desc

from src.core.database import get_db_session
from src.core.dependencies import require_role
from src.models.user import UserRole
from src.services.eleme_service import eleme_service

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/eleme", tags=["eleme"])


# ── Pydantic 请求模型 ────────────────────────────────────────────

class SyncOrdersRequest(BaseModel):
    """手动同步订单请求"""
    brand_id: str
    store_id: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None


class CancelRequest(BaseModel):
    """取消订单请求"""
    reason_code: int = 1
    reason: str = "商家取消"


class UpdateStockRequest(BaseModel):
    """更新库存请求"""
    stock: int = Field(..., ge=0, description="库存数量")


class ToggleFoodRequest(BaseModel):
    """上下架请求"""
    on_sale: bool


class ShopStatusRequest(BaseModel):
    """门店状态切换请求"""
    status: int = Field(..., ge=0, le=1, description="1=营业中, 0=休息中")
    shop_id: Optional[str] = None


class SyncMenuRequest(BaseModel):
    """手动同步菜单请求"""
    brand_id: str
    store_id: Optional[str] = None


# ── Webhook 端点（无需鉴权，靠签名验证） ─────────────────────────

@router.post("/webhook")
async def receive_webhook(request: Request):
    """
    接收饿了么 Webhook 推送回调

    事件类型: order.created, order.paid, order.cancelled,
             order.refunded, delivery.status_changed, food.stock_warning
    """
    body = await request.body()
    payload = await request.json()

    event_type = payload.get("event_type", "")
    timestamp = payload.get("timestamp", "")
    signature = payload.get("signature", "")
    data = payload.get("data", {})

    # 签名验证
    try:
        await eleme_service.handle_webhook(body, signature, timestamp)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    # 处理事件
    async with get_db_session() as session:
        result = await eleme_service.handle_webhook_event(session, event_type, data)

    return {"success": True, **result}


# ── 订单端点 ──────────────────────────────────────────────────────

@router.post("/orders/sync")
async def sync_orders(
    body: SyncOrdersRequest,
    _user=Depends(require_role(UserRole.ADMIN)),
):
    """手动触发饿了么订单同步"""
    async with get_db_session() as session:
        result = await eleme_service.sync_orders(
            session,
            body.brand_id,
            store_id=body.store_id,
            start_time=body.start_time,
            end_time=body.end_time,
        )
    return {"success": True, **result}


@router.get("/orders")
async def list_orders(
    brand_id: str = Query(..., description="品牌ID"),
    store_id: Optional[str] = Query(None, description="门店ID"),
    status: Optional[str] = Query(None, description="订单状态"),
    date: Optional[str] = Query(None, description="日期 YYYY-MM-DD"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _user=Depends(require_role(UserRole.ADMIN)),
):
    """查询已同步的饿了么订单（分页）"""
    from src.models.order import Order

    async with get_db_session() as session:
        query = select(Order).where(
            Order.sales_channel == "eleme"
        )

        if store_id:
            query = query.where(Order.store_id == store_id)
        if status:
            query = query.where(Order.status == status)
        if date:
            try:
                dt = datetime.fromisoformat(date)
                from datetime import timedelta
                query = query.where(
                    Order.order_time >= dt,
                    Order.order_time < dt + timedelta(days=1),
                )
            except ValueError:
                pass

        # 总数
        count_q = select(func.count()).select_from(query.subquery())
        total = (await session.execute(count_q)).scalar() or 0

        # 分页
        query = query.order_by(desc(Order.order_time))
        query = query.offset((page - 1) * page_size).limit(page_size)
        rows = (await session.execute(query)).scalars().all()

        orders = []
        for o in rows:
            meta = o.order_metadata or {}
            orders.append({
                "id": str(o.id),
                "store_id": o.store_id,
                "status": o.status,
                "total_amount": o.total_amount,
                "discount_amount": o.discount_amount,
                "final_amount": o.final_amount,
                "order_time": o.order_time.isoformat() if o.order_time else None,
                "notes": o.notes,
                "items_count": meta.get("items_count", 0),
                "metadata": meta,
            })

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "orders": orders,
    }


@router.post("/orders/{order_id}/confirm")
async def confirm_order(
    order_id: str,
    brand_id: str = Query(..., description="品牌ID"),
    _user=Depends(require_role(UserRole.ADMIN)),
):
    """确认饿了么订单"""
    try:
        result = await eleme_service.confirm_order(brand_id, order_id)

        # 更新本地订单状态
        from src.models.order import Order

        async with get_db_session() as session:
            row = await session.execute(
                select(Order).where(Order.id == f"ELEME_{order_id}")
            )
            order = row.scalar_one_or_none()
            if order:
                order.status = "confirmed"
                await session.commit()

        return {"success": True, "order_id": order_id, "result": result}
    except Exception as e:
        logger.error("饿了么确认订单失败", order_id=order_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/orders/{order_id}/cancel")
async def cancel_order(
    order_id: str,
    body: CancelRequest,
    brand_id: str = Query(..., description="品牌ID"),
    _user=Depends(require_role(UserRole.ADMIN)),
):
    """取消饿了么订单"""
    try:
        result = await eleme_service.cancel_order(
            brand_id, order_id, body.reason_code, body.reason
        )

        from src.models.order import Order

        async with get_db_session() as session:
            row = await session.execute(
                select(Order).where(Order.id == f"ELEME_{order_id}")
            )
            order = row.scalar_one_or_none()
            if order:
                order.status = "cancelled"
                await session.commit()

        return {"success": True, "order_id": order_id, "result": result}
    except Exception as e:
        logger.error("饿了么取消订单失败", order_id=order_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ── 菜单端点 ──────────────────────────────────────────────────────

@router.get("/menu")
async def get_menu(
    brand_id: str = Query(..., description="品牌ID"),
    store_id: Optional[str] = Query(None, description="门店ID"),
    _user=Depends(require_role(UserRole.ADMIN)),
):
    """从饿了么获取菜单"""
    try:
        result = await eleme_service.sync_menu(brand_id, store_id)
        return {"success": True, **result}
    except Exception as e:
        logger.error("饿了么获取菜单失败", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/menu/{food_id}/stock")
async def update_stock(
    food_id: str,
    body: UpdateStockRequest,
    brand_id: str = Query(..., description="品牌ID"),
    _user=Depends(require_role(UserRole.ADMIN)),
):
    """更新商品库存"""
    try:
        result = await eleme_service.update_stock(brand_id, food_id, body.stock)
        return {"success": True, "food_id": food_id, "result": result}
    except Exception as e:
        logger.error("饿了么更新库存失败", food_id=food_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/menu/{food_id}/toggle")
async def toggle_food(
    food_id: str,
    body: ToggleFoodRequest,
    brand_id: str = Query(..., description="品牌ID"),
    _user=Depends(require_role(UserRole.ADMIN)),
):
    """商品上架/下架"""
    try:
        result = await eleme_service.toggle_food(brand_id, food_id, body.on_sale)
        return {"success": True, "food_id": food_id, "on_sale": body.on_sale, "result": result}
    except Exception as e:
        logger.error("饿了么商品切换失败", food_id=food_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ── 门店端点 ──────────────────────────────────────────────────────

@router.get("/shop")
async def get_shop(
    brand_id: str = Query(..., description="品牌ID"),
    shop_id: Optional[str] = Query(None, description="门店ID"),
    _user=Depends(require_role(UserRole.ADMIN)),
):
    """查询饿了么门店信息"""
    try:
        info = await eleme_service.get_shop_info(brand_id, shop_id)
        return {"success": True, "shop": info}
    except Exception as e:
        logger.error("饿了么获取门店信息失败", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/shop/status")
async def toggle_shop_status(
    body: ShopStatusRequest,
    brand_id: str = Query(..., description="品牌ID"),
    _user=Depends(require_role(UserRole.ADMIN)),
):
    """切换门店营业状态"""
    try:
        result = await eleme_service.toggle_shop_status(
            brand_id, body.status, body.shop_id
        )
        return {"success": True, "status": body.status, "result": result}
    except Exception as e:
        logger.error("饿了么门店状态切换失败", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ── 配送端点 ──────────────────────────────────────────────────────

@router.get("/delivery/{order_id}")
async def get_delivery_status(
    order_id: str,
    brand_id: str = Query(..., description="品牌ID"),
    _user=Depends(require_role(UserRole.ADMIN)),
):
    """查询配送状态"""
    try:
        info = await eleme_service.get_delivery_status(brand_id, order_id)
        return {"success": True, "delivery": info}
    except Exception as e:
        logger.error("饿了么配送查询失败", order_id=order_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
