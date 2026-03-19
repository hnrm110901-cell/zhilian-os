"""
POS API Endpoints
POS系统集成API接口
"""

import hashlib
import hmac
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.core.dependencies import get_current_user
from src.models.order import Order, OrderItem, OrderStatus
from src.models.store import Store
from src.services.pos_service import POSService

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
        # 从 external_systems 表获取该门店的 POS 适配器和品智 ognid
        adapter, pinzhi_ognid = await pos_service.get_adapter_for_store(store_id, db)
        if not pinzhi_ognid:
            raise HTTPException(status_code=400, detail=f"门店 {store_id} 未配置品智 ognid")

        # 品智 orderNew.do 只支持单日查询（businessDate），需逐日循环
        all_orders: List[dict] = []
        current = start_date.date() if hasattr(start_date, 'date') else start_date
        end_d = end_date.date() if hasattr(end_date, 'date') else end_date
        while current <= end_d:
            orders = await adapter.query_orders(
                ognid=pinzhi_ognid,
                business_date=current.strftime("%Y-%m-%d"),
                page_size=min(limit, 200),
            )
            all_orders.extend(orders)
            current += timedelta(days=1)

        # 按状态过滤（品智接口不支持状态参数，需在应用层过滤）
        if status:
            all_orders = [o for o in all_orders if o.get("billStatus") == status.value]

        return {
            "success": True,
            "data": all_orders,
            "count": len(all_orders),
            "filters": {
                "store_id": store_id,
                "status": status.value if status else None,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
        }
    except HTTPException:
        raise
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
    获取订单详情 — 从本地 DB 查询（POS Webhook 已落库的订单）
    """
    result = await db.execute(select(Order).where(Order.id == order_id, Order.store_id == store_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    return {"success": True, "data": {
        "id": str(order.id), "store_id": order.store_id,
        "status": order.status, "total_amount": order.total_amount,
        "final_amount": order.final_amount, "order_time": str(order.order_time),
        "table_number": order.table_number,
    }}


@router.get("/stores/{store_id}/status")
async def get_store_status(
    store_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    查询门店 POS 连接状态 — 从 external_systems 读取同步状态
    """
    from sqlalchemy import select as sa_select
    from src.models.integration import ExternalSystem

    result = await db.execute(
        sa_select(ExternalSystem).where(
            ExternalSystem.store_id == store_id,
            ExternalSystem.type == "pos",
        )
    )
    system = result.scalar_one_or_none()
    if not system:
        raise HTTPException(status_code=404, detail="门店未配置 POS 系统")

    return {"success": True, "data": {
        "store_id": store_id,
        "provider": system.provider,
        "status": system.status,
        "last_sync_at": str(system.last_sync_at) if system.last_sync_at else None,
        "last_sync_status": system.last_sync_status,
        "sync_enabled": system.sync_enabled,
    }}


@router.get("/sales/summary")
async def get_sales_summary(
    store_id: str = Query(..., description="门店ID"),
    date: Optional[str] = Query(None, description="营业日（yyyy-MM-dd），默认昨天"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    获取销售汇总 — 调用品智 queryOrderSummary + queryOgnDailyBizData
    """
    if not date:
        date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    pos_service = POSService()
    try:
        adapter, pinzhi_ognid = await pos_service.get_adapter_for_store(store_id, db)
        if not pinzhi_ognid:
            raise HTTPException(status_code=400, detail=f"门店 {store_id} 未配置品智 ognid")

        summary = await adapter.query_order_summary(pinzhi_ognid, date)
        biz_data = await adapter.query_ogn_daily_biz_data(date, ognid=pinzhi_ognid)

        return {
            "success": True,
            "data": {
                "summary": summary,
                "biz_data": biz_data,
            },
            "date": date,
            "store_id": store_id,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取销售汇总失败: {str(e)}")


@router.get("/health")
async def pos_health_check(
    store_id: str = Query(..., description="门店ID"),
    db: AsyncSession = Depends(get_db),
):
    """
    POS系统健康检查 — 调用品智 run_all_checks 检测全部接口连通性
    """
    pos_service = POSService()

    try:
        adapter, pinzhi_ognid = await pos_service.get_adapter_for_store(store_id, db)
        results = await adapter.run_all_checks(
            business_date=(datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"),
            ognid=pinzhi_ognid,
        )
        ok_count = sum(1 for r in results if r["ok"])
        return {
            "success": True,
            "data": {
                "store_id": store_id,
                "pinzhi_ognid": pinzhi_ognid,
                "checks": results,
                "summary": f"{ok_count}/{len(results)} 接口正常",
            },
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
    from ..services.queue_service import QueueStatus, queue_service

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
            order_time=datetime.fromisoformat(payload["order_time"]) if payload.get("order_time") else datetime.utcnow(),
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

        result = await db.execute(select(ExternalSystem).where(ExternalSystem.id == x_pos_system_id))
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
