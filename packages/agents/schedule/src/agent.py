"""
智能排班Agent
基于客流预测和员工技能的自动排班系统
"""
from typing import Dict, Any, List, Optional, TypedDict
from datetime import datetime, timedelta
import structlog
from enum import Enum

logger = structlog.get_logger()


class ShiftType(Enum):
    """班次类型"""

    MORNING = "morning"  # 早班 (06:00-14:00)
    AFTERNOON = "afternoon"  # 中班 (14:00-22:00)
    EVENING = "evening"  # 晚班 (18:00-02:00)
    FULL_DAY = "full_day"  # 全天 (09:00-21:00)


class EmployeeSkill(Enum):
    """员工技能"""

    CASHIER = "cashier"  # 收银
    WAITER = "waiter"  # 服务员
    CHEF = "chef"  # 厨师
    MANAGER = "manager"  # 店长
    CLEANER = "cleaner"  # 清洁


class ScheduleState(TypedDict):
    """排班状态"""

    store_id: str
    date: str
    traffic_data: Dict[str, Any]
    employees: List[Dict[str, Any]]
    requirements: Dict[str, int]
    schedule: List[Dict[str, Any]]
    optimization_suggestions: List[str]
    errors: List[str]


class ScheduleAgent:
    """智能排班Agent"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化排班Agent

        Args:
            config: 配置字典，包含:
                - llm_config: LLM配置
                - min_shift_hours: 最小班次时长
                - max_shift_hours: 最大班次时长
                - max_weekly_hours: 每周最大工作时长
        """
        self.config = config
        self.min_shift_hours = config.get("min_shift_hours", 4)
        self.max_shift_hours = config.get("max_shift_hours", 8)
        self.max_weekly_hours = config.get("max_weekly_hours", 40)

        logger.info("智能排班Agent初始化", config=config)

    async def analyze_traffic(self, state: ScheduleState) -> ScheduleState:
        """
        分析客流数据

        Args:
            state: 当前状态

        Returns:
            更新后的状态
        """
        store_id = state["store_id"]
        date = state["date"]

        logger.info("分析客流", store_id=store_id, date=date)

        # TODO: 从API适配器获取历史客流数据
        # TODO: 使用时间序列模型预测客流

        # 临时模拟数据
        traffic_data = {
            "predicted_customers": {
                "morning": 50,  # 早班预计客流
                "afternoon": 80,  # 中班预计客流
                "evening": 120,  # 晚班预计客流
            },
            "peak_hours": ["12:00-13:00", "18:00-20:00"],
            "confidence": 0.85,
        }

        state["traffic_data"] = traffic_data
        logger.info("客流分析完成", traffic_data=traffic_data)

        return state

    async def calculate_requirements(self, state: ScheduleState) -> ScheduleState:
        """
        计算人力需求

        Args:
            state: 当前状态

        Returns:
            更新后的状态
        """
        traffic_data = state["traffic_data"]
        predicted_customers = traffic_data["predicted_customers"]

        logger.info("计算人力需求", predicted_customers=predicted_customers)

        # 根据客流计算各岗位需求
        # 简化算法：每10个客人需要1个服务员，每30个客人需要1个厨师
        requirements = {
            "morning": {
                "waiter": max(2, predicted_customers["morning"] // 10),
                "chef": max(1, predicted_customers["morning"] // 30),
                "cashier": 1,
            },
            "afternoon": {
                "waiter": max(2, predicted_customers["afternoon"] // 10),
                "chef": max(1, predicted_customers["afternoon"] // 30),
                "cashier": 1,
            },
            "evening": {
                "waiter": max(3, predicted_customers["evening"] // 10),
                "chef": max(2, predicted_customers["evening"] // 30),
                "cashier": 1,
            },
        }

        state["requirements"] = requirements
        logger.info("人力需求计算完成", requirements=requirements)

        return state

    async def generate_schedule(self, state: ScheduleState) -> ScheduleState:
        """
        生成排班表

        Args:
            state: 当前状态

        Returns:
            更新后的状态
        """
        requirements = state["requirements"]
        employees = state["employees"]
        date = state["date"]

        logger.info("生成排班表", date=date, employee_count=len(employees))

        schedule = []
        assigned_employees = set()

        # 按班次分配员工
        for shift_name, shift_requirements in requirements.items():
            for skill, count in shift_requirements.items():
                # 查找具备该技能且未分配的员工
                available_employees = [
                    emp
                    for emp in employees
                    if skill in emp.get("skills", [])
                    and emp["id"] not in assigned_employees
                ]

                # 分配员工
                for i in range(min(count, len(available_employees))):
                    emp = available_employees[i]
                    schedule.append(
                        {
                            "employee_id": emp["id"],
                            "employee_name": emp["name"],
                            "skill": skill,
                            "shift": shift_name,
                            "date": date,
                            "start_time": self._get_shift_start_time(shift_name),
                            "end_time": self._get_shift_end_time(shift_name),
                        }
                    )
                    assigned_employees.add(emp["id"])

        state["schedule"] = schedule
        logger.info("排班表生成完成", schedule_count=len(schedule))

        return state

    async def optimize_schedule(self, state: ScheduleState) -> ScheduleState:
        """
        优化排班表

        Args:
            state: 当前状态

        Returns:
            更新后的状态
        """
        schedule = state["schedule"]
        requirements = state["requirements"]

        logger.info("优化排班表", schedule_count=len(schedule))

        suggestions = []

        # 检查是否满足需求
        for shift_name, shift_requirements in requirements.items():
            for skill, required_count in shift_requirements.items():
                actual_count = len(
                    [s for s in schedule if s["shift"] == shift_name and s["skill"] == skill]
                )
                if actual_count < required_count:
                    suggestions.append(
                        f"{shift_name}班次缺少{required_count - actual_count}名{skill}"
                    )

        # 检查员工工作时长
        employee_hours = {}
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
        """获取班次开始时间"""
        shift_times = {
            "morning": "06:00",
            "afternoon": "14:00",
            "evening": "18:00",
        }
        return shift_times.get(shift_name, "09:00")

    def _get_shift_end_time(self, shift_name: str) -> str:
        """获取班次结束时间"""
        shift_times = {
            "morning": "14:00",
            "afternoon": "22:00",
            "evening": "02:00",
        }
        return shift_times.get(shift_name, "21:00")

    def _calculate_shift_hours(self, start_time: str, end_time: str) -> float:
        """计算班次时长"""
        # 简化计算，实际应该考虑跨天情况
        start_hour = int(start_time.split(":")[0])
        end_hour = int(end_time.split(":")[0])

        if end_hour < start_hour:  # 跨天
            return 24 - start_hour + end_hour
        return end_hour - start_hour

    async def run(
        self,
        store_id: str,
        date: str,
        employees: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        运行排班Agent

        Args:
            store_id: 门店ID
            date: 排班日期 (YYYY-MM-DD)
            employees: 员工列表

        Returns:
            排班结果
        """
        logger.info("开始排班", store_id=store_id, date=date)

        # 初始化状态
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
            # 执行工作流
            state = await self.analyze_traffic(state)
            state = await self.calculate_requirements(state)
            state = await self.generate_schedule(state)
            state = await self.optimize_schedule(state)

            logger.info("排班完成", schedule_count=len(state["schedule"]))

            return {
                "success": True,
                "store_id": store_id,
                "date": date,
                "schedule": state["schedule"],
                "traffic_prediction": state["traffic_data"],
                "requirements": state["requirements"],
                "suggestions": state["optimization_suggestions"],
            }

        except Exception as e:
            logger.error("排班失败", exc_info=e)
            return {
                "success": False,
                "error": str(e),
                "store_id": store_id,
                "date": date,
            }

    async def adjust_schedule(
        self,
        schedule_id: str,
        adjustments: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        调整排班

        Args:
            schedule_id: 排班ID
            adjustments: 调整列表

        Returns:
            调整结果
        """
        logger.info("调整排班", schedule_id=schedule_id, adjustments=adjustments)

        # TODO: 实现排班调整逻辑
        return {
            "success": True,
            "schedule_id": schedule_id,
            "message": "排班调整成功",
        }

    async def get_schedule(
        self, store_id: str, start_date: str, end_date: str
    ) -> Dict[str, Any]:
        """
        查询排班

        Args:
            store_id: 门店ID
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            排班列表
        """
        logger.info("查询排班", store_id=store_id, start_date=start_date, end_date=end_date)

        # TODO: 从数据库查询排班数据
        return {
            "success": True,
            "store_id": store_id,
            "schedules": [],
        }
