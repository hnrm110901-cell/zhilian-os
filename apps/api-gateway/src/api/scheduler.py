"""
Scheduler API - 定时任务管理API

Provides manual trigger endpoints for Celery Beat tasks so ops can
fire them on-demand without waiting for the next scheduled run.
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from pydantic import BaseModel

from src.core.dependencies import get_current_user
from src.models.user import User

router = APIRouter(prefix="/api/v1/scheduler")

# Map of safe task names to their Celery task paths
ALLOWED_TASKS = {
    "detect_revenue_anomaly": "src.core.celery_tasks.detect_revenue_anomaly",
    "generate_daily_report_with_rag": "src.core.celery_tasks.generate_daily_report_with_rag",
    "check_inventory_alert": "src.core.celery_tasks.check_inventory_alert",
    "generate_and_send_daily_report": "src.core.celery_tasks.generate_and_send_daily_report",
    "perform_daily_reconciliation": "src.core.celery_tasks.perform_daily_reconciliation",
}


class TriggerRequest(BaseModel):
    store_id: Optional[str] = None   # None = all stores
    report_date: Optional[str] = None  # YYYY-MM-DD, for daily report tasks


@router.post("/trigger/{task_name}")
async def trigger_task(
    task_name: str,
    body: TriggerRequest = TriggerRequest(),
    current_user: User = Depends(get_current_user),
):
    """
    手动触发定时任务

    支持的任务:
    - **detect_revenue_anomaly**: 营收异常检测（每15分钟自动执行）
    - **generate_daily_report_with_rag**: 昨日简报生成（每天6AM自动执行）
    - **check_inventory_alert**: 库存预警检查（每天10AM自动执行）
    - **generate_and_send_daily_report**: 营业日报（每天22:30自动执行）
    - **perform_daily_reconciliation**: POS对账（每天3AM自动执行）

    store_id为空时对所有门店执行。
    """
    if task_name not in ALLOWED_TASKS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown task '{task_name}'. Allowed: {list(ALLOWED_TASKS)}"
        )

    from src.core.celery_app import celery_app

    task_path = ALLOWED_TASKS[task_name]

    # Build kwargs — only pass what the task accepts
    kwargs = {}
    if body.store_id:
        kwargs["store_id"] = body.store_id
    if body.report_date and task_name in (
        "generate_and_send_daily_report",
        "generate_daily_report_with_rag",
    ):
        kwargs["report_date"] = body.report_date

    result = celery_app.send_task(task_path, kwargs=kwargs, queue="default")

    return {
        "task_name": task_name,
        "task_id": result.id,
        "store_id": body.store_id or "all",
        "status": "queued",
    }


@router.get("/status/{task_id}")
async def get_task_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    查询任务执行状态

    返回 PENDING / STARTED / SUCCESS / FAILURE / RETRY
    """
    from src.core.celery_app import celery_app
    from celery.result import AsyncResult

    result = AsyncResult(task_id, app=celery_app)

    response = {
        "task_id": task_id,
        "status": result.status,
    }

    if result.successful():
        response["result"] = result.result
    elif result.failed():
        response["error"] = str(result.result)

    return response


@router.get("/schedule")
async def get_beat_schedule(
    current_user: User = Depends(get_current_user),
):
    """
    查看当前 Beat 调度配置
    """
    from src.core.celery_app import celery_app

    schedule = {}
    for name, entry in celery_app.conf.beat_schedule.items():
        schedule[name] = {
            "task": entry["task"],
            "schedule": str(entry["schedule"]),
            "queue": entry.get("options", {}).get("queue", "default"),
        }

    return {"beat_schedule": schedule}
