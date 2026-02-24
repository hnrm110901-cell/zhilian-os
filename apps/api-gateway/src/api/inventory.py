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
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

logger = structlog.get_logger()
router = APIRouter()


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
async def record_transaction(
    item_id: str,
    req: InventoryTransactionRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """记录库存变动（入库/出库/损耗）"""
    result = await session.execute(select(InventoryItem).where(InventoryItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="库存项不存在")

    # 更新库存数量
    quantity_before = item.current_quantity
    if req.transaction_type in (TransactionType.PURCHASE,):
        item.current_quantity += req.quantity
    else:
        if item.current_quantity < req.quantity:
            raise HTTPException(status_code=400, detail="库存不足")
        item.current_quantity -= req.quantity
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
