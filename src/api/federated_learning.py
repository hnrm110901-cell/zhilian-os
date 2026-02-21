"""
Federated Learning API Endpoints
联邦学习API端点

Phase 4: 智能优化期 (Intelligence Optimization Period)
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

from ..services.federated_learning_service import (
    FederatedLearningService,
    ModelType,
    TrainingStatus
)
from ..database import get_db
from sqlalchemy.orm import Session
import numpy as np


router = APIRouter(prefix="/api/v1/federated", tags=["federated_learning"])


# Request/Response Models
class ModelTypeEnum(str, Enum):
    """Model type enum"""
    DEMAND_FORECAST = "demand_forecast"
    PRICE_OPTIMIZATION = "price_optimization"
    STAFF_SCHEDULE = "staff_schedule"
    INVENTORY_PREDICTION = "inventory_prediction"
    CUSTOMER_PREFERENCE = "customer_preference"


class SubmitUpdateRequest(BaseModel):
    """Submit local model update request"""
    store_id: str
    model_type: ModelTypeEnum
    weights: Dict[str, List[float]]  # Serialized numpy arrays
    metrics: Dict[str, float]
    sample_count: int


class AggregateRequest(BaseModel):
    """Aggregate updates request"""
    model_type: ModelTypeEnum
    min_participants: int = 3


class DownloadModelRequest(BaseModel):
    """Download global model request"""
    store_id: str
    model_type: ModelTypeEnum


# API Endpoints
@router.post("/update/submit")
async def submit_local_update(
    request: SubmitUpdateRequest,
    db: Session = Depends(get_db)
):
    """
    Submit local model update from store
    提交门店本地模型更新

    Stores train models locally and submit only weights (no raw data).
    This ensures privacy protection.
    """
    try:
        fl_service = FederatedLearningService(db)

        # Convert serialized weights to numpy arrays
        weights = {
            k: np.array(v) for k, v in request.weights.items()
        }

        result = fl_service.submit_local_update(
            store_id=request.store_id,
            model_type=ModelType(request.model_type.value),
            weights=weights,
            metrics=request.metrics,
            sample_count=request.sample_count
        )

        return {
            "success": True,
            **result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/aggregate")
async def aggregate_updates(
    request: AggregateRequest,
    db: Session = Depends(get_db)
):
    """
    Aggregate local updates into global model
    聚合本地更新为全局模型

    Uses Federated Averaging (FedAvg) algorithm.
    Requires minimum number of participating stores.
    """
    try:
        fl_service = FederatedLearningService(db)

        global_model = fl_service.aggregate_updates(
            model_type=ModelType(request.model_type.value),
            min_participants=request.min_participants
        )

        if not global_model:
            return {
                "success": False,
                "message": "Insufficient participants for aggregation"
            }

        return {
            "success": True,
            "model_type": global_model.model_type.value,
            "version": global_model.version,
            "participating_stores": len(global_model.participating_stores),
            "performance_metrics": global_model.performance_metrics,
            "created_at": global_model.created_at.isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/model/download")
async def download_global_model(
    request: DownloadModelRequest,
    db: Session = Depends(get_db)
):
    """
    Download global model for store
    为门店下载全局模型

    Stores download the latest global model to improve local predictions.
    """
    try:
        fl_service = FederatedLearningService(db)

        model_data = fl_service.download_global_model(
            store_id=request.store_id,
            model_type=ModelType(request.model_type.value)
        )

        if not model_data:
            raise HTTPException(
                status_code=404,
                detail="Global model not available"
            )

        # Serialize numpy arrays for JSON response
        model_data["weights"] = {
            k: v.tolist() for k, v in model_data["weights"].items()
        }

        return {
            "success": True,
            **model_data
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{model_type}")
async def get_training_status(
    model_type: ModelTypeEnum,
    db: Session = Depends(get_db)
):
    """
    Get training status for model type
    获取模型训练状态
    """
    try:
        fl_service = FederatedLearningService(db)

        status = fl_service.get_training_status(
            model_type=ModelType(model_type.value)
        )

        return {
            "success": True,
            **status
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/contribution/{store_id}/{model_type}")
async def get_store_contribution(
    store_id: str,
    model_type: ModelTypeEnum,
    db: Session = Depends(get_db)
):
    """
    Get store's contribution to federated learning
    获取门店对联邦学习的贡献
    """
    try:
        fl_service = FederatedLearningService(db)

        contribution = fl_service.get_store_contribution(
            store_id=store_id,
            model_type=ModelType(model_type.value)
        )

        return {
            "success": True,
            **contribution
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
