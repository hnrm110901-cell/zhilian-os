"""
Smart Schedule Service — 智能排班服务
基于餐饮业务特征的自动排班算法，综合考虑需求预测、员工可用性、劳动法约束。

核心约束（劳动法+行业惯例）：
1. 每周工作不超过6天（标准工时制员工）
2. 每日工作不超过8小时（可调整为综合工时）
3. 连续工作不超过6天必须安排休息
4. 未成年工（如实习生）不安排夜班（22:00~06:00）
5. 孕期员工不安排夜班和加班

排班策略：
- 根据门店历史营业额/客流预测每日各时段需求人数
- 按岗位编制（服务员/厨师/收银/领班等）分配
- 尊重员工排班偏好（可选）
- 公平分配周末班和节假日班
"""

import json
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional, Tuple

import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.attendance import ShiftTemplate
from src.models.hr.employment_assignment import EmploymentAssignment
from src.models.hr.person import Person
from src.models.leave import LeaveRequest, LeaveRequestStatus
from src.models.schedule import Schedule, Shift
from src.models.schedule_demand import StoreStaffingDemand


@dataclass
class EmployeeView:
    """排班视图：Person + EmploymentAssignment 合并（替代旧 Employee 对象）。

    属性名与旧 Employee 保持兼容，降低迁移风险。
    """
    id: str               # assignment.id（排班以任职关系为键）
    person_id: str        # person.id
    name: str             # person.name
    position: str         # assignment.position or employment_type
    employment_status: str = "active"    # assignment.status 映射值
    store_id: Optional[str] = None       # person.store_id（过渡期兼容）
    preferences: Dict[str, Any] = field(default_factory=dict)

logger = structlog.get_logger()

# ── 常量 ──────────────────────────────────────────────────────

# 岗位排班优先级（高优先级岗位先分配，确保核心岗位有人）
POSITION_PRIORITY = {
    "chef": 1,
    "manager": 2,
    "cashier": 3,
    "host": 4,
    "waiter": 5,
    "dishwasher": 6,
}

# 默认编制基数（参考徐记海鲜中型门店）
DEFAULT_BASE_STAFFING = {
    "chef": 3,
    "waiter": 4,
    "cashier": 1,
    "host": 1,
    "manager": 1,
    "dishwasher": 2,
}

# 日期类型需求倍率
DAY_TYPE_MULTIPLIER = {
    "weekday": 0.8,  # 周一至周四
    "friday": 1.0,  # 周五
    "weekend": 1.2,  # 周六日
    "holiday": 1.5,  # 节假日
}

# 中国法定节假日列表（需定期维护，此处示例2026年）
# 实际生产环境应从配置表或外部API获取
HOLIDAYS_2026 = {
    date(2026, 1, 1),  # 元旦
    date(2026, 1, 2),
    date(2026, 1, 3),
    date(2026, 2, 17),  # 春节
    date(2026, 2, 18),
    date(2026, 2, 19),
    date(2026, 2, 20),
    date(2026, 2, 21),
    date(2026, 2, 22),
    date(2026, 2, 23),
    date(2026, 4, 5),  # 清明
    date(2026, 4, 6),
    date(2026, 4, 7),
    date(2026, 5, 1),  # 劳动节
    date(2026, 5, 2),
    date(2026, 5, 3),
    date(2026, 5, 4),
    date(2026, 5, 5),
    date(2026, 6, 19),  # 端午
    date(2026, 6, 20),
    date(2026, 6, 21),
    date(2026, 10, 1),  # 国庆+中秋
    date(2026, 10, 2),
    date(2026, 10, 3),
    date(2026, 10, 4),
    date(2026, 10, 5),
    date(2026, 10, 6),
    date(2026, 10, 7),
    date(2026, 10, 8),
}

# 夜班时间界定（劳动法：22:00 ~ 06:00 视为夜班）
NIGHT_SHIFT_START = time(22, 0)
NIGHT_SHIFT_END = time(6, 0)

# 每日最大工作时长（小时）
MAX_DAILY_HOURS = 8
# 综合工时制每日最大工作时长（小时）
MAX_DAILY_HOURS_COMPREHENSIVE = 10
# 每周最大工作天数
MAX_WEEKLY_DAYS = 6
# 连续最大工作天数
MAX_CONSECUTIVE_DAYS = 6

# 劳动法约束类型标识（用于 unresolved 原因追溯）
CONSTRAINT_NIGHT_MINOR = "night_minor"  # 未成年工夜班限制
CONSTRAINT_NIGHT_PREGNANT = "night_pregnant"  # 孕期员工夜班限制
CONSTRAINT_NIGHT_MEDICAL = "night_medical"  # 医疗限制夜班
CONSTRAINT_MAX_HOURS = "max_daily_hours"  # 超日工时上限
CONSTRAINT_MAX_CONSECUTIVE = "max_consecutive"  # 超连续工作天数

DAY_NAMES_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


