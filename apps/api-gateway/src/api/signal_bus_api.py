"""
SignalBus API — 信号路由触发端点
Signal Bus Webhook & Manual Trigger Endpoints

提供 3 个端点：
  POST /api/v1/signal-bus/bad-review/{store_id}     — 差评 webhook（外部平台回调）
  POST /api/v1/signal-bus/near-expiry/{store_id}    — 手动触发临期库存扫描
  POST /api/v1/signal-bus/large-table/{store_id}    — 大桌预订路由
  POST /api/v1/signal-bus/scan/{store_id}           — 手动触发全量周期扫描
  POST /api/v1/signal-bus/celery-scan               — 触发 Celery 异步扫描任务
"""

from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.user import User

router = APIRouter(prefix="/api/v1/signal-bus", tags=["signal_bus"])
logger = structlog.get_logger()


# ── Request Models ────────────────────────────────────────────────────────────


class BadReviewWebhook(BaseModel):
    signal_id: str = Field(..., description="信号ID（幂等键）")
    customer_id: Optional[str] = Field(None, description="顾客ID（可选）")
    rating: int = Field(..., ge=1, le=5, description="评分 1-5")
    content: str = Field("", description="差评内容")


class LargeTableReservationPayload(BaseModel):
    reservation_id: str = Field(..., description="预订ID")
    customer_phone: str = Field(..., description="顾客电话")
    customer_name: str = Field(..., description="顾客姓名")
    party_size: int = Field(..., ge=1, description="人数")
    reservation_date: str = Field(..., description="预订日期 YYYY-MM-DD")


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post(
    "/bad-review/{store_id}",
    summary="差评 Webhook → 触发私域修复旅程",
)
async def webhook_bad_review(
    store_id: str,
    body: BadReviewWebhook,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    接收外部差评平台 webhook，自动触发私域差评修复旅程（review_repair）。

    - 通过 signal_id 幂等去重，同一差评不重复触发
    - rating ≤ 3 才有实质修复行动
    """
    from ..services.signal_bus import route_bad_review

    try:
        result = await route_bad_review(
            store_id=store_id,
            signal_id=body.signal_id,
            customer_id=body.customer_id,
            rating=body.rating,
            content=body.content,
            db=db,
        )
        return {"store_id": store_id, **result}
    except Exception as exc:
        logger.error("signal_bus_api.bad_review_failed", store_id=store_id, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.post(
    "/near-expiry/{store_id}",
    summary="手动触发临期/低库存扫描 → 废料预警推送",
)
async def trigger_near_expiry(
    store_id: str,
    push: bool = True,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    扫描门店临期/低库存食材，生成预警信号并推送企微告警。

    - push=true（默认）：扫描后立即推送企微
    - push=false：仅生成信号记录，不推送
    """
    from ..services.signal_bus import route_near_expiry

    try:
        result = await route_near_expiry(store_id=store_id, db=db, push=push)
        return {"store_id": store_id, **result}
    except Exception as exc:
        logger.error("signal_bus_api.near_expiry_failed", store_id=store_id, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.post(
    "/large-table/{store_id}",
    summary="大桌预订路由 → 裂变场景识别",
)
async def route_large_table(
    store_id: str,
    body: LargeTableReservationPayload,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    ≥6人预订自动触发裂变场景识别，返回裂变场景类型、K值、运营建议。

    可由预订系统确认后回调，也可由店长手动触发。
    """
    from ..services.signal_bus import route_large_table_reservation

    try:
        result = await route_large_table_reservation(
            store_id=store_id,
            reservation_id=body.reservation_id,
            customer_phone=body.customer_phone,
            customer_name=body.customer_name,
            party_size=body.party_size,
            reservation_date=body.reservation_date,
            db=db,
        )
        return {"store_id": store_id, **result}
    except Exception as exc:
        logger.error("signal_bus_api.large_table_failed", store_id=store_id, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.post(
    "/scan/{store_id}",
    summary="手动触发门店全量 SignalBus 扫描",
)
async def manual_scan(
    store_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    手动触发指定门店的 SignalBus 周期扫描（同步执行，约 2-5s）。

    扫描内容：差评路由 + 临期/低库存 + 今日大桌预订
    """
    from ..services.signal_bus import run_periodic_scan

    try:
        result = await run_periodic_scan(store_id=store_id, db=db)
        return result
    except Exception as exc:
        logger.error("signal_bus_api.manual_scan_failed", store_id=store_id, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.post(
    "/celery-scan",
    summary="异步触发全量 Celery SignalBus 扫描任务",
)
async def trigger_celery_scan(
    current_user: User = Depends(get_current_active_user),
):
    """
    异步触发 Celery `run_signal_bus_scan` 任务（覆盖全部门店）。
    立即返回 task_id，可通过 Celery Flower 查询进度。
    """
    try:
        from ..core.celery_tasks import run_signal_bus_scan

        task = run_signal_bus_scan.apply_async(
            queue="default",
            priority=7,
        )
        return {"task_id": task.id, "status": "queued"}
    except Exception as exc:
        logger.error("signal_bus_api.celery_scan_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))
