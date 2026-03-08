"""
智能排班Agent单元测试
"""
import pytest
from datetime import datetime, timedelta
from src.agent import ScheduleAgent, ShiftType, EmployeeSkill, ScheduleState


@pytest.fixture
def agent():
    """创建Agent实例"""
    config = {
        "min_shift_hours": 4,
        "max_shift_hours": 8,
        "max_weekly_hours": 40,
    }
    return ScheduleAgent(config)


@pytest.fixture
def sample_employees():
    """示例员工数据"""
    return [
        {
            "id": "E001",
            "name": "张三",
            "skills": ["waiter", "cashier"],
            "preferences": {"preferred_shifts": ["morning"]},
        },
        {
            "id": "E002",
            "name": "李四",
            "skills": ["chef"],
            "preferences": {"preferred_shifts": ["afternoon"]},
        },
        {
            "id": "E003",
            "name": "王五",
            "skills": ["waiter"],
            "preferences": {"preferred_shifts": ["evening"]},
        },
        {
            "id": "E004",
            "name": "赵六",
            "skills": ["chef"],
            "preferences": {},
        },
        {
            "id": "E005",
            "name": "钱七",
            "skills": ["waiter", "cashier"],
            "preferences": {},
        },
    ]


@pytest.fixture
def initial_state(sample_employees):
    """初始状态"""
    return ScheduleState(
        store_id="STORE001",
        date="2024-01-15",
        traffic_data={},
        employees=sample_employees,
        requirements={},
        schedule=[],
        labor_cost_summary={},
        auto_scheduling_actions=[],
        optimization_suggestions=[],
        errors=[],
    )


