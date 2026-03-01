"""
Store API endpoints
门店管理API接口
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
from pydantic import BaseModel, ConfigDict

from ..models.user import User, UserRole
from ..models.store import Store, StoreStatus
from ..core.dependencies import get_current_active_user, require_role
from ..services.store_service import store_service
import structlog

logger = structlog.get_logger()
router = APIRouter()


# Request/Response models
class CreateStoreRequest(BaseModel):
    id: str
    name: str
    code: str
    address: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    manager_id: Optional[str] = None
    region: Optional[str] = None
    area: Optional[float] = None
    seats: Optional[int] = None
    floors: Optional[int] = 1
    opening_date: Optional[str] = None
    business_hours: Optional[dict] = None
    monthly_revenue_target: Optional[float] = None
    daily_customer_target: Optional[int] = None
    cost_ratio_target: Optional[float] = None
    labor_cost_ratio_target: Optional[float] = None


class UpdateStoreRequest(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    manager_id: Optional[str] = None
    region: Optional[str] = None
    status: Optional[StoreStatus] = None
    area: Optional[float] = None
    seats: Optional[int] = None
    floors: Optional[int] = None
    opening_date: Optional[str] = None
    business_hours: Optional[dict] = None
    monthly_revenue_target: Optional[float] = None
    daily_customer_target: Optional[int] = None
    cost_ratio_target: Optional[float] = None
    labor_cost_ratio_target: Optional[float] = None


class StoreResponse(BaseModel):
    id: str
    name: str
    code: str
    address: Optional[str]
    city: Optional[str]
    district: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    manager_id: Optional[str]
    region: Optional[str]
    status: str
    is_active: bool
    area: Optional[float]
    seats: Optional[int]
    floors: Optional[int]
    opening_date: Optional[str]
    business_hours: Optional[dict]
    monthly_revenue_target: Optional[float]
    daily_customer_target: Optional[int]
    cost_ratio_target: Optional[float]
    labor_cost_ratio_target: Optional[float]
    created_at: Optional[str]
    updated_at: Optional[str]

    model_config = ConfigDict(from_attributes=True)


@router.post("/stores", response_model=StoreResponse)
async def create_store(
    request: CreateStoreRequest,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    """
    创建门店 (仅管理员可操作)
    """
    try:
        store = await store_service.create_store(
            id=request.id,
            name=request.name,
            code=request.code,
            address=request.address,
            city=request.city,
            district=request.district,
            phone=request.phone,
            email=request.email,
            manager_id=request.manager_id,
            region=request.region,
            area=request.area,
            seats=request.seats,
            floors=request.floors,
            opening_date=request.opening_date,
            business_hours=request.business_hours,
            monthly_revenue_target=request.monthly_revenue_target,
            daily_customer_target=request.daily_customer_target,
            cost_ratio_target=request.cost_ratio_target,
            labor_cost_ratio_target=request.labor_cost_ratio_target,
        )

        return StoreResponse(**store.to_dict())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/stores", response_model=List[StoreResponse])
async def get_stores(
    region: Optional[str] = None,
    city: Optional[str] = None,
    status: Optional[StoreStatus] = None,
    is_active: Optional[bool] = None,
    limit: int = Query(100, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_active_user),
):
    """
    获取门店列表
    """
    stores = await store_service.get_stores(
        region=region,
        city=city,
        status=status,
        is_active=is_active,
        limit=limit,
        offset=offset,
    )

    return [StoreResponse(**store.to_dict()) for store in stores]


@router.get("/stores/{store_id}", response_model=StoreResponse)
async def get_store(
    store_id: str,
    current_user: User = Depends(get_current_active_user),
):
    """
    获取门店详情
    """
    store = await store_service.get_store(store_id)

    if not store:
        raise HTTPException(status_code=404, detail="门店不存在")

    return StoreResponse(**store.to_dict())


@router.put("/stores/{store_id}", response_model=StoreResponse)
async def update_store(
    store_id: str,
    request: UpdateStoreRequest,
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.STORE_MANAGER)),
):
    """
    更新门店信息 (管理员和店长可操作)
    """
    # 店长只能更新自己的门店
    if current_user.role == UserRole.STORE_MANAGER and current_user.store_id != store_id:
        raise HTTPException(status_code=403, detail="只能更新自己的门店信息")

    update_data = request.dict(exclude_unset=True)
    store = await store_service.update_store(store_id, **update_data)

    if not store:
        raise HTTPException(status_code=404, detail="门店不存在")

    return StoreResponse(**store.to_dict())


@router.delete("/stores/{store_id}")
async def delete_store(
    store_id: str,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    """
    删除门店 (仅管理员可操作)
    """
    success = await store_service.delete_store(store_id)

    if not success:
        raise HTTPException(status_code=404, detail="门店不存在")

    return {"success": True, "message": "门店已删除"}


@router.get("/stores/{store_id}/stats")
async def get_store_stats(
    store_id: str,
    current_user: User = Depends(get_current_active_user),
):
    """
    获取门店统计信息
    """
    stats = await store_service.get_store_stats(store_id)

    if not stats:
        raise HTTPException(status_code=404, detail="门店不存在")

    return stats


@router.get("/stores-by-region")
async def get_stores_by_region(
    current_user: User = Depends(get_current_active_user),
):
    """
    按区域分组获取门店
    """
    stores_by_region = await store_service.get_stores_by_region()

    # 转换为响应格式
    result = {}
    for region, stores in stores_by_region.items():
        result[region] = [StoreResponse(**store.to_dict()) for store in stores]

    return result


@router.post("/stores/compare")
async def compare_stores(
    store_ids: List[str],
    metrics: List[str] = Query(["revenue", "customers", "cost_ratio"]),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.STORE_MANAGER)),
):
    """
    对比多个门店的数据
    """
    if len(store_ids) < 2:
        raise HTTPException(status_code=400, detail="至少需要2个门店进行对比")

    if len(store_ids) > 10:
        raise HTTPException(status_code=400, detail="最多对比10个门店")

    comparison = await store_service.compare_stores(store_ids, metrics)
    return comparison


@router.get("/stores-count")
async def get_stores_count(
    region: Optional[str] = None,
    status: Optional[StoreStatus] = None,
    current_user: User = Depends(get_current_active_user),
):
    """
    获取门店数量统计
    """
    count = await store_service.get_store_count(region=region, status=status)
    return {"count": count, "region": region, "status": status}
