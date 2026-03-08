"""
智能排班Agent
基于客流预测和员工技能的自动排班系统
无状态设计：状态由调用方从DB查询后传入，Agent不持有任何内存状态
"""
from typing import Dict, Any, List, Optional, TypedDict, Callable
from datetime import datetime, timedelta
import structlog
from enum import Enum
import uuid
import sys
import os
import inspect
from pathlib import Path

# Add core module to path
core_path = Path(__file__).parent.parent.parent.parent.parent / "src" / "core"
sys.path.insert(0, str(core_path))

from base_agent import BaseAgent, AgentResponse

logger = structlog.get_logger()


class ShiftType(Enum):
    MORNING = "morning"      # 早班 (06:00-14:00)
    AFTERNOON = "afternoon"  # 中班 (14:00-22:00)
    EVENING = "evening"      # 晚班 (18:00-02:00)
    FULL_DAY = "full_day"    # 全天 (09:00-21:00)


class EmployeeSkill(Enum):
    CASHIER = "cashier"
    WAITER = "waiter"
    CHEF = "chef"
    MANAGER = "manager"
    CLEANER = "cleaner"


class ScheduleState(TypedDict):
    store_id: str
    date: str
    traffic_data: Dict[str, Any]
    employees: List[Dict[str, Any]]
    requirements: Dict[str, int]
    schedule: List[Dict[str, Any]]
    labor_cost_summary: Dict[str, Any]
    auto_scheduling_actions: List[Dict[str, Any]]
    optimization_suggestions: List[str]
    errors: List[str]


