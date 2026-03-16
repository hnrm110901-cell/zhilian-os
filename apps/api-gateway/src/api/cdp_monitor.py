"""
CDP Monitor API — 消费者数据平台监控

端点：
  GET  /monitor/dashboard           — CDP综合仪表盘
  GET  /monitor/rfm-distribution    — RFM等级分布
  POST /monitor/full-backfill       — 触发全量回填管道（同步）
  POST /monitor/full-backfill/async — 触发全量回填管道（异步Celery）
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.core.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/cdp/monitor", tags=["CDP-Monitor"])


@router.get("/dashboard")
async def get_cdp_dashboard(
    store_id: Optional[str] = Query(None),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """CDP综合仪表盘（填充率+消费者统计+RFM分布+偏差率+KPI达标）"""
    from src.services.cdp_monitor_service import cdp_monitor_service

    return await cdp_monitor_service.get_dashboard(db, store_id=store_id)


@router.get("/rfm-distribution")
async def get_rfm_distribution(
    store_id: Optional[str] = Query(None),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """RFM等级分布（S1-S5各等级人数和占比）"""
    from src.services.cdp_monitor_service import cdp_monitor_service

    return await cdp_monitor_service.get_rfm_distribution(db, store_id=store_id)


class FullBackfillRequest(BaseModel):
    store_id: Optional[str] = None
    batch_size: int = 500


@router.post("/full-backfill")
async def run_full_backfill(
    req: FullBackfillRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    全量回填管道（同步执行）

    步骤：订单回填 → 会员回填 → RFM重算 → 偏差校验
    返回：各步骤结果 + 最终KPI达标状态
    """
    from src.services.cdp_monitor_service import cdp_monitor_service

    return await cdp_monitor_service.run_full_backfill(
        db,
        store_id=req.store_id,
        batch_size=req.batch_size,
    )


@router.post("/full-backfill/async")
async def trigger_async_backfill(
    req: FullBackfillRequest,
    user=Depends(get_current_user),
):
    """
    触发异步全量回填（Celery任务）

    适用于大数据量场景，不阻塞请求
    """
    from src.core.celery_app import celery_app

    task = celery_app.send_task(
        "src.core.celery_tasks.cdp_full_backfill",
        kwargs={"store_id": req.store_id, "batch_size": req.batch_size},
    )
    return {
        "task_id": task.id,
        "status": "submitted",
        "message": "全量回填已提交，可通过任务ID查询进度",
    }
