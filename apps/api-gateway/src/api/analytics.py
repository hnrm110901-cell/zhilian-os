"""
Analytics API
数据分析API - 销售预测、异常检测、关联分析、时间模式分析
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from src.core.database import get_db
from src.core.dependencies import get_current_active_user
from src.models.user import User
from src.services.analytics_service import get_analytics_service

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/predict-sales")
async def predict_sales(
    store_id: str = Query(..., description="门店ID"),
    days_ahead: int = Query(7, ge=1, le=30, description="预测天数"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """销售预测 - 基于历史数据预测未来销售趋势"""
    try:
        service = get_analytics_service(db)
        return await service.predict_sales(store_id=store_id, days_ahead=days_ahead)
    except Exception as e:
        logger.error("predict_sales_error", error=str(e), store_id=store_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/anomalies")
async def detect_anomalies(
    store_id: str = Query(..., description="门店ID"),
    days: int = Query(7, ge=1, le=90, description="分析天数"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """异常检测 - 识别营收、客流等异常波动"""
    try:
        service = get_analytics_service(db)
        return await service.detect_anomalies(store_id=store_id, days=days)
    except Exception as e:
        logger.error("detect_anomalies_error", error=str(e), store_id=store_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/associations")
async def analyze_associations(
    store_id: str = Query(..., description="门店ID"),
    min_support: float = Query(0.1, ge=0.01, le=1.0, description="最小支持度"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """关联分析 - 分析菜品之间的关联关系（购物篮分析）"""
    try:
        service = get_analytics_service(db)
        return await service.analyze_associations(store_id=store_id, min_support=min_support)
    except Exception as e:
        logger.error("analyze_associations_error", error=str(e), store_id=store_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/revenue-trend")
async def revenue_trend(
    store_id:    str = Query(..., description="门店ID"),
    days:        int = Query(30, ge=7, le=365, description="统计天数"),
    granularity: str = Query("daily", regex="^(daily|weekly)$", description="颗粒度: daily / weekly"),
    db:          AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """营收趋势 — 日/周颗粒度的营收时间序列及环比变化"""
    try:
        service = get_analytics_service(db)
        return await service.get_revenue_trend(store_id=store_id, days=days, granularity=granularity)
    except Exception as e:
        logger.error("revenue_trend_error", error=str(e), store_id=store_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/customer-traffic")
async def customer_traffic(
    store_id: str = Query(..., description="门店ID"),
    days:     int = Query(30, ge=7, le=365, description="统计天数"),
    db:       AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """客流分析 — 以订单数为客流代理指标，返回每日趋势及时段分布"""
    try:
        service = get_analytics_service(db)
        return await service.get_customer_traffic(store_id=store_id, days=days)
    except Exception as e:
        logger.error("customer_traffic_error", error=str(e), store_id=store_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dish-contribution")
async def dish_contribution(
    store_id: str = Query(..., description="门店ID"),
    days:     int = Query(30, ge=7, le=365, description="统计天数"),
    top_n:    int = Query(20, ge=5, le=100, description="返回前N名菜品"),
    db:       AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """菜品贡献度 — 帕累托分析（A/B/C 分级），返回各菜品营收占比及累计曲线"""
    try:
        service = get_analytics_service(db)
        return await service.get_dish_contribution(store_id=store_id, days=days, top_n=top_n)
    except Exception as e:
        logger.error("dish_contribution_error", error=str(e), store_id=store_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/time-heatmap")
async def time_heatmap(
    store_id: str = Query(..., description="门店ID"),
    days:     int = Query(30, ge=7, le=365, description="统计天数"),
    db:       AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """时段热力图 — 7（周）× 24（时）平均营收矩阵，供前端渲染热力图"""
    try:
        service = get_analytics_service(db)
        return await service.get_time_heatmap(store_id=store_id, days=days)
    except Exception as e:
        logger.error("time_heatmap_error", error=str(e), store_id=store_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/time-patterns")
async def analyze_time_patterns(
    store_id: str = Query(..., description="门店ID"),
    days: int = Query(30, ge=7, le=365, description="分析天数"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """时间模式分析 - 分析客流、营收的时间规律"""
    try:
        service = get_analytics_service(db)
        return await service.analyze_time_patterns(store_id=store_id, days=days)
    except Exception as e:
        logger.error("analyze_time_patterns_error", error=str(e), store_id=store_id)
        raise HTTPException(status_code=500, detail=str(e))
