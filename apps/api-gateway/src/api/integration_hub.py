"""
Integration Hub API
集成中心 API — 查看所有外部集成的健康状态和同步统计
"""

from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import require_role
from ..models.user import User, UserRole
from ..services.integration_hub_service import integration_hub_service

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/integration-hub", tags=["集成中心"])


# ── 请求模型 ──────────────────────────────────────────────────────────────────


class SyncEventRequest(BaseModel):
    """同步事件请求"""

    success: bool
    error_msg: Optional[str] = None


class UpdateStatusRequest(BaseModel):
    """状态更新请求"""

    status: str
    error_msg: Optional[str] = None


# ── 端点 ──────────────────────────────────────────────────────────────────────


@router.get("/")
async def get_all_statuses(
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """获取所有集成状态"""
    return await integration_hub_service.get_all_statuses(db)


@router.get("/summary")
async def get_dashboard_summary(
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """获取仪表盘概览：总数、健康/异常计数、今日同步量、近期错误"""
    return await integration_hub_service.get_dashboard_summary(db)


@router.get("/categories")
async def get_category_summary(
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """按分类汇总健康状态"""
    return await integration_hub_service.get_category_summary(db)


@router.post("/health-check")
async def trigger_health_check(
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """触发全量健康探测（检查配置 + 同步时效）"""
    results = await integration_hub_service.health_check_all(db)
    return {"message": "健康检查完成", "results": results}


@router.post("/{key}/sync")
async def record_sync_event(
    key: str,
    request: SyncEventRequest,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """记录同步事件（供其他服务内部调用）"""
    try:
        result = await integration_hub_service.record_sync(
            db,
            key,
            success=request.success,
            error_msg=request.error_msg,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/reset-daily")
async def reset_daily_counts(
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """重置每日同步/错误计数器（凌晨定时任务调用）"""
    count = await integration_hub_service.reset_daily_counts(db)
    return {"message": f"已重置 {count} 条记录的每日计数"}
