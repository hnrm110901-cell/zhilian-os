"""
Workforce Auto Schedule Service

Phase 8 Month 3:
- 自动排班（复用 packages/agents/schedule）
- 人工成本预算硬约束检查
- 异常提醒（企微）
"""

from __future__ import annotations

import calendar
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.schedule import Schedule, Shift
from src.repositories import EmployeeRepository, ScheduleRepository
from src.services.schedule_conflict_service import detect_schedule_conflicts
from src.services.staffing_pattern_service import StaffingPatternService
from src.services.wechat_service import wechat_service

logger = structlog.get_logger()

_DEFAULT_HOURLY_WAGE: Dict[str, float] = {
    "waiter": 18.0,
    "chef": 25.0,
    "cashier": 18.0,
    "manager": 35.0,
    "default": 20.0,
}


def calculate_shift_hours(start_time: time, end_time: time) -> float:
    """计算班次时长（支持跨天）。"""
    start_dt = datetime.combine(date.today(), start_time)
    end_dt = datetime.combine(date.today(), end_time)
    if end_dt <= start_dt:
        end_dt += timedelta(days=1)
    return round((end_dt - start_dt).total_seconds() / 3600, 2)


def estimate_labor_cost_yuan(
    shifts: List[Dict[str, Any]],
    wage_map: Optional[Dict[str, float]] = None,
) -> float:
    """按班次估算总人工成本。"""
    merged = {**_DEFAULT_HOURLY_WAGE, **(wage_map or {})}
    total = 0.0
    for shift in shifts:
        position = (shift.get("position") or "default").lower()
        hourly_wage = merged.get(position, merged["default"])
        total += calculate_shift_hours(shift["start_time"], shift["end_time"]) * hourly_wage
    return round(total, 2)


def build_schedule_anomalies(
    shifts: List[Dict[str, Any]],
    estimated_cost_yuan: float,
    daily_budget_yuan: Optional[float],
    max_hours_per_day: float = 8.0,
) -> List[Dict[str, Any]]:
    """构建排班异常列表：预算超限、工时超限、关键岗位缺失。"""
    anomalies: List[Dict[str, Any]] = []

    if daily_budget_yuan and estimated_cost_yuan > daily_budget_yuan:
        over = round(estimated_cost_yuan - daily_budget_yuan, 2)
        anomalies.append(
            {
                "type": "budget_overrun",
                "severity": "high",
                "message": f"预估人工成本超预算 ¥{over}",
                "estimated_cost_yuan": estimated_cost_yuan,
                "daily_budget_yuan": daily_budget_yuan,
                "over_budget_yuan": over,
            }
        )

    hours_by_employee: Dict[str, float] = {}
    for shift in shifts:
        employee_id = str(shift["employee_id"])
        hours_by_employee[employee_id] = (
            hours_by_employee.get(employee_id, 0.0)
            + calculate_shift_hours(shift["start_time"], shift["end_time"])
        )

    for employee_id, hours in hours_by_employee.items():
        if hours > max_hours_per_day:
            anomalies.append(
                {
                    "type": "overtime_risk",
                    "severity": "medium",
                    "employee_id": employee_id,
                    "message": f"员工 {employee_id} 当日排班 {round(hours, 2)} 小时，超过 {max_hours_per_day} 小时",
                    "hours": round(hours, 2),
                }
            )

    covered_positions = {str(s.get("position") or "").lower() for s in shifts}
    if "cashier" not in covered_positions:
        anomalies.append(
            {
                "type": "role_gap",
                "severity": "high",
                "message": "排班缺少收银岗位，存在营业高峰执行风险",
                "missing_position": "cashier",
            }
        )

    return anomalies