class TestScheduleAgent:
    """排班Agent测试类"""

    def test_init(self, agent):
        """测试初始化"""
        assert agent.min_shift_hours == 4
        assert agent.max_shift_hours == 8
        assert agent.max_weekly_hours == 40

    @pytest.mark.asyncio
    async def test_analyze_traffic(self, agent, initial_state):
        """测试客流分析"""
        result = await agent.analyze_traffic(initial_state)

        assert "traffic_data" in result
        assert "predicted_customers" in result["traffic_data"]
        assert "morning" in result["traffic_data"]["predicted_customers"]
        assert "afternoon" in result["traffic_data"]["predicted_customers"]
        assert "evening" in result["traffic_data"]["predicted_customers"]
        assert "confidence" in result["traffic_data"]

    @pytest.mark.asyncio
    async def test_analyze_traffic_uses_model_predictor_first(self, initial_state):
        """测试优先使用真实模型预测"""
        async def predictor(**kwargs):
            return {
                "predicted_customers": {"morning": 66, "afternoon": 88, "evening": 123},
                "confidence": 0.93,
                "peak_hours": ["11:30-13:00", "18:00-20:30"],
                "model_name": "test_model_v1",
            }

        agent = ScheduleAgent(
            {"min_shift_hours": 4, "max_shift_hours": 8, "max_weekly_hours": 40, "traffic_predictor": predictor}
        )
        result = await agent.analyze_traffic(initial_state)
        assert result["traffic_data"]["source"] == "traffic_model"
        assert result["traffic_data"]["predicted_customers"]["morning"] == 66
        assert result["traffic_data"]["model_name"] == "test_model_v1"

    @pytest.mark.asyncio
    async def test_analyze_traffic_fallback_to_historical(self, agent, initial_state, monkeypatch):
        """测试模型不可用时回退历史订单均值"""
        async def broken_predictor(**kwargs):
            raise RuntimeError("model unavailable")

        async def fake_historical(*args, **kwargs):
            return {"morning": 70, "afternoon": 90, "evening": 140}

        agent.config["traffic_predictor"] = broken_predictor
        monkeypatch.setattr(agent, "_fetch_historical_traffic", fake_historical)

        result = await agent.analyze_traffic(initial_state)
        assert result["traffic_data"]["source"] == "historical_orders"
        assert result["traffic_data"]["predicted_customers"]["evening"] == 140

    @pytest.mark.asyncio
    async def test_calculate_requirements(self, agent, initial_state):
        """测试人力需求计算"""
        # 先分析客流
        state = await agent.analyze_traffic(initial_state)
        # 再计算需求
        result = await agent.calculate_requirements(state)

        assert "requirements" in result
        assert "morning" in result["requirements"]
        assert "afternoon" in result["requirements"]
        assert "evening" in result["requirements"]

        # 验证每个班次都有基本岗位需求
        for shift in ["morning", "afternoon", "evening"]:
            assert "waiter" in result["requirements"][shift]
            assert "chef" in result["requirements"][shift]
            assert "cashier" in result["requirements"][shift]

    @pytest.mark.asyncio
    async def test_generate_schedule(self, agent, initial_state):
        """测试排班表生成"""
        # 执行前置步骤
        state = await agent.analyze_traffic(initial_state)
        state = await agent.calculate_requirements(state)
        # 生成排班
        result = await agent.generate_schedule(state)

        assert "schedule" in result
        assert isinstance(result["schedule"], list)
        assert len(result["schedule"]) > 0

        # 验证排班记录结构
        if len(result["schedule"]) > 0:
            shift = result["schedule"][0]
            assert "employee_id" in shift
            assert "employee_name" in shift
            assert "skill" in shift
            assert "shift" in shift
            assert "date" in shift
            assert "start_time" in shift
            assert "end_time" in shift

    @pytest.mark.asyncio
    async def test_optimize_schedule(self, agent, initial_state):
        """测试排班优化"""
        # 执行完整流程
        state = await agent.analyze_traffic(initial_state)
        state = await agent.calculate_requirements(state)
        state = await agent.generate_schedule(state)
        result = await agent.optimize_schedule(state)

        assert "optimization_suggestions" in result
        assert "labor_cost_summary" in result
        assert "auto_scheduling_actions" in result
        assert isinstance(result["optimization_suggestions"], list)

    @pytest.mark.asyncio
    async def test_run_complete_workflow(self, agent, sample_employees):
        """测试完整工作流"""
        result = await agent.run(
            store_id="STORE001", date="2024-01-15", employees=sample_employees
        )

        assert result["success"] is True
        assert result["store_id"] == "STORE001"
        assert result["date"] == "2024-01-15"
        assert "schedule" in result
        assert "traffic_prediction" in result
        assert "requirements" in result
        assert "labor_cost_summary" in result
        assert "auto_scheduling_actions" in result
        assert "suggestions" in result

    @pytest.mark.asyncio
    async def test_cost_target_generates_optimization_suggestion(self, sample_employees):
        """测试超预算时生成成本优化建议"""
        agent = ScheduleAgent(
            {
                "min_shift_hours": 4,
                "max_shift_hours": 8,
                "max_weekly_hours": 40,
                "target_daily_labor_cost": 10,
            }
        )
        result = await agent.run(store_id="STORE001", date="2024-01-15", employees=sample_employees)
        assert result["success"] is True
        assert result["labor_cost_summary"]["estimated_total_cost"] > 10
        assert any("预计人工成本超目标" in s for s in result["suggestions"])
        assert any(a["type"] == "cost_control" for a in result["auto_scheduling_actions"])

    @pytest.mark.asyncio
    async def test_auto_scheduling_actions_contains_gap_filling(self, sample_employees):
        """测试自动排班建议包含补员动作"""
        agent = ScheduleAgent(
            {
                "min_shift_hours": 4,
                "max_shift_hours": 8,
                "max_weekly_hours": 40,
            }
        )
        # 仅1名员工，必然出现缺口
        result = await agent.run(
            store_id="STORE001",
            date="2024-01-15",
            employees=[sample_employees[0]],
        )
        assert result["success"] is True
        assert any(a["type"] == "fill_gap" for a in result["auto_scheduling_actions"])

    @pytest.mark.asyncio
    async def test_run_with_empty_employees(self, agent):
        """测试空员工列表"""
        result = await agent.run(store_id="STORE001", date="2024-01-15", employees=[])

        assert result["success"] is True
        assert len(result["schedule"]) == 0

    def test_get_shift_start_time(self, agent):
        """测试获取班次开始时间"""
        assert agent._get_shift_start_time("morning") == "06:00"
        assert agent._get_shift_start_time("afternoon") == "14:00"
        assert agent._get_shift_start_time("evening") == "18:00"
        assert agent._get_shift_start_time("unknown") == "09:00"  # 默认值

    def test_get_shift_end_time(self, agent):
        """测试获取班次结束时间"""
        assert agent._get_shift_end_time("morning") == "14:00"
        assert agent._get_shift_end_time("afternoon") == "22:00"
        assert agent._get_shift_end_time("evening") == "02:00"
        assert agent._get_shift_end_time("unknown") == "21:00"  # 默认值

    def test_calculate_shift_hours(self, agent):
        """测试计算班次时长"""
        assert agent._calculate_shift_hours("06:00", "14:00") == 8
        assert agent._calculate_shift_hours("14:00", "22:00") == 8
        assert agent._calculate_shift_hours("18:00", "02:00") == 8  # 跨天
        assert agent._calculate_shift_hours("09:00", "13:00") == 4


