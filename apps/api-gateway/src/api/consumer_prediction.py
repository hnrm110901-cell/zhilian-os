"""
消费者预测 API — Phase 4

端点列表：
  GET  /api/v1/consumer/{consumer_id}/prediction/{brand_id}   单人预测（全部类型）
  POST /api/v1/brand/{brand_id}/predictions/batch-run         触发批量预测
  GET  /api/v1/brand/{brand_id}/predictions/at-risk           高风险流失列表
  GET  /api/v1/brand/{brand_id}/predictions/upgrade-ready     接近升级列表
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import get_current_user
from src.services.consumer_prediction_service import consumer_prediction_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Consumer Prediction"])


# ── Request / Response Schemas ───────────────────────────────────────────────


class BatchRunRequest(BaseModel):
    prediction_types: List[str] = Field(
        default=["churn", "upgrade", "clv"],
        description="预测类型子集，可选: churn / upgrade / clv",
    )


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/consumer/{consumer_id}/prediction/{brand_id}")
async def get_consumer_prediction(
    consumer_id: str,
    brand_id: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    单人全量预测：流失风险 + 升级概率 + CLV。
    数据来源：brand_consumer_profiles（实时计算，不依赖快照）。
    """
    try:
        churn = await consumer_prediction_service.predict_churn_risk(
            consumer_id, brand_id, db
        )
        upgrade = await consumer_prediction_service.predict_upgrade_probability(
            consumer_id, brand_id, db
        )
        clv = await consumer_prediction_service.estimate_clv(
            consumer_id, brand_id, db
        )
        return {
            "consumer_id": consumer_id,
            "brand_id": brand_id,
            "churn_risk": churn,
            "upgrade": upgrade,
            "clv": clv,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("prediction_failed", consumer_id=consumer_id, error=str(e))
        raise HTTPException(status_code=500, detail="预测服务暂时不可用")


@router.post("/brand/{brand_id}/predictions/batch-run")
async def batch_run_predictions(
    brand_id: str,
    req: BatchRunRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    触发品牌维度批量预测，结果写入 consumer_prediction_snapshots 表。
    建议通过 Celery 定时任务调用，也支持手动触发。
    """
    valid_types = {"churn", "upgrade", "clv"}
    invalid = set(req.prediction_types) - valid_types
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"无效的 prediction_types: {invalid}，有效值为 {valid_types}",
        )

    try:
        result = await consumer_prediction_service.batch_predict_brand_consumers(
            brand_id=brand_id,
            prediction_types=req.prediction_types,
            session=db,
        )
        return result
    except Exception as e:
        logger.error("batch_predict_failed", brand_id=brand_id, error=str(e))
        raise HTTPException(status_code=500, detail="批量预测失败")


@router.get("/brand/{brand_id}/predictions/at-risk")
async def get_at_risk_consumers(
    brand_id: str,
    risk_threshold: float = Query(default=0.7, ge=0.0, le=1.0, description="流失风险阈值"),
    limit: int = Query(default=100, ge=1, le=500),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取高流失风险会员列表（从 consumer_prediction_snapshots 读取）。
    按 churn_score 倒序排列。
    """
    try:
        consumers = await consumer_prediction_service.get_at_risk_consumers(
            brand_id=brand_id,
            session=db,
            risk_threshold=risk_threshold,
            limit=limit,
        )
        return {
            "brand_id": brand_id,
            "risk_threshold": risk_threshold,
            "count": len(consumers),
            "consumers": consumers,
        }
    except Exception as e:
        logger.error("at_risk_query_failed", brand_id=brand_id, error=str(e))
        raise HTTPException(status_code=500, detail="查询失败")


@router.get("/brand/{brand_id}/predictions/upgrade-ready")
async def get_upgrade_ready_consumers(
    brand_id: str,
    probability_threshold: float = Query(default=0.6, ge=0.0, le=1.0, description="升级概率阈值"),
    limit: int = Query(default=100, ge=1, le=500),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取接近升级的会员列表（从 consumer_prediction_snapshots 读取）。
    按 upgrade_probability 倒序排列。
    """
    try:
        consumers = await consumer_prediction_service.get_upgrade_ready_consumers(
            brand_id=brand_id,
            session=db,
            probability_threshold=probability_threshold,
            limit=limit,
        )
        return {
            "brand_id": brand_id,
            "probability_threshold": probability_threshold,
            "count": len(consumers),
            "consumers": consumers,
        }
    except Exception as e:
        logger.error("upgrade_ready_query_failed", brand_id=brand_id, error=str(e))
        raise HTTPException(status_code=500, detail="查询失败")
