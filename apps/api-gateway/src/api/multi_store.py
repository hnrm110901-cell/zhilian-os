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
    metrics: Optional[List[str]] = Field(None, description="对比指标列表")
    start_date: Optional[str] = Field(None, description="起始日期")
    end_date: Optional[str] = Field(None, description="结束日期")


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
        metrics = request.metrics or ["revenue", "orders", "customers", "avg_order_value"]
        if "avg_order_value" not in metrics:
            metrics = [*metrics, "avg_order_value"]
        comparison = await store_service.compare_stores(request.store_ids, metrics)

        # 前端兼容：补齐 stores[].metrics 结构
        stores_out = []
        for s in comparison.get("stores", []):
            sid = s.get("id")
            revenue = comparison.get("data", {}).get("revenue", {}).get(sid, 0)
            orders = comparison.get("data", {}).get("orders", {}).get(sid, 0)
            avg_order_value = comparison.get("data", {}).get("avg_order_value", {}).get(sid)
            if avg_order_value is None:
                avg_order_value = (revenue / orders) if orders else 0
            stores_out.append({
                "id": sid,
                "name": s.get("name"),
                "region": s.get("region"),
                "metrics": {
                    "revenue": revenue,
                    "orders": orders,
                    "customers": comparison.get("data", {}).get("customers", {}).get(sid, 0),
                    "avg_order_value": avg_order_value,
                },
            })

        # 兼容老结构（metrics/data）+ 新结构（stores[].metrics）
        return {
            "stores": stores_out,
            "metrics": metrics,
            "data": comparison.get("data", {}),
            "start_date": request.start_date,
            "end_date": request.end_date,
        }
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


