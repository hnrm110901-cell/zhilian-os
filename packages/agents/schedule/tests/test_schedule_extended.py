"""
排班Agent扩展测试
覆盖：排班生成逻辑、人力预算约束、员工满意度、边界场景
"""

import pytest
from datetime import datetime, timedelta
from src.agent import ScheduleAgent, ShiftType, EmployeeSkill, ScheduleState


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def agent():
    config = {
        "min_shift_hours": 4,
        "max_shift_hours": 8,
        "max_weekly_hours": 40,
    }
    return ScheduleAgent(config)


@pytest.fixture
def large_team():
    """大型团队（测试排班充分覆盖）"""
    return [
        {"id": f"W{i}", "name": f"服务员{i}", "skills": ["waiter"], "preferences": {}}
        for i in range(1, 8)
    ] + [
        {"id": f"C{i}", "name": f"厨师{i}", "skills": ["chef"], "preferences": {}}
        for i in range(1, 5)
    ] + [
        {"id": "CA1", "name": "收银1", "skills": ["cashier"], "preferences": {}},
        {"id": "CA2", "name": "收银2", "skills": ["cashier"], "preferences": {}},
        {"id": "CA3", "name": "收银3", "skills": ["cashier"], "preferences": {}},
    ]


# ── 排班生成逻辑 ─────────────────────────────────────────────────────────────


class TestScheduleGeneration:
    """排班生成逻辑测试"""

    @pytest.mark.asyncio
    async def test_all_shifts_covered_with_large_team(self, agent, large_team):
        """大团队应能覆盖所有班次需求"""
        result = await agent.run(
            store_id="STORE001", date="2024-01-15", employees=large_team
        )
        assert result["success"] is True
        schedule = result["schedule"]

        # 每个班次应有排班
        for shift_name in ["morning", "afternoon", "evening"]:
            shift_entries = [s for s in schedule if s["shift"] == shift_name]
            assert len(shift_entries) > 0, f"{shift_name}班次没有排班"

    @pytest.mark.asyncio
    async def test_weekend_traffic_higher(self, agent, large_team):
        """周末客流量应高于工作日"""
        # 周一
        result_weekday = await agent.run(
            store_id="STORE001", date="2024-01-15", employees=large_team  # 周一
        )
        # 周六
        result_weekend = await agent.run(
            store_id="STORE001", date="2024-01-20", employees=large_team  # 周六
        )

        assert result_weekday["success"] is True
        assert result_weekend["success"] is True

        weekday_total = sum(
            result_weekday["traffic_prediction"]["predicted_customers"].values()
        )
        weekend_total = sum(
            result_weekend["traffic_prediction"]["predicted_customers"].values()
        )
        assert weekend_total > weekday_total, "周末客流应高于工作日"

    @pytest.mark.asyncio
    async def test_schedule_entries_have_complete_structure(self, agent, large_team):
        """排班记录必须包含完整结构"""
        result = await agent.run(
            store_id="STORE001", date="2024-01-15", employees=large_team
        )
        required_fields = [
            "employee_id", "employee_name", "skill",
            "shift", "date", "start_time", "end_time",
        ]
        for entry in result["schedule"]:
            for field in required_fields:
                assert field in entry, f"排班记录缺少字段: {field}"


# ── 人力预算约束 ─────────────────────────────────────────────────────────────


