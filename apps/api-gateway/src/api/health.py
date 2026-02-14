"""
健康检查API
"""
from fastapi import APIRouter
from pydantic import BaseModel
from datetime import datetime

router = APIRouter()


class HealthResponse(BaseModel):
    """健康检查响应"""

    status: str
    timestamp: datetime
    version: str


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """健康检查端点"""
    return HealthResponse(
        status="healthy", timestamp=datetime.now(), version="0.1.0"
    )


@router.get("/ready")
async def readiness_check():
    """就绪检查端点"""
    # TODO: 检查数据库连接、Redis连接等
    return {"status": "ready"}


@router.get("/live")
async def liveness_check():
    """存活检查端点"""
    return {"status": "alive"}
