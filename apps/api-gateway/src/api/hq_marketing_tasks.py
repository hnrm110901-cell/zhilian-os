# apps/api-gateway/src/api/hq_marketing_tasks.py
"""总部营销任务 API — P3"""

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, List, Optional
from uuid import UUID

from ..core.dependencies import get_db, get_current_user
from ..models.user import User
from ..services.marketing_task_service import marketing_task_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/hq/marketing-tasks", tags=["HQ-营销任务"])


class CreateTaskRequest(BaseModel):
    title: str
    audience_type: str  # preset | ai_query
    audience_config: Dict
    description: str = ""
    script_template: str = ""
    coupon_config: Optional[Dict] = None
    deadline: Optional[str] = None
    store_ids: List[str] = []


class AudiencePreviewRequest(BaseModel):
    audience_type: str
    audience_config: Dict
    store_ids: List[str] = []


class PublishRequest(BaseModel):
    store_ids: List[str]


class AssignRequest(BaseModel):
    assigned_to: str  # user UUID


@router.get("", summary="获取营销任务列表")
async def list_tasks(
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """总部查看营销任务列表，可选按状态过滤"""
    from ..models.marketing_task import MarketingTask
    from sqlalchemy import select

    stmt = select(MarketingTask).where(
        MarketingTask.brand_id == current_user.brand_id,
    ).order_by(MarketingTask.created_at.desc())

    if status:
        stmt = stmt.where(MarketingTask.status == status)

    result = await db.execute(stmt)
    tasks = result.scalars().all()
    return [
        {
            "id": str(t.id), "title": t.title, "status": t.status,
            "audience_type": t.audience_type,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "deadline": t.deadline.isoformat() if t.deadline else None,
        }
        for t in tasks
    ]


@router.post("", summary="创建营销任务")
async def create_task(
    req: CreateTaskRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await marketing_task_service.create_task(
        db=db, brand_id=current_user.brand_id, title=req.title,
        audience_type=req.audience_type, audience_config=req.audience_config,
        created_by=current_user.id, description=req.description,
        script_template=req.script_template, coupon_config=req.coupon_config,
    )


@router.post("/audience-preview", summary="预览人群数量")
async def audience_preview(
    req: AudiencePreviewRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await marketing_task_service.preview_audience(
        db=db, audience_type=req.audience_type,
        audience_config=req.audience_config, store_ids=req.store_ids,
    )


@router.post("/{task_id}/publish", summary="下发任务")
async def publish_task(
    task_id: str,
    req: PublishRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not req.store_ids:
        return {"success": False, "error": "store_ids 不能为空"}
    return await marketing_task_service.publish_task(
        db=db, task_id=UUID(task_id), store_ids=req.store_ids,
    )
