"""
外卖统一接单面板 API
整合美团/饿了么/抖音三平台 — 统一视图、接单、拒单、配置、统计
"""

from typing import List, Optional

import structlog
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..core.dependencies import get_current_user, require_role
from ..models.user import UserRole
from ..services.takeaway_unified_service import takeaway_unified_service

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/takeaway", tags=["外卖统一面板"])


# ── Pydantic 请求体 ────────────────────────────────────────────────


class AcceptOrderRequest(BaseModel):
    """接单请求"""

    estimated_minutes: int = Field(30, ge=5, le=120, description="预计备餐时间（分钟）")


class RejectOrderRequest(BaseModel):
    """拒单请求"""

    reason: str = Field(..., min_length=1, max_length=200, description="拒单原因")


class UpdateAutoAcceptRequest(BaseModel):
    """更新自动接单配置"""

    enabled: bool = Field(..., description="是否开启自动接单")
    max_concurrent_orders: int = Field(
        10, ge=1, le=100, description="最大并发订单数"
    )


class SyncMenuRequest(BaseModel):
    """菜单同步请求"""

    platforms: Optional[List[str]] = Field(
        None, description="指定同步平台（空=全部）"
    )


# ── 路由端点 ──────────────────────────────────────────────────────


@router.get("/orders/pending")
async def get_pending_orders(
    store_id: str = Query(..., description="门店ID"),
    _user=Depends(require_role(UserRole.STORE_MANAGER, UserRole.ADMIN)),
):
    """
    获取所有平台待接单订单（统一格式）

    聚合美团/饿了么/抖音三平台的待处理订单，按创建时间升序排列。
    """
    try:
        orders = await takeaway_unified_service.get_pending_orders(store_id)
        return {
            "success": True,
            "store_id": store_id,
            "total": len(orders),
            "orders": orders,
        }
    except Exception as exc:
        logger.error("获取待接单失败", store_id=store_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"获取待接单失败: {exc}")


@router.post("/orders/{platform}/{order_id}/accept")
async def accept_order(
    platform: str,
    order_id: str,
    store_id: str = Query(..., description="门店ID"),
    body: AcceptOrderRequest = Body(default=AcceptOrderRequest()),
    _user=Depends(require_role(UserRole.STORE_MANAGER, UserRole.ADMIN)),
):
    """
    接单 — 调用对应平台API确认接单

    接单后自动：扣减库存、触发KDS出餐显示。
    platform: meituan | eleme | douyin
    """
    try:
        result = await takeaway_unified_service.accept_order(
            store_id=store_id,
            platform=platform,
            platform_order_id=order_id,
            estimated_minutes=body.estimated_minutes,
        )
        if not result.get("success"):
            raise HTTPException(
                status_code=422,
                detail=result.get("error", "接单失败"),
            )
        return result
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("接单失败", platform=platform, order_id=order_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"接单失败: {exc}")


@router.post("/orders/{platform}/{order_id}/reject")
async def reject_order(
    platform: str,
    order_id: str,
    store_id: str = Query(..., description="门店ID"),
    body: RejectOrderRequest = Body(...),
    _user=Depends(require_role(UserRole.STORE_MANAGER, UserRole.ADMIN)),
):
    """
    拒单 — 调用平台API拒绝订单并记录原因

    platform: meituan | eleme | douyin
    """
    try:
        result = await takeaway_unified_service.reject_order(
            store_id=store_id,
            platform=platform,
            platform_order_id=order_id,
            reason=body.reason,
        )
        if not result.get("success"):
            raise HTTPException(
                status_code=422,
                detail=result.get("error", "拒单失败"),
            )
        return result
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("拒单失败", platform=platform, order_id=order_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"拒单失败: {exc}")


@router.get("/auto-accept-config")
async def get_auto_accept_config(
    store_id: str = Query(..., description="门店ID"),
    _user=Depends(require_role(UserRole.STORE_MANAGER, UserRole.ADMIN)),
):
    """
    获取自动接单配置

    返回各平台的自动接单开关状态和最大并发订单数。
    """
    try:
        config = await takeaway_unified_service.auto_accept_config(store_id)
        return config
    except Exception as exc:
        logger.error("获取自动接单配置失败", store_id=store_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"获取配置失败: {exc}")


