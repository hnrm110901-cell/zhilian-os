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

# Add api-gateway src to path for OrgHierarchyService
api_src_path = Path(__file__).parent.parent.parent.parent.parent / "apps" / "api-gateway" / "src"
if str(api_src_path) not in sys.path:
    sys.path.insert(0, str(api_src_path))

# 导入配置相关（降级安全：导入失败时正常运行）
try:
    from services.org_hierarchy_service import OrgHierarchyService
    from models.org_config import ConfigKey
    _CONFIG_AVAILABLE = True
except ImportError:
    _CONFIG_AVAILABLE = False

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
    satisfaction_summary: Dict[str, Any]
    auto_scheduling_actions: List[Dict[str, Any]]
    optimization_suggestions: List[str]
    errors: List[str]


class ScheduleAgent(BaseAgent):
    """智能排班Agent（无状态设计，状态由调用方传入，多进程安全）"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__()
        self.config = config
        self.store_id = config.get("store_id")
        # 保留默认值，_load_store_config 调用时会用 OrgHierarchyService 覆盖
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

    async def _load_store_config(self, db=None) -> dict:
        """从 OrgConfig 加载门店级配置，无 DB 或导入失败时返回空字典（降级安全）"""
        if not _CONFIG_AVAILABLE or not db or not self.store_id:
            return {}
        try:
            svc = OrgHierarchyService(db)
            return {
                "min_shift_hours": await svc.resolve(self.store_id, "schedule_min_shift_hours", default=self.min_shift_hours),
                "max_shift_hours": await svc.resolve(self.store_id, "schedule_max_shift_hours", default=self.max_shift_hours),
                "max_weekly_hours": await svc.resolve(self.store_id, "schedule_max_weekly_hours", default=self.max_weekly_hours),
                "shift_morning_start": await svc.resolve(self.store_id, "shift_morning_start", default="06:00"),
                "shift_morning_end": await svc.resolve(self.store_id, "shift_morning_end", default="14:00"),
                "shift_afternoon_start": await svc.resolve(self.store_id, "shift_afternoon_start", default="14:00"),
                "shift_afternoon_end": await svc.resolve(self.store_id, "shift_afternoon_end", default="22:00"),
                "shift_evening_start": await svc.resolve(self.store_id, "shift_evening_start", default="18:00"),
                "shift_evening_end": await svc.resolve(self.store_id, "shift_evening_end", default="02:00"),
                "peak_hours": await svc.resolve(self.store_id, "peak_hours", default=[{"start": "12:00", "end": "13:00"}, {"start": "18:00", "end": "20:00"}]),
                "scoring_weights": await svc.resolve(self.store_id, "schedule_scoring_weights", default={"preference": 0.35, "skill": 0.35, "history": 0.25, "fatigue": -0.15}),
            }
        except Exception:
            return {}

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
        return [
            "run",
            "plan_multi_store_schedule",
            "plan_cross_region_allocation",
            "predict_schedule_adjustments",
            "reinforcement_optimize_schedule",
            "evaluate_employee_satisfaction",
            "adjust_schedule",
            "get_schedule",
        ]

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
            elif action == "plan_cross_region_allocation":
                result = await self.plan_cross_region_allocation(
                    date=params["date"],
                    stores=params["stores"],
                )
            elif action == "predict_schedule_adjustments":
                result = await self.predict_schedule_adjustments(
                    store_id=params["store_id"],
                    date=params["date"],
                    current_requirements=params.get("current_requirements", {}),
                    predicted_customers=params["predicted_customers"],
                    baseline_customers=params.get("baseline_customers", {}),
                )
            elif action == "reinforcement_optimize_schedule":
                result = await self.reinforcement_optimize_schedule(
                    store_id=params["store_id"],
                    date=params["date"],
                    current_requirements=params.get("current_requirements", {}),
                    predicted_customers=params.get("predicted_customers", {}),
                    previous_q_values=params.get("previous_q_values", {}),
                    reward=params.get("reward"),
                    candidate_actions=params.get("candidate_actions"),
                )
            elif action == "evaluate_employee_satisfaction":
                result = await self.evaluate_employee_satisfaction(
                    schedule=params["schedule"],
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

    async def analyze_traffic(self, state: ScheduleState, peak_hours: Optional[List] = None) -> ScheduleState:
        """分析客流数据（真实模型优先，历史订单均值次级，无 DB 时回退固定系数）"""
        store_id = state["store_id"]
        date = state["date"]
        logger.info("分析客流", store_id=store_id, date=date)

        # 默认高峰时段（可被 OrgConfig 动态配置覆盖）
        default_peak_hours = peak_hours or [{"start": "12:00", "end": "13:00"}, {"start": "18:00", "end": "20:00"}]

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
            peak_hours = model_result.get("peak_hours", default_peak_hours)
            model_name = model_result.get("model_name", "custom_predictor")
        else:
            # 次级：历史订单均值
            historical = await self._fetch_historical_traffic(store_id, date)
            if historical:
                predicted = historical
                confidence = 0.85 if not is_weekend else 0.80
                source = "historical_orders"
                peak_hours = default_peak_hours
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
                peak_hours = default_peak_hours
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

    async def generate_schedule(
        self,
        state: ScheduleState,
        shift_times: Optional[Dict[str, tuple]] = None,
        scoring_weights: Optional[Dict[str, float]] = None,
    ) -> ScheduleState:
        """生成排班表"""
        requirements = state["requirements"]
        employees = state["employees"]
        date = state["date"]
        use_ml_optimizer = bool(self.config.get("use_ml_optimizer", False))
        logger.info("生成排班表", date=date, employee_count=len(employees))

        schedule = []
        assigned_employees: set = set()

        for shift_name, shift_requirements in requirements.items():
            for skill, count in shift_requirements.items():
                available = [
                    emp for emp in employees
                    if skill in emp.get("skills", []) and emp["id"] not in assigned_employees
                ]
                if use_ml_optimizer:
                    available = sorted(
                        available,
                        key=lambda emp: self._score_employee_ml(emp=emp, shift_name=shift_name, skill=skill, scoring_weights=scoring_weights),
                        reverse=True,
                    )
                for emp in available[:count]:
                    schedule.append({
                        "employee_id": emp["id"],
                        "employee_name": emp["name"],
                        "skill": skill,
                        "shift": shift_name,
                        "date": date,
                        "start_time": self._get_shift_start_time(shift_name, shift_times=shift_times),
                        "end_time": self._get_shift_end_time(shift_name, shift_times=shift_times),
                    })
                    assigned_employees.add(emp["id"])

        state["schedule"] = schedule
        logger.info("排班表生成完成", schedule_count=len(schedule))
        return state

    async def optimize_schedule(self, state: ScheduleState, max_shift_hours: Optional[float] = None) -> ScheduleState:
        """优化排班表"""
        schedule = state["schedule"]
        requirements = state["requirements"]
        effective_max_shift_hours = max_shift_hours if max_shift_hours is not None else self.max_shift_hours
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
            if hours > effective_max_shift_hours:
                suggestions.append(f"员工{emp_id}工作时长超过{effective_max_shift_hours}小时")

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
        satisfaction_summary = await self.evaluate_employee_satisfaction(
            schedule=schedule,
            employees=state.get("employees", []),
        )
        if satisfaction_summary.get("average_score", 1.0) < 0.6:
            suggestions.append("员工满意度偏低，建议优先分配偏好班次并平衡高工时员工")

        state["labor_cost_summary"] = labor_cost_summary
        state["satisfaction_summary"] = satisfaction_summary
        state["auto_scheduling_actions"] = self._build_auto_scheduling_actions(
            requirements=requirements,
            schedule=schedule,
            labor_cost_summary=labor_cost_summary,
            traffic_data=state.get("traffic_data", {}),
            satisfaction_summary=satisfaction_summary,
        )
        state["optimization_suggestions"] = suggestions
        logger.info("排班优化完成", suggestions_count=len(suggestions))
        return state

    def _get_shift_start_time(self, shift_name: str, shift_times: Optional[Dict[str, tuple]] = None) -> str:
        if shift_times and shift_name in shift_times:
            return shift_times[shift_name][0]
        return {"morning": "06:00", "afternoon": "14:00", "evening": "18:00"}.get(shift_name, "09:00")

    def _get_shift_end_time(self, shift_name: str, shift_times: Optional[Dict[str, tuple]] = None) -> str:
        if shift_times and shift_name in shift_times:
            return shift_times[shift_name][1]
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

    def _score_employee_ml(
        self,
        emp: Dict[str, Any],
        shift_name: str,
        skill: str,
        scoring_weights: Optional[Dict[str, float]] = None,
    ) -> float:
        """
        轻量 ML 风格排班打分：
        - 偏好匹配（preferred_shifts）
        - 技能等级（skill_levels[skill] 或 skill_level）
        - 历史表现（historical_performance 0-1）
        - 近期工时惩罚（recent_hours）
        权重可通过 scoring_weights 动态覆盖（来自 OrgConfig）
        """
        preferences = emp.get("preferences", {})
        preferred_shifts = preferences.get("preferred_shifts", []) if isinstance(preferences, dict) else []
        preference_score = 1.0 if shift_name in preferred_shifts else 0.0

        skill_levels = emp.get("skill_levels", {})
        if isinstance(skill_levels, dict) and skill in skill_levels:
            skill_score = float(skill_levels.get(skill, 0.8))
        else:
            skill_score = float(emp.get("skill_level", 0.8))

        historical_score = float(emp.get("historical_performance", 0.7))
        recent_hours = float(emp.get("recent_hours", 0.0))
        fatigue_penalty = min(1.0, recent_hours / 40.0)

        w = scoring_weights or {}
        return round(
            preference_score * w.get("preference", 0.35)
            + skill_score * w.get("skill", 0.35)
            + historical_score * w.get("history", 0.25)
            + fatigue_penalty * w.get("fatigue", -0.15),
            6,
        )

    def _build_auto_scheduling_actions(
        self,
        requirements: Dict[str, Any],
        schedule: List[Dict[str, Any]],
        labor_cost_summary: Dict[str, Any],
        traffic_data: Dict[str, Any],
        satisfaction_summary: Optional[Dict[str, Any]] = None,
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

        if satisfaction_summary and satisfaction_summary.get("average_score", 1.0) < 0.6:
            actions.append(
                {
                    "priority": "medium",
                    "type": "satisfaction_improvement",
                    "title": "员工满意度优化",
                    "action": "rebalance_shift_preferences",
                    "payload": {
                        "average_score": satisfaction_summary.get("average_score"),
                        "low_score_employee_ids": [
                            item.get("employee_id")
                            for item in satisfaction_summary.get("low_score_employees", [])
                        ],
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

    async def evaluate_employee_satisfaction(
        self,
        schedule: List[Dict[str, Any]],
        employees: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        员工满意度评分（0-1）：
        - 偏好班次命中率
        - 工时疲劳惩罚（>8h）
        """
        employee_map = {e.get("id"): e for e in employees}
        details: List[Dict[str, Any]] = []
        for emp_id, emp in employee_map.items():
            shifts = [s for s in schedule if s.get("employee_id") == emp_id]
            if not shifts:
                details.append({"employee_id": emp_id, "score": 0.7, "reason": "未排班"})
                continue

            preferred = set((emp.get("preferences") or {}).get("preferred_shifts", []))
            preferred_hits = sum(1 for s in shifts if s.get("shift") in preferred) if preferred else len(shifts)
            preference_score = preferred_hits / max(1, len(shifts))

            total_hours = sum(self._calculate_shift_hours(s["start_time"], s["end_time"]) for s in shifts)
            fatigue_penalty = min(0.4, max(0.0, total_hours - 8.0) / 20.0)

            score = max(0.0, min(1.0, preference_score - fatigue_penalty))
            details.append({"employee_id": emp_id, "score": round(score, 3), "total_hours": total_hours})

        average = round(sum(d["score"] for d in details) / max(1, len(details)), 3)
        low_score = [d for d in details if d["score"] < 0.5]
        return {
            "average_score": average,
            "employee_scores": details,
            "low_score_employees": low_score,
        }

    async def run(
        self,
        store_id: str,
        date: str,
        employees: List[Dict[str, Any]],
        db=None,
    ) -> Dict[str, Any]:
        """
        运行排班Agent（返回排班结果，由调用方持久化到DB）

        Args:
            store_id: 门店ID
            date: 排班日期 (YYYY-MM-DD)
            employees: 员工列表
            db: 可选 AsyncSession，用于从 OrgConfig 加载门店级配置
        """
        logger.info("开始排班", store_id=store_id, date=date)

        # 从 OrgConfig 加载门店级配置（无 DB 时自动降级为空字典，使用默认值）
        cfg = await self._load_store_config(db)
        min_shift_h = cfg.get("min_shift_hours", self.min_shift_hours)
        max_shift_h = cfg.get("max_shift_hours", self.max_shift_hours)
        peak_hours = cfg.get("peak_hours", [{"start": "12:00", "end": "13:00"}, {"start": "18:00", "end": "20:00"}])
        scoring_weights = cfg.get("scoring_weights", {"preference": 0.35, "skill": 0.35, "history": 0.25, "fatigue": -0.15})
        shift_times = {
            "morning": (cfg.get("shift_morning_start", "06:00"), cfg.get("shift_morning_end", "14:00")),
            "afternoon": (cfg.get("shift_afternoon_start", "14:00"), cfg.get("shift_afternoon_end", "22:00")),
            "evening": (cfg.get("shift_evening_start", "18:00"), cfg.get("shift_evening_end", "02:00")),
        }

        state: ScheduleState = {
            "store_id": store_id,
            "date": date,
            "traffic_data": {},
            "employees": employees,
            "requirements": {},
            "schedule": [],
            "labor_cost_summary": {},
            "satisfaction_summary": {},
            "auto_scheduling_actions": [],
            "optimization_suggestions": [],
            "errors": [],
        }

        try:
            state = await self.analyze_traffic(state, peak_hours=peak_hours)
            state = await self.calculate_requirements(state)
            state = await self.generate_schedule(state, shift_times=shift_times, scoring_weights=scoring_weights)
            state = await self.optimize_schedule(state, max_shift_hours=max_shift_h)

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
                "satisfaction_summary": state["satisfaction_summary"],
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

    async def plan_cross_region_allocation(
        self,
        date: str,
        stores: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        跨区域人力调配：
        - 基于多门店排班缺口
        - 仅匹配 cross_region_available 的员工
        - 可选受 allowed_regions 限制
        """
        base_plan = await self.plan_multi_store_schedule(date=date, stores=stores)
        store_region_map = {s["store_id"]: s.get("region_id", "UNKNOWN") for s in stores}
        cross_region_suggestions: List[Dict[str, Any]] = []

        for suggestion in base_plan.get("transfer_suggestions", []):
            from_store_id = suggestion.get("from_store_id")
            to_store_id = suggestion.get("to_store_id")
            from_region = store_region_map.get(from_store_id, "UNKNOWN")
            to_region = store_region_map.get(to_store_id, "UNKNOWN")
            if from_region == to_region:
                continue

            from_store = next((s for s in stores if s["store_id"] == from_store_id), None)
            employee = None
            if from_store:
                employee = next((e for e in from_store.get("employees", []) if e.get("id") == suggestion.get("employee_id")), None)
            if not employee or not employee.get("cross_region_available", False):
                continue

            allowed_regions = employee.get("allowed_regions")
            if isinstance(allowed_regions, list) and to_region not in allowed_regions:
                continue

            cross_region_suggestions.append(
                {
                    **suggestion,
                    "from_region": from_region,
                    "to_region": to_region,
                    "reason": "目标区域存在班次缺口，员工具备跨区支援条件",
                }
            )

        return {
            "success": True,
            "date": date,
            "store_results": base_plan.get("store_results", []),
            "cross_region_transfer_suggestions": cross_region_suggestions,
        }

    async def predict_schedule_adjustments(
        self,
        store_id: str,
        date: str,
        current_requirements: Dict[str, Any],
        predicted_customers: Dict[str, int],
        baseline_customers: Optional[Dict[str, int]] = None,
    ) -> Dict[str, Any]:
        """
        预测性排班调整：
        对比 baseline 与 predicted 客流，提前给出增减员建议。
        """
        baseline = baseline_customers or {}
        adjustments: List[Dict[str, Any]] = []

        for shift in ("morning", "afternoon", "evening"):
            base = max(1, int(baseline.get(shift, predicted_customers.get(shift, 1))))
            pred = max(1, int(predicted_customers.get(shift, base)))
            change_ratio = (pred - base) / base

            req = current_requirements.get(shift, {})
            current_waiter = int(req.get("waiter", 0))
            current_chef = int(req.get("chef", 0))

            if change_ratio >= 0.2:
                delta_waiter = max(1, int(round(current_waiter * min(change_ratio, 0.5)))) if current_waiter > 0 else 1
                delta_chef = max(1, int(round(current_chef * min(change_ratio, 0.4)))) if current_chef > 0 else 1
                adjustments.append(
                    {
                        "shift": shift,
                        "type": "increase_staff",
                        "change_ratio": round(change_ratio, 3),
                        "recommendation": {"waiter": delta_waiter, "chef": delta_chef},
                        "reason": f"预测客流较基线提升{round(change_ratio * 100, 1)}%",
                    }
                )
            elif change_ratio <= -0.15:
                delta_waiter = max(1, int(round(max(1, current_waiter) * min(abs(change_ratio), 0.4)))) if current_waiter > 0 else 0
                delta_chef = max(1, int(round(max(1, current_chef) * min(abs(change_ratio), 0.3)))) if current_chef > 0 else 0
                adjustments.append(
                    {
                        "shift": shift,
                        "type": "decrease_staff",
                        "change_ratio": round(change_ratio, 3),
                        "recommendation": {"waiter": delta_waiter, "chef": delta_chef},
                        "reason": f"预测客流较基线下降{round(abs(change_ratio) * 100, 1)}%",
                    }
                )

        return {
            "success": True,
            "store_id": store_id,
            "date": date,
            "predictive_adjustments": adjustments,
            "message": f"生成{len(adjustments)}条预测性排班调整建议",
        }

    async def reinforcement_optimize_schedule(
        self,
        store_id: str,
        date: str,
        current_requirements: Dict[str, Any],
        predicted_customers: Dict[str, int],
        previous_q_values: Dict[str, float],
        reward: Optional[float] = None,
        candidate_actions: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        基于强化学习的动态排班（Q-learning简化版）：
        - 输入上次Q值与可选动作
        - 选择当前最优动作（贪心）
        - 若提供reward，更新该动作Q值并返回新Q表
        """
        actions = candidate_actions or [
            "increase_evening_waiter",
            "increase_evening_chef",
            "decrease_morning_waiter",
            "keep_current",
        ]
        q_values = {a: float(previous_q_values.get(a, 0.0)) for a in actions}
        chosen_action = max(actions, key=lambda a: q_values.get(a, 0.0))

        # Apply selected action to generate adjusted requirements
        adjusted = {
            shift: {k: int(v) for k, v in req.items()}
            for shift, req in (current_requirements or {}).items()
        }
        if "evening" not in adjusted:
            adjusted["evening"] = {"waiter": 0, "chef": 0, "cashier": 0}
        if "morning" not in adjusted:
            adjusted["morning"] = {"waiter": 0, "chef": 0, "cashier": 0}

        if chosen_action == "increase_evening_waiter":
            adjusted["evening"]["waiter"] = int(adjusted["evening"].get("waiter", 0)) + 1
        elif chosen_action == "increase_evening_chef":
            adjusted["evening"]["chef"] = int(adjusted["evening"].get("chef", 0)) + 1
        elif chosen_action == "decrease_morning_waiter":
            adjusted["morning"]["waiter"] = max(0, int(adjusted["morning"].get("waiter", 0)) - 1)

        # Q-learning one-step update
        alpha = float(self.config.get("rl_alpha", 0.3))
        gamma = float(self.config.get("rl_gamma", 0.8))
        if reward is not None:
            best_next = max(q_values.values()) if q_values else 0.0
            old_q = q_values.get(chosen_action, 0.0)
            q_values[chosen_action] = round(old_q + alpha * (float(reward) + gamma * best_next - old_q), 6)

        return {
            "success": True,
            "store_id": store_id,
            "date": date,
            "chosen_action": chosen_action,
            "adjusted_requirements": adjusted,
            "q_values": q_values,
            "predicted_customers": predicted_customers,
            "message": "强化学习动态排班建议已生成",
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
