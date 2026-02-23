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
