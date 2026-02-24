"""
POS API Endpoints
POS系统集成API接口
"""
import hashlib
import hmac
import os
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from src.core.database import get_db
from src.core.dependencies import get_current_user
from src.services.pos_service import POSService
from src.models.order import Order, OrderItem, OrderStatus
from src.models.store import Store

router = APIRouter(prefix="/pos", tags=["POS"])


@router.get("/orders")
async def get_orders(
    store_id: str = Query(..., description="门店ID"),
    status: Optional[OrderStatus] = Query(None, description="订单状态"),
    start_date: Optional[datetime] = Query(None, description="开始日期"),
    end_date: Optional[datetime] = Query(None, description="结束日期"),
    limit: int = Query(100, ge=1, le=1000, description="返回数量限制"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    获取POS订单列表

    Args:
        store_id: 门店ID
        status: 订单状态（可选）
        start_date: 开始日期（可选）
        end_date: 结束日期（可选）
        limit: 返回数量限制

    Returns:
        订单列表
    """
    pos_service = POSService()

    # 设置默认日期范围（最近7天）
    if not end_date:
        end_date = datetime.now()
    if not start_date:
        start_date = end_date - timedelta(days=int(os.getenv("POS_DEFAULT_QUERY_DAYS", "7")))

    try:
        orders = await pos_service.get_orders(
            store_id=store_id,
            status=status,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )

        return {
            "success": True,
            "data": orders,
            "count": len(orders),
            "filters": {
                "store_id": store_id,
                "status": status.value if status else None,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取订单失败: {str(e)}")


@router.get("/orders/{order_id}")
async def get_order_detail(
    order_id: str,
    store_id: str = Query(..., description="门店ID"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    获取订单详情

    Args:
        order_id: 订单ID
        store_id: 门店ID

    Returns:
        订单详细信息
    """
    pos_service = POSService()

    try:
        order = await pos_service.get_order_detail(order_id, store_id)

        if not order:
            raise HTTPException(status_code=404, detail="订单不存在")

        return {
            "success": True,
            "data": order,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取订单详情失败: {str(e)}")


@router.get("/inventory")
async def get_inventory(
    store_id: str = Query(..., description="门店ID"),
    low_stock_only: bool = Query(False, description="仅显示低库存商品"),
    category: Optional[str] = Query(None, description="商品分类"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    获取库存信息

    Args:
        store_id: 门店ID
        low_stock_only: 是否仅显示低库存商品
        category: 商品分类（可选）

    Returns:
        库存列表
    """
    pos_service = POSService()

    try:
        inventory = await pos_service.get_inventory(
            store_id=store_id,
            low_stock_only=low_stock_only,
            category=category,
        )

        # 统计库存状态
        total_items = len(inventory)
        low_stock_items = sum(1 for item in inventory if item.get("is_low_stock", False))
        out_of_stock_items = sum(1 for item in inventory if item.get("quantity", 0) == 0)

        return {
            "success": True,
            "data": inventory,
            "summary": {
                "total_items": total_items,
                "low_stock_items": low_stock_items,
                "out_of_stock_items": out_of_stock_items,
            },
            "filters": {
                "store_id": store_id,
                "low_stock_only": low_stock_only,
                "category": category,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取库存失败: {str(e)}")


@router.get("/stores/{store_id}/status")
async def get_store_status(
    store_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    查询门店状态

    Args:
        store_id: 门店ID

    Returns:
        门店状态信息
    """
    pos_service = POSService()

    try:
        status = await pos_service.get_store_status(store_id)

        if not status:
            raise HTTPException(status_code=404, detail="门店不存在")

        return {
            "success": True,
            "data": status,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取门店状态失败: {str(e)}")


@router.get("/sales/summary")
async def get_sales_summary(
    store_id: str = Query(..., description="门店ID"),
    start_date: Optional[datetime] = Query(None, description="开始日期"),
    end_date: Optional[datetime] = Query(None, description="结束日期"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    获取销售汇总

    Args:
        store_id: 门店ID
        start_date: 开始日期（可选，默认今天）
        end_date: 结束日期（可选，默认今天）

    Returns:
        销售汇总数据
    """
    pos_service = POSService()

    # 设置默认日期范围（今天）
    if not end_date:
        end_date = datetime.now()
    if not start_date:
        start_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)

    try:
        summary = await pos_service.get_sales_summary(
            store_id=store_id,
            start_date=start_date,
            end_date=end_date,
        )

        return {
            "success": True,
            "data": summary,
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取销售汇总失败: {str(e)}")


@router.post("/sync")
async def sync_pos_data(
    store_id: str = Query(..., description="门店ID"),
    sync_type: str = Query("all", description="同步类型: all, orders, inventory, products"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    同步POS数据

    Args:
        store_id: 门店ID
        sync_type: 同步类型（all, orders, inventory, products）

    Returns:
        同步结果
    """
    pos_service = POSService()

    try:
        result = await pos_service.sync_data(
            store_id=store_id,
            sync_type=sync_type,
        )

        return {
            "success": True,
            "data": result,
            "message": f"POS数据同步完成: {sync_type}",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"同步POS数据失败: {str(e)}")


@router.get("/health")
async def pos_health_check(
    store_id: str = Query(..., description="门店ID"),
    db: AsyncSession = Depends(get_db),
):
    """
    POS系统健康检查

    Args:
        store_id: 门店ID

    Returns:
        健康状态
    """
    pos_service = POSService()

    try:
        health = await pos_service.health_check(store_id)

        return {
            "success": True,
            "data": health,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }



@router.get("/queue/current")
async def get_current_queue(
    store_id: str = Query(..., description="门店ID"),
    current_user: dict = Depends(get_current_user),
):
    """
    获取当前排队情况（POS集成）

    Args:
        store_id: 门店ID

    Returns:
        当前排队列表和统计
    """
    from ..services.queue_service import queue_service, QueueStatus

    try:
        # 获取等待中的排队
        queues = await queue_service.get_queue_list(
            store_id=store_id,
            status=QueueStatus.WAITING,
            limit=int(os.getenv("POS_QUEUE_LIST_LIMIT", "50")),
        )

        # 获取统计信息
        stats = await queue_service.get_queue_stats(store_id=store_id)

        return {
            "success": True,
            "data": {
                "queues": queues,
                "stats": stats,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取排队情况失败: {str(e)}")


# ── POS Webhook ───────────────────────────────────────────────────────────────

def _verify_signature(body: bytes, secret: str, signature: str) -> bool:
    """Verify HMAC-SHA256 webhook signature from POS system."""
    expected = hmac.new(
        secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


async def _upsert_order(session: AsyncSession, store_id: str, payload: Dict[str, Any]) -> Order:
    """Create or update an Order row from webhook payload."""
    order_id = payload.get("order_id") or payload.get("id")
    if not order_id:
        raise ValueError("payload missing order_id")

    result = await session.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()

    status_raw = payload.get("status", OrderStatus.PENDING.value)
    try:
        status = OrderStatus(status_raw)
    except ValueError:
        status = OrderStatus.PENDING

    if order is None:
        order = Order(
            id=order_id,
            store_id=store_id,
            table_number=payload.get("table_number"),
            customer_name=payload.get("customer_name"),
            customer_phone=payload.get("customer_phone"),
            status=status.value,
            total_amount=int(payload.get("total_amount", 0)),
            discount_amount=int(payload.get("discount_amount", 0)),
            final_amount=int(payload.get("final_amount", payload.get("total_amount", 0))),
            order_time=datetime.fromisoformat(payload["order_time"])
            if payload.get("order_time") else datetime.utcnow(),
            notes=payload.get("notes"),
            order_metadata=payload.get("metadata", {}),
        )
        session.add(order)
    else:
        order.status = status.value
        if payload.get("final_amount"):
            order.final_amount = int(payload["final_amount"])
        if status == OrderStatus.COMPLETED and not order.completed_at:
            order.completed_at = datetime.utcnow()

    await session.flush()
    return order


@router.post("/webhook/{store_id}", status_code=200)
async def pos_webhook(
    store_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_pos_signature: Optional[str] = Header(None, alias="X-POS-Signature"),
    x_pos_system_id: Optional[str] = Header(None, alias="X-POS-System-ID"),
):
    """
    POS实时推送Webhook

    POS系统在订单状态变更时主动推送，替代轮询方式。
    目标延迟: <500ms（从POS事件到企微告警）

    支持的事件类型:
    - order.created / order.updated / order.completed / order.cancelled
    - payment.completed
    - inventory.low_stock

    安全: HMAC-SHA256签名验证（Header: X-POS-Signature: sha256=<hex>）
    系统ID: Header X-POS-System-ID 用于查找签名密钥
    """
    import structlog
    logger = structlog.get_logger()

    body = await request.body()
    payload: Dict[str, Any] = await request.json()
    event_type = payload.get("event_type") or payload.get("type", "unknown")

    # --- signature verification ---
    if x_pos_system_id:
        from src.models.integration import ExternalSystem
        result = await db.execute(
            select(ExternalSystem).where(ExternalSystem.id == x_pos_system_id)
        )
        system = result.scalar_one_or_none()
        if system and x_pos_signature:
            secret = system.webhook_secret or system.api_secret
            if secret and not _verify_signature(body, secret, x_pos_signature):
                logger.warning(
                    "pos_webhook_invalid_signature",
                    store_id=store_id,
                    system_id=x_pos_system_id,
                )
                raise HTTPException(status_code=401, detail="Invalid webhook signature")

    logger.info(
        "pos_webhook_received",
        store_id=store_id,
        event_type=event_type,
        order_id=payload.get("order_id"),
    )

    # --- persist order to DB ---
    if event_type.startswith("order.") and payload.get("order_id"):
        try:
            await _upsert_order(db, store_id, payload)
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error("pos_webhook_order_upsert_failed", error=str(e), store_id=store_id)

    # --- persist POS transaction for payment events ---
    if event_type == "payment.completed" and payload.get("transaction_id"):
        try:
            from src.services.integration_service import integration_service
            await integration_service.create_pos_transaction(
                session=db,
                system_id=x_pos_system_id or "unknown",
                store_id=store_id,
                transaction_data=payload,
            )
        except Exception as e:
            logger.warning("pos_webhook_transaction_persist_failed", error=str(e))

    # --- emit to Neural System (async via Celery) ---
    neural_event_map = {
        "order.created": ("order.created", 8),
        "order.updated": ("order.updated", 5),
        "order.completed": ("order.completed", 7),
        "order.cancelled": ("order.cancelled", 6),
        "payment.completed": ("payment.completed", 7),
        "inventory.low_stock": ("inventory.low_stock", 9),
    }

    if event_type in neural_event_map:
        neural_type, priority = neural_event_map[event_type]
        try:
            from src.services.neural_system import neural_system
            await neural_system.emit_event(
                event_type=neural_type,
                event_source=f"pos_webhook_{x_pos_system_id or store_id}",
                data=payload,
                store_id=store_id,
                priority=priority,
            )
        except Exception as e:
            # Neural emission failure must not block the 200 response
            logger.error("pos_webhook_neural_emit_failed", error=str(e), event_type=event_type)

    return {
        "received": True,
        "event_type": event_type,
        "store_id": store_id,
    }


