"""
Agent OKR API — P1 统一量化日志
前缀: /api/v1/agent-okr
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.services.agent_okr_service import agent_okr_service

router = APIRouter(prefix="/api/v1/agent-okr")


class LogRecommendationIn(BaseModel):
    brand_id: str
    store_id: str
    agent_name: str
    action_type: str
    recommendation_summary: str
    recommendation_yuan: float = 0.0
    confidence: float = 0.8
    priority: str = "P2"
    source_record_id: Optional[str] = None


class RecordAdoptionIn(BaseModel):
    log_id: str
    adopted: bool


class VerifyOutcomeIn(BaseModel):
    log_id: str
    actual_outcome_yuan: float


@router.post("/log")
async def log_recommendation(
    payload: LogRecommendationIn,
    db: AsyncSession = Depends(get_db),
):
    """记录 Agent 推送的建议"""
    log_id = await agent_okr_service.log_recommendation(
        db=db, **payload.model_dump()
    )
    await db.commit()
    return {"log_id": log_id, "message": "建议已记录"}


@router.post("/adoption")
async def record_adoption(
    payload: RecordAdoptionIn,
    db: AsyncSession = Depends(get_db),
):
    """记录用户响应（接受/拒绝）"""
    result = await agent_okr_service.record_adoption(
        db=db, log_id=payload.log_id, adopted=payload.adopted
    )
    await db.commit()
    return result


@router.post("/verify-outcome")
async def verify_outcome(
    payload: VerifyOutcomeIn,
    db: AsyncSession = Depends(get_db),
):
    """回填实际效果，计算预测误差"""
    result = await agent_okr_service.verify_outcome(
        db=db, log_id=payload.log_id, actual_outcome_yuan=payload.actual_outcome_yuan
    )
    await db.commit()
    return result


@router.get("/summary")
async def get_okr_summary(
    brand_id: str = Query(...),
    store_id: Optional[str] = Query(None),
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
):
    """获取所有 Agent 的 OKR 达成概览"""
    return await agent_okr_service.get_okr_summary(
        db=db, brand_id=brand_id, store_id=store_id, days=days
    )


@router.get("/logs")
async def get_recent_logs(
    brand_id: str = Query(...),
    store_id: Optional[str] = Query(None),
    agent_name: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """获取近期 Agent 响应日志"""
    logs = await agent_okr_service.get_recent_logs(
        db=db, brand_id=brand_id, store_id=store_id,
        agent_name=agent_name, status=status, limit=limit
    )
    return {"logs": logs, "count": len(logs)}


@router.post("/snapshot")
async def compute_daily_snapshot(
    brand_id: str = Query(...),
    target_date: date = Query(default_factory=date.today),
    db: AsyncSession = Depends(get_db),
):
    """手动触发日快照计算（生产环境由 Celery Beat 自动触发）"""
    result = await agent_okr_service.compute_daily_snapshot(
        db=db, brand_id=brand_id, target_date=target_date
    )
    await db.commit()
    return result
