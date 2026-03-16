"""
老板多店版简报 + 执行闭环反馈 API
HQ Briefing & Execution Feedback API

端点：
  GET  /api/v1/briefing/hq                          — 获取多店简报（不推送）
  POST /api/v1/briefing/hq/push                     — 立即推送企微
  POST /api/v1/briefing/hq/dry-run                  — 生成但不推送
  POST /api/v1/briefing/hq/celery-push              — Celery 异步推送

  POST /api/v1/decisions/{decision_id}/feedback     — 提交执行反馈
  GET  /api/v1/decisions/{store_id}/feedback-history — 查询反馈历史
"""

from typing import Literal, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.user import User

router = APIRouter(tags=["hq_briefing"])
logger = structlog.get_logger()


# ── Request Models ────────────────────────────────────────────────────────────


class ExecutionFeedbackRequest(BaseModel):
    store_id: str = Field(..., description="门店 ID")
    outcome: Literal["success", "failure", "partial"] = Field(..., description="执行结果")
    actual_impact_yuan: float = Field(..., description="实际¥影响（元）")
    note: Optional[str] = Field(None, description="备注")


# ── HQ 简报端点 ───────────────────────────────────────────────────────────────


@router.get("/api/v1/briefing/hq", summary="获取多店简报（老板版）")
async def get_hq_briefing(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    返回当日多店简报：各店健康分排名、预警门店、全局Top3决策、合并营收。
    """
    from ..services.hq_briefing_service import generate_hq_briefing

    try:
        return await generate_hq_briefing(db)
    except Exception as exc:
        logger.error("hq_briefing_api.get_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/api/v1/briefing/hq/push", summary="立即推送老板版多店简报")
async def push_hq_briefing(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    from ..services.hq_briefing_service import push_hq_briefing

    try:
        return await push_hq_briefing(db, dry_run=False)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/api/v1/briefing/hq/dry-run", summary="生成多店简报（不推送）")
async def dry_run_hq_briefing(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    from ..services.hq_briefing_service import push_hq_briefing

    try:
        return await push_hq_briefing(db, dry_run=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/api/v1/briefing/hq/celery-push", summary="Celery 异步推送多店简报")
async def trigger_hq_celery(
    current_user: User = Depends(get_current_active_user),
):
    try:
        from ..core.celery_tasks import push_hq_daily_briefing

        task = push_hq_daily_briefing.apply_async(queue="default", priority=8)
        return {"task_id": task.id, "status": "queued"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── 执行反馈端点 ──────────────────────────────────────────────────────────────


@router.post(
    "/api/v1/decisions/{decision_id}/feedback",
    summary="提交决策执行反馈（闭环）",
)
async def submit_feedback(
    decision_id: str,
    body: ExecutionFeedbackRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    提交决策执行结果，更新 decision_log 并触发健康分重算。

    返回 before/after 健康分对比，直观展示闭环价值。

    - **outcome**: success / failure / partial
    - **actual_impact_yuan**: 实际¥影响（正数=收益，负数=损失）
    """
    from ..services.execution_feedback_service import submit_execution_feedback

    try:
        return await submit_execution_feedback(
            decision_id=decision_id,
            store_id=body.store_id,
            outcome=body.outcome,
            actual_impact_yuan=body.actual_impact_yuan,
            executor_id=str(current_user.id),
            note=body.note,
            db=db,
        )
    except Exception as exc:
        logger.error("feedback_api.submit_failed", decision_id=decision_id, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get(
    "/api/v1/decisions/{store_id}/feedback-history",
    summary="查询执行反馈历史",
)
async def get_feedback_history(
    store_id: str,
    days: int = Query(30, ge=7, le=90, description="查询天数"),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    返回门店近 N 天的决策执行反馈记录，含：
    - 总决策数 / 成功数 / 采纳率
    - 累计成功¥影响
    - 逐条执行明细
    """
    from ..services.execution_feedback_service import get_feedback_history

    try:
        return await get_feedback_history(store_id, db, days=days, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