class TestScheduleLogic:
    """排班逻辑测试"""

    @pytest.mark.asyncio
    async def test_skill_matching(self, agent, sample_employees):
        """测试技能匹配"""
        result = await agent.run(
            store_id="STORE001", date="2024-01-15", employees=sample_employees
        )

        # 验证每个排班记录的员工都具备相应技能
        for shift in result["schedule"]:
            employee = next(
                (e for e in sample_employees if e["id"] == shift["employee_id"]), None
            )
            assert employee is not None
            assert shift["skill"] in employee["skills"]

    @pytest.mark.asyncio
    async def test_no_duplicate_assignments(self, agent, sample_employees):
        """测试同一员工不会被重复分配到同一班次"""
        result = await agent.run(
            store_id="STORE001", date="2024-01-15", employees=sample_employees
        )

        # 检查每个班次中员工ID是否唯一
        for shift_name in ["morning", "afternoon", "evening"]:
            shift_employees = [
                s["employee_id"]
                for s in result["schedule"]
                if s["shift"] == shift_name
            ]
            assert len(shift_employees) == len(set(shift_employees))

    @pytest.mark.asyncio
    async def test_requirements_coverage(self, agent, sample_employees):
        """测试需求覆盖"""
        result = await agent.run(
            store_id="STORE001", date="2024-01-15", employees=sample_employees
        )

        requirements = result["requirements"]
        schedule = result["schedule"]

        # 统计每个班次每个技能的实际分配人数
        for shift_name, shift_requirements in requirements.items():
            for skill, required_count in shift_requirements.items():
                actual_count = len(
                    [
                        s
                        for s in schedule
                        if s["shift"] == shift_name and s["skill"] == skill
                    ]
                )
                # 实际分配人数应该尽量接近需求（可能因为员工不足而少于需求）
                assert actual_count <= required_count + 1


class TestEdgeCases:
    """边界情况测试"""

    @pytest.mark.asyncio
    async def test_single_employee(self, agent):
        """测试单个员工"""
        employees = [
            {"id": "E001", "name": "张三", "skills": ["waiter", "cashier", "chef"]}
        ]
        result = await agent.run(
            store_id="STORE001", date="2024-01-15", employees=employees
        )

        assert result["success"] is True
        # 单个员工应该被分配到多个班次
        assert len(result["schedule"]) > 0

    @pytest.mark.asyncio
    async def test_no_skilled_employees(self, agent):
        """测试没有技能的员工"""
        employees = [{"id": "E001", "name": "张三", "skills": []}]
        result = await agent.run(
            store_id="STORE001", date="2024-01-15", employees=employees
        )

        assert result["success"] is True
        # 没有技能的员工不应该被分配
        assert len(result["schedule"]) == 0

    @pytest.mark.asyncio
    async def test_future_date(self, agent, sample_employees):
        """测试未来日期排班"""
        future_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        result = await agent.run(
            store_id="STORE001", date=future_date, employees=sample_employees
        )

        assert result["success"] is True
        assert result["date"] == future_date


