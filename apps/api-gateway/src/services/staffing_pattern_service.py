"""
Staffing Pattern Service

从历史最优排班中学习模板，并可应用到相似日期。
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date, datetime, time
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from src.repositories import EmployeeRepository

logger = structlog.get_logger()


def infer_day_type(target_date: date) -> str:
    # 后续可接入节假日服务；当前以周末区分
    return "weekend" if target_date.weekday() >= 5 else "weekday"


def _parse_hhmm(hhmm: str) -> time:
    h, m = map(int, hhmm.split(":"))
    return time(h, m)


class StaffingPatternService:
    @staticmethod
    async def learn_from_history(
        store_id: str,
        start_date: date,
        end_date: date,
        db: AsyncSession,
    ) -> Dict[str, Any]:
        result = await db.execute(
            text("""
                SELECT
                    sc.schedule_date,
                    sh.shift_type,
                    COALESCE(sh.position, 'waiter') AS position,
                    MIN(TO_CHAR(sh.start_time, 'HH24:MI')) AS start_time,
                    MIN(TO_CHAR(sh.end_time, 'HH24:MI')) AS end_time,
                    COUNT(*) AS required_count,
                    lcs.actual_labor_cost_rate
                FROM schedules sc
                JOIN shifts sh ON sh.schedule_id = sc.id
                LEFT JOIN labor_cost_snapshots lcs
                    ON lcs.store_id = sc.store_id
                   AND lcs.snapshot_date = sc.schedule_date
                WHERE sc.store_id = :sid
                  AND sc.schedule_date >= :start_date
                  AND sc.schedule_date <= :end_date
                GROUP BY sc.schedule_date, sh.shift_type, COALESCE(sh.position, 'waiter'), lcs.actual_labor_cost_rate
                ORDER BY sc.schedule_date
                """),
            {"sid": store_id, "start_date": start_date, "end_date": end_date},
        )
        rows = result.fetchall()
        if not rows:
            return {
                "store_id": store_id,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "stored_count": 0,
                "patterns": [],
            }

        by_date: Dict[date, Dict[str, Any]] = {}
        for r in rows:
            dt = r.schedule_date
            item = by_date.setdefault(
                dt,
                {
                    "date": dt,
                    "day_type": infer_day_type(dt),
                    "labor_cost_rate": float(r.actual_labor_cost_rate or 0.0),
                    "shifts": [],
                },
            )
            item["shifts"].append(
                {
                    "shift_type": str(r.shift_type),
                    "position": str(r.position),
                    "required_count": int(r.required_count),
                    "start": str(r.start_time),
                    "end": str(r.end_time),
                }
            )

        day_samples = list(by_date.values())
        rates = [s["labor_cost_rate"] for s in day_samples if s["labor_cost_rate"] > 0]
        median_rate = statistics.median(rates) if rates else 0.0
        optimal_days = [s for s in day_samples if (s["labor_cost_rate"] <= median_rate or median_rate == 0.0)]

        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for d in optimal_days:
            grouped[d["day_type"]].append(d)

        stored = 0
        patterns = []
        for day_type, samples in grouped.items():
            aggregate: Dict[tuple, Dict[str, Any]] = defaultdict(
                lambda: {"count_sum": 0, "n": 0, "start": "09:00", "end": "17:00"}
            )
            sample_rates = [s["labor_cost_rate"] for s in samples if s["labor_cost_rate"] > 0]
            for sample in samples:
                for s in sample["shifts"]:
                    key = (s["shift_type"], s["position"])
                    rec = aggregate[key]
                    rec["count_sum"] += int(s["required_count"])
                    rec["n"] += 1
                    rec["start"] = s["start"]
                    rec["end"] = s["end"]

            template = []
            for (shift_type, position), rec in aggregate.items():
                template.append(
                    {
                        "shift_type": shift_type,
                        "position": position,
                        "required_count": max(1, int(round(rec["count_sum"] / max(rec["n"], 1)))),
                        "start": rec["start"],
                        "end": rec["end"],
                    }
                )
            template.sort(key=lambda x: (x["shift_type"], x["position"]))

            avg_rate = round(sum(sample_rates) / len(sample_rates), 2) if sample_rates else None
            perf = round(100 - (avg_rate or 0), 2)
            pattern_name = f"{day_type}_all_day_template"
            patterns.append(
                {
                    "pattern_name": pattern_name,
                    "day_type": day_type,
                    "meal_period": "all_day",
                    "sample_days": len(samples),
                    "avg_labor_cost_rate": avg_rate,
                    "performance_score": perf,
                    "shifts_template": template,
                }
            )

            try:
                await db.execute(
                    text("""
                        INSERT INTO staffing_patterns (
                            store_id, pattern_name, day_type, meal_period, shifts_template,
                            source_start_date, source_end_date, sample_days,
                            avg_labor_cost_rate, performance_score, is_active, created_at, updated_at
                        ) VALUES (
                            :store_id, :pattern_name, :day_type, :meal_period, :shifts_template,
                            :source_start_date, :source_end_date, :sample_days,
                            :avg_labor_cost_rate, :performance_score, TRUE, NOW(), NOW()
                        )
                        ON CONFLICT (store_id, day_type, meal_period)
                        DO UPDATE SET
                            pattern_name = EXCLUDED.pattern_name,
                            shifts_template = EXCLUDED.shifts_template,
                            source_start_date = EXCLUDED.source_start_date,
                            source_end_date = EXCLUDED.source_end_date,
                            sample_days = EXCLUDED.sample_days,
                            avg_labor_cost_rate = EXCLUDED.avg_labor_cost_rate,
                            performance_score = EXCLUDED.performance_score,
                            is_active = TRUE,
                            updated_at = NOW()
                        """),
                    {
                        "store_id": store_id,
                        "pattern_name": pattern_name,
                        "day_type": day_type,
                        "meal_period": "all_day",
                        "shifts_template": template,
                        "source_start_date": start_date,
                        "source_end_date": end_date,
                        "sample_days": len(samples),
                        "avg_labor_cost_rate": avg_rate,
                        "performance_score": perf,
                    },
                )
                stored += 1
            except Exception as exc:
                logger.warning("staffing_pattern.learn.persist_failed", store_id=store_id, day_type=day_type, error=str(exc))

        await db.commit()
        return {
            "store_id": store_id,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "stored_count": stored,
            "patterns": patterns,
        }

    @staticmethod
    async def get_best_pattern(
        store_id: str,
        target_date: date,
        db: AsyncSession,
    ) -> Optional[Dict[str, Any]]:
        day_type = infer_day_type(target_date)
        result = await db.execute(
            text("""
                SELECT
                    pattern_name, day_type, meal_period, shifts_template,
                    sample_days, avg_labor_cost_rate, performance_score
                FROM staffing_patterns
                WHERE store_id = :sid
                  AND day_type = :day_type
                  AND is_active = TRUE
                ORDER BY performance_score DESC NULLS LAST, sample_days DESC
                LIMIT 1
                """),
            {"sid": store_id, "day_type": day_type},
        )
        row = result.fetchone()
        if not row:
            return None
        return {
            "pattern_name": row.pattern_name,
            "day_type": row.day_type,
            "meal_period": row.meal_period,
            "shifts_template": row.shifts_template or [],
            "sample_days": int(row.sample_days or 0),
            "avg_labor_cost_rate": float(row.avg_labor_cost_rate) if row.avg_labor_cost_rate is not None else None,
            "performance_score": float(row.performance_score) if row.performance_score is not None else None,
        }

    @staticmethod
    async def build_shifts_from_best_pattern(
        store_id: str,
        target_date: date,
        db: AsyncSession,
    ) -> List[Dict[str, Any]]:
        pattern = await StaffingPatternService.get_best_pattern(store_id=store_id, target_date=target_date, db=db)
        if not pattern:
            return []

        employees = await EmployeeRepository.get_by_store(db, store_id)
        active = [e for e in employees if getattr(e, "is_active", True)]
        if not active:
            return []

        shifts: List[Dict[str, Any]] = []
        idx = 0
        for item in pattern.get("shifts_template", []):
            required = int(item.get("required_count", 1))
            position = str(item.get("position", "waiter"))
            candidates = [e for e in active if position in (getattr(e, "skills", None) or [])]
            if not candidates:
                candidates = active
            for _ in range(required):
                emp = candidates[idx % len(candidates)]
                idx += 1
                shifts.append(
                    {
                        "employee_id": str(emp.id),
                        "shift_type": str(item.get("shift_type", "morning")),
                        "start_time": _parse_hhmm(str(item.get("start", "09:00"))),
                        "end_time": _parse_hhmm(str(item.get("end", "17:00"))),
                        "position": position,
                    }
                )
        return shifts
