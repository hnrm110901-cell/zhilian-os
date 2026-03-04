"""
Multi-Store Management API
多门店管理API端点
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from pydantic import BaseModel, Field
import structlog

from ..services.store_service import store_service
from ..core.dependencies import get_current_active_user
from ..models.user import User
from ..models.store import StoreStatus

logger = structlog.get_logger()

router = APIRouter()


# ==================== Request/Response Models ====================


class CreateStoreRequest(BaseModel):
    """创建门店请求"""

    id: str = Field(..., description="门店ID")
    name: str = Field(..., description="门店名称")
    code: str = Field(..., description="门店编码")
    address: Optional[str] = Field(None, description="地址")
    city: Optional[str] = Field(None, description="城市")
    district: Optional[str] = Field(None, description="区域")
    phone: Optional[str] = Field(None, description="电话")
    email: Optional[str] = Field(None, description="邮箱")
    manager_id: Optional[str] = Field(None, description="店长ID")
    region: Optional[str] = Field(None, description="大区")
    area: Optional[float] = Field(None, description="面积（平方米）")
    seats: Optional[int] = Field(None, description="座位数")
    floors: Optional[int] = Field(1, description="楼层数")
    opening_date: Optional[str] = Field(None, description="开业日期")
    business_hours: Optional[dict] = Field(None, description="营业时间")


class UpdateStoreRequest(BaseModel):
    """更新门店请求"""

    name: Optional[str] = Field(None, description="门店名称")
    address: Optional[str] = Field(None, description="地址")
    city: Optional[str] = Field(None, description="城市")
    district: Optional[str] = Field(None, description="区域")
    phone: Optional[str] = Field(None, description="电话")
    email: Optional[str] = Field(None, description="邮箱")
    manager_id: Optional[str] = Field(None, description="店长ID")
    region: Optional[str] = Field(None, description="大区")
    status: Optional[str] = Field(None, description="状态")
    area: Optional[float] = Field(None, description="面积")
    seats: Optional[int] = Field(None, description="座位数")
    business_hours: Optional[dict] = Field(None, description="营业时间")


class CompareStoresRequest(BaseModel):
    """门店对比请求"""

    store_ids: List[str] = Field(..., description="门店ID列表")
    metrics: List[str] = Field(..., description="对比指标列表")


# ==================== API Endpoints ====================


@router.post("/create", summary="创建门店")
async def create_store(
    request: CreateStoreRequest,
    current_user: User = Depends(get_current_active_user),
):
    """
    创建门店

    需要权限: store:write
    """
    try:
        store = await store_service.create_store(**request.model_dump())
        return {
            "success": True,
            "store_id": store.id,
            "message": "门店创建成功",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("创建门店失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"创建门店失败: {str(e)}")


@router.get("/list", summary="获取门店列表")
async def get_stores(
    region: Optional[str] = Query(None, description="大区"),
    city: Optional[str] = Query(None, description="城市"),
    status: Optional[str] = Query(None, description="状态"),
    is_active: Optional[bool] = Query(None, description="是否激活"),
    limit: int = Query(100, ge=1, le=1000, description="每页数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
    current_user: User = Depends(get_current_active_user),
):
    """
    获取门店列表

    需要权限: store:read
    """
    try:
        status_enum = StoreStatus(status) if status else None
        stores = await store_service.get_stores(
            region=region,
            city=city,
            status=status_enum,
            is_active=is_active,
            limit=limit,
            offset=offset,
        )

        return {
            "stores": [
                {
                    "id": s.id,
                    "name": s.name,
                    "code": s.code,
                    "address": s.address,
                    "city": s.city,
                    "district": s.district,
                    "region": s.region,
                    "status": s.status,
                    "is_active": s.is_active,
                    "manager_id": s.manager_id,
                    "area": s.area,
                    "seats": s.seats,
                    "phone": s.phone,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                }
                for s in stores
            ],
            "total": len(stores),
            "limit": limit,
            "offset": offset,
        }
    except Exception as e:
        logger.error("获取门店列表失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"获取门店列表失败: {str(e)}")


@router.get("/{store_id}", summary="获取门店详情")
async def get_store(
    store_id: str,
    current_user: User = Depends(get_current_active_user),
):
    """
    获取门店详情

    需要权限: store:read
    """
    try:
        store = await store_service.get_store(store_id)
        if not store:
            raise HTTPException(status_code=404, detail="门店不存在")

        return {
            "id": store.id,
            "name": store.name,
            "code": store.code,
            "address": store.address,
            "city": store.city,
            "district": store.district,
            "region": store.region,
            "status": store.status,
            "is_active": store.is_active,
            "manager_id": store.manager_id,
            "area": store.area,
            "seats": store.seats,
            "floors": store.floors,
            "phone": store.phone,
            "email": store.email,
            "opening_date": store.opening_date,
            "business_hours": store.business_hours,
            "monthly_revenue_target": store.monthly_revenue_target,
            "created_at": store.created_at.isoformat() if store.created_at else None,
            "updated_at": store.updated_at.isoformat() if store.updated_at else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取门店详情失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"获取门店详情失败: {str(e)}")


@router.put("/{store_id}", summary="更新门店信息")
async def update_store(
    store_id: str,
    request: UpdateStoreRequest,
    current_user: User = Depends(get_current_active_user),
):
    """
    更新门店信息

    需要权限: store:write
    """
    try:
        update_data = request.dict(exclude_none=True)
        store = await store_service.update_store(store_id, **update_data)

        if not store:
            raise HTTPException(status_code=404, detail="门店不存在")

        return {
            "success": True,
            "message": "门店信息更新成功",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("更新门店信息失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"更新门店信息失败: {str(e)}")


@router.delete("/{store_id}", summary="删除门店")
async def delete_store(
    store_id: str,
    current_user: User = Depends(get_current_active_user),
):
    """
    删除门店（软删除）

    需要权限: store:delete
    """
    try:
        success = await store_service.delete_store(store_id)

        if not success:
            raise HTTPException(status_code=404, detail="门店不存在")

        return {
            "success": True,
            "message": "门店已删除",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("删除门店失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"删除门店失败: {str(e)}")


@router.get("/{store_id}/stats", summary="获取门店统计")
async def get_store_stats(
    store_id: str,
    current_user: User = Depends(get_current_active_user),
):
    """
    获取门店统计信息

    需要权限: store:read
    """
    try:
        stats = await store_service.get_store_stats(store_id)

        if not stats:
            raise HTTPException(status_code=404, detail="门店不存在")

        return stats
    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取门店统计失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"获取门店统计失败: {str(e)}")


@router.post("/compare", summary="门店对比")
async def compare_stores(
    request: CompareStoresRequest,
    current_user: User = Depends(get_current_active_user),
):
    """
    对比多个门店的数据

    需要权限: store:read
    """
    try:
        comparison = await store_service.compare_stores(
            request.store_ids, request.metrics
        )
        return comparison
    except Exception as e:
        logger.error("门店对比失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"门店对比失败: {str(e)}")


@router.get("/regional/summary", summary="获取区域汇总")
async def get_regional_summary(
    current_user: User = Depends(get_current_active_user),
):
    """
    获取区域汇总数据

    需要权限: store:read
    """
    try:
        summary = await store_service.get_regional_summary()
        return summary
    except Exception as e:
        logger.error("获取区域汇总失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"获取区域汇总失败: {str(e)}")


@router.get("/ranking/performance", summary="获取业绩排名")
async def get_performance_ranking(
    metric: str = Query("revenue", description="排名指标"),
    limit: int = Query(10, ge=1, le=100, description="返回数量"),
    current_user: User = Depends(get_current_active_user),
):
    """
    获取门店业绩排名

    需要权限: store:read
    """
    try:
        ranking = await store_service.get_performance_ranking(metric, limit)
        return {"metric": metric, "ranking": ranking}
    except Exception as e:
        logger.error("获取业绩排名失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"获取业绩排名失败: {str(e)}")


@router.get("/count", summary="获取门店数量")
async def get_store_count(
    region: Optional[str] = Query(None, description="大区"),
    status: Optional[str] = Query(None, description="状态"),
    current_user: User = Depends(get_current_active_user),
):
    """
    获取门店数量

    需要权限: store:read
    """
    try:
        status_enum = StoreStatus(status) if status else None
        count = await store_service.get_store_count(region=region, status=status_enum)
        return {"count": count, "region": region, "status": status}
    except Exception as e:
        logger.error("获取门店数量失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"获取门店数量失败: {str(e)}")
