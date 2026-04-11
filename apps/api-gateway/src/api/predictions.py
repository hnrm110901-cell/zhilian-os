"""
预测准确率与OKR级联 API

端点：
  GET  /api/v1/predictions/{store_id}/accuracy       — 预测准确率
  GET  /api/v1/predictions/brand/{brand_id}/dashboard — 品牌预测总览
  POST /api/v1/predictions/{store_id}/generate        — 手动生成预测
  POST /api/v1/objectives/cascade/auto                — 一键目标级联
  GET  /api/v1/objectives/cascade/{brand_id}/health   — 级联健康检查
  GET  /api/v1/objectives/{brand_id}/deviations       — 目标偏差预警
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user, validate_store_brand
from ..models.user import User
from ..services.prediction_feedback_service import PredictionFeedbackService
from ..services.okr_cascade_service import OkrCascadeService
from ..services.agent_event_processor import AgentEventProcessor

logger = structlog.get_logger()
router = APIRouter()


# ── Pydantic Schemas ──────────────────────────────────────────────────────────


class AutoCascadeRequest(BaseModel):
    """一键目标级联请求"""
    brand_id: str = Field(..., description="品牌ID")
    annual_objective_id: str = Field(..., description="年度目标ID")
    store_ids: List[str] = Field(default_factory=list, description="目标门店ID列表，为空则自动选择品牌下所有活跃门店")


# ── Routes — 预测准确率 ──────────────────────────────────────────────────────


@router.get(
    "/predictions/{store_id}/accuracy",
    summary="预测准确率",
    tags=["predictions"],
)
async def get_prediction_accuracy(
    store_id: str,
    prediction_type: str = Query(default="revenue", description="预测类型: revenue|order_count|customer_flow"),
    days: int = Query(default=30, ge=1, le=365, description="回看天数"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """获取门店预测准确率，包含MAPE/RMSE等指标"""
    await validate_store_brand(store_id, current_user)

    try:
        service = PredictionFeedbackService(db)
        result = await service.get_prediction_accuracy(
            store_id=store_id,
            prediction_type=prediction_type,
            days=days,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))

    logger.info(
        "prediction_accuracy_fetched",
        store_id=store_id,
        prediction_type=prediction_type,
        days=days,
        mape=result.get("mape"),
    )

    return {
        "store_id": store_id,
        "prediction_type": prediction_type,
        "days": days,
        "mape": result.get("mape"),
        "rmse": result.get("rmse"),
        "accuracy_pct": result.get("accuracy_pct"),
        "sample_count": result.get("sample_count", 0),
        "trend": result.get("trend", []),
    }


@router.get(
    "/predictions/brand/{brand_id}/dashboard",
    summary="品牌预测总览",
    tags=["predictions"],
)
async def get_accuracy_dashboard(
    brand_id: str,
    days: int = Query(default=30, ge=1, le=365, description="回看天数"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """品牌维度的预测准确率总览，按门店和预测类型汇总"""
    if current_user.brand_id and current_user.brand_id != brand_id:
        raise HTTPException(status_code=403, detail="无权访问该品牌数据")

    try:
        service = PredictionFeedbackService(db)
        result = await service.get_accuracy_dashboard(
            brand_id=brand_id,
            days=days,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))

    logger.info(
        "prediction_dashboard_fetched",
        brand_id=brand_id,
        days=days,
        store_count=result.get("store_count", 0),
    )

    return {
        "brand_id": brand_id,
        "days": days,
        "overall_accuracy_pct": result.get("overall_accuracy_pct"),
        "store_count": result.get("store_count", 0),
        "by_store": result.get("by_store", []),
        "by_type": result.get("by_type", []),
    }


@router.post(
    "/predictions/{store_id}/generate",
    summary="手动生成预测",
    tags=["predictions"],
)
async def generate_predictions(
    store_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """手动触发门店预测生成（营收/客流/订单量）"""
    await validate_store_brand(store_id, current_user)

    # 从stores表获取brand_id
    store_row = await db.execute(
        text("SELECT brand_id FROM stores WHERE id = :sid AND is_active = TRUE"),
        {"sid": store_id},
    )
    store = store_row.mappings().first()
    if not store:
        raise HTTPException(status_code=404, detail="门店不存在或已停用")

    brand_id = store["brand_id"]

    try:
        service = PredictionFeedbackService(db)
        result = await service.generate_predictions(
            store_id=store_id,
            brand_id=brand_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    logger.info(
        "predictions_generated",
        store_id=store_id,
        brand_id=brand_id,
        prediction_count=result.get("prediction_count", 0),
    )

    return {
        "store_id": store_id,
        "brand_id": brand_id,
        "status": "generated",
        "prediction_count": result.get("prediction_count", 0),
        "predictions": result.get("predictions", []),
    }


# ── Routes — OKR级联 ─────────────────────────────────────────────────────────


@router.post(
    "/objectives/cascade/auto",
    summary="一键目标级联",
    tags=["objectives", "predictions"],
)
async def auto_cascade(
    req: AutoCascadeRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    一键将年度目标自动级联分解到各门店

    根据门店历史业绩、座位数等因素智能分配，生成季度/月度子目标。
    """
    if current_user.brand_id and current_user.brand_id != req.brand_id:
        raise HTTPException(status_code=403, detail="无权操作该品牌目标")

    try:
        service = OkrCascadeService(db)
        result = await service.auto_cascade_full(
            brand_id=req.brand_id,
            annual_objective_id=req.annual_objective_id,
            store_ids=req.store_ids,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))

    logger.info(
        "okr_cascade_completed",
        brand_id=req.brand_id,
        annual_objective_id=req.annual_objective_id,
        store_count=result.get("store_count", 0),
        objective_count=result.get("objective_count", 0),
    )

    return {
        "brand_id": req.brand_id,
        "annual_objective_id": req.annual_objective_id,
        "status": "cascaded",
        "store_count": result.get("store_count", 0),
        "objective_count": result.get("objective_count", 0),
        "stores": result.get("stores", []),
    }


