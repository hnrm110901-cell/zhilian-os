"""
Schedule Conflict Service

检测同一员工的排班时间冲突（支持跨天班次）。
"""

from __future__ import annotations

from datetime import datetime, timedelta, time
from typing import Any, Dict, List, Tuple


def _to_interval(start: time, end: time) -> Tuple[datetime, datetime]:
    base = datetime(2000, 1, 1)
    start_dt = datetime.combine(base.date(), start)
    end_dt = datetime.combine(base.date(), end)
    if end_dt <= start_dt:
        end_dt += timedelta(days=1)
    return start_dt, end_dt


def _is_overlap(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return max(a_start, b_start) < min(a_end, b_end)


def detect_schedule_conflicts(shifts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    输入班次列表，返回冲突列表。

    每个 shift 需包含:
      - employee_id
      - start_time
      - end_time
      - shift_type (可选)
      - position (可选)
    """
    conflicts: List[Dict[str, Any]] = []
    normalized = []
    for idx, s in enumerate(shifts):
        start_dt, end_dt = _to_interval(s["start_time"], s["end_time"])
        normalized.append(
            {
                "idx": idx,
                "employee_id": str(s["employee_id"]),
                "start": start_dt,
                "end": end_dt,
                "shift_type": s.get("shift_type"),
                "position": s.get("position"),
            }
        )

    for i in range(len(normalized)):
        for j in range(i + 1, len(normalized)):
            a = normalized[i]
            b = normalized[j]
            if a["employee_id"] != b["employee_id"]:
                continue
            if _is_overlap(a["start"], a["end"], b["start"], b["end"]):
                conflicts.append(
                    {
                        "employee_id": a["employee_id"],
                        "left_index": a["idx"],
                        "right_index": b["idx"],
                        "left_shift_type": a["shift_type"],
                        "right_shift_type": b["shift_type"],
                        "message": f"员工 {a['employee_id']} 存在班次时间重叠",
                    }
                )
    return conflicts
