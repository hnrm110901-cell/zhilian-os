"""
联邦学习API端点
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

from src.services.federated_learning_service import (
    FederatedLearningService,
    FederatedLearningCoordinator,
    ModelType,
    AggregationMethod,
)
from src.core.dependencies import get_current_user
from src.models.user import User

router = APIRouter(prefix="/federated-learning", tags=["federated-learning"])


# Pydantic模型
class TrainingRoundCreate(BaseModel):
    model_type: ModelType = Field(..., description="模型类型")
    target_stores: List[str] = Field(..., description="目标门店列表")
    config: Dict[str, Any] = Field(default_factory=dict, description="训练配置")


class ModelUpload(BaseModel):
    round_id: str = Field(..., description="训练轮次ID")
    model_parameters: Dict[str, Any] = Field(..., description="模型参数")
    training_metrics: Dict[str, float] = Field(..., description="训练指标")


class AggregationRequest(BaseModel):
    round_id: str = Field(..., description="训练轮次ID")
    method: AggregationMethod = Field(
        AggregationMethod.FEDAVG,
        description="聚合方法"
    )


# 全局协调器实例
coordinator = FederatedLearningCoordinator()


@router.post("/rounds")
async def create_training_round(
    request: TrainingRoundCreate,
    current_user: User = Depends(get_current_user),
):
    """
    创建训练轮次

    需要管理员权限
    """
    if current_user.role not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    round_id = await coordinator.start_training_round(
        model_type=request.model_type,
        target_stores=request.target_stores,
        config=request.config,
    )

    return {
        "round_id": round_id,
        "status": "created",
        "message": "Training round created successfully",
    }


@router.post("/rounds/{round_id}/join")
async def join_training_round(
    round_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    门店加入训练轮次
    """
    service = FederatedLearningService()

    try:
        result = await service.join_training_round(round_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/rounds/{round_id}/upload")
async def upload_local_model(
    round_id: str,
    upload: ModelUpload,
    current_user: User = Depends(get_current_user),
):
    """
    上传本地训练的模型参数
    """
    service = FederatedLearningService()

    try:
        result = await service.upload_local_model(
            round_id=upload.round_id,
            model_parameters=upload.model_parameters,
            training_metrics=upload.training_metrics,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/rounds/{round_id}/aggregate")
async def aggregate_models(
    round_id: str,
    request: AggregationRequest,
    current_user: User = Depends(get_current_user),
):
    """
    聚合模型参数

    需要管理员权限
    """
    if current_user.role not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    try:
        result = await coordinator.finalize_training_round(round_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/rounds/{round_id}/status")
async def get_training_status(
    round_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    获取训练轮次状态
    """
    try:
        status = await coordinator.monitor_training_progress(round_id)
        return status
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/rounds/{round_id}/download")
async def download_global_model(
    round_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    下载全局模型
    """
    service = FederatedLearningService()

    try:
        model = await service.download_global_model(round_id)
        return model
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/rounds")
async def list_training_rounds(
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    """
    列出训练轮次
    """
    from src.core.database import get_db_session
    from src.models.federated_learning import FLTrainingRound
    from sqlalchemy import select

    async with get_db_session() as session:
        stmt = select(FLTrainingRound).order_by(FLTrainingRound.created_at.desc()).limit(50)
        if status:
            stmt = stmt.where(FLTrainingRound.status == status)
        result = await session.execute(stmt)
        fl_rounds = result.scalars().all()

    rounds = [
        {
            "round_id": r.id,
            "model_type": r.model_type,
            "status": r.status,
            "participating_stores": r.num_participating_stores or 0,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        }
        for r in fl_rounds
    ]

    return {"rounds": rounds, "total": len(rounds)}