class SmartScheduleService:
    """
    智能排班服务 — 基于餐饮业务特征的自动排班算法。

    使用方式：
        service = SmartScheduleService()
        result = await service.generate_weekly_schedule(
            db, store_id="S001", brand_id="B001",
            week_start=date(2026, 3, 16)
        )
    """

    # ──────────────────────────────────────────────────────────
    # 主入口：生成一周排班
    # ──────────────────────────────────────────────────────────

    async def generate_weekly_schedule(
        self,
        db: AsyncSession,
        store_id: str,
        brand_id: str,
        week_start: date,
        demand_forecast: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        生成一周排班计划。

        Args:
            db: 数据库会话
            store_id: 门店ID
            brand_id: 品牌ID
            week_start: 周一日期
            demand_forecast: 外部需求预测覆盖（可选）

        Returns:
            完整的周排班计划，包含每日班次、覆盖率、统计、警告等
        """
        # 确保 week_start 是周一
        if week_start.weekday() != 0:
            # 自动调整到本周一
            week_start = week_start - timedelta(days=week_start.weekday())
            logger.warning(
                "week_start 不是周一，已自动调整",
                adjusted_to=str(week_start),
            )

        week_end = week_start + timedelta(days=6)
        logger.info(
            "开始生成智能排班",
            store_id=store_id,
            week=f"{week_start} ~ {week_end}",
        )

        # 1. 获取班次模板
        shift_templates = await self._get_shift_templates(db, brand_id, store_id)
        if not shift_templates:
            # 使用默认班次模板
            shift_templates = self._default_shift_templates()
            logger.warning("未找到班次模板，使用默认模板", store_id=store_id)

        # 2. 获取所有在职员工
        all_employees = await self._get_store_employees(db, store_id)
        if not all_employees:
            return {
                "store_id": store_id,
                "week_start": str(week_start),
                "week_end": str(week_end),
                "daily_schedules": [],
                "stats": self._empty_stats(),
                "warnings": ["该门店没有在职员工，无法生成排班"],
                "unresolved": [],
            }

        # 3. 获取本周已批准请假
        leaves = await self._get_approved_leaves(db, store_id, week_start, week_end)

        # 4. 获取上周排班（用于计算连续工作天数、公平性）
        prev_week_start = week_start - timedelta(days=7)
        prev_schedules = await self._get_existing_shifts(db, store_id, prev_week_start, week_start - timedelta(days=1))

        # 5. 构建员工状态跟踪器
        tracker = self._build_employee_tracker(all_employees, leaves, prev_schedules, week_start)

        # 6. 逐日生成排班
        daily_schedules = []
        all_warnings: List[str] = []
        all_unresolved: List[str] = []
        total_shifts = 0
        total_hours = 0.0
        total_cost_fen = 0

        for day_offset in range(7):
            current_date = week_start + timedelta(days=day_offset)
            day_of_week = current_date.weekday()
            day_type = self._get_day_type(current_date)

            # 获取当日需求
            if demand_forecast and str(current_date) in demand_forecast:
                day_demand = demand_forecast[str(current_date)]
            else:
                day_demand = await self._get_demand_forecast(db, store_id, current_date)

            # 获取当日可用员工
            available = self._get_available_employees_for_date(tracker, current_date)

            # 贪心分配
            assignments, warnings, unresolved = self._assign_shifts_greedy(
                available, day_demand, shift_templates, tracker, current_date
            )

            # 更新 tracker（记录当日排班，影响后续天的连续工作天数）
            for assignment in assignments:
                emp_id = assignment["employee_id"]
                tracker[emp_id]["scheduled_dates"].add(current_date)
                tracker[emp_id]["weekly_hours"] += assignment["hours"]
                if day_of_week >= 5:  # 周六日
                    tracker[emp_id]["weekend_count"] += 1

            # 统计覆盖率
            coverage = defaultdict(int)
            for a in assignments:
                coverage[a["position"]] += 1

            day_schedule = {
                "date": str(current_date),
                "day_of_week": DAY_NAMES_CN[day_of_week],
                "day_type": day_type,
                "shifts": [
                    {
                        "employee_id": a["employee_id"],
                        "employee_name": a["employee_name"],
                        "position": a["position"],
                        "shift_template_id": a.get("shift_template_id"),
                        "shift_type": a["shift_type"],
                        "start_time": a["start_time"],
                        "end_time": a["end_time"],
                    }
                    for a in assignments
                ],
                "coverage": dict(coverage),
                "demand": day_demand,
            }
            daily_schedules.append(day_schedule)
            total_shifts += len(assignments)
            total_hours += sum(a["hours"] for a in assignments)
            total_cost_fen += sum(a.get("cost_fen", 0) for a in assignments)
            all_warnings.extend(warnings)
            all_unresolved.extend(unresolved)

        # 7. 统计公平性得分
        fairness_score = self._calculate_fairness_score(tracker, all_employees)
        scheduled_employees = sum(1 for t in tracker.values() if t["scheduled_dates"])

        # 8. 生成连续工作预警
        consecutive_warnings = self._check_consecutive_warnings(tracker, week_end)
        all_warnings.extend(consecutive_warnings)

        # 9. 覆盖率
        total_demand_slots = 0
        total_covered_slots = 0
        for ds in daily_schedules:
            for pos, needed in ds["demand"].items():
                total_demand_slots += needed
                total_covered_slots += min(ds["coverage"].get(pos, 0), needed)
        coverage_rate = round(total_covered_slots / total_demand_slots, 2) if total_demand_slots > 0 else 1.0

        result = {
            "store_id": store_id,
            "week_start": str(week_start),
            "week_end": str(week_end),
            "daily_schedules": daily_schedules,
            "stats": {
                "total_shifts": total_shifts,
                "employees_scheduled": scheduled_employees,
                "labor_hours": round(total_hours, 1),
                "estimated_labor_cost_fen": total_cost_fen,
                "estimated_labor_cost_yuan": round(total_cost_fen / 100, 2),
                "coverage_rate": coverage_rate,
                "fairness_score": fairness_score,
            },
            "warnings": all_warnings,
            "unresolved": all_unresolved,
        }

        logger.info(
            "智能排班生成完成",
            store_id=store_id,
            total_shifts=total_shifts,
            coverage_rate=coverage_rate,
            fairness=fairness_score,
            warnings_count=len(all_warnings),
        )
        return result

    # ──────────────────────────────────────────────────────────
    # 手动调整
    # ──────────────────────────────────────────────────────────

    async def adjust_schedule(
        self,
        db: AsyncSession,
        store_id: str,
        schedule_date: date,
        changes: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        手动调整排班：换班、加人、减人。

        changes 格式:
        [
            {"action": "swap", "from_employee_id": "E001", "to_employee_id": "E002"},
            {"action": "add", "employee_id": "E003", "shift_type": "morning", "position": "waiter"},
            {"action": "remove", "employee_id": "E004"},
        ]
        """
        # 获取当日排班
        stmt = select(Schedule).where(
            and_(
                Schedule.store_id == store_id,
                Schedule.schedule_date == schedule_date,
            )
        )
        result = await db.execute(stmt)
        schedule = result.scalar_one_or_none()

        if not schedule:
            return {
                "success": False,
                "message": f"未找到 {schedule_date} 的排班记录",
            }

        if schedule.is_published:
            return {
                "success": False,
                "message": "已发布的排班不能直接调整，请先撤回发布",
            }

        applied = []
        errors = []

        for change in changes:
            action = change.get("action")
            try:
                if action == "swap":
                    # 交换两位员工的班次
                    from_id = change["from_employee_id"]
                    to_id = change["to_employee_id"]
                    shifts_stmt = select(Shift).where(
                        and_(
                            Shift.schedule_id == schedule.id,
                            Shift.employee_id == from_id,
                        )
                    )
                    shift_result = await db.execute(shifts_stmt)
                    shift = shift_result.scalar_one_or_none()
                    if shift:
                        shift.employee_id = to_id
                        applied.append(f"换班: {from_id} → {to_id}")
                    else:
                        errors.append(f"未找到 {from_id} 的班次")

                elif action == "add":
                    # 加人
                    emp_id = change["employee_id"]
                    shift_type = change.get("shift_type", "morning")
                    position = change.get("position", "waiter")
                    # 根据 shift_type 获取默认时间
                    start_t, end_t = self._default_shift_times(shift_type)
                    new_shift = Shift(
                        id=uuid.uuid4(),
                        schedule_id=schedule.id,
                        employee_id=emp_id,
                        shift_type=shift_type,
                        start_time=start_t,
                        end_time=end_t,
                        position=position,
                    )
                    db.add(new_shift)
                    applied.append(f"加人: {emp_id} ({shift_type})")

                elif action == "remove":
                    # 减人
                    emp_id = change["employee_id"]
                    del_stmt = select(Shift).where(
                        and_(
                            Shift.schedule_id == schedule.id,
                            Shift.employee_id == emp_id,
                        )
                    )
                    del_result = await db.execute(del_stmt)
                    shift = del_result.scalar_one_or_none()
                    if shift:
                        await db.delete(shift)
                        applied.append(f"减人: {emp_id}")
                    else:
                        errors.append(f"未找到 {emp_id} 的班次")

            except Exception as e:
                errors.append(f"操作 {action} 失败: {str(e)}")

        await db.flush()

        return {
            "success": True,
            "date": str(schedule_date),
            "applied": applied,
            "errors": errors,
        }

    # ──────────────────────────────────────────────────────────
    # 发布排班
    # ──────────────────────────────────────────────────────────

    async def publish_schedule(
        self,
        db: AsyncSession,
        store_id: str,
        week_start: date,
        published_by: str = "system",
    ) -> Dict[str, Any]:
        """
        发布一周排班并通知员工。
        发布后排班不可直接修改（需先撤回）。
        """
        week_end = week_start + timedelta(days=6)

        stmt = select(Schedule).where(
            and_(
                Schedule.store_id == store_id,
                Schedule.schedule_date >= week_start,
                Schedule.schedule_date <= week_end,
            )
        )
        result = await db.execute(stmt)
        schedules = result.scalars().all()

        if not schedules:
            return {
                "success": False,
                "message": f"未找到 {week_start} ~ {week_end} 的排班记录",
            }

        published_count = 0
        for sched in schedules:
            if not sched.is_published:
                sched.is_published = True
                sched.published_by = published_by
                published_count += 1

        await db.flush()

        logger.info(
            "排班已发布",
            store_id=store_id,
            week=f"{week_start} ~ {week_end}",
            published_count=published_count,
        )

        return {
            "success": True,
            "store_id": store_id,
            "week_start": str(week_start),
            "week_end": str(week_end),
            "published_count": published_count,
            "message": f"已发布 {published_count} 天排班",
        }

    # ──────────────────────────────────────────────────────────
    # AI 优化建议
    # ──────────────────────────────────────────────────────────

    async def get_schedule_suggestions(
        self,
        db: AsyncSession,
        store_id: str,
        week_start: date,
    ) -> List[Dict[str, Any]]:
        """
        基于已生成排班，给出优化建议。
        分析维度：人力成本、覆盖缺口、公平性、合规风险。

        策略：
        - 合规检查（劳动法）始终走规则引擎，不依赖 LLM
        - 成本优化/公平性/效率分析 优先走 LLM，fallback 到规则
        - 每条建议必须包含 expected_saving_yuan（¥量化）
        """
        week_end = week_start + timedelta(days=6)

        # 获取当周排班
        stmt = select(Schedule).where(
            and_(
                Schedule.store_id == store_id,
                Schedule.schedule_date >= week_start,
                Schedule.schedule_date <= week_end,
            )
        )
        result = await db.execute(stmt)
        schedules = result.scalars().all()

        if not schedules:
            return [
                {
                    "type": "warning",
                    "title": "排班缺失",
                    "detail": "本周尚未生成排班，建议先运行自动排班",
                    "action": "generate_schedule",
                    "expected_saving_yuan": 0,
                    "confidence": 1.0,
                    "priority": "high",
                }
            ]

        # 获取员工信息用于分析
        employees = await self._get_store_employees(db, store_id)
        emp_map = {e.id: e for e in employees}

        # 获取班次明细
        schedule_ids = [s.id for s in schedules]
        shift_stmt = select(Shift).where(Shift.schedule_id.in_(schedule_ids))
        shift_result = await db.execute(shift_stmt)
        all_shifts = shift_result.scalars().all()

        # ── 1. 劳动法合规性扫描（规则引擎，始终执行） ──
        labor_violations = self._scan_labor_violations(all_shifts, schedules, emp_map)
        # 统一字段格式
        compliance_suggestions = []
        for v in labor_violations:
            compliance_suggestions.append(
                {
                    "type": "compliance",
                    "title": v["title"],
                    "detail": v["description"],
                    "action": v["action"],
                    "expected_saving_yuan": 0,
                    "confidence": v.get("confidence", 1.0),
                    "priority": "high",
                }
            )

        # ── 2. 收集排班上下文数据 ──
        context = self._build_schedule_context(store_id, week_start, schedules, all_shifts, emp_map)

        # ── 3. 尝试 LLM 分析（成本优化、公平性、效率） ──
        ai_suggestions = await self._get_ai_suggestions(context)

        # ── 4. 合并结果：合规在前（优先级最高），AI/规则建议在后 ──
        if ai_suggestions is not None:
            all_suggestions = compliance_suggestions + ai_suggestions
        else:
            # LLM 不可用，fallback 到规则引擎
            rule_suggestions = self._get_rule_based_suggestions(all_shifts, schedules, emp_map)
            all_suggestions = compliance_suggestions + rule_suggestions

        if not all_suggestions:
            all_suggestions.append(
                {
                    "type": "efficiency",
                    "title": "排班状况良好",
                    "detail": "当前排班无明显优化空间",
                    "action": None,
                    "expected_saving_yuan": 0,
                    "confidence": 0.90,
                    "priority": "low",
                }
            )

        return all_suggestions

    def _build_schedule_context(
        self,
        store_id: str,
        week_start: date,
        schedules: List[Any],
        all_shifts: List[Any],
        emp_map: Dict[str, Any],
    ) -> Dict[str, Any]:
        """收集排班上下文数据，用于 LLM 分析"""
        # 基本统计
        emp_hours: Dict[str, float] = defaultdict(float)
        emp_shift_count: Dict[str, int] = defaultdict(int)
        total_labor_hours = 0.0

        for shift in all_shifts:
            hours = self._calc_shift_hours(shift.start_time, shift.end_time)
            emp_hours[shift.employee_id] += hours
            emp_shift_count[shift.employee_id] += 1
            total_labor_hours += hours

        # 周末班分布（公平性指标）
        weekend_distribution: Dict[str, int] = defaultdict(int)
        for shift in all_shifts:
            for sched in schedules:
                if sched.id == shift.schedule_id and sched.schedule_date.weekday() >= 5:
                    emp = emp_map.get(shift.employee_id)
                    name = emp.name if emp else str(shift.employee_id)[:8]
                    weekend_distribution[name] += 1
                    break

        # 连续工作天数统计
        emp_dates: Dict[str, List[date]] = defaultdict(list)
        for shift in all_shifts:
            for sched in schedules:
                if sched.id == shift.schedule_id:
                    emp_dates[shift.employee_id].append(sched.schedule_date)
                    break

        consecutive_days_max: Dict[str, int] = {}
        for emp_id, dates_list in emp_dates.items():
            sorted_dates = sorted(set(dates_list))
            max_streak = 1
            current_streak = 1
            for i in range(1, len(sorted_dates)):
                if sorted_dates[i] - sorted_dates[i - 1] == timedelta(days=1):
                    current_streak += 1
                    max_streak = max(max_streak, current_streak)
                else:
                    current_streak = 1
            emp = emp_map.get(emp_id)
            name = emp.name if emp else str(emp_id)[:8]
            consecutive_days_max[name] = max_streak

        # 估算人力成本（假设平均时薪25元，加班1.5倍）
        estimated_cost_yuan = 0.0
        overtime_hours_month: Dict[str, float] = {}
        for emp_id, hours in emp_hours.items():
            emp = emp_map.get(emp_id)
            name = emp.name if emp else str(emp_id)[:8]
            base_rate = 25.0  # 默认时薪
            regular_hours = min(hours, 40)
            overtime = max(0, hours - 40)
            estimated_cost_yuan += regular_hours * base_rate + overtime * base_rate * 1.5
            if overtime > 0:
                overtime_hours_month[name] = round(overtime, 1)

        # 覆盖缺口分析
        coverage_gaps = []
        position_counts: Dict[str, int] = defaultdict(int)
        for shift in all_shifts:
            if shift.position:
                position_counts[shift.position] += 1
        for pos, base in DEFAULT_BASE_STAFFING.items():
            # 一周7天每天都需要的最低编制
            expected_weekly = base * len(schedules)
            actual = position_counts.get(pos, 0)
            if actual < expected_weekly * 0.7:
                coverage_gaps.append(f"{pos} 实际{actual}班次 vs 预期{expected_weekly}班次（不足30%+）")

        # 员工工时分布（用名字而非 ID）
        hours_by_name: Dict[str, float] = {}
        for emp_id, hours in emp_hours.items():
            emp = emp_map.get(emp_id)
            name = emp.name if emp else str(emp_id)[:8]
            hours_by_name[name] = round(hours, 1)

        # 用工类型分布
        fulltime_count = sum(1 for e in emp_map.values() if e.employment_type == "regular")
        parttime_count = sum(1 for e in emp_map.values() if e.employment_type in ("part_time", "parttime"))

        context = {
            "store_id": store_id,
            "week": str(week_start),
            "current_schedule": {
                "total_shifts": len(all_shifts),
                "employees_scheduled": len(emp_hours),
                "total_labor_hours": round(total_labor_hours, 1),
                "estimated_cost_yuan": round(estimated_cost_yuan, 2),
                "coverage_gaps": coverage_gaps,
            },
            "employee_stats": {
                "hours_distribution": hours_by_name,
                "weekend_distribution": dict(weekend_distribution),
                "consecutive_days_max": consecutive_days_max,
                "overtime_hours_month": overtime_hours_month,
            },
            "workforce": {
                "fulltime_count": fulltime_count,
                "parttime_count": parttime_count,
                "total_employees": len(emp_map),
            },
            "constraints_violated_count": 0,  # 合规问题由规则引擎独立处理
        }
        return context

    async def _get_ai_suggestions(self, context: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """
        调用 LLM 进行排班深度分析。
        返回 None 表示 LLM 不可用，需 fallback 到规则引擎。
        """
        from src.core.config import settings

        if not settings.LLM_ENABLED:
            logger.info("llm_disabled_fallback_to_rules")
            return None

        system_prompt = """你是一位连锁餐饮排班优化专家。
基于以下排班数据，分析排班效率并给出优化建议。

分析维度：
1. 人力成本效率：加班费/营业额比率是否合理？哪些时段人力过剩或不足？
2. 公平性：周末班和节假日班分配是否均衡？工时差距是否过大？
3. 效率优化：兼职替换正式工的空间？排班密度是否合理？
4. 优化空间：具体的调整方案，包含预期节省¥金额

注意：合规性（劳动法违规）由规则引擎单独处理，你不需要检查劳动法合规问题。

以纯JSON格式返回（不要包含```json标记），包含suggestions数组，每个suggestion包含：
- type: "cost_optimization" | "fairness" | "efficiency"
- title: 简短标题（中文，15字以内）
- detail: 详细分析（中文，2-3句话）
- action: 具体建议操作（英文标识符，如 rebalance_hours, replace_with_parttime）
- expected_saving_yuan: 预期月度节省金额（正数=节省，负数=增加投入，0=无直接金额影响）
- confidence: 0-1的置信度
- priority: "high" | "medium" | "low"

至少给出2条建议，最多5条。每条建议的expected_saving_yuan必须是具体数字。"""

        try:
            from src.core.llm import get_llm_client

            response = await get_llm_client().generate(
                prompt=json.dumps(context, ensure_ascii=False, default=str),
                system_prompt=system_prompt,
                max_tokens=1000,
                temperature=0.3,
            )

            # 解析 LLM 返回的 JSON
            parsed = json.loads(response.strip())
            raw_suggestions = parsed.get("suggestions", [])

            # 校验并规范化每条建议
            validated: List[Dict[str, Any]] = []
            for s in raw_suggestions:
                validated.append(
                    {
                        "type": s.get("type", "efficiency"),
                        "title": s.get("title", "优化建议"),
                        "detail": s.get("detail", ""),
                        "action": s.get("action"),
                        "expected_saving_yuan": float(s.get("expected_saving_yuan", 0)),
                        "confidence": min(1.0, max(0.0, float(s.get("confidence", 0.5)))),
                        "priority": s.get("priority", "medium"),
                    }
                )

            logger.info(
                "ai_schedule_suggestions_generated",
                store_id=context["store_id"],
                suggestion_count=len(validated),
            )
            return validated

        except json.JSONDecodeError as e:
            logger.warning(
                "ai_suggestions_json_parse_error",
                error=str(e),
                store_id=context["store_id"],
            )
            return None
        except Exception as e:
            logger.warning(
                "ai_suggestions_failed_fallback_to_rules",
                error=str(e),
                store_id=context["store_id"],
            )
            return None

    def _get_rule_based_suggestions(
        self,
        all_shifts: List[Any],
        schedules: List[Any],
        emp_map: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        规则引擎排班建议（LLM 不可用时的 fallback）。
        检查工时不均、周末班集中、兼职替换空间。
        """
        suggestions: List[Dict[str, Any]] = []

        # 分析1：员工工时不均
        emp_hours: Dict[str, float] = defaultdict(float)
        for shift in all_shifts:
            hours = self._calc_shift_hours(shift.start_time, shift.end_time)
            emp_hours[shift.employee_id] += hours

        if emp_hours:
            hours_list = list(emp_hours.values())
            max_hours = max(hours_list)
            min_hours = min(hours_list)

            if max_hours - min_hours > 16:
                max_emp = max(emp_hours, key=emp_hours.get)
                min_emp = min(emp_hours, key=emp_hours.get)
                max_name = emp_map.get(max_emp)
                min_name = emp_map.get(min_emp)
                max_name_str = max_name.name if max_name else str(max_emp)[:8]
                min_name_str = min_name.name if min_name else str(min_emp)[:8]

                suggestions.append(
                    {
                        "type": "fairness",
                        "title": "工时分配不均",
                        "detail": (
                            f"{max_name_str} 本周 {max_hours:.0f}h，"
                            f"{min_name_str} 仅 {min_hours:.0f}h，"
                            f"建议调整使工时差距 < 16h"
                        ),
                        "action": "rebalance_hours",
                        "expected_saving_yuan": 0,
                        "confidence": 0.85,
                        "priority": "medium",
                    }
                )

        # 分析2：周末班集中
        weekend_counts: Dict[str, int] = defaultdict(int)
        for shift in all_shifts:
            for sched in schedules:
                if sched.id == shift.schedule_id:
                    if sched.schedule_date.weekday() >= 5:
                        weekend_counts[shift.employee_id] += 1
                    break

        if weekend_counts:
            max_wk = max(weekend_counts.values())
            if max_wk >= 4:
                emp_id = max(weekend_counts, key=weekend_counts.get)
                emp_obj = emp_map.get(emp_id)
                name = emp_obj.name if emp_obj else str(emp_id)[:8]
                suggestions.append(
                    {
                        "type": "fairness",
                        "title": "周末班过于集中",
                        "detail": f"{name} 本周有 {max_wk} 个周末班次，建议分摊给其他同事",
                        "action": "redistribute_weekend",
                        "expected_saving_yuan": 0,
                        "confidence": 0.80,
                        "priority": "medium",
                    }
                )

        # 分析3：人力成本优化（兼职替换建议）
        fulltime_weekend_hours = 0.0
        for shift in all_shifts:
            for sched in schedules:
                if sched.id == shift.schedule_id and sched.schedule_date.weekday() >= 5:
                    emp = emp_map.get(shift.employee_id)
                    if emp and emp.employment_type == "regular":
                        fulltime_weekend_hours += self._calc_shift_hours(shift.start_time, shift.end_time)
                    break

        if fulltime_weekend_hours > 20:
            estimated_save_yuan = round(fulltime_weekend_hours * 15, 2)
            suggestions.append(
                {
                    "type": "cost_optimization",
                    "title": "周末可用兼职替换正式工",
                    "detail": (
                        f"本周周末正式工累计 {fulltime_weekend_hours:.0f}h，"
                        f"建议用兼职替换部分班次，预估月度可节省 ¥{estimated_save_yuan:.2f}"
                    ),
                    "action": "replace_with_parttime",
                    "expected_saving_yuan": estimated_save_yuan,
                    "confidence": 0.70,
                    "priority": "medium",
                }
            )

        return suggestions

    # ──────────────────────────────────────────────────────────
    # AI 人力成本效率分析
    # ──────────────────────────────────────────────────────────

    async def analyze_labor_cost_efficiency(
        self,
        db: AsyncSession,
        store_id: str,
        month: date,
    ) -> Dict[str, Any]:
        """
        分析门店人力成本效率 — Claude驱动

        分析维度：
        - 人力成本/营业额比率趋势
        - 加班费/总人力成本比率
        - 人均产出（营业额/在岗人数）
        - 优化建议（排班调整 vs 编制调整 vs 用工类型调整）
        """
        # 获取月度排班数据
        month_start = month.replace(day=1)
        if month.month == 12:
            month_end = month.replace(year=month.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            month_end = month.replace(month=month.month + 1, day=1) - timedelta(days=1)

        stmt = select(Schedule).where(
            and_(
                Schedule.store_id == store_id,
                Schedule.schedule_date >= month_start,
                Schedule.schedule_date <= month_end,
            )
        )
        result = await db.execute(stmt)
        schedules = result.scalars().all()

        employees = await self._get_store_employees(db, store_id)
        emp_map = {e.id: e for e in employees}

        # 统计月度工时
        total_labor_hours = 0.0
        emp_hours: Dict[str, float] = defaultdict(float)
        overtime_hours: Dict[str, float] = defaultdict(float)

        if schedules:
            schedule_ids = [s.id for s in schedules]
            shift_stmt = select(Shift).where(Shift.schedule_id.in_(schedule_ids))
            shift_result = await db.execute(shift_stmt)
            all_shifts = shift_result.scalars().all()

            # 按员工、按周统计工时
            emp_weekly_hours: Dict[str, Dict[int, float]] = defaultdict(lambda: defaultdict(float))
            for shift in all_shifts:
                hours = self._calc_shift_hours(shift.start_time, shift.end_time)
                emp_hours[shift.employee_id] += hours
                total_labor_hours += hours
                for sched in schedules:
                    if sched.id == shift.schedule_id:
                        week_num = sched.schedule_date.isocalendar()[1]
                        emp_weekly_hours[shift.employee_id][week_num] += hours
                        break

            # 计算加班工时（每周超过40小时部分）
            for emp_id, weekly in emp_weekly_hours.items():
                for week_num, hours in weekly.items():
                    ot = max(0, hours - 40)
                    if ot > 0:
                        overtime_hours[emp_id] += ot
        else:
            all_shifts = []

        total_overtime = sum(overtime_hours.values())
        base_rate = 25.0  # 默认平均时薪
        estimated_labor_cost = (total_labor_hours - total_overtime) * base_rate + total_overtime * base_rate * 1.5
        overtime_cost = total_overtime * base_rate * 0.5  # 加班溢价部分

        # 用工结构分析
        fulltime_hours = sum(
            h for eid, h in emp_hours.items() if emp_map.get(eid) and emp_map[eid].employment_type == "regular"
        )
        parttime_hours = total_labor_hours - fulltime_hours

        # 基础分析数据
        analysis_data = {
            "store_id": store_id,
            "month": str(month_start),
            "metrics": {
                "total_labor_hours": round(total_labor_hours, 1),
                "total_overtime_hours": round(total_overtime, 1),
                "estimated_labor_cost_yuan": round(estimated_labor_cost, 2),
                "overtime_cost_yuan": round(overtime_cost, 2),
                "overtime_cost_ratio": round(overtime_cost / estimated_labor_cost * 100, 1) if estimated_labor_cost > 0 else 0,
                "avg_hours_per_employee": round(total_labor_hours / len(emp_hours), 1) if emp_hours else 0,
                "fulltime_hours_ratio": round(fulltime_hours / total_labor_hours * 100, 1) if total_labor_hours > 0 else 0,
                "employee_count": len(emp_hours),
                "schedule_days": len(schedules),
            },
            "workforce_structure": {
                "fulltime_hours": round(fulltime_hours, 1),
                "parttime_hours": round(parttime_hours, 1),
                "fulltime_count": sum(1 for e in emp_map.values() if e.employment_type == "regular"),
                "parttime_count": sum(1 for e in emp_map.values() if e.employment_type in ("part_time", "parttime")),
            },
            "suggestions": [],
        }

        # 尝试 LLM 深度分析
        from src.core.config import settings

        if settings.LLM_ENABLED:
            ai_analysis = await self._get_ai_labor_analysis(analysis_data)
            if ai_analysis:
                analysis_data["suggestions"] = ai_analysis.get("suggestions", [])
                analysis_data["ai_summary"] = ai_analysis.get("summary", "")
                return analysis_data

        # Fallback: 规则引擎建议
        if total_overtime > 20:
            analysis_data["suggestions"].append(
                {
                    "type": "cost_optimization",
                    "title": "加班工时偏高",
                    "detail": (
                        f"本月加班 {total_overtime:.0f}h，加班费约 ¥{overtime_cost:.2f}，"
                        f"建议增加兼职或调整排班密度以减少加班"
                    ),
                    "action": "reduce_overtime",
                    "expected_saving_yuan": round(overtime_cost * 0.5, 2),
                    "confidence": 0.75,
                    "priority": "high",
                }
            )

        if parttime_hours > 0 and fulltime_hours / total_labor_hours > 0.9 and total_labor_hours > 0:
            analysis_data["suggestions"].append(
                {
                    "type": "cost_optimization",
                    "title": "兼职工比例偏低",
                    "detail": "正式工工时占比超90%，周末高峰时段可增加兼职工降低人力成本",
                    "action": "increase_parttime_ratio",
                    "expected_saving_yuan": round(fulltime_hours * 0.1 * 15, 2),
                    "confidence": 0.65,
                    "priority": "medium",
                }
            )

        return analysis_data

    async def _get_ai_labor_analysis(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """调用 LLM 分析人力成本效率"""
        system_prompt = """你是一位连锁餐饮人力成本效率分析专家。
基于以下门店月度人力数据，给出深度分析和优化建议。

分析维度：
1. 人力成本效率：加班费占比是否合理？（行业基准：加班费 < 总人力成本的8%）
2. 用工结构：正式工/兼职工比例是否最优？（餐饮行业建议兼职占20-30%）
3. 人均产出：排班密度是否合理？
4. 优化方向：排班调整 vs 编制调整 vs 用工类型调整

以纯JSON格式返回（不要包含```json标记）：
{
  "summary": "一段话总结（中文，50字以内）",
  "suggestions": [
    {
      "type": "cost_optimization" | "efficiency",
      "title": "简短标题（中文，15字以内）",
      "detail": "详细分析（中文，2-3句话）",
      "action": "具体建议操作标识符",
      "expected_saving_yuan": 预期月度节省金额数字,
      "confidence": 0-1,
      "priority": "high" | "medium" | "low"
    }
  ]
}

至少给出2条建议，最多4条。每条建议必须有具体的expected_saving_yuan数字。"""

        try:
            from src.core.llm import get_llm_client

            response = await get_llm_client().generate(
                prompt=json.dumps(data, ensure_ascii=False, default=str),
                system_prompt=system_prompt,
                max_tokens=800,
                temperature=0.3,
            )

            parsed = json.loads(response.strip())
            logger.info(
                "ai_labor_analysis_completed",
                store_id=data["store_id"],
            )
            return parsed

        except Exception as e:
            logger.warning(
                "ai_labor_analysis_failed",
                error=str(e),
                store_id=data["store_id"],
            )
            return None

    def _scan_labor_violations(
        self,
        shifts: List[Any],
        schedules: List[Any],
        emp_map: Dict[str, EmployeeView],
    ) -> List[Dict[str, Any]]:
        """
        扫描现有排班中的劳动法违规项。
        这是事后校验，用于检测手动调整或历史排班中的合规问题。

        检查项：
        1. 未成年工被安排夜班
        2. 孕期员工被安排夜班
        3. 医疗限制员工被安排夜班
        4. 连续工作超过6天
        5. 单日工时超上限
        """
        violations: List[Dict[str, Any]] = []

        # 构建每个员工的排班日期和班次信息
        emp_shifts: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for shift in shifts:
            sched_date = None
            for sched in schedules:
                if sched.id == shift.schedule_id:
                    sched_date = sched.schedule_date
                    break

            emp_shifts[shift.employee_id].append(
                {
                    "date": sched_date,
                    "start_time": shift.start_time,
                    "end_time": shift.end_time,
                    "shift_type": shift.shift_type,
                }
            )

        for emp_id, shift_list in emp_shifts.items():
            emp = emp_map.get(emp_id)
            if not emp:
                continue

            # ── 检查1：夜班合规 ──
            for s in shift_list:
                if s["start_time"] and s["end_time"]:
                    is_night = self._is_night_shift_template(s["start_time"], s["end_time"])
                    if not is_night:
                        continue

                    # 未成年工夜班违规
                    if self._is_minor(emp):
                        violations.append(
                            {
                                "type": "violation",
                                "title": f"【违法】未成年工 {emp.name} 被安排夜班",
                                "description": (
                                    f"{emp.name}（未满18周岁）在 {s['date']} 被安排夜班"
                                    f"（{s['start_time']}~{s['end_time']}），"
                                    f"违反《劳动法》第64条，必须立即调整"
                                ),
                                "action": "remove_night_shift",
                                "impact_yuan": None,
                                "confidence": 1.0,
                            }
                        )

                    # 孕期员工夜班违规
                    prefs = emp.preferences or {}
                    if prefs.get("is_pregnant"):
                        violations.append(
                            {
                                "type": "violation",
                                "title": f"【违法】孕期员工 {emp.name} 被安排夜班",
                                "description": (
                                    f"{emp.name}（孕期）在 {s['date']} 被安排夜班"
                                    f"（{s['start_time']}~{s['end_time']}），"
                                    f"违反《劳动法》第61条，必须立即调整"
                                ),
                                "action": "remove_night_shift",
                                "impact_yuan": None,
                                "confidence": 1.0,
                            }
                        )

                    # 医疗限制员工夜班
                    if prefs.get("medical_restriction"):
                        violations.append(
                            {
                                "type": "violation",
                                "title": f"【注意】医疗限制员工 {emp.name} 被安排夜班",
                                "description": (
                                    f"{emp.name}（{prefs.get('medical_note', '医疗限制')}）"
                                    f"在 {s['date']} 被安排夜班，建议调整"
                                ),
                                "action": "remove_night_shift",
                                "impact_yuan": None,
                                "confidence": 0.95,
                            }
                        )

            # ── 检查2：连续工作天数 ──
            work_dates = sorted(set(s["date"] for s in shift_list if s["date"]))
            if work_dates:
                max_streak = 1
                current_streak = 1
                for i in range(1, len(work_dates)):
                    if work_dates[i] - work_dates[i - 1] == timedelta(days=1):
                        current_streak += 1
                        max_streak = max(max_streak, current_streak)
                    else:
                        current_streak = 1

                if max_streak > MAX_CONSECUTIVE_DAYS:
                    violations.append(
                        {
                            "type": "violation",
                            "title": f"【违规】{emp.name} 连续工作{max_streak}天",
                            "description": (
                                f"{emp.name} 连续工作 {max_streak} 天（上限 {MAX_CONSECUTIVE_DAYS} 天），"
                                f"违反连续工作天数限制，需安排休息日"
                            ),
                            "action": "add_rest_day",
                            "impact_yuan": None,
                            "confidence": 1.0,
                        }
                    )

            # ── 检查3：单日工时超上限 ──
            work_hour_type = emp.work_hour_type or "标准工时"
            max_hours = MAX_DAILY_HOURS_COMPREHENSIVE if work_hour_type == "综合工时" else MAX_DAILY_HOURS
            for s in shift_list:
                if s["start_time"] and s["end_time"]:
                    hours = self._calc_shift_hours(s["start_time"], s["end_time"])
                    if hours > max_hours:
                        violations.append(
                            {
                                "type": "violation",
                                "title": f"【违规】{emp.name} 在 {s['date']} 工时超限",
                                "description": (
                                    f"{emp.name} 在 {s['date']} 排班 {hours:.1f}h，" f"超过{work_hour_type}制上限 {max_hours}h"
                                ),
                                "action": "reduce_hours",
                                "impact_yuan": None,
                                "confidence": 1.0,
                            }
                        )

        return violations

    # ──────────────────────────────────────────────────────────
    # 内部方法：数据获取
    # ──────────────────────────────────────────────────────────

    async def _get_shift_templates(self, db: AsyncSession, brand_id: str, store_id: str) -> List[ShiftTemplate]:
        """获取班次模板（门店级优先，品牌级兜底）"""
        stmt = (
            select(ShiftTemplate)
            .where(
                and_(
                    ShiftTemplate.brand_id == brand_id,
                    ShiftTemplate.is_active.is_(True),
                    (ShiftTemplate.store_id == store_id) | ShiftTemplate.store_id.is_(None),
                )
            )
            .order_by(ShiftTemplate.sort_order, ShiftTemplate.start_time)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def _get_store_employees(self, db: AsyncSession, store_id: str) -> List[EmployeeView]:
        """获取门店所有在职员工（基于 Person + EmploymentAssignment 三层模型）"""
        stmt = (
            select(Person, EmploymentAssignment)
            .join(EmploymentAssignment, EmploymentAssignment.person_id == Person.id)
            .where(
                and_(
                    Person.store_id == store_id,
                    Person.is_active.is_(True),
                    EmploymentAssignment.status == "active",
                )
            )
            .order_by(EmploymentAssignment.position, Person.name)
        )
        result = await db.execute(stmt)
        rows = result.all()
        return [
            EmployeeView(
                id=str(assignment.id),
                person_id=str(person.id),
                name=person.name,
                position=assignment.position or assignment.employment_type or "waiter",
                employment_status="active",
                store_id=person.store_id,
                preferences=person.preferences or {},
            )
            for person, assignment in rows
        ]

    async def _get_approved_leaves(
        self,
        db: AsyncSession,
        store_id: str,
        start: date,
        end: date,
    ) -> List[LeaveRequest]:
        """获取指定日期范围内已批准的请假"""
        stmt = select(LeaveRequest).where(
            and_(
                LeaveRequest.store_id == store_id,
                LeaveRequest.status == LeaveRequestStatus.APPROVED,
                LeaveRequest.start_date <= end,
                LeaveRequest.end_date >= start,
            )
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def _get_existing_shifts(
        self,
        db: AsyncSession,
        store_id: str,
        start: date,
        end: date,
    ) -> List[Dict[str, Any]]:
        """获取已有排班（用于计算连续工作天数等历史数据）"""
        stmt = (
            select(Schedule, Shift)
            .join(Shift, Schedule.id == Shift.schedule_id)
            .where(
                and_(
                    Schedule.store_id == store_id,
                    Schedule.schedule_date >= start,
                    Schedule.schedule_date <= end,
                )
            )
        )
        result = await db.execute(stmt)
        rows = result.all()

        shifts = []
        for schedule, shift in rows:
            shifts.append(
                {
                    "employee_id": shift.employee_id,
                    "date": schedule.schedule_date,
                    "shift_type": shift.shift_type,
                }
            )
        return shifts

    async def _get_demand_forecast(self, db: AsyncSession, store_id: str, target_date: date) -> Dict[str, int]:
        """
        获取指定日期的人力需求预测。
        优先从 store_staffing_demands 表读取配置，
        没有配置则使用默认编制 × 日期类型倍率。
        """
        day_type = self._get_day_type(target_date)

        # 尝试从配置表获取
        stmt = select(StoreStaffingDemand).where(
            and_(
                StoreStaffingDemand.store_id == store_id,
                StoreStaffingDemand.day_type == day_type,
                StoreStaffingDemand.is_active.is_(True),
            )
        )
        result = await db.execute(stmt)
        demands = result.scalars().all()

        if demands:
            # 按岗位汇总（取各班次的 min_count 之和作为全天需求）
            # 注意：这里简化为取各岗位在所有活跃班次中的最大 min_count
            position_demand: Dict[str, int] = {}
            for d in demands:
                current = position_demand.get(d.position, 0)
                position_demand[d.position] = max(current, d.min_count)
            return position_demand

        # 降级：使用默认编制 × 倍率
        multiplier = DAY_TYPE_MULTIPLIER.get(day_type, 1.0)
        demand = {}
        for position, base_count in DEFAULT_BASE_STAFFING.items():
            demand[position] = max(1, round(base_count * multiplier))
        return demand

    # ──────────────────────────────────────────────────────────
    # 内部方法：约束判断与跟踪
    # ──────────────────────────────────────────────────────────

    def _get_day_type(self, d: date) -> str:
        """判断日期类型"""
        if d in HOLIDAYS_2026:
            return "holiday"
        weekday = d.weekday()
        if weekday < 4:  # 0=周一 ~ 3=周四
            return "weekday"
        elif weekday == 4:  # 周五
            return "friday"
        else:  # 5=周六, 6=周日
            return "weekend"

    def _build_employee_tracker(
        self,
        employees: List[EmployeeView],
        leaves: List[LeaveRequest],
        prev_shifts: List[Dict[str, Any]],
        week_start: date,
    ) -> Dict[str, Dict[str, Any]]:
        """
        构建员工排班状态跟踪器。
        包含：请假日期集合、上周连续工作天数、本周已排日期集合等。
        """
        tracker: Dict[str, Dict[str, Any]] = {}

        for emp in employees:
            # 计算上周连续工作天数
            prev_dates = set()
            for ps in prev_shifts:
                if ps["employee_id"] == emp.id:
                    prev_dates.add(ps["date"])

            # 从上周日往前数连续工作天数
            consecutive = 0
            check_date = week_start - timedelta(days=1)
            while check_date in prev_dates:
                consecutive += 1
                check_date -= timedelta(days=1)

            # 请假日期集合
            leave_dates: set = set()
            for leave in leaves:
                if leave.employee_id == emp.id:
                    d = leave.start_date
                    while d <= leave.end_date:
                        leave_dates.add(d)
                        d += timedelta(days=1)

            # ── 劳动法受保护身份判断 ──

            # 未成年工判断：基于 birth_date 计算年龄
            is_minor = False
            if emp.birth_date:
                age = (week_start - emp.birth_date).days / 365.25
                if age < 18:
                    is_minor = True

            # 孕期标记：通过请假类型推断（产假记录）或 preferences 标记
            is_pregnant = False
            for leave in leaves:
                if (
                    leave.employee_id == emp.id
                    and hasattr(leave, "leave_category")
                    and str(leave.leave_category) in ("maternity", "LeaveCategory.MATERNITY")
                ):
                    is_pregnant = True
                    break
            # 也检查 preferences 中的孕期标记（由HR手动设置）
            prefs = emp.preferences or {}
            if prefs.get("is_pregnant"):
                is_pregnant = True

            # 医疗限制：通过 preferences.medical_restriction 标记
            # 例如：{"medical_restriction": "no_night_shift", "medical_note": "腰椎术后恢复期"}
            has_medical_restriction = bool(prefs.get("medical_restriction"))
            medical_note = prefs.get("medical_note", "")

            tracker[emp.id] = {
                "employee": emp,
                "leave_dates": leave_dates,
                "consecutive_from_prev": consecutive,
                "scheduled_dates": set(),
                "weekly_hours": 0.0,
                "weekend_count": 0,
                "is_minor": is_minor,
                "is_pregnant": is_pregnant,
                "has_medical_restriction": has_medical_restriction,
                "medical_note": medical_note,
                "work_hour_type": emp.work_hour_type or "标准工时",
            }

        return tracker

    def _get_available_employees_for_date(self, tracker: Dict[str, Dict[str, Any]], target_date: date) -> List[Dict[str, Any]]:
        """获取某日可排班的员工列表（排除请假、已达最大天数等）"""
        available = []
        for emp_id, t in tracker.items():
            # 请假不可排
            if target_date in t["leave_dates"]:
                continue

            # 计算含本日的连续工作天数
            scheduled = t["scheduled_dates"]
            consecutive = t["consecutive_from_prev"]
            # 从 target_date 前一天往前数本周已排的连续天数
            check = target_date - timedelta(days=1)
            streak = 0
            while check in scheduled:
                streak += 1
                check -= timedelta(days=1)
            total_consecutive = streak + (consecutive if streak > 0 and not scheduled else 0)
            # 加上从上周延续的连续天数（仅当本周第一个排班日连续时）
            if streak == 0 and target_date == min((d for d in scheduled), default=target_date):
                total_consecutive = consecutive

            # 重新计算：从 target_date-1 往前看实际连续
            total_consecutive = 0
            check = target_date - timedelta(days=1)
            while check in scheduled:
                total_consecutive += 1
                check -= timedelta(days=1)
            # 如果连到上周，加上上周的连续
            if total_consecutive > 0 or not scheduled:
                if total_consecutive == len(scheduled):
                    # 本周排班都连续到上周
                    total_consecutive += consecutive

            if total_consecutive >= MAX_CONSECUTIVE_DAYS:
                continue

            # 本周工作天数上限
            if len(scheduled) >= MAX_WEEKLY_DAYS:
                continue

            emp = t["employee"]
            available.append(
                {
                    "employee_id": emp.id,
                    "employee_name": emp.name,
                    "position": emp.position or "waiter",
                    "employment_type": emp.employment_type or "regular",
                    "daily_wage_fen": emp.daily_wage_standard_fen or 0,
                    "skills": emp.skills or [],
                    "preferences": emp.preferences or {},
                    "consecutive_days": total_consecutive,
                    "weekly_hours": t["weekly_hours"],
                    "weekend_count": t["weekend_count"],
                    "is_minor": t["is_minor"],
                    "is_pregnant": t["is_pregnant"],
                    "has_medical_restriction": t["has_medical_restriction"],
                    "medical_note": t.get("medical_note", ""),
                    "work_hour_type": t.get("work_hour_type", "标准工时"),
                }
            )

        return available

    # ──────────────────────────────────────────────────────────
    # 核心：贪心排班分配算法
    # ──────────────────────────────────────────────────────────

    def _assign_shifts_greedy(
        self,
        available: List[Dict[str, Any]],
        demand: Dict[str, int],
        shift_templates: List[Any],
        tracker: Dict[str, Dict[str, Any]],
        current_date: date,
    ) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
        """
        贪心分配算法：
        1. 按岗位优先级排序需求（厨师 > 领班 > 收银 > 迎宾 > 服务员 > 洗碗工）
        2. 对每个岗位，按公平性排序候选员工
        3. 分配直到需求满足或无可用人员
        4. 检查劳动法约束

        Returns:
            (assignments, warnings, unresolved)
        """
        assignments: List[Dict[str, Any]] = []
        warnings: List[str] = []
        unresolved: List[str] = []

        # 已分配的员工ID（每日每人只排一班）
        assigned_ids: set = set()

        # 选择合适的班次模板（默认选第一个适用的模板）
        template_map = self._build_template_map(shift_templates)

        # 按岗位优先级排序
        sorted_positions = sorted(
            demand.keys(),
            key=lambda p: POSITION_PRIORITY.get(p, 99),
        )

        for position in sorted_positions:
            needed = demand[position]
            filled = 0

            # 筛选该岗位的候选人
            candidates = [e for e in available if e["employee_id"] not in assigned_ids and self._matches_position(e, position)]

            # 按公平性排序
            candidates.sort(
                key=lambda e: (
                    e["consecutive_days"],  # 连续天数少的优先
                    e["weekend_count"],  # 周末班少的优先
                    e["weekly_hours"],  # 本周工时少的优先
                    0 if e["position"] == position else 1,  # 精确匹配优先
                )
            )

            # 记录因劳动法约束被跳过的人数，用于 unresolved 原因分析
            skipped_by_constraint: Dict[str, int] = defaultdict(int)

            for candidate in candidates:
                if filled >= needed:
                    break

                emp_id = candidate["employee_id"]

                # 选择班次
                shift_type, start_t, end_t, template_id = self._pick_shift(template_map, position, current_date)

                # ── 劳动法强制约束检查（违反则跳过，不可覆盖） ──

                # 约束1：夜班限制 — 未成年工/孕期员工/医疗限制不可安排夜班
                is_night = self._is_night_shift_template(start_t, end_t)
                if is_night:
                    restriction_reason = self._is_restricted_from_night(candidate)
                    if restriction_reason:
                        warnings.append(f"{candidate['employee_name']}({restriction_reason})不可安排夜班，已自动跳过")
                        skipped_by_constraint[restriction_reason] += 1
                        continue

                # 计算工时
                hours = self._calc_shift_hours(start_t, end_t)

                # 约束2：每日工时上限 — 标准工时制不超过8h，综合工时制不超过10h
                max_hours = MAX_DAILY_HOURS_COMPREHENSIVE if candidate.get("work_hour_type") == "综合工时" else MAX_DAILY_HOURS
                if hours > max_hours:
                    warnings.append(
                        f"{candidate['employee_name']} 班次 {hours:.1f}h 超过"
                        f"{'综合' if max_hours == MAX_DAILY_HOURS_COMPREHENSIVE else '标准'}工时制"
                        f" {max_hours}h 上限，已自动跳过"
                    )
                    skipped_by_constraint[CONSTRAINT_MAX_HOURS] += 1
                    continue

                # 约束3：连续工作天数 — 不超过6天（此处为二次校验，可防止并发排班场景）
                if candidate["consecutive_days"] >= MAX_CONSECUTIVE_DAYS:
                    warnings.append(
                        f"{candidate['employee_name']} 已连续工作{candidate['consecutive_days']}天"
                        f"（≥{MAX_CONSECUTIVE_DAYS}天），必须休息，已自动跳过"
                    )
                    skipped_by_constraint[CONSTRAINT_MAX_CONSECUTIVE] += 1
                    continue

                # 约束4：孕期员工不安排加班（超过标准8小时视为加班）
                if candidate["is_pregnant"] and hours > MAX_DAILY_HOURS:
                    warnings.append(
                        f"{candidate['employee_name']}(孕期员工)不可安排加班"
                        f"（{hours:.1f}h > {MAX_DAILY_HOURS}h），已自动跳过"
                    )
                    skipped_by_constraint[CONSTRAINT_NIGHT_PREGNANT] += 1
                    continue

                # ── 通过所有约束，分配班次 ──

                # 估算成本（日薪 / 8 × 实际工时）
                cost_fen = 0
                if candidate["daily_wage_fen"]:
                    cost_fen = int(candidate["daily_wage_fen"] * hours / 8)

                assignments.append(
                    {
                        "employee_id": emp_id,
                        "employee_name": candidate["employee_name"],
                        "position": position,
                        "shift_type": shift_type,
                        "shift_template_id": template_id,
                        "start_time": start_t.strftime("%H:%M") if isinstance(start_t, time) else start_t,
                        "end_time": end_t.strftime("%H:%M") if isinstance(end_t, time) else end_t,
                        "hours": hours,
                        "cost_fen": cost_fen,
                    }
                )
                assigned_ids.add(emp_id)
                filled += 1

            # 需求未满足 — 附带劳动法约束导致的缺口原因
            if filled < needed:
                gap = needed - filled
                day_cn = DAY_NAMES_CN[current_date.weekday()]
                reason_parts = [f"{current_date} ({day_cn}) 缺 {gap} 名{self._position_cn(position)}"]
                if skipped_by_constraint:
                    constraint_details = "、".join(f"{reason}{count}人" for reason, count in skipped_by_constraint.items())
                    reason_parts.append(f"（因劳动法约束跳过: {constraint_details}）")
                unresolved.append("".join(reason_parts))

        return assignments, warnings, unresolved

    # ──────────────────────────────────────────────────────────
    # 内部方法：辅助函数
    # ──────────────────────────────────────────────────────────

    def _matches_position(self, employee: Dict, position: str) -> bool:
        """判断员工是否能胜任该岗位（精确匹配或技能匹配）"""
        if employee["position"] == position:
            return True
        # 技能匹配：员工可能有多技能
        if position in (employee.get("skills") or []):
            return True
        # 服务员可以由任何岗位的人临时填充
        if position == "waiter":
            return True
        return False

    def _build_template_map(self, templates: List[Any]) -> Dict[str, Dict[str, Any]]:
        """构建班次模板索引：code → template 信息"""
        result = {}
        for t in templates:
            if isinstance(t, dict):
                code = t.get("code", t.get("shift_type", "morning"))
                result[code] = t
            else:
                result[t.code] = {
                    "id": str(t.id),
                    "code": t.code,
                    "start_time": t.start_time,
                    "end_time": t.end_time,
                    "is_cross_day": t.is_cross_day,
                    "applicable_positions": t.applicable_positions or [],
                }
        return result

    def _pick_shift(
        self,
        template_map: Dict[str, Dict[str, Any]],
        position: str,
        current_date: date,
    ) -> Tuple[str, time, time, Optional[str]]:
        """
        为指定岗位选择合适的班次。
        餐饮业默认逻辑：
        - 厨师通常排早班或中班（备餐）
        - 服务员各班均可
        - 收银/迎宾跟营业时间
        """
        # 尝试匹配模板
        preferred_codes = {
            "chef": ["morning", "afternoon"],
            "waiter": ["morning", "afternoon", "evening"],
            "cashier": ["morning", "afternoon"],
            "host": ["morning", "afternoon"],
            "manager": ["morning"],
            "dishwasher": ["morning", "afternoon", "evening"],
        }

        codes_to_try = preferred_codes.get(position, ["morning"])
        for code in codes_to_try:
            if code in template_map:
                tmpl = template_map[code]
                return (
                    code,
                    tmpl["start_time"],
                    tmpl["end_time"],
                    tmpl.get("id"),
                )

        # 兜底：第一个可用模板
        if template_map:
            first = next(iter(template_map.values()))
            return (
                first.get("code", "morning"),
                first["start_time"],
                first["end_time"],
                first.get("id"),
            )

        # 无模板：使用默认时间
        default_start, default_end = self._default_shift_times("morning")
        return ("morning", default_start, default_end, None)

    def _default_shift_times(self, shift_type: str) -> Tuple[time, time]:
        """默认班次时间（无模板时兜底）"""
        defaults = {
            "morning": (time(9, 0), time(14, 0)),
            "afternoon": (time(14, 0), time(21, 0)),
            "evening": (time(17, 0), time(22, 0)),
        }
        return defaults.get(shift_type, (time(9, 0), time(17, 0)))

    def _default_shift_templates(self) -> List[Dict[str, Any]]:
        """默认班次模板（无配置时使用）"""
        return [
            {
                "code": "morning",
                "start_time": time(9, 0),
                "end_time": time(14, 0),
                "is_cross_day": False,
                "applicable_positions": [],
            },
            {
                "code": "afternoon",
                "start_time": time(14, 0),
                "end_time": time(21, 0),
                "is_cross_day": False,
                "applicable_positions": [],
            },
            {
                "code": "evening",
                "start_time": time(17, 0),
                "end_time": time(22, 0),
                "is_cross_day": False,
                "applicable_positions": [],
            },
        ]

    def _is_night_shift(self, start: time, end: time) -> bool:
        """判断是否为夜班（包含 22:00~06:00 时段）— 向后兼容保留"""
        return self._is_night_shift_template(start, end)

    def _is_night_shift_template(self, start: time, end: time) -> bool:
        """
        判断班次是否与夜班时段（22:00~06:00）重叠。
        劳动法定义：22:00 至次日 06:00 之间的工作时段属于夜班。

        判断逻辑：
        1. 跨天班次（end < start）必然覆盖夜间时段
        2. 开始时间 >= 22:00
        3. 结束时间 <= 06:00 且 > 00:00（凌晨结束的班次）
        4. 班次横跨 22:00 点（start < 22:00 且 end > 22:00）
        """
        start = self._parse_time(start)
        end = self._parse_time(end)

        # 跨天班次（如 22:00~06:00, 21:00~02:00）必然包含夜间时段
        if end <= start:
            return True
        # 开始时间在22:00之后
        if start >= NIGHT_SHIFT_START:
            return True
        # 结束时间在凌晨06:00之前（非跨天情况说明是凌晨的班次）
        if time(0, 0) < end <= NIGHT_SHIFT_END:
            return True
        # 班次横跨22:00（如 20:00~23:00）
        if start < NIGHT_SHIFT_START < end:
            return True
        return False

    def _is_minor(self, employee_or_dict) -> bool:
        """
        判断员工是否为未成年工（< 18周岁）。
        依据：《劳动法》第58条，未成年工指年满16周岁未满18周岁的劳动者。
        """
        if isinstance(employee_or_dict, dict):
            return bool(employee_or_dict.get("is_minor", False))
        # EmployeeView 对象 — 无 birth_date 字段，从 preferences 读取
        prefs = getattr(employee_or_dict, "preferences", {}) or {}
        if prefs.get("is_minor"):
            return True
        return False

    def _is_restricted_from_night(self, candidate: Dict[str, Any]) -> Optional[str]:
        """
        判断员工是否受夜班限制，返回限制原因（中文）。
        返回 None 表示无限制，可以安排夜班。

        劳动法依据：
        - 《劳动法》第64条：不得安排未成年工从事夜班劳动
        - 《劳动法》第61条：不得安排孕期女职工从事夜班劳动
        - 医疗限制：持有医院证明不适合夜班的员工
        """
        # 未成年工不可安排夜班（劳动法第64条）
        if candidate.get("is_minor"):
            return "未成年工"

        # 孕期员工不可安排夜班（劳动法第61条）
        if candidate.get("is_pregnant"):
            return "孕期员工"

        # 医疗限制（如腰椎术后、心脏病等，由HR通过 preferences.medical_restriction 标记）
        if candidate.get("has_medical_restriction"):
            note = candidate.get("medical_note", "医疗限制")
            return f"医疗限制-{note}" if note else "医疗限制"

        return None

    @staticmethod
    def _parse_time(t) -> time:
        """将字符串或 time 对象统一转为 time"""
        if isinstance(t, str):
            parts = t.split(":")
            return time(int(parts[0]), int(parts[1]))
        return t

    def _calc_shift_hours(self, start: time, end: time) -> float:
        """计算班次工时"""
        start = self._parse_time(start)
        end = self._parse_time(end)

        start_minutes = start.hour * 60 + start.minute
        end_minutes = end.hour * 60 + end.minute
        if end_minutes <= start_minutes:
            # 跨天
            end_minutes += 24 * 60
        return (end_minutes - start_minutes) / 60

    def _calculate_fairness_score(self, tracker: Dict[str, Dict[str, Any]], employees: List[EmployeeView]) -> float:
        """
        计算公平性得分（0~1）。
        基于本周各员工排班天数和周末班次的标准差。
        标准差越小越公平。
        """
        if not employees:
            return 1.0

        days_list = []
        weekend_list = []
        for emp in employees:
            t = tracker.get(emp.id)
            if t:
                days_list.append(len(t["scheduled_dates"]))
                weekend_list.append(t["weekend_count"])
            else:
                days_list.append(0)
                weekend_list.append(0)

        if not days_list:
            return 1.0

        # 标准差归一化
        avg_days = sum(days_list) / len(days_list)
        variance = sum((d - avg_days) ** 2 for d in days_list) / len(days_list)
        std_days = variance**0.5

        # 得分：std=0 → 1.0, std=3 → 0.0
        score = max(0.0, 1.0 - std_days / 3.0)
        return round(score, 2)

    def _check_consecutive_warnings(self, tracker: Dict[str, Dict[str, Any]], week_end: date) -> List[str]:
        """检查本周末连续工作天数，对下周给出预警"""
        warnings = []
        for emp_id, t in tracker.items():
            emp = t["employee"]
            scheduled = t["scheduled_dates"]
            if not scheduled:
                continue

            # 从 week_end 往前数连续天数
            consecutive = 0
            check = week_end
            while check in scheduled:
                consecutive += 1
                check -= timedelta(days=1)

            if consecutive >= 5:
                next_monday = week_end + timedelta(days=1)
                warnings.append(
                    f"{emp.name} 连续工作{consecutive}天，"
                    f"{next_monday.strftime('%m/%d')}({DAY_NAMES_CN[next_monday.weekday()]})建议休息"
                )

        return warnings

    def _position_cn(self, position: str) -> str:
        """岗位中文名"""
        mapping = {
            "chef": "厨师",
            "waiter": "服务员",
            "cashier": "收银员",
            "host": "迎宾",
            "manager": "领班",
            "dishwasher": "洗碗工",
        }
        return mapping.get(position, position)

    def _empty_stats(self) -> Dict[str, Any]:
        """空统计"""
        return {
            "total_shifts": 0,
            "employees_scheduled": 0,
            "labor_hours": 0,
            "estimated_labor_cost_fen": 0,
            "estimated_labor_cost_yuan": 0,
            "coverage_rate": 0,
            "fairness_score": 0,
        }


# 全局服务实例
smart_schedule_service = SmartScheduleService()
