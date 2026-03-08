"""
Inventory Management API
库存管理API
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
import structlog

from ..core.database import get_db
from ..core.dependencies import get_current_active_user, require_role
from ..models.inventory import InventoryItem, InventoryStatus, TransactionType, InventoryTransaction
from ..models.user import User, UserRole
from ..models.decision_log import DecisionLog, DecisionType, DecisionStatus
from ..repositories import InventoryRepository
from ..services.redis_cache_service import RedisCacheService
from ..services.approval_service import approval_service
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from ..core.clock import now_utc, utcnow_naive

logger = structlog.get_logger()
router = APIRouter()

# Redis Lua 原子扣减脚本
# KEYS[1] = 库存锁定key (inventory:lock:{item_id})
# KEYS[2] = 库存数量key (inventory:qty:{item_id})
# ARGV[1] = 扣减数量
# 返回: 扣减后数量，或 -1 表示库存不足，或 -2 表示key不存在（回退到DB）
_LUA_DEDUCT_STOCK = """
local lock_key = KEYS[1]
local qty_key = KEYS[2]
local deduct = tonumber(ARGV[1])
local current = redis.call('GET', qty_key)
if current == false then
    return -2
end
current = tonumber(current)
if current < deduct then
    return -1
end
local new_qty = current - deduct
redis.call('SET', qty_key, new_qty)
return new_qty
"""

_redis_svc = RedisCacheService()


class CreateInventoryItemRequest(BaseModel):
    id: str
    store_id: str
    name: str
    category: Optional[str] = None
    unit: Optional[str] = None
    current_quantity: float = 0
    min_quantity: float
    max_quantity: Optional[float] = None
    unit_cost: Optional[int] = None


class UpdateInventoryItemRequest(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    unit: Optional[str] = None
    current_quantity: Optional[float] = None
    min_quantity: Optional[float] = None
    max_quantity: Optional[float] = None
    unit_cost: Optional[int] = None
    status: Optional[InventoryStatus] = None


class InventoryTransactionRequest(BaseModel):
    transaction_type: TransactionType
    quantity: float
    notes: Optional[str] = None


class InventoryItemResponse(BaseModel):
    id: str
    store_id: str
    name: str
    category: Optional[str]
    unit: Optional[str]
    current_quantity: float
    min_quantity: float
    max_quantity: Optional[float]
    unit_cost: Optional[int]
    status: Optional[str]


@router.get("/inventory", response_model=List[InventoryItemResponse])
async def list_inventory(
    store_id: str = Query(..., description="门店ID"),
    low_stock_only: bool = Query(False, description="仅显示低库存"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取库存列表"""
    if low_stock_only:
        items = await InventoryRepository.get_low_stock(session, store_id)
    else:
        items = await InventoryRepository.get_by_store(session, store_id)
    return [InventoryItemResponse(
        id=i.id, store_id=i.store_id, name=i.name, category=i.category,
        unit=i.unit, current_quantity=i.current_quantity, min_quantity=i.min_quantity,
        max_quantity=i.max_quantity, unit_cost=i.unit_cost,
        status=i.status.value if hasattr(i.status, "value") else i.status
    ) for i in items]


