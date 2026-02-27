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
from ..repositories import InventoryRepository
from ..services.redis_cache_service import RedisCacheService
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

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
        status=i.status.value if i.status else None
    ) for i in items]


@router.get("/inventory/{item_id}", response_model=InventoryItemResponse)
async def get_inventory_item(
    item_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取库存项详情"""
    result = await session.execute(select(InventoryItem).where(InventoryItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="库存项不存在")
    return InventoryItemResponse(
        id=item.id, store_id=item.store_id, name=item.name, category=item.category,
        unit=item.unit, current_quantity=item.current_quantity, min_quantity=item.min_quantity,
        max_quantity=item.max_quantity, unit_cost=item.unit_cost,
        status=item.status.value if item.status else None
    )


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
        status=item.status.value if item.status else None
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
        status=item.status.value if item.status else None
    )


@router.post("/inventory/{item_id}/transaction", status_code=201)
async def record_transaction(    item_id: str,
    req: InventoryTransactionRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """记录库存变动（入库/出库/损耗）"""
    result = await session.execute(select(InventoryItem).where(InventoryItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="库存项不存在")

    quantity_before = item.current_quantity

    if req.transaction_type in (TransactionType.PURCHASE,):
        # 入库：直接更新DB，无并发竞争风险
        item.current_quantity += req.quantity
    else:
        # 出库/损耗：使用 Redis Lua 原子扣减防止超卖
        qty_key = f"inventory:qty:{item_id}"
        lock_key = f"inventory:lock:{item_id}"
        new_qty = None

        try:
            await _redis_svc.initialize()
            r = _redis_svc._redis
            if r:
                # 若 Redis 中无缓存，先写入当前 DB 值
                if not await r.exists(qty_key):
                    await r.set(qty_key, item.current_quantity)

                result_lua = await r.eval(
                    _LUA_DEDUCT_STOCK, 2, lock_key, qty_key, req.quantity
                )
                if result_lua == -1:
                    raise HTTPException(status_code=400, detail="库存不足")
                if result_lua >= 0:
                    new_qty = float(result_lua)
        except HTTPException:
            raise
        except Exception as e:
            logger.warning("Redis Lua扣减失败，回退到DB校验", error=str(e))

        # 回退或同步 DB
        if new_qty is None:
            # Redis 不可用，回退到 DB 校验
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
    """获取库存物品流水记录"""
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
        s = i.status.value if i.status else "normal"
        status_dist[s] = status_dist.get(s, 0) + 1
    return {
        "total_items": len(items),
        "total_value": total_value,  # 分
        "category_distribution": category_dist,
        "status_distribution": status_dist,
        "alert_items": [
            {"id": i.id, "name": i.name, "status": i.status.value if i.status else "normal",
             "current_quantity": i.current_quantity, "min_quantity": i.min_quantity, "unit": i.unit}
            for i in items if i.status and i.status.value != "normal"
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