class TestAdjustSchedule:
    """排班调整测试"""

    @pytest.mark.asyncio
    async def test_adjust_schedule_leave_remove_only(self, agent):
        schedule = {
            "schedule": [
                {
                    "employee_id": "E001",
                    "employee_name": "张三",
                    "skill": "waiter",
                    "shift": "morning",
                    "date": "2024-01-15",
                    "start_time": "06:00",
                    "end_time": "14:00",
                },
                {
                    "employee_id": "E002",
                    "employee_name": "李四",
                    "skill": "chef",
                    "shift": "morning",
                    "date": "2024-01-15",
                    "start_time": "06:00",
                    "end_time": "14:00",
                },
            ]
        }
        result = await agent.adjust_schedule(
            schedule_id="SCH001",
            schedule=schedule,
            adjustments=[{"action": "leave", "employee_id": "E001"}],
        )
        assert result["success"] is True
        assert all(s["employee_id"] != "E001" for s in result["updated_schedule"])
        assert any("请假" in msg for msg in result["applied_adjustments"])

    @pytest.mark.asyncio
    async def test_adjust_schedule_leave_with_replacement(self, agent):
        schedule = {
            "schedule": [
                {
                    "employee_id": "E001",
                    "employee_name": "张三",
                    "skill": "waiter",
                    "shift": "evening",
                    "date": "2024-01-15",
                    "start_time": "18:00",
                    "end_time": "02:00",
                }
            ]
        }
        result = await agent.adjust_schedule(
            schedule_id="SCH002",
            schedule=schedule,
            adjustments=[
                {
                    "action": "leave",
                    "employee_id": "E001",
                    "replacement_employee_id": "E009",
                    "replacement_employee_name": "替补员",
                    "replacement_skills": ["waiter", "cashier"],
                }
            ],
        )
        assert result["success"] is True
        assert any(s["employee_id"] == "E009" for s in result["updated_schedule"])
        assert any("顶班" in msg for msg in result["applied_adjustments"])

    @pytest.mark.asyncio
    async def test_adjust_schedule_leave_replacement_skill_mismatch(self, agent):
        schedule = {
            "schedule": [
                {
                    "employee_id": "E001",
                    "employee_name": "张三",
                    "skill": "chef",
                    "shift": "afternoon",
                    "date": "2024-01-15",
                    "start_time": "14:00",
                    "end_time": "22:00",
                }
            ]
        }
        result = await agent.adjust_schedule(
            schedule_id="SCH003",
            schedule=schedule,
            adjustments=[
                {
                    "action": "leave",
                    "employee_id": "E001",
                    "replacement_employee_id": "E010",
                    "replacement_skills": ["waiter"],
                }
            ],
        )
        assert result["success"] is True
        assert all(s["employee_id"] != "E010" for s in result["updated_schedule"])
        assert any("技能不匹配" in msg for msg in result["applied_adjustments"])


class TestMultiStoreSchedule:
    """多门店协同排班测试"""

    @pytest.mark.asyncio
    async def test_plan_multi_store_schedule_returns_transfer_suggestions(self, agent):
        stores = [
            {
                "store_id": "STORE_A",
                "employees": [
                    {
                        "id": "A_E1",
                        "name": "跨店厨师",
                        "skills": ["chef"],
                        "multi_store_available": True,
                        "allowed_stores": ["STORE_B"],
                    }
                ],
            },
            {
                "store_id": "STORE_B",
                "employees": [
                    {
                        "id": "B_E1",
                        "name": "收银",
                        "skills": ["cashier"],
                        "multi_store_available": False,
                    }
                ],
            },
        ]
        result = await agent.plan_multi_store_schedule(date="2024-01-15", stores=stores)
        assert result["success"] is True
        assert len(result["store_results"]) == 2
        assert any(s["to_store_id"] == "STORE_B" for s in result["transfer_suggestions"])


class TestEnums:
    """枚举类型测试"""

    def test_shift_type_enum(self):
        """测试班次类型枚举"""
        assert ShiftType.MORNING.value == "morning"
        assert ShiftType.AFTERNOON.value == "afternoon"
        assert ShiftType.EVENING.value == "evening"
        assert ShiftType.FULL_DAY.value == "full_day"

    def test_employee_skill_enum(self):
        """测试员工技能枚举"""
        assert EmployeeSkill.CASHIER.value == "cashier"
        assert EmployeeSkill.WAITER.value == "waiter"
        assert EmployeeSkill.CHEF.value == "chef"
        assert EmployeeSkill.MANAGER.value == "manager"
        assert EmployeeSkill.CLEANER.value == "cleaner"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
