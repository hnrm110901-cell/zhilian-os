"""AttendanceService — 考勤计算引擎（规则驱动多班次版）

AI差异化：异常打卡模式识别（凌晨2-3点场景特殊处理）
P3重写：从硬编码常量 → 合同绑定考勤规则 → 多班次支持
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

# 后备常量：仅当员工未绑定考勤规则时使用
_FALLBACK_WORK_START = time(9, 0)
_FALLBACK_WORK_END = time(22, 0)
_FALLBACK_STANDARD_MINUTES = 480
_FALLBACK_LATE_THRESHOLD = 5
_ANOMALY_HOURS = (2, 3)  # 凌晨2-3点打卡视为异常


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
        """计算某天的考勤结果（规则驱动）"""
        # 1. 解析班次规则
        shift_start, shift_end, rule_config = await self._resolve_shift(
            assignment_id, target_date, session,
        )

        late_threshold = (
            rule_config.get("late_threshold_minutes", _FALLBACK_LATE_THRESHOLD)
            if rule_config else _FALLBACK_LATE_THRESHOLD
        )
        standard_minutes = (
            rule_config.get("standard_work_minutes_per_shift", _FALLBACK_STANDARD_MINUTES)
            if rule_config else _FALLBACK_STANDARD_MINUTES
        )

        # 2. 确定打卡查询窗口（夜班延伸到次日凌晨）
        day_start = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
        cutoff_hour = rule_config.get("night_shift_cutoff_hour", 3) if rule_config else 3
        if shift_end and shift_end.hour >= 22:
            day_end = datetime.combine(
                target_date + timedelta(days=1),
                time(cutoff_hour, 0),
                tzinfo=timezone.utc,
            )
        else:
            day_end = datetime.combine(
                target_date + timedelta(days=1), time.min, tzinfo=timezone.utc,
            )

        # 3. 查找当日所有打卡记录
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

        # 4. 计算各指标
        status, work_minutes, late_minutes, early_leave_minutes, overtime_minutes = (
            self._compute_attendance(
                records, target_date,
                shift_start=shift_start,
                shift_end=shift_end,
                late_threshold=late_threshold,
                standard_minutes=standard_minutes,
            )
        )

        # 5. upsert日考勤记录
        existing = await session.execute(
            select(DailyAttendance).where(
                DailyAttendance.assignment_id == assignment_id,
                DailyAttendance.date == target_date,
            )
        )
        attendance = existing.scalar_one_or_none()

        if attendance:
            if attendance.locked:
                logger.warning(
                    "attendance.locked_skip",
                    assignment_id=str(assignment_id),
                    date=str(target_date),
                )
                return attendance
            attendance.status = status
            attendance.work_minutes = work_minutes
            attendance.late_minutes = late_minutes
            attendance.early_leave_minutes = early_leave_minutes
            attendance.overtime_minutes = overtime_minutes
            attendance.scheduled_start_time = shift_start
            attendance.scheduled_end_time = shift_end
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
                scheduled_start_time=shift_start,
                scheduled_end_time=shift_end,
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

    # ── 班次解析 ──────────────────────────────────────────────────────────

    async def _resolve_shift(
        self,
        assignment_id: uuid.UUID,
        target_date: date,
        session: AsyncSession,
    ) -> tuple[time, time, dict]:
        """解析当日班次：合同规则 -> 排班表 -> 默认后备"""
        from ...models.hr.employment_contract import EmploymentContract
        from ...models.hr.attendance_rule import AttendanceRule

        contract_result = await session.execute(
            select(EmploymentContract)
            .where(
                EmploymentContract.assignment_id == assignment_id,
                EmploymentContract.valid_from <= target_date,
            )
            .order_by(EmploymentContract.valid_from.desc())
            .limit(1)
        )
        contract = contract_result.scalar_one_or_none()

        rule_config: dict = {}
        if contract and contract.attendance_rule_id:
            rule_result = await session.execute(
                select(AttendanceRule).where(
                    AttendanceRule.id == contract.attendance_rule_id,
                )
            )
            rule = rule_result.scalar_one_or_none()
            if rule and rule.rule_config:
                rule_config = rule.rule_config

        # 从规则配置中解析班次
        shifts = rule_config.get("shifts", {})
        default_shift_name = rule_config.get("default_shift", "full")
        shift_config = shifts.get(default_shift_name, {})

        start_str = shift_config.get("start", "09:00")
        end_str = shift_config.get("end", "22:00")
        shift_start = time.fromisoformat(start_str)
        shift_end = time.fromisoformat(end_str)

        return shift_start, shift_end, rule_config

    # ── 考勤计算（纯函数） ────────────────────────────────────────────────

    def _compute_attendance(
        self,
        records: list,
        target_date: date,
        shift_start: time = _FALLBACK_WORK_START,
        shift_end: time = _FALLBACK_WORK_END,
        late_threshold: int = _FALLBACK_LATE_THRESHOLD,
        standard_minutes: int = _FALLBACK_STANDARD_MINUTES,
    ) -> tuple[str, int, int, int, int]:
        """纯函数：根据打卡记录 + 班次参数计算考勤状态

        Returns:
            (status, work_minutes, late_minutes, early_leave_minutes, overtime_minutes)
        """
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

        # 计算迟到分钟（相对班次开始时间）
        late_minutes = 0
        if first_in:
            scheduled_start = datetime.combine(
                target_date, shift_start, tzinfo=first_in.tzinfo,
            )
            if first_in > scheduled_start + timedelta(minutes=late_threshold):
                late_minutes = int((first_in - scheduled_start).total_seconds() / 60)

        # 计算早退分钟（相对班次结束时间）
        early_leave_minutes = 0
        if last_out:
            # 夜班：结束时间跨日
            end_date = target_date
            if shift_end <= shift_start:
                end_date = target_date + timedelta(days=1)
            scheduled_end = datetime.combine(
                end_date, shift_end, tzinfo=last_out.tzinfo,
            )
            if last_out < scheduled_end:
                early_leave_minutes = int(
                    (scheduled_end - last_out).total_seconds() / 60
                )

        # 加班分钟
        overtime_minutes = max(0, work_minutes - standard_minutes)

        # 判断状态
        if late_minutes > 0 and early_leave_minutes > 0:
            status = "late"  # 迟到优先
        elif late_minutes > 0:
            status = "late"
        elif early_leave_minutes > 0:
            status = "early_leave"
        elif work_minutes > standard_minutes:
            status = "overtime"
        else:
            status = "normal"

        return (status, work_minutes, late_minutes, early_leave_minutes, overtime_minutes)

    # ── 考勤申诉 ─────────────────────────────────────────────────────────

    async def submit_appeal(
        self,
        assignment_id: uuid.UUID,
        target_date: date,
        reason: str,
        created_by: str,
        session: AsyncSession,
    ) -> dict:
        """提交考勤申诉（通过审批工作流）"""
        from .approval_workflow_service import HRApprovalWorkflowService

        appeal_resource_id = uuid.uuid4()

        svc = HRApprovalWorkflowService()
        try:
            instance = await svc.start(
                resource_type="attendance_appeal",
                resource_id=appeal_resource_id,
                initiator=created_by,
                session=session,
                extra_data={
                    "assignment_id": str(assignment_id),
                    "date": target_date.isoformat(),
                    "reason": reason,
                },
            )
            return {
                "appeal_id": str(appeal_resource_id),
                "approval_instance_id": str(instance.id),
                "status": "submitted",
            }
        except ValueError:
            # 无审批模板时直接提交（无工作流）
            return {
                "appeal_id": str(appeal_resource_id),
                "approval_instance_id": None,
                "status": "submitted_no_workflow",
            }

    async def resolve_appeal(
        self,
        assignment_id: uuid.UUID,
        target_date: date,
        new_status: str,
        session: AsyncSession,
    ) -> None:
        """申诉通过：覆盖考勤状态"""
        if new_status not in ("normal", "leave", "overtime"):
            raise ValueError(f"Invalid override status: {new_status!r}")

        await session.execute(
            update(DailyAttendance)
            .where(
                DailyAttendance.assignment_id == assignment_id,
                DailyAttendance.date == target_date,
            )
            .values(status=new_status)
        )
        await session.flush()