@router.post("/inventory", response_model=InventoryItemResponse, status_code=201)
async def create_inventory_item(
    req: CreateInventoryItemRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.STORE_MANAGER)),
):
    """创建库存项"""
    item = InventoryItem(
        id=req.id, store_id=req.store_id, name=req.name, category=req.category,
        unit=req.unit, current_quantity=req.current_quantity, min_quantity=req.min_quantity,
        max_quantity=req.max_quantity, unit_cost=req.unit_cost,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    logger.info("inventory_item_created", item_id=item.id)
    return InventoryItemResponse(
        id=item.id, store_id=item.store_id, name=item.name, category=item.category,
        unit=item.unit, current_quantity=item.current_quantity, min_quantity=item.min_quantity,
        max_quantity=item.max_quantity, unit_cost=item.unit_cost,
        status=item.status.value if hasattr(item.status, "value") else item.status
    )


@router.patch("/inventory/{item_id}", response_model=InventoryItemResponse)
async def update_inventory_item(
    item_id: str,
    req: UpdateInventoryItemRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.STORE_MANAGER)),
):
    """更新库存项"""
    result = await session.execute(select(InventoryItem).where(InventoryItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="库存项不存在")
    for field, value in req.model_dump(exclude_none=True).items():
        setattr(item, field, value)
    await session.commit()
    await session.refresh(item)
    return InventoryItemResponse(
        id=item.id, store_id=item.store_id, name=item.name, category=item.category,
        unit=item.unit, current_quantity=item.current_quantity, min_quantity=item.min_quantity,
        max_quantity=item.max_quantity, unit_cost=item.unit_cost,
        status=item.status.value if hasattr(item.status, "value") else item.status
    )


@router.get("/inventory-stats")
async def get_inventory_stats(
    store_id: str = Query(...),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """库存统计：总价值、分类分布、预警汇总"""
    items = await InventoryRepository.get_by_store(session, store_id)
    total_value = sum((i.current_quantity * (i.unit_cost or 0)) for i in items)
    category_dist: dict = {}
    status_dist: dict = {"normal": 0, "low": 0, "critical": 0, "out_of_stock": 0}
    for i in items:
        cat = i.category or "其他"
        category_dist[cat] = category_dist.get(cat, 0) + 1
        s = i.status.value if hasattr(i.status, "value") else (i.status or "normal")
        status_dist[s] = status_dist.get(s, 0) + 1
    return {
        "total_items": len(items),
        "total_value": total_value,  # 分
        "category_distribution": category_dist,
        "status_distribution": status_dist,
        "alert_items": [
            {"id": i.id, "name": i.name,
             "status": i.status.value if hasattr(i.status, "value") else (i.status or "normal"),
             "current_quantity": i.current_quantity, "min_quantity": i.min_quantity, "unit": i.unit}
            for i in items if i.status and (i.status.value if hasattr(i.status, "value") else i.status) != "normal"
        ],
    }


class PurchaseRequestBody(BaseModel):
    item_ids: Optional[List[str]] = None  # None = 所有低库存品


@router.post("/inventory/purchase-request", status_code=201)
async def create_purchase_request(
    req: PurchaseRequestBody,
    store_id: str = Query(...),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """生成采购审批请求（不直接执行，需店长审批后才补货）"""
    from ..services.approval_service import approval_service
    from ..models.decision_log import DecisionType

    if req.item_ids:
        from sqlalchemy import and_
        result = await session.execute(
            select(InventoryItem).where(
                and_(InventoryItem.store_id == store_id, InventoryItem.id.in_(req.item_ids))
            )
        )
        items = result.scalars().all()
    else:
        items = await InventoryRepository.get_low_stock(session, store_id)

    if not items:
        return {"message": "无需补货的库存项", "items": []}

    suggestions = []
    for item in items:
        target = item.max_quantity or item.min_quantity * 3
        if item.current_quantity >= target:
            continue
        restock_qty = target - item.current_quantity
        suggestions.append({
            "item_id": item.id,
            "item_name": item.name,
            "current_quantity": item.current_quantity,
            "target_quantity": target,
            "restock_quantity": restock_qty,
            "unit": item.unit,
            "estimated_cost": int(restock_qty * (item.unit_cost or 0)),
        })

    if not suggestions:
        return {"message": "所有库存充足，无需补货", "items": []}

    total_cost = sum(s["estimated_cost"] for s in suggestions)
    decision_log = await approval_service.create_approval_request(
        decision_type=DecisionType.PURCHASE_SUGGESTION,
        agent_type="inventory_agent",
        agent_method="generate_purchase_request",
        store_id=store_id,
        ai_suggestion={"items": suggestions, "total_estimated_cost": total_cost},
        ai_confidence=0.85,
        ai_reasoning=f"检测到 {len(suggestions)} 个库存项低于安全库存，建议补货至目标数量",
        db=session,
    )
    logger.info("purchase_request_created", store_id=store_id, items=len(suggestions))
    return {
        "decision_id": decision_log.id,
        "status": "pending_approval",
        "items": suggestions,
        "total_estimated_cost": total_cost,
    }


class BatchRestockRequest(BaseModel):
    item_ids: Optional[List[str]] = None  # None = 所有低库存品


@router.post("/inventory/batch-restock", status_code=201)
async def batch_restock(
    req: BatchRestockRequest,
    store_id: str = Query(...),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """批量补货：将低库存品补至 max_quantity（或 min*3）"""
    if req.item_ids:
        from sqlalchemy import and_
        result = await session.execute(
            select(InventoryItem).where(
                and_(InventoryItem.store_id == store_id, InventoryItem.id.in_(req.item_ids))
            )
        )
        items = result.scalars().all()
    else:
        items = await InventoryRepository.get_low_stock(session, store_id)

    restocked = []
    for item in items:
        target = item.max_quantity or item.min_quantity * 3
        if item.current_quantity >= target:
            continue
        restock_qty = target - item.current_quantity
        qty_before = item.current_quantity
        item.current_quantity = target
        txn = InventoryTransaction(
            item_id=item.id,
            store_id=item.store_id,
            transaction_type=TransactionType.PURCHASE,
            quantity=restock_qty,
            quantity_before=qty_before,
            quantity_after=target,
            notes="批量补货",
            performed_by=str(current_user.id),
        )
        session.add(txn)
        restocked.append({"id": item.id, "name": item.name, "restocked_qty": restock_qty, "new_qty": target})

    await session.commit()
    logger.info("batch_restock_completed", store_id=store_id, count=len(restocked))
    return {"restocked": len(restocked), "items": restocked}


class TransferRequestBody(BaseModel):
    source_item_id: str
    target_store_id: str
    quantity: float
    target_item_id: Optional[str] = None
    reason: Optional[str] = None


class TransferApprovalBody(BaseModel):
    manager_feedback: Optional[str] = None


class TransferRejectBody(BaseModel):
    manager_feedback: str


class TransferSuggestionResponse(BaseModel):
    workflow: str
    source_store_id: str
    target_store_id: str
    source_item_id: str
    target_item_id: str
    item_name: str
    unit: Optional[str] = None
    quantity: float
    reason: str
    requested_by: str


class TransferRequestCreateResponse(BaseModel):
    decision_id: str
    status: str
    transfer: TransferSuggestionResponse


class TransferRequestListItemResponse(BaseModel):
    decision_id: str
    status: str
    source_store_id: Optional[str] = None
    target_store_id: Optional[str] = None
    source_item_id: Optional[str] = None
    target_item_id: Optional[str] = None
    item_name: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    reason: Optional[str] = None
    manager_feedback: Optional[str] = None
    created_at: Optional[str] = None
    approved_at: Optional[str] = None
    executed_at: Optional[str] = None


class TransferRequestListResponse(BaseModel):
    total: int
    items: List[TransferRequestListItemResponse]


class TransferActionResponse(BaseModel):
    success: bool
    decision_id: str
    status: str
    source_new_quantity: Optional[float] = None
    target_new_quantity: Optional[float] = None


@router.post("/inventory/transfer-request", status_code=201, response_model=TransferRequestCreateResponse)
async def create_transfer_request(
    req: TransferRequestBody,
    store_id: str = Query(..., description="来源门店ID"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """创建跨店调货审批请求。"""
    if req.quantity <= 0:
        raise HTTPException(status_code=400, detail="调货数量必须大于0")
    if req.target_store_id == store_id:
        raise HTTPException(status_code=400, detail="目标门店不能与来源门店相同")

    source_result = await session.execute(
        select(InventoryItem).where(
            InventoryItem.id == req.source_item_id,
            InventoryItem.store_id == store_id,
        )
    )
    source_item = source_result.scalar_one_or_none()
    if not source_item:
        raise HTTPException(status_code=404, detail="来源库存项不存在")
    if source_item.current_quantity < req.quantity:
        raise HTTPException(status_code=400, detail="来源门店库存不足")

    target_item = None
    if req.target_item_id:
        target_result = await session.execute(
            select(InventoryItem).where(
                InventoryItem.id == req.target_item_id,
                InventoryItem.store_id == req.target_store_id,
            )
        )
        target_item = target_result.scalar_one_or_none()
    else:
        target_result = await session.execute(
            select(InventoryItem).where(
                InventoryItem.store_id == req.target_store_id,
                InventoryItem.name == source_item.name,
            )
        )
        target_item = target_result.scalar_one_or_none()

    if not target_item:
        raise HTTPException(status_code=404, detail="目标门店匹配库存项不存在")

    transfer_payload = {
        "workflow": "inventory_transfer",
        "source_store_id": store_id,
        "target_store_id": req.target_store_id,
        "source_item_id": source_item.id,
        "target_item_id": target_item.id,
        "item_name": source_item.name,
        "unit": source_item.unit,
        "quantity": req.quantity,
        "reason": req.reason or "跨店调货",
        "requested_by": str(current_user.id),
    }

    decision = await approval_service.create_approval_request(
        decision_type=DecisionType.PURCHASE_SUGGESTION,
        agent_type="inventory_agent",
        agent_method="create_transfer_request",
        store_id=store_id,
        ai_suggestion=transfer_payload,
        ai_confidence=0.82,
        ai_reasoning=f"来源门店库存充足，建议向 {req.target_store_id} 调拨 {req.quantity} {source_item.unit or ''}",
        context_data={"workflow": "inventory_transfer"},
        db=session,
    )

    return {
        "decision_id": decision.id,
        "status": "pending_approval",
        "transfer": transfer_payload,
    }


@router.get("/inventory/transfer-requests", response_model=TransferRequestListResponse)
async def list_transfer_requests(
    store_id: Optional[str] = Query(None, description="筛选门店（来源或目标）"),
    status: Optional[str] = Query(None, description="pending/approved/rejected/executed"),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """查询跨店调货审批请求。"""
    stmt = (
        select(DecisionLog)
        .where(
            DecisionLog.decision_type == DecisionType.PURCHASE_SUGGESTION,
            DecisionLog.agent_type == "inventory_agent",
            DecisionLog.agent_method == "create_transfer_request",
        )
        .order_by(desc(DecisionLog.created_at))
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()

    items = []
    for row in rows:
        suggestion = row.ai_suggestion or {}
        if store_id and not (row.store_id == store_id or suggestion.get("target_store_id") == store_id):
            continue
        status_value = row.decision_status.value if hasattr(row.decision_status, "value") else str(row.decision_status)
        if status and status_value != status:
            continue
        items.append({
            "decision_id": row.id,
            "status": status_value,
            "source_store_id": suggestion.get("source_store_id", row.store_id),
            "target_store_id": suggestion.get("target_store_id"),
            "source_item_id": suggestion.get("source_item_id"),
            "target_item_id": suggestion.get("target_item_id"),
            "item_name": suggestion.get("item_name"),
            "quantity": suggestion.get("quantity"),
            "unit": suggestion.get("unit"),
            "reason": suggestion.get("reason"),
            "manager_feedback": row.manager_feedback,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "approved_at": row.approved_at.isoformat() if row.approved_at else None,
            "executed_at": row.executed_at.isoformat() if row.executed_at else None,
        })

    return {"total": len(items), "items": items}


@router.post("/inventory/transfer-requests/{decision_id}/approve", response_model=TransferActionResponse)
async def approve_transfer_request(
    decision_id: str,
    req: TransferApprovalBody,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """批准并执行跨店调货。"""
    result = await session.execute(
        select(DecisionLog).where(
            DecisionLog.id == decision_id,
            DecisionLog.decision_type == DecisionType.PURCHASE_SUGGESTION,
            DecisionLog.agent_type == "inventory_agent",
            DecisionLog.agent_method == "create_transfer_request",
        )
    )
    decision = result.scalar_one_or_none()
    if not decision:
        raise HTTPException(status_code=404, detail="调货申请不存在")

    status_value = decision.decision_status.value if hasattr(decision.decision_status, "value") else str(decision.decision_status)
    if status_value not in {DecisionStatus.PENDING.value, "pending"}:
        raise HTTPException(status_code=400, detail="仅待审批的调货申请可批准")

    suggestion = decision.ai_suggestion or {}
    source_item_id = suggestion.get("source_item_id")
    target_item_id = suggestion.get("target_item_id")
    quantity = float(suggestion.get("quantity") or 0)
    if not source_item_id or not target_item_id or quantity <= 0:
        raise HTTPException(status_code=400, detail="调货申请数据不完整")

    source_item = (await session.execute(select(InventoryItem).where(InventoryItem.id == source_item_id))).scalar_one_or_none()
    target_item = (await session.execute(select(InventoryItem).where(InventoryItem.id == target_item_id))).scalar_one_or_none()
    if not source_item or not target_item:
        raise HTTPException(status_code=404, detail="调货库存项不存在")
    if source_item.current_quantity < quantity:
        raise HTTPException(status_code=400, detail="来源门店库存不足，无法执行调货")

    source_before = source_item.current_quantity
    target_before = target_item.current_quantity
    source_item.current_quantity = source_before - quantity
    target_item.current_quantity = target_before + quantity

    source_txn = InventoryTransaction(
        item_id=source_item.id,
        store_id=source_item.store_id,
        transaction_type=TransactionType.TRANSFER,
        quantity=-quantity,
        quantity_before=source_before,
        quantity_after=source_item.current_quantity,
        notes=f"跨店调出，审批单 {decision_id}",
        performed_by=str(current_user.id),
    )
    target_txn = InventoryTransaction(
        item_id=target_item.id,
        store_id=target_item.store_id,
        transaction_type=TransactionType.TRANSFER,
        quantity=quantity,
        quantity_before=target_before,
        quantity_after=target_item.current_quantity,
        notes=f"跨店调入，审批单 {decision_id}",
        performed_by=str(current_user.id),
    )
    session.add(source_txn)
    session.add(target_txn)

    decision.decision_status = DecisionStatus.EXECUTED
    decision.manager_id = str(current_user.id)
    decision.manager_feedback = req.manager_feedback
    decision.manager_decision = {"action": "approve_transfer", "quantity": quantity}
    decision.approved_at = utcnow_naive()
    decision.executed_at = utcnow_naive()
    chain = decision.approval_chain or []
    chain.append({
        "action": "approved_transfer",
        "manager_id": str(current_user.id),
        "timestamp": now_utc().isoformat(),
        "feedback": req.manager_feedback,
    })
    decision.approval_chain = chain

    await session.commit()
    return {
        "success": True,
        "decision_id": decision_id,
        "status": DecisionStatus.EXECUTED.value,
        "source_new_quantity": source_item.current_quantity,
        "target_new_quantity": target_item.current_quantity,
    }


@router.post("/inventory/transfer-requests/{decision_id}/reject", response_model=TransferActionResponse)
async def reject_transfer_request(
    decision_id: str,
    req: TransferRejectBody,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """拒绝跨店调货申请。"""
    result = await session.execute(
        select(DecisionLog).where(
            DecisionLog.id == decision_id,
            DecisionLog.decision_type == DecisionType.PURCHASE_SUGGESTION,
            DecisionLog.agent_type == "inventory_agent",
            DecisionLog.agent_method == "create_transfer_request",
        )
    )
    decision = result.scalar_one_or_none()
    if not decision:
        raise HTTPException(status_code=404, detail="调货申请不存在")

    status_value = decision.decision_status.value if hasattr(decision.decision_status, "value") else str(decision.decision_status)
    if status_value not in {DecisionStatus.PENDING.value, "pending"}:
        raise HTTPException(status_code=400, detail="仅待审批的调货申请可拒绝")

    decision.decision_status = DecisionStatus.REJECTED
    decision.manager_id = str(current_user.id)
    decision.manager_feedback = req.manager_feedback
    decision.approved_at = utcnow_naive()
    chain = decision.approval_chain or []
    chain.append({
        "action": "rejected_transfer",
        "manager_id": str(current_user.id),
        "timestamp": now_utc().isoformat(),
        "feedback": req.manager_feedback,
    })
    decision.approval_chain = chain

    await session.commit()
    return {"success": True, "decision_id": decision_id, "status": DecisionStatus.REJECTED.value}


@router.get("/inventory/{item_id}", response_model=InventoryItemResponse)
async def get_inventory_item(
    item_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取库存项详情。放在静态子路径后，避免吞掉 transfer-* 路由。"""
    result = await session.execute(select(InventoryItem).where(InventoryItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="库存项不存在")
    return InventoryItemResponse(
        id=item.id, store_id=item.store_id, name=item.name, category=item.category,
        unit=item.unit, current_quantity=item.current_quantity, min_quantity=item.min_quantity,
        max_quantity=item.max_quantity, unit_cost=item.unit_cost,
        status=item.status.value if hasattr(item.status, "value") else item.status
    )


@router.post("/inventory/{item_id}/transaction", status_code=201)
async def record_transaction(
    item_id: str,
    req: InventoryTransactionRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """记录库存变动（入库/出库/损耗）。"""
    result = await session.execute(select(InventoryItem).where(InventoryItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="库存项不存在")

    quantity_before = item.current_quantity

    if req.transaction_type in (TransactionType.PURCHASE,):
        item.current_quantity += req.quantity
    else:
        qty_key = f"inventory:qty:{item_id}"
        lock_key = f"inventory:lock:{item_id}"
        new_qty = None

        try:
            await _redis_svc.initialize()
            r = _redis_svc._redis
            if r:
                if not await r.exists(qty_key):
                    await r.set(qty_key, item.current_quantity)

                result_lua = await r.eval(_LUA_DEDUCT_STOCK, 2, lock_key, qty_key, req.quantity)
                if result_lua == -1:
                    raise HTTPException(status_code=400, detail="库存不足")
                if result_lua >= 0:
                    new_qty = float(result_lua)
        except HTTPException:
            raise
        except Exception as e:
            logger.warning("Redis Lua扣减失败，回退到DB校验", error=str(e))

        if new_qty is None:
            if item.current_quantity < req.quantity:
                raise HTTPException(status_code=400, detail="库存不足")
            item.current_quantity -= req.quantity
        else:
            item.current_quantity = new_qty

    quantity_after = item.current_quantity

    txn = InventoryTransaction(
        item_id=item_id,
        store_id=item.store_id,
        transaction_type=req.transaction_type,
        quantity=req.quantity,
        quantity_before=quantity_before,
        quantity_after=quantity_after,
        notes=req.notes,
        performed_by=str(current_user.id),
    )
    session.add(txn)
    await session.commit()
    logger.info("inventory_transaction_recorded", item_id=item_id, type=req.transaction_type.value)
    return {"success": True, "new_quantity": item.current_quantity}


@router.get("/inventory/{item_id}/transactions")
async def get_item_transactions(
    item_id: str,
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取库存物品流水记录。"""
    from sqlalchemy import desc

    result = await session.execute(
        select(InventoryTransaction)
        .where(InventoryTransaction.item_id == item_id)
        .order_by(desc(InventoryTransaction.transaction_time))
        .limit(limit)
    )
    txns = result.scalars().all()
    return [
        {
            "id": str(t.id),
            "transaction_type": t.transaction_type.value,
            "quantity": t.quantity,
            "quantity_before": t.quantity_before,
            "quantity_after": t.quantity_after,
            "notes": t.notes,
            "performed_by": t.performed_by,
            "transaction_time": t.transaction_time.isoformat() if t.transaction_time else None,
        }
        for t in txns
    ]
