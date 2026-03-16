"""
Attendance Engine — 考勤计算引擎
打卡→状态判定→扣款计算→月度汇总
"""

import math
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.attendance import AttendanceLog, AttendanceRule, ShiftTemplate
from ..models.schedule import Schedule, Shift

logger = structlog.get_logger()

# ── 默认规则常量（兜底用，当数据库无匹配规则时） ─────────────
_DEFAULT_RULE = {
    "late_threshold_minutes": 5,
    "early_leave_threshold_minutes": 5,
    "late_deduction_fen": 0,
    "absent_deduction_fen": 0,
    "early_leave_deduction_fen": 0,
    "gps_fence_enabled": False,
    "gps_radius_meters": 200,
    "weekday_overtime_rate": Decimal("1.5"),
    "weekend_overtime_rate": Decimal("2.0"),
    "holiday_overtime_rate": Decimal("3.0"),
    "monthly_standard_hours": Decimal("174"),
}

# 地球平均半径（米），用于 Haversine 公式
_EARTH_RADIUS_METERS = 6_371_000


class AttendanceEngine:
    """考勤计算引擎 — 打卡→状态判定→扣款计算"""

    def __init__(self, store_id: str, brand_id: str):
        self.store_id = store_id
        self.brand_id = brand_id

    # ─────────────────────────────────────────────────────────
    # 1. 处理打卡事件
    # ─────────────────────────────────────────────────────────
    async def process_clock_event(
        self,
        db: AsyncSession,
        employee_id: str,
        clock_time: datetime,
        clock_type: str,  # "clock_in" | "clock_out"
        gps_data: Optional[Dict[str, Any]] = None,
        source: str = "wechat",
    ) -> Dict[str, Any]:
        """
        处理一次打卡事件。
        1. 查找当天排班（Shift 表）
        2. 匹配班次模板获取 start_time / end_time
        3. GPS 围栏校验
        4. 判定打卡状态：normal / late / early_leave
        5. 按 AttendanceRule 计算扣款
        6. 写入或更新 AttendanceLog
        返回处理结果字典。
        """
        work_date = clock_time.date()
        log = logger.bind(
            employee_id=employee_id,
            store_id=self.store_id,
            clock_type=clock_type,
            work_date=str(work_date),
        )

        # ── 1. 查找当天排班 ──
        # 跨天班次处理算法：
        #   夜班示例：22:00-06:00 (is_cross_day=True)
        #   scheduled_start = 当天 22:00，scheduled_end = 次日 06:00
        #   打卡场景1: 员工 21:55 打卡上班 → 与 22:00 比较 → 正常（阈值内）
        #   打卡场景2: 员工 06:10 打卡下班 → 与 06:00 比较 → 早退10分钟
        #   边缘场景: 员工午夜后(如 00:30)打 clock_in，仍应匹配前一天的夜班排班
        shift = await self._find_shift(db, employee_id, work_date)
        template: Optional[ShiftTemplate] = None
        scheduled_start: Optional[datetime] = None
        scheduled_end: Optional[datetime] = None

        if shift is not None:
            # 尝试关联班次模板（按 shift_type 匹配 code）
            template = await self._match_template(db, shift.shift_type)
            is_cross = (template and template.is_cross_day) or (shift.end_time <= shift.start_time)

            scheduled_start = datetime.combine(work_date, shift.start_time, tzinfo=clock_time.tzinfo)
            if is_cross:
                # 跨天班次：结束时间在次日
                scheduled_end = datetime.combine(work_date + timedelta(days=1), shift.end_time, tzinfo=clock_time.tzinfo)
            else:
                scheduled_end = datetime.combine(work_date, shift.end_time, tzinfo=clock_time.tzinfo)

        # 边缘场景：午夜后打卡（如 00:30），可能属于前一天的跨天夜班
        # 如果当天无排班且打卡时间在凌晨（00:00-08:00），尝试匹配前一天的跨天班次
        if shift is None and clock_time.hour < 8:
            prev_date = work_date - timedelta(days=1)
            prev_shift = await self._find_shift(db, employee_id, prev_date)
            if prev_shift is not None:
                prev_template = await self._match_template(db, prev_shift.shift_type)
                prev_is_cross = (prev_template and prev_template.is_cross_day) or (
                    prev_shift.end_time <= prev_shift.start_time
                )
                if prev_is_cross:
                    # 命中前一天的跨天班次，将排班信息修正到前一天
                    shift = prev_shift
                    template = prev_template
                    work_date = prev_date
                    scheduled_start = datetime.combine(prev_date, prev_shift.start_time, tzinfo=clock_time.tzinfo)
                    scheduled_end = datetime.combine(
                        prev_date + timedelta(days=1), prev_shift.end_time, tzinfo=clock_time.tzinfo
                    )
                    log = log.bind(work_date=str(work_date), cross_day_matched="prev_day")

        # ── 2. 获取考勤规则 ──
        rule = await self.get_attendance_rule(db)

        # ── 3. GPS 围栏校验 ──
        gps_valid = True
        if gps_data and rule.get("gps_fence_enabled"):
            gps_valid = await self.validate_gps(gps_data, rule)
            if not gps_valid:
                log.warning("GPS 围栏校验失败", gps_data=gps_data)

        # ── 4. 判定状态 + 扣款 ──
        late_threshold = rule.get("late_threshold_minutes", 5)
        early_threshold = rule.get("early_leave_threshold_minutes", 5)

        status = "normal"
        late_minutes: Optional[int] = None
        early_leave_minutes: Optional[int] = None
        deduction_fen = 0
        deduction_reason: Optional[str] = None
        is_cross_day = False

        if clock_type == "clock_in" and scheduled_start:
            diff = (clock_time - scheduled_start).total_seconds() / 60
            if diff > late_threshold:
                status = "late"
                late_minutes = int(diff)
                deduction_fen = rule.get("late_deduction_fen", 0)
                deduction_reason = f"迟到{late_minutes}分钟"
                log.info("判定迟到", late_minutes=late_minutes)

        if clock_type == "clock_out" and scheduled_end:
            diff = (scheduled_end - clock_time).total_seconds() / 60
            if diff > early_threshold:
                status = "early_leave"
                early_leave_minutes = int(diff)
                deduction_fen = rule.get("early_leave_deduction_fen", 0)
                deduction_reason = f"早退{early_leave_minutes}分钟"
                log.info("判定早退", early_leave_minutes=early_leave_minutes)

        if template and template.is_cross_day:
            is_cross_day = True

        if not gps_valid:
            deduction_reason = (deduction_reason or "") + "; GPS围栏外打卡"

        # ── 5. 写入或更新 AttendanceLog ──
        existing = await self._get_existing_log(db, employee_id, work_date)

        if existing is None:
            # 新建记录（首次打卡通常是 clock_in）
            new_log = AttendanceLog(
                id=uuid.uuid4(),
                store_id=self.store_id,
                employee_id=employee_id,
                work_date=work_date,
                clock_in=clock_time if clock_type == "clock_in" else clock_time,
                status=status,
                late_minutes=late_minutes,
                source=source,
                shift_template_id=template.id if template else None,
                scheduled_start=scheduled_start,
                scheduled_end=scheduled_end,
                early_leave_minutes=early_leave_minutes,
                gps_clock_in=gps_data if clock_type == "clock_in" else None,
                gps_clock_out=gps_data if clock_type == "clock_out" else None,
                is_cross_day=is_cross_day,
                deduction_fen=deduction_fen,
                deduction_reason=deduction_reason,
            )
            db.add(new_log)
            await db.flush()
            log.info("新建考勤记录", status=status)
            record_id = str(new_log.id)
        else:
            # 更新已有记录（clock_out 补充）
            update_values: Dict[str, Any] = {}
            if clock_type == "clock_out":
                update_values["clock_out"] = clock_time
                update_values["gps_clock_out"] = gps_data
                # 计算实际工时
                if existing.clock_in:
                    total_seconds = (clock_time - existing.clock_in).total_seconds()
                    break_mins = existing.break_minutes or (template.break_minutes if template else 0) or 0
                    actual_h = max(0, (total_seconds / 3600) - (break_mins / 60))
                    update_values["actual_hours"] = round(actual_h, 2)
                    update_values["break_minutes"] = break_mins
                    # 加班判断
                    standard = float(rule.get("monthly_standard_hours", 174)) / 21.75
                    if actual_h > standard:
                        update_values["overtime_hours"] = round(actual_h - standard, 2)

            if early_leave_minutes is not None:
                update_values["early_leave_minutes"] = early_leave_minutes
            if status != "normal":
                update_values["status"] = status
            if deduction_fen > 0:
                update_values["deduction_fen"] = (existing.deduction_fen or 0) + deduction_fen
                existing_reason = existing.deduction_reason or ""
                update_values["deduction_reason"] = (
                    f"{existing_reason}; {deduction_reason}" if existing_reason else deduction_reason
                )

            if update_values:
                stmt = update(AttendanceLog).where(AttendanceLog.id == existing.id).values(**update_values)
                await db.execute(stmt)
                await db.flush()

            log.info("更新考勤记录", status=status, updates=list(update_values.keys()))
            record_id = str(existing.id)

        return {
            "record_id": record_id,
            "employee_id": employee_id,
            "work_date": str(work_date),
            "clock_type": clock_type,
            "status": status,
            "late_minutes": late_minutes,
            "early_leave_minutes": early_leave_minutes,
            "deduction_fen": deduction_fen,
            "deduction_reason": deduction_reason,
            "gps_valid": gps_valid,
            "is_cross_day": is_cross_day,
        }

    # ─────────────────────────────────────────────────────────
    # 2. 获取考勤规则（三级降级）
    # ─────────────────────────────────────────────────────────
    async def get_attendance_rule(
        self,
        db: AsyncSession,
        employment_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        获取考勤规则，三级降级：
        1. store_id + employment_type 精确匹配
        2. brand_id + employment_type
        3. brand_id + NULL employment_type（品牌默认）
        4. 兜底：内置默认值
        """
        candidates = [
            # Level 1: 门店 + 用工类型
            and_(
                AttendanceRule.brand_id == self.brand_id,
                AttendanceRule.store_id == self.store_id,
                AttendanceRule.employment_type == employment_type,
                AttendanceRule.is_active.is_(True),
            ),
            # Level 2: 品牌 + 用工类型
            and_(
                AttendanceRule.brand_id == self.brand_id,
                AttendanceRule.store_id.is_(None),
                AttendanceRule.employment_type == employment_type,
                AttendanceRule.is_active.is_(True),
            ),
            # Level 3: 品牌默认（无用工类型限定）
            and_(
                AttendanceRule.brand_id == self.brand_id,
                AttendanceRule.store_id.is_(None),
                AttendanceRule.employment_type.is_(None),
                AttendanceRule.is_active.is_(True),
            ),
        ]

        for condition in candidates:
            result = await db.execute(select(AttendanceRule).where(condition).limit(1))
            rule = result.scalar_one_or_none()
            if rule is not None:
                return self._rule_to_dict(rule)

        logger.warning(
            "未找到考勤规则，使用默认值",
            brand_id=self.brand_id,
            store_id=self.store_id,
        )
        return dict(_DEFAULT_RULE)

    # ─────────────────────────────────────────────────────────
    # 3. 月度考勤汇总
    # ─────────────────────────────────────────────────────────
    async def calculate_monthly_summary(
        self,
        db: AsyncSession,
        employee_id: str,
        pay_month: str,
    ) -> Dict[str, Any]:
        """
        月度考勤汇总 — 供薪酬计算使用。
        pay_month 格式: "2026-03"
        """
        year, month = int(pay_month[:4]), int(pay_month[5:7])
        month_start = date(year, month, 1)
        if month == 12:
            month_end = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(year, month + 1, 1) - timedelta(days=1)

        result = await db.execute(
            select(AttendanceLog).where(
                and_(
                    AttendanceLog.store_id == self.store_id,
                    AttendanceLog.employee_id == employee_id,
                    AttendanceLog.work_date >= month_start,
                    AttendanceLog.work_date <= month_end,
                )
            )
        )
        logs = result.scalars().all()

        total_days = len(logs)
        normal_days = 0
        late_count = 0
        total_late_minutes = 0
        early_leave_count = 0
        absent_days = 0
        leave_days = 0
        total_actual_hours = Decimal("0")
        total_overtime_hours = Decimal("0")
        total_deduction_fen = 0

        # 按加班类型分类统计（需要 work_date 判断是否为周末/节假日）
        overtime_hours_weekday = Decimal("0")
        overtime_hours_weekend = Decimal("0")
        overtime_hours_holiday = Decimal("0")

        for log in logs:
            if log.status == "normal":
                normal_days += 1
            elif log.status == "late":
                late_count += 1
                normal_days += 1  # 迟到也算出勤
                total_late_minutes += log.late_minutes or 0
            elif log.status == "early_leave":
                early_leave_count += 1
                normal_days += 1  # 早退也算出勤
            elif log.status == "absent":
                absent_days += 1
            elif log.status == "leave":
                leave_days += 1

            if log.actual_hours:
                total_actual_hours += Decimal(str(log.actual_hours))
            if log.overtime_hours and log.overtime_hours > 0:
                ot = Decimal(str(log.overtime_hours))
                total_overtime_hours += ot
                weekday = log.work_date.weekday()
                if weekday < 5:
                    overtime_hours_weekday += ot
                else:
                    overtime_hours_weekend += ot

            total_deduction_fen += log.deduction_fen or 0

        workday_count = sum(1 for log in logs if log.status in ("normal", "late", "early_leave"))

        return {
            "employee_id": employee_id,
            "pay_month": pay_month,
            "total_days": total_days,
            "workday_days": workday_count,
            "normal_days": normal_days,
            "late_count": late_count,
            "total_late_minutes": total_late_minutes,
            "early_leave_count": early_leave_count,
            "absent_days": absent_days,
            "leave_days": leave_days,
            "total_actual_hours": float(total_actual_hours),
            "overtime_hours_weekday": float(overtime_hours_weekday),
            "overtime_hours_weekend": float(overtime_hours_weekend),
            "overtime_hours_holiday": float(overtime_hours_holiday),
            "total_overtime_hours": float(total_overtime_hours),
            "total_deduction_fen": total_deduction_fen,
            "total_deduction_yuan": round(total_deduction_fen / 100, 2),
        }

    # ─────────────────────────────────────────────────────────
    # 4. GPS 围栏验证
    # ─────────────────────────────────────────────────────────
    async def validate_gps(
        self,
        gps_data: Dict[str, Any],
        rule: Dict[str, Any],
    ) -> bool:
        """
        GPS 围栏验证 — Haversine 公式计算实际距离是否在允许半径内。
        gps_data: {"lat": float, "lng": float, "accuracy": float}
        """
        lat1 = gps_data.get("lat")
        lng1 = gps_data.get("lng")
        if lat1 is None or lng1 is None:
            logger.warning("GPS 数据缺失经纬度")
            return False

        lat2 = rule.get("gps_latitude")
        lng2 = rule.get("gps_longitude")
        if lat2 is None or lng2 is None:
            # 规则未配置坐标，跳过校验
            return True

        lat2 = float(lat2)
        lng2 = float(lng2)
        radius = rule.get("gps_radius_meters", 200)

        distance = self._haversine(float(lat1), float(lng1), lat2, lng2)
        # 考虑手机 GPS 精度误差
        accuracy = gps_data.get("accuracy", 0)
        effective_distance = max(0, distance - float(accuracy))

        is_valid = effective_distance <= radius
        logger.info(
            "GPS 围栏校验",
            distance_m=round(distance, 1),
            accuracy_m=accuracy,
            radius_m=radius,
            valid=is_valid,
        )
        return is_valid

    # ─────────────────────────────────────────────────────────
    # 5. 批量导入打卡数据
    # ─────────────────────────────────────────────────────────
    async def batch_import_clock_data(
        self,
        db: AsyncSession,
        records: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        批量导入打卡数据（从考勤机/企微/钉钉同步）。
        每条记录格式:
        {
            "employee_id": str,
            "clock_time": str (ISO format),
            "clock_type": "clock_in" | "clock_out",
            "source": str,
            "gps_data": optional dict
        }
        """
        total = len(records)
        success = 0
        failed = 0
        errors: List[Dict[str, Any]] = []

        for idx, record in enumerate(records):
            try:
                # 每条记录使用 savepoint，单条失败不影响其余记录
                async with db.begin_nested():
                    employee_id = record["employee_id"]
                    clock_time_str = record["clock_time"]
                    clock_type = record.get("clock_type", "clock_in")
                    source = record.get("source", "import")
                    gps_data = record.get("gps_data")

                    if isinstance(clock_time_str, str):
                        clock_time = datetime.fromisoformat(clock_time_str)
                    else:
                        clock_time = clock_time_str

                    await self.process_clock_event(
                        db=db,
                        employee_id=employee_id,
                        clock_time=clock_time,
                        clock_type=clock_type,
                        gps_data=gps_data,
                        source=source,
                    )
                success += 1
            except Exception as e:
                # savepoint 自动回滚，继续处理下一条
                failed += 1
                errors.append(
                    {
                        "index": idx,
                        "employee_id": record.get("employee_id"),
                        "error": str(e),
                    }
                )
                logger.error(
                    "批量导入打卡失败",
                    index=idx,
                    employee_id=record.get("employee_id"),
                    error=str(e),
                )

        logger.info(
            "批量导入打卡完成",
            total=total,
            success=success,
            failed=failed,
        )
        return {
            "total": total,
            "success": success,
            "failed": failed,
            "errors": errors[:50],  # 最多返回50条错误
        }

    # ─────────────────────────────────────────────────────────
    # 内部辅助方法
    # ─────────────────────────────────────────────────────────
    async def _find_shift(
        self,
        db: AsyncSession,
        employee_id: str,
        work_date: date,
    ) -> Optional[Shift]:
        """查找员工当天排班"""
        result = await db.execute(
            select(Shift)
            .join(Schedule, Shift.schedule_id == Schedule.id)
            .where(
                and_(
                    Schedule.store_id == self.store_id,
                    Schedule.schedule_date == work_date,
                    Shift.employee_id == employee_id,
                )
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _match_template(
        self,
        db: AsyncSession,
        shift_type: str,
    ) -> Optional[ShiftTemplate]:
        """按 shift_type(code) 匹配班次模板，门店级优先"""
        # 先查门店级
        result = await db.execute(
            select(ShiftTemplate)
            .where(
                and_(
                    ShiftTemplate.brand_id == self.brand_id,
                    ShiftTemplate.store_id == self.store_id,
                    ShiftTemplate.code == shift_type,
                    ShiftTemplate.is_active.is_(True),
                )
            )
            .limit(1)
        )
        template = result.scalar_one_or_none()
        if template:
            return template

        # 品牌通用
        result = await db.execute(
            select(ShiftTemplate)
            .where(
                and_(
                    ShiftTemplate.brand_id == self.brand_id,
                    ShiftTemplate.store_id.is_(None),
                    ShiftTemplate.code == shift_type,
                    ShiftTemplate.is_active.is_(True),
                )
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _get_existing_log(
        self,
        db: AsyncSession,
        employee_id: str,
        work_date: date,
    ) -> Optional[AttendanceLog]:
        """获取当天已有考勤记录"""
        result = await db.execute(
            select(AttendanceLog)
            .where(
                and_(
                    AttendanceLog.store_id == self.store_id,
                    AttendanceLog.employee_id == employee_id,
                    AttendanceLog.work_date == work_date,
                )
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """Haversine 公式计算两点间距离（米）"""
        lat1_r = math.radians(lat1)
        lat2_r = math.radians(lat2)
        dlat = math.radians(lat2 - lat1)
        dlng = math.radians(lng2 - lng1)

        a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlng / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return _EARTH_RADIUS_METERS * c

    @staticmethod
    def _rule_to_dict(rule: AttendanceRule) -> Dict[str, Any]:
        """AttendanceRule ORM 对象转字典"""
        return {
            "id": str(rule.id),
            "brand_id": rule.brand_id,
            "store_id": rule.store_id,
            "employment_type": rule.employment_type,
            "clock_methods": rule.clock_methods or ["wechat"],
            "gps_fence_enabled": rule.gps_fence_enabled or False,
            "gps_latitude": rule.gps_latitude,
            "gps_longitude": rule.gps_longitude,
            "gps_radius_meters": rule.gps_radius_meters or 200,
            "late_deduction_fen": rule.late_deduction_fen or 0,
            "absent_deduction_fen": rule.absent_deduction_fen or 0,
            "early_leave_deduction_fen": rule.early_leave_deduction_fen or 0,
            "late_threshold_minutes": 5,  # 模板级别的阈值
            "early_leave_threshold_minutes": 5,
            "weekday_overtime_rate": rule.weekday_overtime_rate or Decimal("1.5"),
            "weekend_overtime_rate": rule.weekend_overtime_rate or Decimal("2.0"),
            "holiday_overtime_rate": rule.holiday_overtime_rate or Decimal("3.0"),
            "work_hour_type": rule.work_hour_type or "standard",
            "monthly_standard_hours": rule.monthly_standard_hours or Decimal("174"),
            "is_active": rule.is_active,
        }
