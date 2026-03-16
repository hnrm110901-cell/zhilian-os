"""
指挥中心 API — Command Center
跨系统聚合仪表盘：实时概览、事件流、KPI矩阵、行动调度、系统脉搏。
仅限平台管理员(ADMIN)访问。
"""

from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import require_role
from ..models.user import User, UserRole
from ..services.command_center_service import command_center_service

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/command-center", tags=["指挥中心"])


# ── 请求模型 ──────────────────────────────────────────────────────────────────


class DispatchRequest(BaseModel):
    """行动调度请求"""

    action_type: str  # sync_all / run_closing / check_procurement / generate_alerts
    params: dict = {}


# ── 端点 ──────────────────────────────────────────────────────────────────────


@router.get("/overview")
async def get_live_overview(
    brand_id: str = Query(..., description="品牌ID"),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """实时概览 — 今日营收/订单/合规/集成/告警/待办"""
    try:
        return await command_center_service.get_live_overview(db, brand_id)
    except Exception as e:
        logger.error("command_center.overview.error", error=str(e))
        raise HTTPException(status_code=500, detail=f"获取概览失败: {str(e)}")


@router.get("/event-stream")
async def get_event_stream(
    brand_id: str = Query(..., description="品牌ID"),
    limit: int = Query(50, ge=1, le=200, description="返回事件数量上限"),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """跨系统事件流 — 最近24h内各系统事件，按时间倒序"""
    try:
        return await command_center_service.get_event_stream(db, brand_id, limit)
    except Exception as e:
        logger.error("command_center.event_stream.error", error=str(e))
        raise HTTPException(status_code=500, detail=f"获取事件流失败: {str(e)}")


@router.get("/kpi-matrix")
async def get_kpi_matrix(
    brand_id: str = Query(..., description="品牌ID"),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """KPI矩阵 — 营收/运营/合规/集成多维指标"""
    try:
        return await command_center_service.get_kpi_matrix(db, brand_id)
    except Exception as e:
        logger.error("command_center.kpi_matrix.error", error=str(e))
        raise HTTPException(status_code=500, detail=f"获取KPI矩阵失败: {str(e)}")


@router.post("/dispatch")
async def dispatch_action(
    body: DispatchRequest,
    brand_id: str = Query(..., description="品牌ID"),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """行动调度 — 触发全量同步/日结/采购检查/告警生成"""
    try:
        result = await command_center_service.dispatch_action(db, brand_id, body.action_type, body.params)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("message", "操作失败"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("command_center.dispatch.error", error=str(e))
        raise HTTPException(status_code=500, detail=f"行动调度失败: {str(e)}")


@router.get("/pulse")
async def get_system_pulse(
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """系统脉搏 — 平台级全局指标（品牌数/门店数/订单数/集成状态）"""
    try:
        return await command_center_service.get_system_pulse(db)
    except Exception as e:
        logger.error("command_center.pulse.error", error=str(e))
        raise HTTPException(status_code=500, detail=f"获取系统脉搏失败: {str(e)}")
