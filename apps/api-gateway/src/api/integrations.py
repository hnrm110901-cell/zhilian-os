"""
Integration API endpoints
外部系统集成API接口
"""
from fastapi import APIRouter, Depends, HTTPException, Body
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime

from ..models.user import User, UserRole
from ..models.integration import (
    IntegrationType,
    IntegrationStatus,
    SyncStatus,
)
from ..core.dependencies import get_current_active_user, require_role
from ..core.database import get_db
from ..services.integration_service import integration_service
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

logger = structlog.get_logger()
router = APIRouter()


# Request/Response Models
class CreateSystemRequest(BaseModel):
    """创建外部系统请求"""
    name: str
    type: IntegrationType
    provider: str
    store_id: Optional[str] = None
    config: Dict[str, Any]


class UpdateSystemRequest(BaseModel):
    """更新外部系统请求"""
    name: Optional[str] = None
    status: Optional[IntegrationStatus] = None
    config: Optional[Dict[str, Any]] = None
    sync_enabled: Optional[bool] = None
    sync_interval: Optional[int] = None


class POSTransactionRequest(BaseModel):
    """POS交易请求"""
    transaction_id: str
    order_number: Optional[str] = None
    type: str = "sale"
    subtotal: float = 0
    tax: float = 0
    discount: float = 0
    total: float = 0
    payment_method: Optional[str] = None
    items: Optional[List[Dict[str, Any]]] = None
    customer: Optional[Dict[str, Any]] = None
    transaction_time: Optional[str] = None


class SupplierOrderRequest(BaseModel):
    """供应商订单请求"""
    order_number: str
    supplier_id: Optional[str] = None
    supplier_name: Optional[str] = None
    type: str = "purchase"
    status: str = "pending"
    subtotal: float = 0
    tax: float = 0
    shipping: float = 0
    total: float = 0
    items: Optional[List[Dict[str, Any]]] = None
    delivery: Optional[Dict[str, Any]] = None
    order_date: Optional[str] = None
    expected_delivery: Optional[str] = None


class MemberSyncRequest(BaseModel):
    """会员同步请求"""
    member_id: str
    external_id: Optional[str] = None
    phone: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    level: Optional[str] = None
    points: int = 0
    balance: float = 0


# External System Management Endpoints
@router.post("/integrations/systems")
async def create_external_system(
    request: CreateSystemRequest,
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.STORE_MANAGER)),
    session: AsyncSession = Depends(get_db),
):
    """
    创建外部系统配置
    需要管理员或门店经理权限
    """
    system = await integration_service.create_system(
        session=session,
        name=request.name,
        type=request.type,
        provider=request.provider,
        config=request.config,
        created_by=str(current_user.id),
        store_id=request.store_id,
    )

    return system.to_dict()


@router.get("/integrations/systems")
async def get_external_systems(
    type: Optional[IntegrationType] = None,
    store_id: Optional[str] = None,
    status: Optional[IntegrationStatus] = None,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """
    获取外部系统列表
    可按类型、门店、状态筛选
    """
    systems = await integration_service.get_systems(
        session=session,
        type=type,
        store_id=store_id,
        status=status,
    )

    return [system.to_dict() for system in systems]


@router.get("/integrations/systems/{system_id}")
async def get_external_system(
    system_id: str,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """获取外部系统详情"""
    system = await integration_service.get_system(session, system_id)
    if not system:
        raise HTTPException(status_code=404, detail="系统不存在")

    return system.to_dict()


@router.put("/integrations/systems/{system_id}")
async def update_external_system(
    system_id: str,
    request: UpdateSystemRequest,
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.STORE_MANAGER)),
    session: AsyncSession = Depends(get_db),
):
    """
    更新外部系统配置
    需要管理员或门店经理权限
    """
    update_data = request.dict(exclude_unset=True)
    system = await integration_service.update_system(
        session=session,
        system_id=system_id,
        **update_data,
    )

    if not system:
        raise HTTPException(status_code=404, detail="系统不存在")

    return system.to_dict()


@router.delete("/integrations/systems/{system_id}")
async def delete_external_system(
    system_id: str,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_db),
):
    """
    删除外部系统配置
    需要管理员权限
    """
    success = await integration_service.delete_system(session, system_id)
    if not success:
        raise HTTPException(status_code=404, detail="系统不存在")

    return {"success": True, "message": "系统已删除"}


