"""
高级分析API
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.auth import get_current_user
from src.services.analytics_service import get_analytics_service
from src.models import User

router = APIRouter()


@router.get("/predict/sales")
async def predict_sales(
    store_id: str = Query(..., description="门店ID"),
    days_ahead: int = Query(7, ge=1, le=30, description="预测天数"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """销售预测"""
    service = get_analytics_service(db)
    return await service.predict_sales(store_id, days_ahead)


@router.get("/anomalies")
async def detect_anomalies(
    store_id: str = Query(..., description="门店ID"),
    metric: str = Query("revenue", description="指标类型: revenue, cost"),
    days: int = Query(30, ge=7, le=90, description="分析天数"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """异常检测"""
    service = get_analytics_service(db)
    return await service.detect_anomalies(store_id, metric, days)


@router.get("/associations")
async def analyze_associations(
    store_id: str = Query(..., description="门店ID"),
    min_support: float = Query(0.1, ge=0.01, le=1.0, description="最小支持度"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """关联分析"""
    service = get_analytics_service(db)
    return await service.analyze_associations(store_id, min_support)


@router.get("/time-patterns")
async def analyze_time_patterns(
    store_id: str = Query(..., description="门店ID"),
    days: int = Query(30, ge=7, le=90, description="分析天数"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """时段分析"""
    service = get_analytics_service(db)
    return await service.analyze_time_patterns(store_id, days)
