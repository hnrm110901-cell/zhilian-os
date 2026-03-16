"""
评论行动引擎 API 路由
前缀: /api/v1/review-actions

提供规则 CRUD、批量处理、执行日志查询和统计接口
"""

from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db_session
from src.core.dependencies import require_role
from src.models.user import UserRole
from src.services.review_action_service import review_action_service

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/review-actions", tags=["review-actions"])


# ── Pydantic 请求模型 ────────────────────────────────────────────────


class CreateRuleRequest(BaseModel):
    """创建规则请求"""

    brand_id: str
    rule_name: str = Field(..., max_length=100)
    trigger_condition: Dict[str, Any] = Field(default_factory=dict)
    action_type: str = Field(..., description="auto_reply/alert_manager/create_task/signal_bus/wechat_notify")
    action_config: Dict[str, Any] = Field(default_factory=dict)
    is_enabled: bool = True
    priority: int = 0


class UpdateRuleRequest(BaseModel):
    """更新规则请求"""

    rule_name: Optional[str] = None
    trigger_condition: Optional[Dict[str, Any]] = None
    action_type: Optional[str] = None
    action_config: Optional[Dict[str, Any]] = None
    is_enabled: Optional[bool] = None
    priority: Optional[int] = None


class BatchProcessRequest(BaseModel):
    """批量处理请求"""

    brand_id: str


# ── 规则管理端点 ──────────────────────────────────────────────────────


@router.post("/rules")
async def create_rule(
    req: CreateRuleRequest,
    _user=Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """创建评论行动规则"""
    valid_types = {"auto_reply", "alert_manager", "create_task", "signal_bus", "wechat_notify"}
    if req.action_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"无效的 action_type，可选: {', '.join(valid_types)}")

    result = await review_action_service.create_rule(db, req.model_dump())
    return result


@router.get("/rules")
async def list_rules(
    brand_id: str = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _user=Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """分页查询评论行动规则"""
    return await review_action_service.list_rules(db, brand_id, page, page_size)


@router.put("/rules/{rule_id}")
async def update_rule(
    rule_id: str,
    req: UpdateRuleRequest,
    _user=Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """更新评论行动规则"""
    data = {k: v for k, v in req.model_dump().items() if v is not None}
    if not data:
        raise HTTPException(status_code=400, detail="未提供任何更新字段")

    result = await review_action_service.update_rule(db, rule_id, data)
    if result is None:
        raise HTTPException(status_code=404, detail="规则不存在")
    return result


@router.delete("/rules/{rule_id}")
async def delete_rule(
    rule_id: str,
    _user=Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """删除评论行动规则"""
    deleted = await review_action_service.delete_rule(db, rule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="规则不存在")
    return {"success": True, "message": "规则已删除"}


# ── 批量处理 ──────────────────────────────────────────────────────────


@router.post("/process")
async def batch_process(
    req: BatchProcessRequest,
    _user=Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """批量处理未读评论，执行匹配的行动规则"""
    result = await review_action_service.batch_process_unread(db, req.brand_id)
    return result


# ── 日志查询 ──────────────────────────────────────────────────────────


@router.get("/logs")
async def get_logs(
    brand_id: str = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    action_type: Optional[str] = Query(None),
    _user=Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """查询行动执行日志"""
    return await review_action_service.get_action_logs(
        db,
        brand_id,
        page,
        page_size,
        action_type,
    )


# ── 统计 ──────────────────────────────────────────────────────────────


@router.get("/stats")
async def get_stats(
    brand_id: str = Query(...),
    _user=Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """获取行动引擎统计数据"""
    return await review_action_service.get_stats(db, brand_id)
