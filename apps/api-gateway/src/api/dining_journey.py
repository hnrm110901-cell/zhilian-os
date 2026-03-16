"""
全链路用餐旅程 API

覆盖消费者从预订→到店→用餐→离店→售后的完整生命周期端点。
"""

from datetime import date, time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.user import User

router = APIRouter()


# ── Request / Response Models ─────────────────────────────────────


class TableRecommendRequest(BaseModel):
    store_id: str
    party_size: int
    reservation_date: date
    reservation_time: time
    preference: Optional[str] = None  # "包厢"/"大厅"/"VIP"


class QueueToReservationRequest(BaseModel):
    queue_id: str
    table_number: Optional[str] = None


class PatrolRequest(BaseModel):
    store_id: str
    table_number: str
    patrol_by: str
    checklist_results: Dict[str, float]  # {"food_quality": 90, ...}
    issues: Optional[List[Dict[str, str]]] = None
    reservation_id: Optional[str] = None


class ReviewRequest(BaseModel):
    reservation_id: str
    review_source: str  # meituan/dianping/wecom/internal
    review_text: str
    platform_rating: Optional[int] = None


# ── Phase 1: 等位 → 预订转换 ──────────────────────────────────────


@router.post("/dining-journey/queue-to-reservation")
async def queue_to_reservation(
    req: QueueToReservationRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """等位叫号后自动转换为预订记录"""
    from ..services.dining_journey_service import convert_queue_to_reservation

    try:
        reservation = await convert_queue_to_reservation(
            session,
            req.queue_id,
            req.table_number,
        )
        await session.commit()
        return {
            "reservation_id": reservation.id,
            "status": reservation.status.value,
            "table_number": reservation.table_number,
            "message": f"等位已转换为预订 {reservation.id}",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Phase 2: 智能桌台推荐 ────────────────────────────────────────


@router.post("/dining-journey/recommend-table")
async def recommend_table(
    req: TableRecommendRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """根据人数+偏好智能推荐桌台"""
    from ..services.dining_journey_service import recommend_table as _recommend

    candidates = await _recommend(
        session,
        req.store_id,
        req.party_size,
        req.reservation_date,
        req.reservation_time,
        req.preference,
    )
    return {
        "store_id": req.store_id,
        "party_size": req.party_size,
        "candidates": candidates,
        "total": len(candidates),
    }


# ── Phase 2: 到店前推送 ──────────────────────────────────────────


@router.get("/dining-journey/pre-arrival/{store_id}")
async def get_pre_arrival_list(
    store_id: str,
    hours: int = Query(24, description="未来N小时内的预订"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取即将到店的预订列表（用于催确认/推送）"""
    from ..services.dining_journey_service import get_pre_arrival_reservations

    upcoming = await get_pre_arrival_reservations(session, store_id, hours)
    return {
        "store_id": store_id,
        "hours_ahead": hours,
        "reservations": upcoming,
        "total": len(upcoming),
        "needs_confirmation": sum(1 for r in upcoming if r.get("needs_confirmation")),
    }


@router.post("/dining-journey/pre-arrival/{reservation_id}/push")
async def send_pre_arrival_push(
    reservation_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """为指定预订生成并发送千人千面到店前推送"""
    from ..services.dining_journey_service import generate_pre_arrival_push

    content = await generate_pre_arrival_push(session, reservation_id)
    if content.get("error"):
        raise HTTPException(status_code=404, detail=content["error"])
    return content


@router.post("/dining-journey/pre-arrival/{store_id}/batch-remind")
async def batch_send_reminders(
    store_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """批量发送到店前提醒（T-24h + T-4h）"""
    from ..services.dining_journey_service import send_pre_arrival_reminders

    result = await send_pre_arrival_reminders(session, store_id)
    return result


# ── Phase 3: 老客识别 ────────────────────────────────────────────


@router.get("/dining-journey/customer-recognition")
async def recognize_customer(
    phone: str = Query(..., description="客户手机号"),
    store_id: str = Query(..., description="门店ID"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """老客户识别 + 消费画像 + 推荐动作"""
    from ..services.dining_journey_service import recognize_returning_customer

    result = await recognize_returning_customer(session, phone, store_id)
    return result


@router.post("/dining-journey/birthday-scan/{store_id}")
async def scan_birthdays(
    store_id: str,
    horizon_days: int = Query(3, description="扫描未来N天"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """扫描即将生日的客户并触发旅程"""
    from ..services.dining_journey_service import trigger_birthday_journey

    triggered = await trigger_birthday_journey(session, store_id, horizon_days)
    return {
        "store_id": store_id,
        "horizon_days": horizon_days,
        "triggered": triggered,
        "total": len(triggered),
    }


# ── Phase 4: 巡台检查 ────────────────────────────────────────────


@router.get("/dining-journey/patrol/checklist")
async def get_patrol_checklist(
    current_user: User = Depends(get_current_active_user),
):
    """获取巡台检查模板"""
    from ..services.dining_journey_service import PATROL_CHECKLIST

    return {"checklist": PATROL_CHECKLIST}


@router.post("/dining-journey/patrol")
async def submit_patrol(
    req: PatrolRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """提交巡台检查结果"""
    from ..services.dining_journey_service import create_patrol_record

    result = await create_patrol_record(
        session,
        req.store_id,
        req.table_number,
        req.patrol_by,
        req.checklist_results,
        req.issues,
        req.reservation_id,
    )
    return result


# ── Phase 5: 满意度调查 ──────────────────────────────────────────


@router.post("/dining-journey/satisfaction/{reservation_id}")
async def trigger_satisfaction(
    reservation_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """触发离店前满意度调查"""
    from ..services.dining_journey_service import trigger_satisfaction_survey

    result = await trigger_satisfaction_survey(session, reservation_id)
    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ── Phase 6: 评价管理 + 售后 ─────────────────────────────────────


@router.post("/dining-journey/review")
async def process_review(
    req: ReviewRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """处理客户评价（情感分析 + 自动售后）"""
    from ..services.dining_journey_service import process_post_dining_review

    result = await process_post_dining_review(
        session,
        req.reservation_id,
        req.review_source,
        req.review_text,
        req.platform_rating,
    )
    return result


@router.get("/dining-journey/post-dining/{store_id}")
async def get_post_dining_dashboard(
    store_id: str,
    days: int = Query(7, description="近N天"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """离店后综合管理看板（评价+售后+跟进）"""
    from ..services.dining_journey_service import get_post_dining_summary

    result = await get_post_dining_summary(session, store_id, days)
    return result