@router.put("/auto-accept-config/{platform}")
async def update_auto_accept_config(
    platform: str,
    store_id: str = Query(..., description="门店ID"),
    body: UpdateAutoAcceptRequest = Body(...),
    _user=Depends(require_role(UserRole.STORE_MANAGER, UserRole.ADMIN)),
):
    """
    更新自动接单配置

    platform: meituan | eleme | douyin
    """
    try:
        result = await takeaway_unified_service.update_auto_accept(
            store_id=store_id,
            platform=platform,
            enabled=body.enabled,
            max_concurrent_orders=body.max_concurrent_orders,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("更新自动接单配置失败", platform=platform, error=str(exc))
        raise HTTPException(status_code=500, detail=f"更新配置失败: {exc}")


@router.get("/stats")
async def get_platform_stats(
    store_id: str = Query(..., description="门店ID"),
    days: int = Query(7, ge=1, le=90, description="统计天数"),
    _user=Depends(require_role(UserRole.STORE_MANAGER, UserRole.ADMIN)),
):
    """
    外卖平台统计

    返回各平台近 N 天的订单量、营收（元）、取消率、平均送达时间。
    """
    try:
        stats = await takeaway_unified_service.get_platform_stats(store_id, days)
        return stats
    except Exception as exc:
        logger.error("获取平台统计失败", store_id=store_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"获取统计失败: {exc}")


@router.post("/sync-menu")
async def sync_menu_to_platforms(
    store_id: str = Query(..., description="门店ID"),
    body: SyncMenuRequest = Body(default=SyncMenuRequest()),
    _user=Depends(require_role(UserRole.STORE_MANAGER, UserRole.ADMIN)),
):
    """
    菜单同步到各平台（防超卖）

    将当前沽清状态推送到外卖平台，自动下架已售罄菜品。
    """
    try:
        result = await takeaway_unified_service.sync_menu_to_platforms(
            store_id=store_id,
            platforms=body.platforms,
        )
        return result
    except Exception as exc:
        logger.error("菜单同步失败", store_id=store_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"菜单同步失败: {exc}")


@router.get("/dashboard")
async def get_takeaway_dashboard(
    store_id: str = Query(..., description="门店ID"),
    _user=Depends(require_role(UserRole.STORE_MANAGER, UserRole.ADMIN)),
):
    """
    外卖驾驶舱（BFF端点）

    一次性返回：
    - 各平台待接单数量
    - 今日各平台营收
    - 自动接单状态
    - 近期异常订单摘要
    """
    try:
        # 并发获取各部分数据（尽力而为，单项失败不阻塞整体）
        pending_orders = []
        today_stats = {}
        auto_config = {}
        errors = []

        try:
            pending_orders = await takeaway_unified_service.get_pending_orders(store_id)
        except Exception as exc:
            errors.append(f"待接单: {exc}")

        try:
            today_stats = await takeaway_unified_service.get_platform_stats(store_id, days=1)
        except Exception as exc:
            errors.append(f"今日统计: {exc}")

        try:
            auto_config = await takeaway_unified_service.auto_accept_config(store_id)
        except Exception as exc:
            errors.append(f"自动接单配置: {exc}")

        # 按平台汇总待接单数量
        pending_by_platform = {}
        for order in pending_orders:
            platform = order.get("platform", "unknown")
            pending_by_platform[platform] = pending_by_platform.get(platform, 0) + 1

        return {
            "store_id": store_id,
            "pending_orders": {
                "total": len(pending_orders),
                "by_platform": pending_by_platform,
            },
            "today_revenue": {
                "total_yuan": today_stats.get("total_revenue_yuan", 0.0),
                "by_platform": {
                    p: v.get("revenue_yuan", 0.0)
                    for p, v in today_stats.get("platforms", {}).items()
                },
            },
            "auto_accept": auto_config.get("platforms", {}),
            "errors": errors,
        }
    except Exception as exc:
        logger.error("外卖驾驶舱失败", store_id=store_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"驾驶舱数据加载失败: {exc}")
