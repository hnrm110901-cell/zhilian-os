"""班次公平性评分服务。"""

from collections import defaultdict
from datetime import date, time, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.schedule import Schedule, Shift

UNFAVORABLE_SHIFT_TYPES = {"night", "evening", "close", "closing"}
EARLY_SHIFT_CUTOFF = time(8, 0)


def is_unfavorable_shift(shift_type: Optional[str], start_time: Optional[time]) -> bool:
    """判断是否为相对不友好班次（深夜/晚班/过早班）。"""
    normalized = (shift_type or "").lower()
    if normalized in UNFAVORABLE_SHIFT_TYPES:
        return True
    if start_time and start_time <= EARLY_SHIFT_CUTOFF:
        return True
    return False


def compute_employee_unfavorable_ratio(shift_records: List[Dict[str, Any]]) -> float:
    """计算员工不友好班次占比。"""
    total = len(shift_records)
    if total == 0:
        return 0.0

    unfavorable = sum(
        1
        for record in shift_records
        if is_unfavorable_shift(record.get("shift_type"), record.get("start_time"))
    )
    return round(unfavorable / total, 4)


def compute_gini(values: List[float]) -> float:
    """基尼系数，范围 [0, 1]。"""
    if not values:
        return 0.0

    non_negative = [max(0.0, float(v)) for v in values]
    total = sum(non_negative)
    if total == 0:
        return 0.0

    sorted_values = sorted(non_negative)
    n = len(sorted_values)
    weighted_sum = sum((idx + 1) * value for idx, value in enumerate(sorted_values))
    gini = (2 * weighted_sum) / (n * total) - (n + 1) / n
    return round(max(0.0, min(1.0, gini)), 6)


def compute_fairness_index(unfavorable_ratios: List[float]) -> float:
    """公平性指数（0-100，越高越公平）。"""
    if not unfavorable_ratios:
        return 100.0
    gini = compute_gini(unfavorable_ratios)
    return round((1 - gini) * 100, 2)


def find_consecutive_worst_employees(
    weekly_unfavorable_counts: List[Dict[str, int]],
    min_weeks: int = 3,
) -> List[str]:
    """识别连续 N 周处于最差班次分配顶部的员工。"""
    if min_weeks <= 1:
        min_weeks = 1

    streaks: Dict[str, int] = defaultdict(int)
    flagged = set()

    for week_map in weekly_unfavorable_counts:
        if not week_map:
            continue

        max_count = max(week_map.values())
        winners = {employee_id for employee_id, count in week_map.items() if count == max_count and count > 0}

        for employee_id in list(streaks.keys()):
            if employee_id not in winners:
                streaks[employee_id] = 0

        for employee_id in winners:
            streaks[employee_id] += 1
            if streaks[employee_id] >= min_weeks:
                flagged.add(employee_id)

    return sorted(flagged)


class ShiftFairnessService:
    """班次公平性评分服务。"""

    async def get_monthly_shift_fairness(
        self,
        store_id: str,
        year: int,
        month: int,
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """统计门店月度班次公平性。"""
        start_date = date(year, month, 1)
        if month == 12:
            end_date = date(year + 1, 1, 1)
        else:
            end_date = date(year, month + 1, 1)

        stmt = (
            select(Shift.employee_id, Shift.shift_type, Shift.start_time, Schedule.schedule_date)
            .join(Schedule, Shift.schedule_id == Schedule.id)
            .where(
                and_(
                    Schedule.store_id == store_id,
                    Schedule.schedule_date >= start_date,
                    Schedule.schedule_date < end_date,
                )
            )
        )
        result = await db.execute(stmt)
        rows = result.all()

        employee_shifts: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for row in rows:
            employee_shifts[str(row[0])].append(
                {
                    "shift_type": row[1],
                    "start_time": row[2],
                    "schedule_date": row[3],
                }
            )

        employee_stats = []
        unfavorable_ratios = []
        for employee_id, records in employee_shifts.items():
            unfavorable_count = sum(
                1
                for record in records
                if is_unfavorable_shift(record.get("shift_type"), record.get("start_time"))
            )
            ratio = compute_employee_unfavorable_ratio(records)
            employee_stats.append(
                {
                    "employee_id": employee_id,
                    "total_shifts": len(records),
                    "unfavorable_shifts": unfavorable_count,
                    "unfavorable_ratio": ratio,
                }
            )
            unfavorable_ratios.append(ratio)

        employee_stats.sort(key=lambda item: item["unfavorable_ratio"], reverse=True)

        return {
            "store_id": store_id,
            "year": year,
            "month": month,
            "fairness_index": compute_fairness_index(unfavorable_ratios),
            "total_employees": len(employee_stats),
            "employee_stats": employee_stats,
        }

    async def detect_unfair_assignment_alerts(
        self,
        store_id: str,
        end_date: date,
        db: AsyncSession,
        lookback_weeks: int = 3,
    ) -> Dict[str, Any]:
        """检测连续多周被分配最差班次的员工。"""
        if lookback_weeks < 1:
            lookback_weeks = 1

        start_date = end_date - timedelta(days=lookback_weeks * 7)

        stmt = (
            select(Shift.employee_id, Shift.shift_type, Shift.start_time, Schedule.schedule_date)
            .join(Schedule, Shift.schedule_id == Schedule.id)
            .where(
                and_(
                    Schedule.store_id == store_id,
                    Schedule.schedule_date >= start_date,
                    Schedule.schedule_date <= end_date,
                )
            )
        )
        result = await db.execute(stmt)
        rows = result.all()

        weekly_map: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for row in rows:
            employee_id = str(row[0])
            shift_type = row[1]
            start_time = row[2]
            schedule_date = row[3]
            if not is_unfavorable_shift(shift_type, start_time):
                continue

            iso_year, iso_week, _ = schedule_date.isocalendar()
            week_key = f"{iso_year}-W{iso_week:02d}"
            weekly_map[week_key][employee_id] += 1

        ordered_weekly_counts = [
            dict(weekly_map[key])
            for key in sorted(weekly_map.keys())
        ]

        high_risk_employees = find_consecutive_worst_employees(
            ordered_weekly_counts,
            min_weeks=lookback_weeks,
        )

        return {
            "store_id": store_id,
            "lookback_weeks": lookback_weeks,
            "high_risk_employees": high_risk_employees,
            "weekly_unfavorable_counts": {
                key: dict(value)
                for key, value in sorted(weekly_map.items())
            },
        }
