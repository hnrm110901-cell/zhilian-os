"""AttendanceService — 考勤计算引擎

AI差异化：异常打卡模式识别（凌晨2-3点场景特殊处理）
"""
import uuid
from datetime import date, datetime, time, timezone, timedelta
from typing import Optional
import structlog
from sqlalchemy import select, update, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.hr.clock_record import ClockRecord
from ...models.hr.daily_attendance import DailyAttendance

logger = structlog.get_logger()

# 标准工作时段（餐饮行业默认）
_DEFAULT_WORK_START = time(9, 0)   # 09:00
_DEFAULT_WORK_END = time(22, 0)    # 22:00（餐饮常见长班）
_STANDARD_WORK_MINUTES = 480       # 8小时标准工时
_LATE_THRESHOLD_MINUTES = 5        # 5分钟以内不算迟到
_ANOMALY_HOURS = (2, 3)            # 凌晨2-3点打卡视为异常


class AttendanceService:

    async def record_clock(
        self,
        assignment_id: uuid.UUID,
        clock_type: str,
        clock_time: datetime,
        source: str,
        session: AsyncSession,
        location: Optional[dict] = None,
    ) -> ClockRecord:
        """记录打卡"""
        if clock_type not in ("in", "out", "break_start", "break_end"):
            raise ValueError(f"Invalid clock_type: {clock_type!r}")
        if source not in ("wechat_work", "dingtalk", "manual", "face_recognition"):
            raise ValueError(f"Invalid source: {source!r}")

        # 异常打卡检测：凌晨2-3点
        is_anomaly = clock_time.hour in _ANOMALY_HOURS

        record = ClockRecord(
            assignment_id=assignment_id,
            clock_type=clock_type,
            clock_time=clock_time,
            source=source,
            location=location,
            is_anomaly=is_anomaly,
        )
        session.add(record)
        await session.flush()
        logger.info(
            "attendance.clock_recorded",
            record_id=str(record.id),
            assignment_id=str(assignment_id),
            clock_type=clock_type,
            is_anomaly=is_anomaly,
        )
        return record

    async def calculate_daily(
        self,
        assignment_id: uuid.UUID,
        target_date: date,
        session: AsyncSession,
    ) -> DailyAttendance:
        """计算某天的考勤结果"""
        # 查找当日所有打卡记录
        day_start = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
        day_end = datetime.combine(target_date + timedelta(days=1), time.min, tzinfo=timezone.utc)

        result = await session.execute(
            select(ClockRecord)
            .where(
                ClockRecord.assignment_id == assignment_id,
                ClockRecord.clock_time >= day_start,
                ClockRecord.clock_time < day_end,
                ClockRecord.is_anomaly == False,  # noqa: E712 — 排除异常打卡
            )
            .order_by(ClockRecord.clock_time)
        )
        records = list(result.scalars().all())

        # 计算各指标
        status, work_minutes, late_minutes, early_leave_minutes, overtime_minutes = (
            self._compute_attendance(records, target_date)
        )

        # upsert日考勤记录
        existing = await session.execute(
            select(DailyAttendance).where(
                DailyAttendance.assignment_id == assignment_id,
                DailyAttendance.date == target_date,
            )
        )
        attendance = existing.scalar_one_or_none()

        if attendance:
            if attendance.locked:
                logger.warning("attendance.locked_skip", assignment_id=str(assignment_id), date=str(target_date))
                return attendance
            attendance.status = status
            attendance.work_minutes = work_minutes
            attendance.late_minutes = late_minutes
            attendance.early_leave_minutes = early_leave_minutes
            attendance.overtime_minutes = overtime_minutes
            attendance.calculated_at = datetime.now(timezone.utc)
        else:
            attendance = DailyAttendance(
                assignment_id=assignment_id,
                date=target_date,
                status=status,
                work_minutes=work_minutes,
                late_minutes=late_minutes,
                early_leave_minutes=early_leave_minutes,
                overtime_minutes=overtime_minutes,
            )
            session.add(attendance)

        await session.flush()
        return attendance

    async def get_monthly_summary(
        self,
        assignment_id: uuid.UUID,
        year: int,
        month: int,
        session: AsyncSession,
    ) -> dict:
        """月度考勤汇总"""
        first_day = date(year, month, 1)
        if month == 12:
            last_day = date(year + 1, 1, 1)
        else:
            last_day = date(year, month + 1, 1)

        result = await session.execute(
            select(DailyAttendance).where(
                DailyAttendance.assignment_id == assignment_id,
                DailyAttendance.date >= first_day,
                DailyAttendance.date < last_day,
            )
        )
        rows = list(result.scalars().all())

        total_work_minutes = sum(r.work_minutes for r in rows)
        total_overtime = sum(r.overtime_minutes for r in rows)
        late_count = sum(1 for r in rows if r.status == "late")
        early_leave_count = sum(1 for r in rows if r.status == "early_leave")
        absent_count = sum(1 for r in rows if r.status == "absent")
        normal_count = sum(1 for r in rows if r.status == "normal")

        return {
            "assignment_id": str(assignment_id),
            "year": year,
            "month": month,
            "total_days": len(rows),
            "normal_days": normal_count,
            "late_count": late_count,
            "early_leave_count": early_leave_count,
            "absent_count": absent_count,
            "total_work_hours": round(total_work_minutes / 60, 1),
            "total_overtime_hours": round(total_overtime / 60, 1),
        }

    async def detect_anomalies(
        self,
        assignment_id: uuid.UUID,
        target_date: date,
        session: AsyncSession,
    ) -> list[str]:
        """检测异常打卡"""
        day_start = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
        day_end = datetime.combine(target_date + timedelta(days=1), time.min, tzinfo=timezone.utc)

        result = await session.execute(
            select(ClockRecord).where(
                ClockRecord.assignment_id == assignment_id,
                ClockRecord.clock_time >= day_start,
                ClockRecord.clock_time < day_end,
                ClockRecord.is_anomaly == True,  # noqa: E712
            )
        )
        anomalies = list(result.scalars().all())
        return [
            f"异常打卡：{r.clock_type} at {r.clock_time.strftime('%H:%M')} (source={r.source})"
            for r in anomalies
        ]

    def _compute_attendance(
        self,
        records: list,
        target_date: date,
    ) -> tuple[str, int, int, int, int]:
        """纯函数：根据打卡记录计算考勤状态"""
        if not records:
            return ("absent", 0, 0, 0, 0)

        # 找最早的in和最晚的out
        clock_ins = [r for r in records if r.clock_type == "in"]
        clock_outs = [r for r in records if r.clock_type == "out"]

        if not clock_ins and not clock_outs:
            return ("absent", 0, 0, 0, 0)

        first_in = min(r.clock_time for r in clock_ins) if clock_ins else None
        last_out = max(r.clock_time for r in clock_outs) if clock_outs else None

        # 计算工作分钟
        work_minutes = 0
        if first_in and last_out and last_out > first_in:
            work_minutes = int((last_out - first_in).total_seconds() / 60)

        # 计算迟到分钟（相对标准上班时间）
        late_minutes = 0
        if first_in:
            scheduled_start = datetime.combine(
                target_date, _DEFAULT_WORK_START, tzinfo=first_in.tzinfo
            )
            if first_in > scheduled_start + timedelta(minutes=_LATE_THRESHOLD_MINUTES):
                late_minutes = int((first_in - scheduled_start).total_seconds() / 60)

        # 计算早退分钟（相对标准下班时间）
        early_leave_minutes = 0
        if last_out:
            scheduled_end = datetime.combine(
                target_date, _DEFAULT_WORK_END, tzinfo=last_out.tzinfo
            )
            if last_out < scheduled_end:
                early_leave_minutes = int((scheduled_end - last_out).total_seconds() / 60)

        # 加班分钟
        overtime_minutes = max(0, work_minutes - _STANDARD_WORK_MINUTES)

        # 判断状态
        if late_minutes > 0 and early_leave_minutes > 0:
            status = "late"  # 迟到优先
        elif late_minutes > 0:
            status = "late"
        elif early_leave_minutes > 0:
            status = "early_leave"
        elif work_minutes > _STANDARD_WORK_MINUTES:
            status = "overtime"
        else:
            status = "normal"

        return (status, work_minutes, late_minutes, early_leave_minutes, overtime_minutes)