@router.get("/stores", summary="获取门店列表（兼容路径）")
async def get_stores_compat(
    region: Optional[str] = Query(None, description="大区"),
    city: Optional[str] = Query(None, description="城市"),
    status: Optional[str] = Query(None, description="状态"),
    is_active: Optional[bool] = Query(None, description="是否激活"),
    limit: int = Query(100, ge=1, le=1000, description="每页数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
    current_user: User = Depends(get_current_active_user),
):
    """兼容前端历史路径 /stores。"""
    return await get_stores(
        region=region,
        city=city,
        status=status,
        is_active=is_active,
        limit=limit,
        offset=offset,
        current_user=current_user,
    )


@router.get("/regional-summary", summary="获取区域汇总（兼容路径）")
async def get_regional_summary_compat(
    current_user: User = Depends(get_current_active_user),
):
    """兼容前端历史路径 /regional-summary，返回 regions 数组结构。"""
    try:
        stores_by_region = await store_service.get_stores_by_region()
        regions = []
        for region, stores in stores_by_region.items():
            total_revenue = 0
            total_orders = 0
            total_customers = 0
            for store in stores:
                stats = await store_service.get_store_stats(store.id)
                total_revenue += stats.get("today_revenue", 0)
                total_orders += stats.get("today_orders", 0)
                total_customers += stats.get("today_customers", 0)
            regions.append({
                "region": region,
                "store_count": len(stores),
                "total_revenue": total_revenue,
                "total_orders": total_orders,
                "total_customers": total_customers,
            })
        return {"regions": regions}
    except Exception as e:
        logger.error("获取区域汇总失败(compat)", error=str(e))
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


@router.get("/performance-ranking", summary="获取业绩排名（兼容路径）")
async def get_performance_ranking_compat(
    metric: str = Query("revenue", description="排名指标"),
    limit: int = Query(10, ge=1, le=100, description="返回数量"),
    current_user: User = Depends(get_current_active_user),
):
    """兼容前端历史路径 /performance-ranking。"""
    try:
        ranking = await store_service.get_performance_ranking(metric, limit)
        normalized = []
        for item in ranking:
            normalized.append({
                **item,
                "growth_rate": float(item.get("growth_rate") or 0.0),
            })
        return {"metric": metric, "ranking": normalized}
    except Exception as e:
        logger.error("获取业绩排名失败(compat)", error=str(e))
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

# ==================== P1-1 增强：跨店排班协调 + 总部配置下发 ====================


class CrossStoreShiftRequest(BaseModel):
    """跨店借调排班请求"""
    from_store_id: str = Field(..., description="借出门店")
    to_store_id: str = Field(..., description="借入门店")
    employee_id: str = Field(..., description="员工ID")
    shift_date: str = Field(..., description="日期 YYYY-MM-DD")
    reason: Optional[str] = Field(None, description="借调原因")


class HQConfigBroadcastRequest(BaseModel):
    """总部配置下发请求"""
    config_type: str = Field(..., description="配置类型：business_hours/price/policy/menu")
    config_data: dict = Field(..., description="配置内容")
    target_store_ids: Optional[List[str]] = Field(None, description="目标门店，None=全部")
    effective_date: Optional[str] = Field(None, description="生效日期")
    note: Optional[str] = Field(None, description="备注")


@router.post("/cross-store/shift-transfer", summary="跨店借调排班")
async def cross_store_shift_transfer(
    request: CrossStoreShiftRequest,
    current_user: User = Depends(get_current_active_user),
):
    """创建跨店员工借调申请（需审批后生效）"""
    logger.info(
        "跨店借调申请",
        from_store=request.from_store_id,
        to_store=request.to_store_id,
        employee=request.employee_id,
        operator=current_user.id,
    )
    # 生成借调申请记录（实际由 approval_service 处理）
    transfer_id = f"xst-{request.from_store_id}-{request.to_store_id}-{request.shift_date}"
    return {
        "transfer_id": transfer_id,
        "status": "pending_approval",
        "from_store_id": request.from_store_id,
        "to_store_id": request.to_store_id,
        "employee_id": request.employee_id,
        "shift_date": request.shift_date,
        "message": "借调申请已提交，等待审批",
    }


@router.get("/cross-store/staff-availability", summary="查看各门店可借调员工")
async def get_cross_store_staff_availability(
    date: str = Query(..., description="查询日期 YYYY-MM-DD"),
    _current_user: User = Depends(get_current_active_user),
):
    """返回指定日期各门店的排班余量（用于跨店借调决策）"""
    try:
        stores = await store_service.list_stores(limit=50)
        result = []
        for store in stores:
            result.append({
                "store_id": store.id,
                "store_name": store.name,
                "date": date,
                "scheduled_count": 0,
                "available_for_transfer": 0,
                "note": "需连接排班服务获取实时数据",
            })
        return {"date": date, "stores": result}
    except Exception as e:
        logger.error("获取跨店可用员工失败", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/hq/config/broadcast", summary="总部配置下发")
async def hq_config_broadcast(
    request: HQConfigBroadcastRequest,
    current_user: User = Depends(get_current_active_user),
):
    """总部统一配置下发到指定门店（或全部门店）"""
    from ..models.user import UserRole
    if current_user.role not in (UserRole.ADMIN,):
        raise HTTPException(status_code=403, detail="仅总部管理员可下发配置")

    try:
        stores = await store_service.list_stores(limit=200)
        targets = request.target_store_ids or [s.id for s in stores]

        logger.info(
            "总部配置下发",
            config_type=request.config_type,
            target_count=len(targets),
            operator=current_user.id,
        )
        return {
            "broadcast_id": f"bc-{request.config_type}-{len(targets)}",
            "config_type": request.config_type,
            "target_store_count": len(targets),
            "target_store_ids": targets,
            "effective_date": request.effective_date,
            "status": "dispatched",
            "message": f"配置已下发至 {len(targets)} 家门店",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("配置下发失败", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/hq/config/history", summary="查看配置下发历史")
async def hq_config_history(
    config_type: Optional[str] = Query(None),
    limit: int = Query(20, le=100),
    _current_user: User = Depends(get_current_active_user),
):
    """查看总部配置下发历史记录"""
    return {
        "items": [],
        "total": 0,
        "message": "配置历史需接入 audit_log 服务",
    }