class WorkforceAutoScheduleService:
    """自动排班 + 预算约束 + 异常提醒。"""

    @staticmethod
    async def generate_schedule_with_constraints(
        store_id: str,
        schedule_date: date,
        db: AsyncSession,
        *,
        auto_publish: bool = True,
        notify_on_anomaly: bool = True,
        recipient_user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        existing = await ScheduleRepository.get_by_date(db, store_id, schedule_date)
        if existing:
            return {
                "created": False,
                "reason": "exists",
                "schedule_id": str(existing.id),
                "store_id": store_id,
                "schedule_date": schedule_date.isoformat(),
            }

        employees = await EmployeeRepository.get_by_store(db, store_id)
        active_employees = [e for e in employees if getattr(e, "is_active", True)]
        if not active_employees:
            raise ValueError("该门店暂无在职员工，无法自动排班")

        # 提前获取预算，作为排班生成的硬约束传入 Agent
        daily_budget = await WorkforceAutoScheduleService._fetch_daily_budget_yuan(
            store_id=store_id,
            schedule_date=schedule_date,
            db=db,
        )

        shifts_payload = await StaffingPatternService.build_shifts_from_best_pattern(
            store_id=store_id,
            target_date=schedule_date,
            db=db,
        )
        source = "staffing_pattern"
        if not shifts_payload:
            shifts_payload = await WorkforceAutoScheduleService._generate_shifts_from_agent(
                store_id=store_id,
                schedule_date=schedule_date,
                employees=active_employees,
                daily_budget_yuan=daily_budget,
            )
            source = "schedule_agent"
        if not shifts_payload:
            raise ValueError("自动排班失败：未生成任何班次")

        conflicts = detect_schedule_conflicts(shifts_payload)
        if conflicts:
            raise ValueError(f"自动排班冲突: {conflicts[0]['message']}")

        estimated_cost = estimate_labor_cost_yuan(shifts_payload)
        anomalies = build_schedule_anomalies(
            shifts=shifts_payload,
            estimated_cost_yuan=estimated_cost,
            daily_budget_yuan=daily_budget,
        )

        schedule = Schedule(
            store_id=store_id,
            schedule_date=schedule_date,
            total_employees=str(len({str(s["employee_id"]) for s in shifts_payload})),
            total_hours=str(round(sum(calculate_shift_hours(s["start_time"], s["end_time"]) for s in shifts_payload), 1)),
            is_published=auto_publish,
            published_by="auto_scheduler" if auto_publish else None,
        )
        db.add(schedule)
        await db.flush()

        for s in shifts_payload:
            db.add(
                Shift(
                    schedule_id=schedule.id,
                    employee_id=str(s["employee_id"]),
                    shift_type=str(s["shift_type"]),
                    start_time=s["start_time"],
                    end_time=s["end_time"],
                    position=s.get("position"),
                )
            )

        await db.commit()

        notified = False
        if anomalies and notify_on_anomaly:
            notified = await WorkforceAutoScheduleService._notify_anomalies(
                store_id=store_id,
                schedule_date=schedule_date,
                anomalies=anomalies,
                recipient_user_id=recipient_user_id or f"store_{store_id}",
            )

        return {
            "created": True,
            "store_id": store_id,
            "schedule_id": str(schedule.id),
            "schedule_date": schedule_date.isoformat(),
            "auto_published": auto_publish,
            "daily_budget_yuan": daily_budget,
            "estimated_labor_cost_yuan": estimated_cost,
            "within_budget": (daily_budget is None) or (estimated_cost <= daily_budget),
            "anomaly_count": len(anomalies),
            "anomalies": anomalies,
            "notified": notified,
            "shift_count": len(shifts_payload),
            "source": source,
        }

    @staticmethod
    async def _generate_shifts_from_agent(
        store_id: str,
        schedule_date: date,
        employees: List[Any],
        daily_budget_yuan: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        employee_payload = []
        for e in employees:
            skills = list(getattr(e, "skills", None) or [])
            if not skills and getattr(e, "position", None):
                skills = [str(e.position)]
            employee_payload.append(
                {
                    "id": str(e.id),
                    "name": str(getattr(e, "name", e.id)),
                    "skills": skills,
                }
            )

        try:
            schedule_agent_cls = WorkforceAutoScheduleService._load_schedule_agent_cls()
            if schedule_agent_cls is None:
                raise RuntimeError("schedule agent unavailable")

            agent_config: Dict[str, Any] = {"store_id": store_id}
            if daily_budget_yuan is not None:
                agent_config["target_daily_labor_cost"] = daily_budget_yuan
            agent = schedule_agent_cls(agent_config)
            result = await agent.run(
                store_id=store_id,
                date=schedule_date.isoformat(),
                employees=employee_payload,
            )
            if not result.get("success"):
                raise RuntimeError(result.get("error", "schedule agent run failed"))

            mapped = WorkforceAutoScheduleService._map_agent_schedule(result.get("schedule", []))
            if mapped:
                return mapped
        except Exception as exc:
            logger.warning("workforce.auto_schedule.agent_fallback", store_id=store_id, error=str(exc))

        return WorkforceAutoScheduleService._fallback_greedy_schedule(employee_payload)

    @staticmethod
    def _load_schedule_agent_cls():
        repo_root = next(
            (p for p in Path(__file__).resolve().parents if (p / "packages").is_dir()),
            Path(__file__).resolve().parents[2],
        )
        core_dir = Path(__file__).resolve().parents[1] / "core"
        if str(core_dir) not in sys.path:
            sys.path.insert(0, str(core_dir))
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        try:
            from packages.agents.schedule.src.agent import ScheduleAgent

            return ScheduleAgent
        except Exception as exc:
            logger.warning("workforce.auto_schedule.import_failed", error=str(exc))
            return None

    @staticmethod
    def _map_agent_schedule(schedule_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        shift_type_map = {
            "morning": ("06:00", "14:00"),
            "afternoon": ("14:00", "22:00"),
            "evening": ("18:00", "02:00"),
            "full_day": ("09:00", "21:00"),
        }
        mapped: List[Dict[str, Any]] = []
        for row in schedule_rows:
            shift_type = str(row.get("shift") or "morning")
            start = str(row.get("start_time") or shift_type_map.get(shift_type, ("09:00", "17:00"))[0])
            end = str(row.get("end_time") or shift_type_map.get(shift_type, ("09:00", "17:00"))[1])
            start_h, start_m = map(int, start.split(":"))
            end_h, end_m = map(int, end.split(":"))
            mapped.append(
                {
                    "employee_id": str(row["employee_id"]),
                    "shift_type": shift_type,
                    "start_time": time(start_h, start_m),
                    "end_time": time(end_h, end_m),
                    "position": str(row.get("skill") or "waiter"),
                }
            )
        return mapped

    @staticmethod
    def _fallback_greedy_schedule(employees: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not employees:
            return []
        shift_rules = {
            "morning": ("08:00", "14:00", ["waiter", "cashier", "chef"]),
            "afternoon": ("14:00", "20:00", ["waiter", "cashier", "chef"]),
            "evening": ("20:00", "23:00", ["waiter", "manager"]),
        }
        rows: List[Dict[str, Any]] = []
        idx = 0
        for shift_type, (start, end, needs) in shift_rules.items():
            start_h, start_m = map(int, start.split(":"))
            end_h, end_m = map(int, end.split(":"))
            for pos in needs:
                candidates = [e for e in employees if pos in (e.get("skills") or [])] or employees
                selected = candidates[idx % len(candidates)]
                idx += 1
                rows.append(
                    {
                        "employee_id": str(selected["id"]),
                        "shift_type": shift_type,
                        "start_time": time(start_h, start_m),
                        "end_time": time(end_h, end_m),
                        "position": pos,
                    }
                )
        return rows

    @staticmethod
    async def _fetch_daily_budget_yuan(
        store_id: str,
        schedule_date: date,
        db: AsyncSession,
    ) -> Optional[float]:
        period = schedule_date.strftime("%Y-%m")
        result = await db.execute(
            text(
                """
                SELECT daily_budget_yuan, max_labor_cost_yuan
                FROM store_labor_budgets
                WHERE store_id = :sid
                  AND budget_period = :period
                  AND is_active = TRUE
                ORDER BY updated_at DESC
                LIMIT 1
                """
            ),
            {"sid": store_id, "period": period},
        )
        row = result.fetchone()
        if not row:
            return None
        if row.daily_budget_yuan is not None:
            return float(row.daily_budget_yuan)
        if row.max_labor_cost_yuan is not None:
            days = calendar.monthrange(schedule_date.year, schedule_date.month)[1]
            return round(float(row.max_labor_cost_yuan) / days, 2)
        return None

    @staticmethod
    async def _notify_anomalies(
        store_id: str,
        schedule_date: date,
        anomalies: List[Dict[str, Any]],
        recipient_user_id: str,
    ) -> bool:
        top = anomalies[:3]
        detail_lines = [f"{idx}. {item.get('message', '异常')}" for idx, item in enumerate(top, start=1)]
        description = (
            f"门店：{store_id}<br/>"
            f"日期：{schedule_date.isoformat()}<br/>"
            f"异常数：{len(anomalies)}<br/>"
            f"{'<br/>'.join(detail_lines)}"
        )
        try:
            await wechat_service.send_decision_card(
                to_user_id=recipient_user_id,
                title="自动排班异常提醒",
                description=description,
                action_url=f"/workforce?store_id={store_id}&date={schedule_date.isoformat()}",
                btntxt="查看",
                message_id=f"wf_auto_schedule_anomaly:{store_id}:{schedule_date.isoformat()}",
            )
            return True
        except Exception as exc:
            logger.warning(
                "workforce.auto_schedule.notify_failed",
                store_id=store_id,
                recipient=recipient_user_id,
                error=str(exc),
            )
            return False
