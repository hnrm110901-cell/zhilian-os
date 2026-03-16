"""
店长版每日简报 API
Store Manager Daily Briefing API

端点：
  GET  /api/v1/briefing/sm/{store_id}          — 获取当日简报（不推送）
  POST /api/v1/briefing/sm/{store_id}/push     — 立即生成并推送企微
  POST /api/v1/briefing/sm/{store_id}/dry-run  — 生成但不推送（测试用）
  POST /api/v1/briefing/sm/celery-push         — 触发 Celery 异步推送全部门店
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.user import User

router = APIRouter(prefix="/api/v1/briefing", tags=["briefing"])
logger = structlog.get_logger()


@router.get("/sm/{store_id}", summary="获取店长版每日简报（结构化）")
async def get_sm_briefing(
    store_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    返回当日简报完整结构（JSON），包含：
    - 私域健康分（综合得分 + 5维度）
    - Top3 决策（¥预期影响 + 置信度）
    - 昨日经营快照（营收/成本率/损耗）
    - 流失预警数
    - 今日核心行动建议
    - push_text：企微推送正文（可直接预览）
    """
    from ..services.store_manager_briefing_service import generate_briefing

    try:
        return await generate_briefing(store_id, db)
    except Exception as exc:
        logger.error("briefing_api.get_failed", store_id=store_id, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/sm/{store_id}/push", summary="立即推送企微简报")
async def push_sm_briefing(
    store_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    立即生成并推送企微简报（同步执行，约 2-5s）。
    推送失败时返回 briefing 结构 + 错误信息，不抛 500。
    """
    from ..services.store_manager_briefing_service import push_briefing

    try:
        return await push_briefing(store_id, db, dry_run=False)
    except Exception as exc:
        logger.error("briefing_api.push_failed", store_id=store_id, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/sm/{store_id}/dry-run", summary="生成简报（不推送，测试用）")
async def dry_run_sm_briefing(
    store_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    生成简报结构但不发送企微消息（用于预览/调试）。
    返回与 push 完全相同的结构，pushed=false。
    """
    from ..services.store_manager_briefing_service import push_briefing

    try:
        return await push_briefing(store_id, db, dry_run=True)
    except Exception as exc:
        logger.error("briefing_api.dry_run_failed", store_id=store_id, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/sm/celery-push", summary="异步触发全门店简报推送（Celery）")
async def trigger_celery_briefing(
    current_user: User = Depends(get_current_active_user),
):
    """
    异步触发 Celery `push_sm_daily_briefing` 任务（覆盖全部门店）。
    立即返回 task_id，推送在后台执行。
    """
    try:
        from ..core.celery_tasks import push_sm_daily_briefing

        task = push_sm_daily_briefing.apply_async(queue="default", priority=9)
        return {"task_id": task.id, "status": "queued"}
    except Exception as exc:
        logger.error("briefing_api.celery_push_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))