@router.post("/integrations/systems/{system_id}/test")
async def test_system_connection(
    system_id: str,
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.STORE_MANAGER)),
    session: AsyncSession = Depends(get_db),
):
    """
    测试外部系统连接
    需要管理员或门店经理权限
    """
    result = await integration_service.test_connection(session, system_id)
    return result


# POS Integration Endpoints
@router.post("/integrations/pos/{system_id}/transactions")
async def create_pos_transaction(
    system_id: str,
    request: POSTransactionRequest,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """
    接收POS交易数据
    用于POS系统推送交易记录
    """
    # 验证系统存在
    system = await integration_service.get_system(session, system_id)
    if not system:
        raise HTTPException(status_code=404, detail="系统不存在")

    if system.type != IntegrationType.POS:
        raise HTTPException(status_code=400, detail="系统类型不匹配")

    # 创建交易记录
    transaction = await integration_service.create_pos_transaction(
        session=session,
        system_id=system_id,
        store_id=current_user.store_id or system.store_id,
        transaction_data=request.model_dump(),
    )

    return transaction.to_dict()


@router.get("/integrations/pos/transactions")
async def get_pos_transactions(
    store_id: Optional[str] = None,
    sync_status: Optional[SyncStatus] = None,
    limit: int = 100,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """
    获取POS交易记录
    可按门店、同步状态筛选
    """
    transactions = await integration_service.get_pos_transactions(
        session=session,
        store_id=store_id or current_user.store_id,
        sync_status=sync_status,
        limit=limit,
    )

    return [t.to_dict() for t in transactions]


# Supplier Integration Endpoints
@router.post("/integrations/supplier/{system_id}/orders")
async def create_supplier_order(
    system_id: str,
    request: SupplierOrderRequest,
    current_user: User = Depends(require_role(
        UserRole.ADMIN,
        UserRole.STORE_MANAGER,
        UserRole.WAREHOUSE_MANAGER,
    )),
    session: AsyncSession = Depends(get_db),
):
    """
    创建供应商订单
    需要管理员、门店经理或仓库经理权限
    """
    # 验证系统存在
    system = await integration_service.get_system(session, system_id)
    if not system:
        raise HTTPException(status_code=404, detail="系统不存在")

    if system.type != IntegrationType.SUPPLIER:
        raise HTTPException(status_code=400, detail="系统类型不匹配")

    # 创建订单
    order = await integration_service.create_supplier_order(
        session=session,
        system_id=system_id,
        store_id=current_user.store_id or system.store_id,
        order_data=request.model_dump(),
    )

    return order.to_dict()


@router.get("/integrations/supplier/orders")
async def get_supplier_orders(
    store_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """
    获取供应商订单
    可按门店、状态筛选
    """
    orders = await integration_service.get_supplier_orders(
        session=session,
        store_id=store_id or current_user.store_id,
        status=status,
        limit=limit,
    )

    return [o.to_dict() for o in orders]


# Member Integration Endpoints
@router.post("/integrations/member/{system_id}/sync")
async def sync_member_data(
    system_id: str,
    request: MemberSyncRequest,
    current_user: User = Depends(require_role(
        UserRole.ADMIN,
        UserRole.STORE_MANAGER,
        UserRole.CUSTOMER_MANAGER,
    )),
    session: AsyncSession = Depends(get_db),
):
    """
    同步会员数据
    需要管理员、门店经理或客户经理权限
    """
    # 验证系统存在
    system = await integration_service.get_system(session, system_id)
    if not system:
        raise HTTPException(status_code=404, detail="系统不存在")

    if system.type != IntegrationType.MEMBER:
        raise HTTPException(status_code=400, detail="系统类型不匹配")

    # 同步会员
    member = await integration_service.sync_member(
        session=session,
        system_id=system_id,
        member_data=request.model_dump(),
    )

    return member.to_dict()


# Webhook Endpoints
@router.post("/integrations/webhooks/pos/{system_id}")
async def pos_webhook(
    system_id: str,
    payload: Dict[str, Any] = Body(...),
    session: AsyncSession = Depends(get_db),
):
    """
    POS系统Webhook接收端点
    用于接收POS系统推送的实时数据
    """
    logger.info("收到POS Webhook", system_id=system_id, payload=payload)

    # 验证系统存在
    system = await integration_service.get_system(session, system_id)
    if not system:
        raise HTTPException(status_code=404, detail="系统不存在")

    # 处理webhook数据 - 根据payload类型进行不同处理
    event_type = payload.get("event_type") or payload.get("type")

    if event_type == "order.created":
        # 处理订单创建事件
        logger.info("处理订单创建事件", order_id=payload.get("order_id"))
        # 可以触发Neural System事件
        from ..services.neural_system import neural_system
        await neural_system.emit_event(
            event_type="order.created",
            event_source=f"pos_system_{system_id}",
            data=payload,
            store_id=payload.get("store_id", "default")
        )
    elif event_type == "order.updated":
        # 处理订单更新事件
        logger.info("处理订单更新事件", order_id=payload.get("order_id"))
    elif event_type == "inventory.low":
        # 处理库存预警事件
        logger.info("处理库存预警事件", item=payload.get("item_name"))
    else:
        # 通用处理
        logger.info("处理通用Webhook事件", event_type=event_type)

    return {"success": True, "message": "Webhook已接收并处理", "event_type": event_type}


@router.post("/integrations/webhooks/supplier/{system_id}")
async def supplier_webhook(
    system_id: str,
    payload: Dict[str, Any] = Body(...),
    session: AsyncSession = Depends(get_db),
):
    """
    供应商系统Webhook接收端点
    用于接收供应商系统推送的订单状态更新
    """
    logger.info("收到供应商Webhook", system_id=system_id, payload=payload)

    # 验证系统存在
    system = await integration_service.get_system(session, system_id)
    if not system:
        raise HTTPException(status_code=404, detail="系统不存在")

    # 处理webhook数据 - 更新订单状态
    order_id = payload.get("order_id") or payload.get("external_order_id")
    status = payload.get("status")

    if order_id and status:
        logger.info(
            "更新订单状态",
            order_id=order_id,
            status=status,
            system_id=system_id
        )

        # 触发订单状态更新事件
        from ..services.neural_system import neural_system
        await neural_system.emit_event(
            event_type="order.status_updated",
            event_source=f"supplier_system_{system_id}",
            data={
                "order_id": order_id,
                "status": status,
                "updated_at": payload.get("updated_at"),
                "delivery_time": payload.get("delivery_time"),
                "tracking_number": payload.get("tracking_number"),
            },
            store_id=payload.get("store_id", "default")
        )

        return {
            "success": True,
            "message": "订单状态已更新",
            "order_id": order_id,
            "status": status
        }
    else:
        logger.warning("Webhook数据缺少必要字段", payload=payload)
        return {
            "success": False,
            "message": "缺少order_id或status字段"
        }


# Reservation Integration Endpoints
class ReservationSyncRequest(BaseModel):
    """预订同步请求"""
    reservation_id: str
    external_id: Optional[str] = None
    reservation_number: Optional[str] = None
    customer_name: str
    customer_phone: str
    customer_count: int
    reservation_date: str  # ISO format
    reservation_time: str  # e.g., "18:00-20:00"
    arrival_time: Optional[str] = None
    table_type: Optional[str] = None
    table_number: Optional[str] = None
    area: Optional[str] = None
    status: str = "pending"
    special_requirements: Optional[str] = None
    notes: Optional[str] = None
    deposit_required: bool = False
    deposit_amount: float = 0
    deposit_paid: bool = False
    source: str = "yiding"
    channel: Optional[str] = None


@router.post("/integrations/reservation/{system_id}/sync")
async def sync_reservation(
    system_id: str,
    request: ReservationSyncRequest,
    current_user: User = Depends(require_role(
        UserRole.ADMIN,
        UserRole.STORE_MANAGER,
        UserRole.CUSTOMER_MANAGER,
    )),
    session: AsyncSession = Depends(get_db),
):
    """
    同步预订数据
    需要管理员、门店经理或客户经理权限
    """
    # 验证系统存在
    system = await integration_service.get_system(session, system_id)
    if not system:
        raise HTTPException(status_code=404, detail="系统不存在")

    if system.type != IntegrationType.RESERVATION:
        raise HTTPException(status_code=400, detail="系统类型不匹配")

    # 同步预订
    reservation = await integration_service.sync_reservation(
        session=session,
        system_id=system_id,
        store_id=current_user.store_id or system.store_id,
        reservation_data=request.model_dump(),
    )

    return reservation.to_dict()


@router.get("/integrations/reservation/list")
async def get_reservations(
    store_id: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 100,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """
    获取预订列表
    可按门店、状态、日期范围筛选
    """
    from datetime import datetime

    date_from_dt = datetime.fromisoformat(date_from) if date_from else None
    date_to_dt = datetime.fromisoformat(date_to) if date_to else None

    reservations = await integration_service.get_reservations(
        session=session,
        store_id=store_id or current_user.store_id,
        status=status,
        date_from=date_from_dt,
        date_to=date_to_dt,
        limit=limit,
    )

    return [r.to_dict() for r in reservations]


@router.put("/integrations/reservation/{reservation_id}/status")
async def update_reservation_status(
    reservation_id: str,
    status: str,
    arrival_time: Optional[str] = None,
    table_number: Optional[str] = None,
    current_user: User = Depends(require_role(
        UserRole.ADMIN,
        UserRole.STORE_MANAGER,
        UserRole.FLOOR_MANAGER,
    )),
    session: AsyncSession = Depends(get_db),
):
    """
    更新预订状态
    需要管理员、门店经理或楼面经理权限
    """
    kwargs = {}
    if arrival_time:
        kwargs["arrival_time"] = arrival_time
    if table_number:
        kwargs["table_number"] = table_number

    reservation = await integration_service.update_reservation_status(
        session=session,
        reservation_id=reservation_id,
        status=status,
        **kwargs,
    )

    if not reservation:
        raise HTTPException(status_code=404, detail="预订不存在")

    return reservation.to_dict()


@router.post("/integrations/webhooks/reservation/{system_id}")
async def reservation_webhook(
    system_id: str,
    payload: Dict[str, Any] = Body(...),
    session: AsyncSession = Depends(get_db),
):
    """
    预订系统Webhook接收端点
    用于接收易订等预订系统推送的实时预订数据
    """
    logger.info("收到预订Webhook", system_id=system_id, payload=payload)

    # 验证系统存在
    system = await integration_service.get_system(session, system_id)
    if not system:
        raise HTTPException(status_code=404, detail="系统不存在")

    # 处理webhook数据
    # 易订系统推送格式示例:
    # {
    #   "event": "reservation.created" | "reservation.updated" | "reservation.cancelled",
    #   "data": {
    #     "reservation_id": "...",
    #     "customer_name": "...",
    #     ...
    #   }
    # }

    event = payload.get("event")
    data = payload.get("data", {})

    if event in ["reservation.created", "reservation.updated"]:
        # 同步预订数据
        try:
            reservation = await integration_service.sync_reservation(
                session=session,
                system_id=system_id,
                store_id=system.store_id,
                reservation_data=data,
            )
            logger.info("预订数据同步成功", reservation_id=data.get("reservation_id"))
        except Exception as e:
            logger.error("预订数据同步失败", error=str(e))
            return {"success": False, "error": str(e)}

    elif event == "reservation.cancelled":
        # 更新预订状态为取消
        try:
            reservation = await integration_service.update_reservation_status(
                session=session,
                reservation_id=data.get("reservation_id"),
                status="cancelled",
            )
            logger.info("预订取消成功", reservation_id=data.get("reservation_id"))
        except Exception as e:
            logger.error("预订取消失败", error=str(e))
            return {"success": False, "error": str(e)}

    return {"success": True, "message": "Webhook已接收并处理"}


# Sync Log Endpoints
@router.get("/integrations/sync-logs")
async def get_sync_logs(
    system_id: Optional[str] = None,
    sync_type: Optional[str] = None,
    limit: int = 50,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """
    获取同步日志
    可按系统、同步类型筛选
    """
    logs = await integration_service.get_sync_logs(
        session=session,
        system_id=system_id,
        sync_type=sync_type,
        limit=limit,
    )

    return [log.to_dict() for log in logs]