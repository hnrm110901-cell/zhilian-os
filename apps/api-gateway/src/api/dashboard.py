"""
Dashboard API
数据可视化大屏API端点
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
import structlog

from ..services.dashboard_service import dashboard_service
from ..core.dependencies import get_current_active_user
from ..models.user import User

logger = structlog.get_logger()

router = APIRouter()


@router.get("/overview", summary="获取概览统计数据")
async def get_overview_stats(
    current_user: User = Depends(get_current_active_user),
):
    """
    获取概览统计数据

    包括门店、订单、会员、营收等核心指标

    需要权限: dashboard:read
    """
    try:
        stats = await dashboard_service.get_overview_stats()
        return stats
    except Exception as e:
        logger.error("获取概览统计数据失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"获取概览统计数据失败: {str(e)}")


@router.get("/sales-trend", summary="获取销售趋势")
async def get_sales_trend(
    days: int = Query(7, ge=1, le=30, description="天数"),
    current_user: User = Depends(get_current_active_user),
):
    """
    获取销售趋势数据

    需要权限: dashboard:read
    """
    try:
        trend = await dashboard_service.get_sales_trend(days)
        return trend
    except Exception as e:
        logger.error("获取销售趋势失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"获取销售趋势失败: {str(e)}")


@router.get("/category-sales", summary="获取菜品类别销售")
async def get_category_sales(
    current_user: User = Depends(get_current_active_user),
):
    """
    获取菜品类别销售数据

    需要权限: dashboard:read
    """
    try:
        sales = await dashboard_service.get_category_sales()
        return sales
    except Exception as e:
        logger.error("获取菜品类别销售失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"获取菜品类别销售失败: {str(e)}")


@router.get("/payment-methods", summary="获取支付方式分布")
async def get_payment_methods(
    current_user: User = Depends(get_current_active_user),
):
    """
    获取支付方式分布数据

    需要权限: dashboard:read
    """
    try:
        methods = await dashboard_service.get_payment_methods()
        return methods
    except Exception as e:
        logger.error("获取支付方式分布失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"获取支付方式分布失败: {str(e)}")


@router.get("/member-stats", summary="获取会员统计")
async def get_member_stats(
    current_user: User = Depends(get_current_active_user),
):
    """
    获取会员统计数据

    需要权限: dashboard:read
    """
    try:
        stats = await dashboard_service.get_member_stats()
        return stats
    except Exception as e:
        logger.error("获取会员统计失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"获取会员统计失败: {str(e)}")


@router.get("/agent-performance", summary="获取Agent性能")
async def get_agent_performance(
    current_user: User = Depends(get_current_active_user),
):
    """
    获取Agent性能数据

    需要权限: dashboard:read
    """
    try:
        performance = await dashboard_service.get_agent_performance()
        return performance
    except Exception as e:
        logger.error("获取Agent性能失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"获取Agent性能失败: {str(e)}")


@router.get("/realtime-metrics", summary="获取实时指标")
async def get_realtime_metrics(
    current_user: User = Depends(get_current_active_user),
):
    """
    获取实时指标数据

    需要权限: dashboard:read
    """
    try:
        metrics = await dashboard_service.get_realtime_metrics()
        return metrics
    except Exception as e:
        logger.error("获取实时指标失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"获取实时指标失败: {str(e)}")
