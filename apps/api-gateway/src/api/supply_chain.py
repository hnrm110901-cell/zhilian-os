"""
供应链管理API
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from src.core.database import get_db
from src.core.dependencies import get_current_active_user, require_permission
from src.services.supply_chain_service import get_supply_chain_service
from src.models import User

router = APIRouter()


# Pydantic模型
class SupplierCreate(BaseModel):
    name: str = Field(..., description="供应商名称")
    code: Optional[str] = Field(None, description="供应商编码")
    category: str = Field("food", description="类别: food, beverage, equipment, other")
    contact_person: Optional[str] = Field(None, description="联系人")
    phone: Optional[str] = Field(None, description="电话")
    email: Optional[str] = Field(None, description="邮箱")
    address: Optional[str] = Field(None, description="地址")
    status: str = Field("active", description="状态: active, inactive, suspended")
    rating: float = Field(5.0, ge=1.0, le=5.0, description="评分 1-5")
    payment_terms: str = Field("net30", description="付款条款")
    delivery_time: int = Field(3, description="平均交货时间（天）")


class PurchaseOrderCreate(BaseModel):
    supplier_id: str = Field(..., description="供应商ID")
    store_id: str = Field(..., description="门店ID")
    order_number: Optional[str] = Field(None, description="订单号")
    total_amount: int = Field(0, description="总金额（分）")
    expected_delivery: Optional[datetime] = Field(None, description="预计交货时间")
    notes: Optional[str] = Field(None, description="备注")


class OrderStatusUpdate(BaseModel):
    status: str = Field(..., description="状态")
    notes: Optional[str] = Field(None, description="备注")


@router.get("/suppliers")
async def get_suppliers(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取供应商列表"""
    service = get_supply_chain_service(db)
    return await service.get_suppliers(skip=skip, limit=limit, status=status, category=category)


@router.post("/suppliers")
async def create_supplier(
    data: SupplierCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("supply_chain:write")),
):
    """创建供应商"""
    service = get_supply_chain_service(db)
    return await service.create_supplier(data.dict())


@router.get("/suppliers/{supplier_id}/performance")
async def get_supplier_performance(
    supplier_id: str,
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取供应商绩效"""
    service = get_supply_chain_service(db)
    return await service.get_supplier_performance(supplier_id, days)


@router.get("/purchase-orders")
async def get_purchase_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: Optional[str] = Query(None),
    supplier_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取采购订单列表"""
    service = get_supply_chain_service(db)
    return await service.get_purchase_orders(
        skip=skip, limit=limit, status=status, supplier_id=supplier_id
    )


@router.post("/purchase-orders")
async def create_purchase_order(
    data: PurchaseOrderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("supply_chain:write")),
):
    """创建采购订单"""
    service = get_supply_chain_service(db)
    order_data = data.dict()
    order_data["created_by"] = current_user.id
    return await service.create_purchase_order(order_data)


@router.patch("/purchase-orders/{order_id}/status")
async def update_order_status(
    order_id: str,
    data: OrderStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("supply_chain:write")),
):
    """更新采购订单状态"""
    service = get_supply_chain_service(db)
    return await service.update_order_status(order_id, data.status, data.notes)


@router.get("/replenishment-suggestions")
async def get_replenishment_suggestions(
    store_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取补货建议"""
    service = get_supply_chain_service(db)
    suggestions = await service.get_replenishment_suggestions(store_id)
    return {"suggestions": suggestions, "total": len(suggestions)}