class ScheduleAgent(BaseAgent):
    """智能排班Agent（无状态设计，状态由调用方传入，多进程安全）"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__()
        self.config = config
        self.min_shift_hours = config.get("min_shift_hours", int(os.getenv("SCHEDULE_MIN_SHIFT_HOURS", "4")))
        self.max_shift_hours = config.get("max_shift_hours", int(os.getenv("SCHEDULE_MAX_SHIFT_HOURS", "8")))
        self.max_weekly_hours = config.get("max_weekly_hours", int(os.getenv("SCHEDULE_MAX_WEEKLY_HOURS", "40")))
        self._db_engine = None
        # 不持有任何内存状态
        logger.info("智能排班Agent初始化", store_id=config.get("store_id"))

    def _get_db_engine(self):
        """获取数据库引擎（延迟初始化）"""
        if self._db_engine is None:
            db_url = os.getenv("DATABASE_URL")
            if db_url:
                try:
                    from sqlalchemy import create_engine
                    self._db_engine = create_engine(db_url, pool_pre_ping=True)
                except Exception as e:
                    logger.warning("schedule_db_engine_init_failed", error=str(e))
        return self._db_engine

    async def _fetch_historical_traffic(
        self, store_id: str, date: str, lookback_weeks: int = 4
    ) -> Optional[Dict[str, int]]:
        """
        从 orders 表查询历史同星期客流均值，用于替代固定系数预测。
        返回 {"morning": N, "afternoon": N, "evening": N} 或 None（无 DB 时）。
        """
        engine = self._get_db_engine()
        if not engine:
            return None
        try:
            from sqlalchemy import text
            query = text("""
                SELECT
                    SUM(CASE WHEN EXTRACT(HOUR FROM created_at) BETWEEN 6 AND 13 THEN 1 ELSE 0 END) AS morning,
                    SUM(CASE WHEN EXTRACT(HOUR FROM created_at) BETWEEN 14 AND 17 THEN 1 ELSE 0 END) AS afternoon,
                    SUM(CASE WHEN EXTRACT(HOUR FROM created_at) BETWEEN 18 AND 23 THEN 1 ELSE 0 END) AS evening,
                    COUNT(DISTINCT DATE(created_at)) AS day_count
                FROM orders
                WHERE store_id = :store_id
                  AND EXTRACT(DOW FROM created_at) = EXTRACT(DOW FROM :target_date::date)
                  AND created_at >= :target_date::date - (:weeks * INTERVAL '1 week')
                  AND created_at < :target_date::date
            """)
            with engine.connect() as conn:
                row = conn.execute(query, {
                    "store_id": store_id,
                    "target_date": date,
                    "weeks": lookback_weeks,
                }).fetchone()
            if row and row[3] and int(row[3]) > 0:
                day_count = int(row[3])
                return {
                    "morning": max(1, int((row[0] or 0) / day_count)),
                    "afternoon": max(1, int((row[1] or 0) / day_count)),
                    "evening": max(1, int((row[2] or 0) / day_count)),
                }
        except Exception as e:
            logger.warning("schedule_traffic_db_failed", error=str(e))
        return None

    def _normalize_predicted_customers(self, data: Any) -> Optional[Dict[str, int]]:
        """规范化模型输出，确保包含 morning/afternoon/evening 三段且为正整数。"""
        if not isinstance(data, dict):
            return None
        required_keys = ("morning", "afternoon", "evening")
        if not all(k in data for k in required_keys):
            return None
        try:
            normalized = {k: max(1, int(data[k])) for k in required_keys}
            return normalized
        except (TypeError, ValueError):
            return None

    async def _fetch_model_traffic(
        self, store_id: str, date: str, is_weekend: bool
    ) -> Optional[Dict[str, Any]]:
        """
        调用可注入的真实客流预测模型。
        config["traffic_predictor"] 支持同步/异步函数，返回:
          {"predicted_customers": {...}, "confidence": 0.xx, "peak_hours": [...]} 或直接 {...}
        """
        predictor: Optional[Callable[..., Any]] = self.config.get("traffic_predictor")
        if not callable(predictor):
            return None

        try:
            raw = predictor(store_id=store_id, date=date, is_weekend=is_weekend)
            if inspect.isawaitable(raw):
                raw = await raw
        except Exception as e:
            logger.warning("schedule_traffic_model_failed", error=str(e))
            return None

        predicted = None
        confidence = 0.90 if not is_weekend else 0.86
        peak_hours = ["12:00-13:00", "18:00-20:00"]
        model_name = "custom_predictor"

        if isinstance(raw, dict):
            if "predicted_customers" in raw:
                predicted = self._normalize_predicted_customers(raw.get("predicted_customers"))
                confidence = float(raw.get("confidence", confidence))
                if isinstance(raw.get("peak_hours"), list):
                    peak_hours = raw["peak_hours"]
                model_name = str(raw.get("model_name", model_name))
            else:
                predicted = self._normalize_predicted_customers(raw)

        if not predicted:
            return None

        return {
            "predicted_customers": predicted,
            "confidence": max(0.0, min(1.0, confidence)),
            "peak_hours": peak_hours,
            "model_name": model_name,
        }

    def get_supported_actions(self) -> List[str]:
        return ["run", "plan_multi_store_schedule", "adjust_schedule", "get_schedule"]

    async def execute(self, action: str, params: Dict[str, Any]) -> AgentResponse:
        try:
            if action == "run":
                result = await self.run(
                    store_id=params["store_id"],
                    date=params["date"],
                    employees=params["employees"],
                )
            elif action == "plan_multi_store_schedule":
                result = await self.plan_multi_store_schedule(
                    date=params["date"],
                    stores=params["stores"],
                )
            elif action == "adjust_schedule":
                result = await self.adjust_schedule(
                    schedule_id=params["schedule_id"],
                    schedule=params["schedule"],
                    adjustments=params["adjustments"],
                )
            elif action == "get_schedule":
                result = await self.get_schedule(
                    store_id=params["store_id"],
                    start_date=params["start_date"],
                    end_date=params["end_date"],
                    schedules=params.get("schedules", []),
                )
            else:
                return AgentResponse(success=False, data=None, error=f"Unsupported action: {action}")

            return AgentResponse(
                success=result.get("success", True),
                data=result,
                error=result.get("error") if not result.get("success", True) else None,
            )
        except Exception as e:
            return AgentResponse(success=False, data=None, error=str(e))

    async def analyze_traffic(self, state: ScheduleState) -> ScheduleState:
        """分析客流数据（真实模型优先，历史订单均值次级，无 DB 时回退固定系数）"""
        store_id = state["store_id"]
        date = state["date"]
        logger.info("分析客流", store_id=store_id, date=date)

        try:
            weekday = datetime.strptime(date, "%Y-%m-%d").weekday()  # 0=周一
        except ValueError:
            weekday = 0
        is_weekend = weekday >= 5

        # 优先：真实模型预测
        model_result = await self._fetch_model_traffic(store_id, date, is_weekend)
        if model_result:
            predicted = model_result["predicted_customers"]
            confidence = model_result["confidence"]
            source = "traffic_model"
            peak_hours = model_result.get("peak_hours", ["12:00-13:00", "18:00-20:00"])
            model_name = model_result.get("model_name", "custom_predictor")
        else:
            # 次级：历史订单均值
            historical = await self._fetch_historical_traffic(store_id, date)
            if historical:
                predicted = historical
                confidence = 0.85 if not is_weekend else 0.80
                source = "historical_orders"
                peak_hours = ["12:00-13:00", "18:00-20:00"]
                model_name = None
            else:
                # 兜底：固定系数
                weekend_factor = float(os.getenv("SCHEDULE_WEEKEND_TRAFFIC_FACTOR", "1.4")) if is_weekend else 1.0
                base_morning = int(os.getenv("SCHEDULE_BASE_MORNING_CUSTOMERS", "50"))
                base_afternoon = int(os.getenv("SCHEDULE_BASE_AFTERNOON_CUSTOMERS", "80"))
                base_evening = int(os.getenv("SCHEDULE_BASE_EVENING_CUSTOMERS", "120"))
                predicted = {
                    "morning": int(base_morning * weekend_factor),
                    "afternoon": int(base_afternoon * weekend_factor),
                    "evening": int(base_evening * weekend_factor),
                }
                confidence = 0.75 if not is_weekend else 0.65
                source = "default_coefficients"
                peak_hours = ["12:00-13:00", "18:00-20:00"]
                model_name = None

        state["traffic_data"] = {
            "predicted_customers": predicted,
            "peak_hours": peak_hours,
            "confidence": confidence,
            "weekend": is_weekend,
            "source": source,
        }
        if model_name:
            state["traffic_data"]["model_name"] = model_name

        logger.info("客流分析完成", traffic_data=state["traffic_data"])
        return state

    async def calculate_requirements(self, state: ScheduleState) -> ScheduleState:
        """计算人力需求"""
        predicted_customers = state["traffic_data"]["predicted_customers"]
        logger.info("计算人力需求", predicted_customers=predicted_customers)

        _customers_per_waiter = int(os.getenv("SCHEDULE_CUSTOMERS_PER_WAITER", "10"))
        _customers_per_chef = int(os.getenv("SCHEDULE_CUSTOMERS_PER_CHEF", "30"))
        state["requirements"] = {
            "morning": {
                "waiter": max(int(os.getenv("SCHEDULE_MIN_WAITERS_MORNING", "2")), predicted_customers["morning"] // _customers_per_waiter),
                "chef": max(int(os.getenv("SCHEDULE_MIN_CHEFS_MORNING", "1")), predicted_customers["morning"] // _customers_per_chef),
                "cashier": 1,
            },
            "afternoon": {
                "waiter": max(int(os.getenv("SCHEDULE_MIN_WAITERS_MORNING", "2")), predicted_customers["afternoon"] // _customers_per_waiter),
                "chef": max(int(os.getenv("SCHEDULE_MIN_CHEFS_MORNING", "1")), predicted_customers["afternoon"] // _customers_per_chef),
                "cashier": 1,
            },
            "evening": {
                "waiter": max(int(os.getenv("SCHEDULE_MIN_WAITERS_EVENING", "3")), predicted_customers["evening"] // _customers_per_waiter),
                "chef": max(int(os.getenv("SCHEDULE_MIN_CHEFS_EVENING", "2")), predicted_customers["evening"] // _customers_per_chef),
                "cashier": 1,
            },
        }
        logger.info("人力需求计算完成", requirements=state["requirements"])
        return state

    async def generate_schedule(self, state: ScheduleState) -> ScheduleState:
        """生成排班表"""
        requirements = state["requirements"]
        employees = state["employees"]
        date = state["date"]
        logger.info("生成排班表", date=date, employee_count=len(employees))

        schedule = []
        assigned_employees: set = set()

        for shift_name, shift_requirements in requirements.items():
            for skill, count in shift_requirements.items():
                available = [
                    emp for emp in employees
                    if skill in emp.get("skills", []) and emp["id"] not in assigned_employees
                ]
                for emp in available[:count]:
                    schedule.append({
                        "employee_id": emp["id"],
                        "employee_name": emp["name"],
                        "skill": skill,
                        "shift": shift_name,
                        "date": date,
                        "start_time": self._get_shift_start_time(shift_name),
                        "end_time": self._get_shift_end_time(shift_name),
                    })
                    assigned_employees.add(emp["id"])

        state["schedule"] = schedule
        logger.info("排班表生成完成", schedule_count=len(schedule))
        return state

    async def optimize_schedule(self, state: ScheduleState) -> ScheduleState:
        """优化排班表"""
        schedule = state["schedule"]
        requirements = state["requirements"]
        logger.info("优化排班表", schedule_count=len(schedule))

        suggestions = []
        for shift_name, shift_requirements in requirements.items():
            for skill, required_count in shift_requirements.items():
                actual_count = len([s for s in schedule if s["shift"] == shift_name and s["skill"] == skill])
                if actual_count < required_count:
                    suggestions.append(f"{shift_name}班次缺少{required_count - actual_count}名{skill}")

        employee_hours: Dict[str, float] = {}
        for shift in schedule:
            emp_id = shift["employee_id"]
            hours = self._calculate_shift_hours(shift["start_time"], shift["end_time"])
            employee_hours[emp_id] = employee_hours.get(emp_id, 0) + hours

        for emp_id, hours in employee_hours.items():
            if hours > self.max_shift_hours:
                suggestions.append(f"员工{emp_id}工作时长超过{self.max_shift_hours}小时")

        labor_cost_summary = self._estimate_labor_cost(schedule)
        target_labor_cost = float(
            self.config.get("target_daily_labor_cost", os.getenv("SCHEDULE_TARGET_DAILY_LABOR_COST", "0"))
        )
        if target_labor_cost > 0 and labor_cost_summary["estimated_total_cost"] > target_labor_cost:
            overrun = round(labor_cost_summary["estimated_total_cost"] - target_labor_cost, 2)
            suggestions.append(
                f"预计人工成本超目标¥{overrun}，建议优先压降非高峰班次或采用低成本技能替补"
            )
        labor_cost_summary["target_daily_labor_cost"] = round(target_labor_cost, 2)
        labor_cost_summary["overrun_amount"] = round(
            max(0.0, labor_cost_summary["estimated_total_cost"] - target_labor_cost), 2
        )

        state["labor_cost_summary"] = labor_cost_summary
        state["auto_scheduling_actions"] = self._build_auto_scheduling_actions(
            requirements=requirements,
            schedule=schedule,
            labor_cost_summary=labor_cost_summary,
            traffic_data=state.get("traffic_data", {}),
        )
        state["optimization_suggestions"] = suggestions
        logger.info("排班优化完成", suggestions_count=len(suggestions))
        return state

    def _get_shift_start_time(self, shift_name: str) -> str:
        return {"morning": "06:00", "afternoon": "14:00", "evening": "18:00"}.get(shift_name, "09:00")

    def _get_shift_end_time(self, shift_name: str) -> str:
        return {"morning": "14:00", "afternoon": "22:00", "evening": "02:00"}.get(shift_name, "21:00")

    def _calculate_shift_hours(self, start_time: str, end_time: str) -> float:
        start_hour = int(start_time.split(":")[0])
        end_hour = int(end_time.split(":")[0])
        if end_hour < start_hour:  # 跨天
            return 24 - start_hour + end_hour
        return float(end_hour - start_hour)

    def _estimate_labor_cost(self, schedule: List[Dict[str, Any]]) -> Dict[str, Any]:
        """估算人工成本，用于成本优化目标。"""
        hourly_cost = {
            "manager": float(self.config.get("hourly_cost_manager", os.getenv("SCHEDULE_HOURLY_COST_MANAGER", "40"))),
            "chef": float(self.config.get("hourly_cost_chef", os.getenv("SCHEDULE_HOURLY_COST_CHEF", "32"))),
            "waiter": float(self.config.get("hourly_cost_waiter", os.getenv("SCHEDULE_HOURLY_COST_WAITER", "24"))),
            "cashier": float(self.config.get("hourly_cost_cashier", os.getenv("SCHEDULE_HOURLY_COST_CASHIER", "26"))),
            "cleaner": float(self.config.get("hourly_cost_cleaner", os.getenv("SCHEDULE_HOURLY_COST_CLEANER", "20"))),
        }

        breakdown: Dict[str, float] = {}
        total = 0.0
        for shift in schedule:
            skill = shift.get("skill", "waiter")
            hours = self._calculate_shift_hours(shift["start_time"], shift["end_time"])
            cost = round(hours * hourly_cost.get(skill, hourly_cost["waiter"]), 2)
            total += cost
            breakdown[skill] = round(breakdown.get(skill, 0.0) + cost, 2)

        return {
            "estimated_total_cost": round(total, 2),
            "cost_breakdown_by_skill": breakdown,
            "hourly_cost_config": hourly_cost,
        }

    def _build_auto_scheduling_actions(
        self,
        requirements: Dict[str, Any],
        schedule: List[Dict[str, Any]],
        labor_cost_summary: Dict[str, Any],
        traffic_data: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """输出结构化自动排班建议，供前端/编排器直接消费。"""
        actions: List[Dict[str, Any]] = []

        for shift_name, shift_requirements in requirements.items():
            for skill, required_count in shift_requirements.items():
                actual_count = len([s for s in schedule if s.get("shift") == shift_name and s.get("skill") == skill])
                gap = required_count - actual_count
                if gap > 0:
                    actions.append(
                        {
                            "priority": "high",
                            "type": "fill_gap",
                            "title": f"{shift_name}班次补员",
                            "action": "add_employee",
                            "payload": {"shift": shift_name, "skill": skill, "count": gap},
                        }
                    )

        if labor_cost_summary.get("overrun_amount", 0) > 0:
            actions.append(
                {
                    "priority": "medium",
                    "type": "cost_control",
                    "title": "人工成本超预算压降",
                    "action": "reduce_non_peak",
                    "payload": {
                        "overrun_amount": labor_cost_summary["overrun_amount"],
                        "target_daily_labor_cost": labor_cost_summary.get("target_daily_labor_cost", 0),
                    },
                }
            )

        predicted_customers = traffic_data.get("predicted_customers", {})
        if isinstance(predicted_customers, dict):
            evening = int(predicted_customers.get("evening", 0))
            morning = int(predicted_customers.get("morning", 0))
            if evening >= morning * 2 and evening > 0:
                actions.append(
                    {
                        "priority": "medium",
                        "type": "peak_preparation",
                        "title": "晚高峰预排班",
                        "action": "pre_allocate_evening",
                        "payload": {"expected_evening_customers": evening},
                    }
                )

        return actions

    async def run(
        self,
        store_id: str,
        date: str,
        employees: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        运行排班Agent（返回排班结果，由调用方持久化到DB）

        Args:
            store_id: 门店ID
            date: 排班日期 (YYYY-MM-DD)
            employees: 员工列表
        """
        logger.info("开始排班", store_id=store_id, date=date)

        state: ScheduleState = {
            "store_id": store_id,
            "date": date,
            "traffic_data": {},
            "employees": employees,
            "requirements": {},
            "schedule": [],
            "labor_cost_summary": {},
            "auto_scheduling_actions": [],
            "optimization_suggestions": [],
            "errors": [],
        }

        try:
            state = await self.analyze_traffic(state)
            state = await self.calculate_requirements(state)
            state = await self.generate_schedule(state)
            state = await self.optimize_schedule(state)

            schedule_id = f"SCH{uuid.uuid4().hex[:12].upper()}"
            logger.info("排班完成", schedule_id=schedule_id, schedule_count=len(state["schedule"]))
            return {
                "success": True,
                "schedule_id": schedule_id,
                "store_id": store_id,
                "date": date,
                "schedule": state["schedule"],
                "traffic_prediction": state["traffic_data"],
                "requirements": state["requirements"],
                "labor_cost_summary": state["labor_cost_summary"],
                "auto_scheduling_actions": state["auto_scheduling_actions"],
                "suggestions": state["optimization_suggestions"],
            }
        except Exception as e:
            logger.error("排班失败", exc_info=e)
            return {"success": False, "error": str(e), "store_id": store_id, "date": date}

    async def plan_multi_store_schedule(
        self,
        date: str,
        stores: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        多门店协同排班：
        - 逐门店生成排班结果
        - 根据缺口与可跨店员工，生成调配建议
        """
        per_store_results: List[Dict[str, Any]] = []
        for store in stores:
            store_id = store["store_id"]
            employees = store.get("employees", [])
            result = await self.run(store_id=store_id, date=date, employees=employees)
            per_store_results.append(result)

        # 聚合缺口：来自结构化自动建议
        gaps: List[Dict[str, Any]] = []
        for result in per_store_results:
            if not result.get("success"):
                continue
            for action in result.get("auto_scheduling_actions", []):
                if action.get("type") == "fill_gap":
                    payload = action.get("payload", {})
                    gaps.append(
                        {
                            "target_store_id": result.get("store_id"),
                            "shift": payload.get("shift"),
                            "skill": payload.get("skill"),
                            "count": int(payload.get("count", 0)),
                        }
                    )

        # 候选可跨店员工池
        transfer_suggestions: List[Dict[str, Any]] = []
        for gap in gaps:
            needed = gap["count"]
            if needed <= 0:
                continue
            for store in stores:
                from_store_id = store["store_id"]
                if from_store_id == gap["target_store_id"]:
                    continue
                for emp in store.get("employees", []):
                    if needed <= 0:
                        break
                    if gap["skill"] not in emp.get("skills", []):
                        continue
                    if not emp.get("multi_store_available", False):
                        continue
                    allowed_stores = emp.get("allowed_stores")
                    if isinstance(allowed_stores, list) and gap["target_store_id"] not in allowed_stores:
                        continue
                    transfer_suggestions.append(
                        {
                            "employee_id": emp.get("id"),
                            "employee_name": emp.get("name"),
                            "from_store_id": from_store_id,
                            "to_store_id": gap["target_store_id"],
                            "shift": gap["shift"],
                            "skill": gap["skill"],
                            "reason": "目标门店该班次存在技能缺口，建议跨店支援",
                        }
                    )
                    needed -= 1
                if needed <= 0:
                    break

        return {
            "success": True,
            "date": date,
            "store_results": per_store_results,
            "transfer_suggestions": transfer_suggestions,
        }

    async def adjust_schedule(
        self,
        schedule_id: str,
        schedule: Dict[str, Any],
        adjustments: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        调整排班

        Args:
            schedule_id: 排班ID
            schedule: 当前排班数据（由调用方从DB查询后传入）
            adjustments: 调整列表，支持 action: swap/add/remove/change_shift/leave
        """
        logger.info("调整排班", schedule_id=schedule_id, adjustments=adjustments)

        entries: List[Dict[str, Any]] = list(schedule.get("schedule", []))
        applied = []

        for adj in adjustments:
            action = adj.get("action")
            emp_id = adj.get("employee_id")

            if action == "remove" and emp_id:
                entries = [s for s in entries if s["employee_id"] != emp_id]
                applied.append(f"移除员工 {emp_id}")

            elif action == "add" and adj.get("entry"):
                entries.append(adj["entry"])
                applied.append(f"新增员工 {adj['entry'].get('employee_id', emp_id)}")

            elif action == "change_shift" and emp_id:
                new_shift = adj.get("new_shift")
                if not new_shift:
                    continue
                for s in entries:
                    if s["employee_id"] == emp_id:
                        s["shift"] = new_shift
                        s["start_time"] = self._get_shift_start_time(new_shift)
                        s["end_time"] = self._get_shift_end_time(new_shift)
                applied.append(f"调整员工 {emp_id} 班次为 {new_shift}")

            elif action == "leave" and emp_id:
                # 员工请假：移除原排班，可选自动补位
                leave_entries = [s for s in entries if s["employee_id"] == emp_id]
                if not leave_entries:
                    applied.append(f"请假失败：员工 {emp_id} 不在排班中")
                    continue

                entries = [s for s in entries if s["employee_id"] != emp_id]
                applied.append(f"员工 {emp_id} 请假，移除 {len(leave_entries)} 个班次")

                replacement_id = adj.get("replacement_employee_id")
                if replacement_id:
                    replacement_name = adj.get("replacement_employee_name", replacement_id)
                    replacement_skills = set(adj.get("replacement_skills", []))
                    replaced_count = 0
                    for leave_entry in leave_entries:
                        needed_skill = leave_entry.get("skill")
                        if replacement_skills and needed_skill not in replacement_skills:
                            continue
                        entries.append({
                            "employee_id": replacement_id,
                            "employee_name": replacement_name,
                            "skill": needed_skill,
                            "shift": leave_entry.get("shift"),
                            "date": leave_entry.get("date"),
                            "start_time": leave_entry.get("start_time"),
                            "end_time": leave_entry.get("end_time"),
                        })
                        replaced_count += 1
                    if replaced_count > 0:
                        applied.append(f"替补员工 {replacement_id} 顶班 {replaced_count} 个班次")
                    else:
                        applied.append(f"替补员工 {replacement_id} 技能不匹配，未成功顶班")

            elif action == "swap":
                # 互换两名员工的班次
                emp_a = adj.get("employee_id_a")
                emp_b = adj.get("employee_id_b")
                if not emp_a or not emp_b:
                    continue
                entry_a = next((s for s in entries if s["employee_id"] == emp_a), None)
                entry_b = next((s for s in entries if s["employee_id"] == emp_b), None)
                if entry_a and entry_b:
                    entry_a["shift"], entry_b["shift"] = entry_b["shift"], entry_a["shift"]
                    entry_a["start_time"] = self._get_shift_start_time(entry_a["shift"])
                    entry_a["end_time"] = self._get_shift_end_time(entry_a["shift"])
                    entry_b["start_time"] = self._get_shift_start_time(entry_b["shift"])
                    entry_b["end_time"] = self._get_shift_end_time(entry_b["shift"])
                    applied.append(f"互换员工 {emp_a} 和 {emp_b} 的班次")
                else:
                    applied.append(f"swap 失败：员工 {emp_a} 或 {emp_b} 不在排班中")

        return {
            "success": True,
            "schedule_id": schedule_id,
            "updated_schedule": entries,
            "applied_adjustments": applied,
            "message": f"排班调整成功，共 {len(applied)} 项变更",
        }

    async def get_schedule(
        self,
        store_id: str,
        start_date: str,
        end_date: str,
        schedules: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        查询排班

        Args:
            schedules: 候选排班列表（由调用方从DB查询后传入）
        """
        logger.info("查询排班", store_id=store_id, start_date=start_date, end_date=end_date)

        try:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError:
            return {"success": False, "message": "日期格式错误，请使用 YYYY-MM-DD"}

        matched = [
            s for s in (schedules or [])
            if s.get("store_id") == store_id
            and start <= datetime.strptime(s["date"], "%Y-%m-%d") <= end
        ]

        return {
            "success": True,
            "store_id": store_id,
            "start_date": start_date,
            "end_date": end_date,
            "schedules": matched,
            "total": len(matched),
        }
