"""
Banquet Lifecycle REST API — 宴会全生命周期管理

端点：
  GET  /api/v1/banquet-lifecycle/{store_id}/pipeline              — 7 阶段销售漏斗视图
  PUT  /api/v1/banquet-lifecycle/{store_id}/{reservation_id}/stage — 推进阶段
  POST /api/v1/banquet-lifecycle/{store_id}/{reservation_id}/init  — 初始化阶段（进入 lead）
  GET  /api/v1/banquet-lifecycle/{store_id}/availability/{year}/{month} — 销控日历
  GET  /api/v1/banquet-lifecycle/{store_id}/funnel                — 漏斗转化率统计
  GET  /api/v1/banquet-lifecycle/{store_id}/{reservation_id}/history — 阶段变更历史
  POST /api/v1/banquet-lifecycle/{store_id}/release-locks         — 释放超时锁台
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import get_current_user
from src.models.user import User
from src.models.banquet_lifecycle import BanquetStage
from src.services.banquet_lifecycle_service import (
    BanquetLifecycleService,
    StageTransitionError,
    RoomConflictError,
)

router = APIRouter(
    prefix="/api/v1/banquet-lifecycle",
    tags=["banquet_lifecycle"],
)


# ── Pydantic Schemas ──────────────────────────────────────────────────────────

class AdvanceStageRequest(BaseModel):
    to_stage: str              = Field(..., description="目标阶段：lead/intent/room_lock/signed/preparation/service/completed/cancelled")
    reason:   Optional[str]   = Field(None, description="变更原因")
    metadata: Optional[Dict[str, Any]] = Field(None, description="额外元数据（合同编号、定金等）")


class InitStageRequest(BaseModel):
    reason: str = Field("宴会预约创建，进入销售漏斗", description="初始化原因")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get(
    "/{store_id}/pipeline",
    summary="查看宴会销售漏斗（7 阶段分组视图）",
)
async def get_pipeline(
    store_id:       str,
    event_date_gte: Optional[str] = Query(None, description="宴会日期下限 YYYY-MM-DD"),
    event_date_lte: Optional[str] = Query(None, description="宴会日期上限 YYYY-MM-DD"),
    db:  AsyncSession = Depends(get_db),
    _:   User         = Depends(get_current_user),
):
    """
    查看宴会销售漏斗：

    每个阶段展示预约列表（客户名、日期、人数、预算），
    帮助宴会销售团队掌握全局进展并识别卡单预约。

    阶段从左到右：
    商机(lead) → 意向(intent) → 锁台(room_lock) → 签约(signed) →
    准备(preparation) → 服务(service) → 完成(completed)
    """
    from datetime import date as _date

    gte = _date.fromisoformat(event_date_gte) if event_date_gte else None
    lte = _date.fromisoformat(event_date_lte) if event_date_lte else None

    svc = BanquetLifecycleService(db)
    return await svc.get_pipeline(store_id, event_date_gte=gte, event_date_lte=lte)


@router.get(
    "/{store_id}/availability/{year}/{month}",
    summary="宴会销控日历（月视图 + 吉日感知）",
)
async def get_availability_calendar(
    store_id:     str,
    year:         int,
    month:        int,
    max_capacity: int = Query(200, ge=1, description="场地最大接待人数"),
    db:  AsyncSession = Depends(get_db),
    _:   User         = Depends(get_current_user),
):
    """
    宴会销控日历（月视图），供销售顾问参考：

    - `confirmed_count`: 已签约宴会场数
    - `locked_count`:    锁台中（未签约）
    - `total_guests`:    当日预计总宾客数
    - `available`:       是否还有接待容量
    - `demand_factor`:   吉日需求倍增因子（好日子 > 1.5）
    - `is_auspicious`:   是否为「好日子」（5/20、七夕等）

    好日子 + 容量紧张 = 建议尽早锁台签约！
    """
    if not (1 <= month <= 12):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"月份无效：{month}（应为 1-12）",
        )

    svc = BanquetLifecycleService(db)
    return await svc.get_availability_calendar(
        store_id=store_id,
        year=year,
        month=month,
        max_capacity=max_capacity,
    )


@router.get(
    "/{store_id}/funnel",
    summary="漏斗转化率统计",
)
async def get_funnel_stats(
    store_id:  str,
    days_back: int = Query(90, ge=1, le=365, description="统计过去 N 天（默认 90 天）"),
    db:  AsyncSession = Depends(get_db),
    _:   User         = Depends(get_current_user),
):
    """
    宴会销售漏斗转化率统计：

    - 各阶段当前数量
    - 相邻阶段转化率（lead→intent 转化率 = intent数/lead数）
    - 平均签约周期（lead 到 signed 的平均天数）

    用于：识别哪个阶段流失最多（提升销售效率的抓手）。
    """
    svc = BanquetLifecycleService(db)
    return await svc.get_funnel_stats(store_id=store_id, days_back=days_back)


@router.get(
    "/{store_id}/{reservation_id}/history",
    summary="查看阶段变更历史",
)
async def get_stage_history(
    store_id:       str,
    reservation_id: str,
    db:  AsyncSession = Depends(get_db),
    _:   User         = Depends(get_current_user),
):
    """
    查看指定宴会预约的完整阶段变更历史（时间线）。

    记录每次阶段推进的操作人、时间和原因，提供完整审计追踪。
    """
    svc = BanquetLifecycleService(db)
    history = await svc.get_stage_history(reservation_id)
    return {
        "store_id":       store_id,
        "reservation_id": reservation_id,
        "history":        history,
        "total_changes":  len(history),
    }


@router.post(
    "/{store_id}/{reservation_id}/init",
    summary="初始化宴会阶段（进入销售漏斗）",
    status_code=status.HTTP_201_CREATED,
)
async def init_stage(
    store_id:       str,
    reservation_id: str,
    body:           InitStageRequest,
    db:   AsyncSession = Depends(get_db),
    user: User         = Depends(get_current_user),
):
    """
    将宴会预约初始化到「商机(lead)」阶段，正式进入 7 阶段销售漏斗。

    仅对 `reservation_type=banquet` 且 `banquet_stage=NULL` 的预约有效。
    """
    operator = str(user.id) if hasattr(user, "id") else "store_manager"
    svc = BanquetLifecycleService(db)
    try:
        reservation = await svc.initialize_stage(
            reservation_id=reservation_id,
            operator=operator,
            reason=body.reason,
        )
        await db.commit()
        return {
            "reservation_id": reservation_id,
            "banquet_stage":  reservation.banquet_stage,
            "message":        "宴会预约已进入销售漏斗（lead 阶段）",
        }
    except (StageTransitionError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.put(
    "/{store_id}/{reservation_id}/stage",
    summary="推进宴会阶段",
)
async def advance_stage(
    store_id:       str,
    reservation_id: str,
    body:           AdvanceStageRequest,
    db:   AsyncSession = Depends(get_db),
    user: User         = Depends(get_current_user),
):
    """
    推进宴会预约到目标阶段（严格按状态机校验合法性）：

    合法转换路径：
    ```
    lead → intent → room_lock → signed → preparation → service → completed
          ↘                 ↗
          任意阶段 → cancelled（终态）
    ```

    特殊行为：
    - `room_lock`：自动检查场地容量冲突（超限则 409）
    - `signed`：自动生成/刷新 BEO 单（异步，非致命）
    - `cancelled`：任意阶段均可取消

    返回更新后的预约信息。
    """
    # 校验目标阶段合法性
    try:
        target_stage = BanquetStage(body.to_stage)
    except ValueError:
        valid = [s.value for s in BanquetStage]
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"无效阶段 '{body.to_stage}'。有效值：{valid}",
        )

    operator = str(user.id) if hasattr(user, "id") else "store_manager"
    svc      = BanquetLifecycleService(db)

    try:
        reservation = await svc.advance_stage(
            reservation_id=reservation_id,
            to_stage=target_stage,
            operator=operator,
            reason=body.reason,
            metadata=body.metadata,
            store_id=store_id,
        )
        await db.commit()
        return {
            "reservation_id":   reservation_id,
            "banquet_stage":    reservation.banquet_stage,
            "room_locked_at":   reservation.room_locked_at.isoformat() if reservation.room_locked_at else None,
            "signed_at":        reservation.signed_at.isoformat() if reservation.signed_at else None,
            "message":          f"阶段已更新为 {reservation.banquet_stage}",
        }
    except StageTransitionError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,      detail=str(e))
    except RoomConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,      detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,     detail=str(e))


@router.post(
    "/{store_id}/release-locks",
    summary="释放超时锁台（Celery 定时任务手动触发）",
)
async def release_expired_locks(
    store_id: str,
    db:  AsyncSession = Depends(get_db),
    _:   User         = Depends(get_current_user),
):
    """
    手动触发超时锁台释放检查。

    锁台（room_lock）超过 `ROOM_LOCK_TIMEOUT_DAYS` 天（默认 7 天）
    未推进到签约（signed），自动回退到意向（intent）阶段，释放场地资源。

    通常由 Celery 定时任务每天运行；此端点供手动触发使用。
    """
    svc      = BanquetLifecycleService(db)
    released = await svc.release_expired_locks()
    await db.commit()
    return {
        "store_id":        store_id,
        "released_count":  len(released),
        "released_ids":    released,
        "message":         f"已释放 {len(released)} 个超时锁台预约",
    }
