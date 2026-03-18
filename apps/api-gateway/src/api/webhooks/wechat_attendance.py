"""企业微信考勤打卡Webhook接入"""
import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone

from ...core.database import get_db
from ...services.hr.attendance_service import AttendanceService

logger = structlog.get_logger()
router = APIRouter()


class WechatClockEvent(BaseModel):
    """企微打卡事件（简化版）"""
    userid: str
    checkin_type: str  # "上班打卡"/"下班打卡"
    checkin_time: int  # 秒级时间戳
    location_title: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None


class WechatAttendancePayload(BaseModel):
    """企微考勤回调载荷"""
    msg_type: str = "attendance"
    event: WechatClockEvent


@router.post("/webhooks/wechat/attendance")
async def receive_attendance_webhook(
    payload: WechatAttendancePayload,
    session: AsyncSession = Depends(get_db),
):
    """接收企业微信考勤打卡回调

    验证签名 → 解析clock_in/clock_out → 写ClockRecord → 返回确认
    注：签名验证在中间件层处理，此处只做数据写入
    """
    event = payload.event

    # 映射企微打卡类型到系统clock_type
    clock_type = "in" if "上班" in event.checkin_type else "out"
    clock_time = datetime.fromtimestamp(event.checkin_time, tz=timezone.utc)

    location = None
    if event.lat and event.lng:
        location = {
            "lat": event.lat,
            "lng": event.lng,
            "address": event.location_title or "",
        }

    # userid → assignment_id 映射（通过employee_id_map查找）
    import sqlalchemy as sa
    result = await session.execute(
        sa.text(
            "SELECT ea.id FROM employment_assignments ea "
            "JOIN employee_id_map eim ON eim.person_id = ea.person_id "
            "WHERE eim.external_id = :userid AND ea.status = 'active' "
            "LIMIT 1"
        ),
        {"userid": event.userid},
    )
    row = result.scalar_one_or_none()
    if row is None:
        logger.warning("wechat_attendance.user_not_found", userid=event.userid)
        return {"status": "skipped", "reason": "user_not_mapped"}

    svc = AttendanceService()
    record = await svc.record_clock(
        assignment_id=row,
        clock_type=clock_type,
        clock_time=clock_time,
        source="wechat_work",
        session=session,
        location=location,
    )
    await session.commit()

    logger.info(
        "wechat_attendance.recorded",
        record_id=str(record.id),
        userid=event.userid,
        clock_type=clock_type,
    )
    return {"status": "ok", "record_id": str(record.id)}