@router.get(
    "/objectives/cascade/{brand_id}/health",
    summary="级联健康检查",
    tags=["objectives", "predictions"],
)
async def check_cascade_health(
    brand_id: str,
    fiscal_year: int = Query(default=2026, description="财年"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    检查品牌目标级联的健康度

    包含：子目标覆盖率、分解偏差、缺失门店等诊断信息。
    """
    if current_user.brand_id and current_user.brand_id != brand_id:
        raise HTTPException(status_code=403, detail="无权访问该品牌数据")

    try:
        service = OkrCascadeService(db)
        result = await service.check_cascade_health(
            brand_id=brand_id,
            fiscal_year=fiscal_year,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))

    logger.info(
        "cascade_health_checked",
        brand_id=brand_id,
        fiscal_year=fiscal_year,
        health_score=result.get("health_score"),
    )

    return {
        "brand_id": brand_id,
        "fiscal_year": fiscal_year,
        "health_score": result.get("health_score"),
        "coverage_pct": result.get("coverage_pct"),
        "issues": result.get("issues", []),
        "missing_stores": result.get("missing_stores", []),
        "deviation_summary": result.get("deviation_summary"),
    }


@router.get(
    "/objectives/{brand_id}/deviations",
    summary="目标偏差预警",
    tags=["objectives", "predictions"],
)
async def check_objective_deviations(
    brand_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    检测品牌下各门店目标的偏差预警

    对比实际值与目标值，标记偏差超阈值的目标，生成预警和建议动作。
    """
    if current_user.brand_id and current_user.brand_id != brand_id:
        raise HTTPException(status_code=403, detail="无权访问该品牌数据")

    try:
        processor = AgentEventProcessor(db)
        result = await processor.check_objective_deviations(brand_id=brand_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))

    logger.info(
        "objective_deviations_checked",
        brand_id=brand_id,
        deviation_count=len(result.get("deviations", [])),
    )

    return {
        "brand_id": brand_id,
        "deviation_count": len(result.get("deviations", [])),
        "deviations": result.get("deviations", []),
        "alerts": result.get("alerts", []),
        "recommended_actions": result.get("recommended_actions", []),
    }