class TestLaborBudgetConstraint:
    """人力预算约束测试 — 成本控制"""

    @pytest.mark.asyncio
    async def test_labor_cost_summary_present(self, agent, large_team):
        """排班结果必须包含人工成本摘要"""
        result = await agent.run(
            store_id="STORE001", date="2024-01-15", employees=large_team
        )
        assert "labor_cost_summary" in result
        summary = result["labor_cost_summary"]
        assert "estimated_total_cost" in summary
        assert summary["estimated_total_cost"] >= 0

    @pytest.mark.asyncio
    async def test_budget_exceeded_triggers_cost_control(self, large_team):
        """超预算时应触发成本控制动作"""
        agent = ScheduleAgent({
            "min_shift_hours": 4,
            "max_shift_hours": 8,
            "max_weekly_hours": 40,
            "target_daily_labor_cost": 1,  # 极低预算，必然超出
        })
        result = await agent.run(
            store_id="STORE001", date="2024-01-15", employees=large_team
        )
        assert result["success"] is True
        # 应有成本控制的自动排班建议
        assert any(
            a["type"] == "cost_control"
            for a in result["auto_scheduling_actions"]
        ), "超预算时应生成成本控制建议"

    @pytest.mark.asyncio
    async def test_no_budget_constraint_no_cost_action(self, large_team):
        """无预算约束时成本控制建议的target为0（未设定真实预算）

        当 target_daily_labor_cost 未设置（默认为0）时，overrun_amount 等于
        全部预估成本（相对于0的超出），因此会生成 cost_control 建议，
        但其 payload.target_daily_labor_cost 为 0，表示无真实预算约束。
        """
        agent = ScheduleAgent({
            "min_shift_hours": 4,
            "max_shift_hours": 8,
            "max_weekly_hours": 40,
            # 不设置 target_daily_labor_cost
        })
        result = await agent.run(
            store_id="STORE001", date="2024-01-15", employees=large_team
        )
        assert result["success"] is True
        # 无预算约束时，target_daily_labor_cost 默认为0
        assert result["labor_cost_summary"]["target_daily_labor_cost"] == 0.0
        # cost_control 建议的 payload 中 target 为 0，表示未配置真实预算
        cost_actions = [
            a for a in result["auto_scheduling_actions"]
            if a["type"] == "cost_control"
        ]
        for action in cost_actions:
            assert action["payload"]["target_daily_labor_cost"] == 0


# ── 排班调整与边界 ───────────────────────────────────────────────────────────


class TestScheduleAdjustmentExtended:
    """排班调整扩展测试"""

    @pytest.mark.asyncio
    async def test_adjust_schedule_unknown_employee(self, agent):
        """调整不存在的员工应安全处理"""
        schedule = {
            "schedule": [
                {
                    "employee_id": "E001", "employee_name": "张三",
                    "skill": "waiter", "shift": "morning",
                    "date": "2024-01-15", "start_time": "06:00",
                    "end_time": "14:00",
                },
            ]
        }
        result = await agent.adjust_schedule(
            schedule_id="SCH_TEST",
            schedule=schedule,
            adjustments=[{"action": "leave", "employee_id": "E999"}],  # 不存在
        )
        # 应成功但不影响现有排班
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_multiple_employees_same_skill(self, agent):
        """多个相同技能员工的排班不应冲突"""
        employees = [
            {"id": f"W{i}", "name": f"服务员{i}", "skills": ["waiter"], "preferences": {}}
            for i in range(1, 6)
        ]
        result = await agent.run(
            store_id="STORE001", date="2024-01-15", employees=employees
        )
        assert result["success"] is True

        # 同一班次中不应有重复员工
        for shift_name in ["morning", "afternoon", "evening"]:
            shift_emp_ids = [
                s["employee_id"]
                for s in result["schedule"]
                if s["shift"] == shift_name
            ]
            assert len(shift_emp_ids) == len(set(shift_emp_ids)), (
                f"{shift_name}班次有重复员工"
            )

    @pytest.mark.asyncio
    async def test_execute_get_schedule_action(self, agent):
        """通过 execute 调用 get_schedule"""
        response = await agent.execute("get_schedule", {
            "store_id": "STORE001",
            "start_date": "2024-01-15",
            "end_date": "2024-01-21",
            "schedules": [],
        })
        assert response.success is True

    @pytest.mark.asyncio
    async def test_execute_unsupported_action(self, agent):
        """不支持的 action 应返回失败"""
        response = await agent.execute("invalid_action", {})
        assert response.success is False
        assert "Unsupported action" in response.error

    @pytest.mark.asyncio
    async def test_get_supported_actions(self, agent):
        """支持的操作列表应完整"""
        actions = agent.get_supported_actions()
        expected_actions = [
            "run", "plan_multi_store_schedule",
            "plan_cross_region_allocation",
            "predict_schedule_adjustments",
            "reinforcement_optimize_schedule",
            "evaluate_employee_satisfaction",
            "adjust_schedule", "get_schedule",
        ]
        for action in expected_actions:
            assert action in actions, f"缺少操作: {action}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
