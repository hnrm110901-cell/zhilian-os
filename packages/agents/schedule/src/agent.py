"""
智能排班Agent
基于客流预测和员工技能的自动排班系统
无状态设计：状态由调用方从DB查询后传入，Agent不持有任何内存状态
"""
from typing import Dict, Any, List, Optional, TypedDict
from datetime import datetime, timedelta
import structlog
from enum import Enum
import uuid
import sys
import os
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
                  AND created_at >= :target_date::date - INTERVAL ':weeks weeks'
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

    def get_supported_actions(self) -> List[str]:
        return ["run", "adjust_schedule", "get_schedule"]

    async def execute(self, action: str, params: Dict[str, Any]) -> AgentResponse:
        try:
            if action == "run":
                result = await self.run(
                    store_id=params["store_id"],
                    date=params["date"],
                    employees=params["employees"],
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
        """分析客流数据（优先使用历史订单均值，无 DB 时回退到固定系数）"""
        store_id = state["store_id"]
        date = state["date"]
        logger.info("分析客流", store_id=store_id, date=date)

        try:
            weekday = datetime.strptime(date, "%Y-%m-%d").weekday()  # 0=周一
        except ValueError:
            weekday = 0
        is_weekend = weekday >= 5

        # 优先从历史订单数据预测
        historical = await self._fetch_historical_traffic(store_id, date)
        if historical:
            predicted = historical
            confidence = 0.85 if not is_weekend else 0.80
            source = "historical_orders"
        else:
            # Fallback：固定系数
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

        state["traffic_data"] = {
            "predicted_customers": predicted,
            "peak_hours": ["12:00-13:00", "18:00-20:00"],
            "confidence": confidence,
            "weekend": is_weekend,
            "source": source,
        }
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
                "suggestions": state["optimization_suggestions"],
            }
        except Exception as e:
            logger.error("排班失败", exc_info=e)
            return {"success": False, "error": str(e), "store_id": store_id, "date": date}

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
            adjustments: 调整列表，支持 action: swap/add/remove/change_shift
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

