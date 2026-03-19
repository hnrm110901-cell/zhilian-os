# apps/api-gateway/src/api/sm_marketing_tasks.py
"""店长端营销任务 API — P3"""

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from ..core.dependencies import get_db, get_current_user
from ..models.user import User
from ..models.marketing_task import MarketingTask, MarketingTaskAssignment

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/sm/marketing-tasks", tags=["SM-营销任务"])


@router.get("", summary="获取本店营销任务")
async def list_store_assignments(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """返回当前用户所属门店的营销任务分配列表"""
    stmt = (
        select(MarketingTaskAssignment, MarketingTask)
        .join(MarketingTask, MarketingTask.id == MarketingTaskAssignment.task_id)
        .where(MarketingTaskAssignment.store_id == current_user.store_id)
        .order_by(MarketingTaskAssignment.created_at.desc())
    )
    result = await db.execute(stmt)
    rows = result.all()
    return [
        {
            "id": str(a.id),
            "task_title": t.title,
            "status": a.status,
            "target_count": a.target_count or 0,
            "completed_count": a.completed_count or 0,
            "deadline": t.deadline.isoformat() if t.deadline else None,
        }
        for a, t in rows
    ]
