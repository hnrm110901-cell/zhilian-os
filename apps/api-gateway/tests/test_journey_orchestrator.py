"""
JourneyOrchestrator 单元测试

覆盖：
  - 纯函数：evaluate_condition（4种场景）
  - 纯函数：format_journey_message（已知/未知模板）
  - 服务：get_definition（已知/未知旅程）
  - 服务：trigger（成功路径 + 未知旅程）
  - 服务：execute_step（条件通过 + 条件不满足 + 频控 + 无企微 + 最后步骤完成）
  - 内置旅程完整性（3条旅程至少1个步骤，每步 delay >= 0）
"""

import os
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("APP_ENV", "test")

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.journey_orchestrator import (
    BUILTIN_JOURNEYS,
    JourneyOrchestrator,
    JourneyStep,
    evaluate_condition,
    format_journey_message,
)


# ════════════════════════════════════════════════════════════════════════════════
# 纯函数：evaluate_condition
# ════════════════════════════════════════════════════════════════════════════════

class TestEvaluateCondition:
    def test_none_condition_always_true(self):
        assert evaluate_condition(None, 0)   is True
        assert evaluate_condition(None, 10)  is True

    def test_order_pay_no_order_should_execute(self):
        assert evaluate_condition({"event_not_exist": "order_pay"}, 0) is True

    def test_order_pay_has_order_should_skip(self):
        assert evaluate_condition({"event_not_exist": "order_pay"}, 1) is False
        assert evaluate_condition({"event_not_exist": "order_pay"}, 5) is False

    def test_unknown_condition_defaults_to_true(self):
        assert evaluate_condition({"event_not_exist": "something_else"}, 0) is True
        assert evaluate_condition({"event_not_exist": "something_else"}, 1) is True


# ════════════════════════════════════════════════════════════════════════════════
# 纯函数：format_journey_message
# ════════════════════════════════════════════════════════════════════════════════

class TestFormatJourneyMessage:
    def test_known_template_returns_nonempty(self):
        msg = format_journey_message("journey_welcome", "S001", "C001")
        assert isinstance(msg, str)
        assert len(msg) > 0

    def test_unknown_template_returns_fallback(self):
        msg = format_journey_message("nonexistent_template", "S001", "C001")
        assert isinstance(msg, str)
        assert len(msg) > 0

    def test_all_builtin_templates_defined(self):
        template_ids = {
            s.template_id
            for j in BUILTIN_JOURNEYS.values()
            for s in j.steps
        }
        for tid in template_ids:
            msg = format_journey_message(tid, "S001", "C001")
            assert msg != format_journey_message("__nonexistent__", "S001", "C001"), (
                f"Template '{tid}' should have a dedicated message, not fallback"
            )


# ════════════════════════════════════════════════════════════════════════════════
# 旅程定义完整性
# ════════════════════════════════════════════════════════════════════════════════

class TestBuiltinJourneys:
    def test_all_three_journeys_exist(self):
        assert "member_activation"      in BUILTIN_JOURNEYS
        assert "first_order_conversion" in BUILTIN_JOURNEYS
        assert "dormant_wakeup"         in BUILTIN_JOURNEYS

    def test_each_journey_has_steps(self):
        for jid, jdef in BUILTIN_JOURNEYS.items():
            assert len(jdef.steps) >= 1, f"{jid} must have at least 1 step"

    def test_step_delays_non_negative(self):
        for jdef in BUILTIN_JOURNEYS.values():
            for step in jdef.steps:
                assert step.delay_minutes >= 0

    def test_member_activation_first_step_is_immediate(self):
        first_step = BUILTIN_JOURNEYS["member_activation"].steps[0]
        assert first_step.delay_minutes == 0

    def test_dormant_wakeup_has_comeback_coupon(self):
        steps = BUILTIN_JOURNEYS["dormant_wakeup"].steps
        step_ids = [s.step_id for s in steps]
        assert "comeback_coupon" in step_ids


# ════════════════════════════════════════════════════════════════════════════════
# 服务：get_definition
# ════════════════════════════════════════════════════════════════════════════════

class TestGetDefinition:
    def test_known_journey_returns_definition(self):
        orch = JourneyOrchestrator()
        defn = orch.get_definition("member_activation")
        assert defn is not None
        assert defn.journey_id == "member_activation"

    def test_unknown_journey_returns_none(self):
        orch = JourneyOrchestrator()
        assert orch.get_definition("nonexistent_journey") is None


# ════════════════════════════════════════════════════════════════════════════════
# 服务：trigger
# ════════════════════════════════════════════════════════════════════════════════

class TestTrigger:
    @pytest.mark.asyncio
    async def test_trigger_known_journey_creates_record(self):
        orch = JourneyOrchestrator()
        db   = AsyncMock()

        with patch("src.services.journey_orchestrator.JourneyOrchestrator.trigger",
                   wraps=orch.trigger):
            with patch("src.core.celery_tasks.execute_journey_step") as mock_task:
                mock_task.apply_async = MagicMock()
                result = await orch.trigger("C001", "S001", "member_activation", db)

        assert "error"          not in result
        assert result["journey_id"]      == "member_activation"
        assert result["total_steps"]     == 3
        db.execute.assert_called_once()
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_trigger_unknown_journey_returns_error(self):
        orch = JourneyOrchestrator()
        db   = AsyncMock()

        result = await orch.trigger("C001", "S001", "nonexistent", db)

        assert "error" in result
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_trigger_schedules_steps(self):
        orch = JourneyOrchestrator()
        db   = AsyncMock()

        with patch("src.services.journey_orchestrator.JourneyOrchestrator.trigger",
                   wraps=orch.trigger):
            with patch("src.core.celery_tasks.execute_journey_step") as mock_task:
                mock_task.apply_async = MagicMock()
                result = await orch.trigger("C001", "S001", "dormant_wakeup", db)

        assert result["steps_scheduled"] == 2  # dormant_wakeup 有2步


# ════════════════════════════════════════════════════════════════════════════════
# 服务：execute_step
# ════════════════════════════════════════════════════════════════════════════════

def _make_journey_row(**kwargs):
    """构造模拟旅程 DB 行。"""
    defaults = {
        "id":           "test-uuid-001",
        "journey_type": "member_activation",
        "customer_id":  "C001",
        "store_id":     "S001",
        "status":       "running",
        "started_at":   datetime(2026, 3, 1, 0, 0, 0),
        "step_history": [],
    }
    defaults.update(kwargs)
    row = MagicMock()
    for k, v in defaults.items():
        setattr(row, k, v)
    return row


class TestExecuteStep:
    @pytest.mark.asyncio
    async def test_condition_pass_sends_message(self):
        """条件满足（无订单）且有企微服务 → 发送消息。"""
        orch   = JourneyOrchestrator()
        db     = AsyncMock()
        wechat = AsyncMock()

        # journey 记录查询
        db.execute.return_value.fetchone.side_effect = [
            _make_journey_row(),   # 旅程记录
            MagicMock(cnt=0),      # orders_since (0 = 无新订单)
        ]

        result = await orch.execute_step(
            "test-uuid-001", 0, db,
            wechat_user_id="wx_user_001",
            wechat_service=wechat,
        )

        assert result["executed"] is True
        wechat.send_text_message.assert_called_once()
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_condition_fail_skips_step(self):
        """条件不满足（已有订单）→ 跳过，不发消息。"""
        orch   = JourneyOrchestrator()
        db     = AsyncMock()
        wechat = AsyncMock()

        # step_index=1 有 condition={"event_not_exist": "order_pay"}
        db.execute.return_value.fetchone.side_effect = [
            _make_journey_row(),   # 旅程记录
            MagicMock(cnt=1),      # 1条新订单 → 条件不满足
        ]

        result = await orch.execute_step(
            "test-uuid-001", 1, db,
            wechat_user_id="wx_user_001",
            wechat_service=wechat,
        )

        assert result["executed"] is False
        assert "条件不满足" in result["skipped_reason"]
        wechat.send_text_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_freq_cap_blocks_send(self):
        """频控拦截 → 跳过发送。"""
        orch      = JourneyOrchestrator()
        db        = AsyncMock()
        wechat    = AsyncMock()
        freq_cap  = AsyncMock()
        freq_cap.can_send.return_value = False

        db.execute.return_value.fetchone.side_effect = [
            _make_journey_row(),
            MagicMock(cnt=0),
        ]

        result = await orch.execute_step(
            "test-uuid-001", 0, db,
            wechat_user_id="wx_user_001",
            wechat_service=wechat,
            freq_cap_engine=freq_cap,
        )

        assert result["executed"] is False
        assert "频控" in result["skipped_reason"]
        wechat.send_text_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_wechat_service_skips_send_but_executes(self):
        """无企微服务 → 执行但 sent=False。"""
        orch = JourneyOrchestrator()
        db   = AsyncMock()

        db.execute.return_value.fetchone.side_effect = [
            _make_journey_row(),
            MagicMock(cnt=0),
        ]

        result = await orch.execute_step("test-uuid-001", 0, db)

        assert result["executed"] is True
        assert result["sent"]     is False

    @pytest.mark.asyncio
    async def test_last_step_marks_journey_completed(self):
        """最后一步执行后，旅程状态变为 completed。"""
        orch = JourneyOrchestrator()
        db   = AsyncMock()

        # dormant_wakeup 有2步，step_index=1 是最后一步
        db.execute.return_value.fetchone.side_effect = [
            _make_journey_row(journey_type="dormant_wakeup"),
            MagicMock(cnt=0),
        ]

        await orch.execute_step("test-uuid-001", 1, db)

        # 检查 UPDATE 调用中包含 completed
        update_call = db.execute.call_args_list[-1]
        params = update_call.args[1]
        assert params["status"] == "completed"
        assert params["completed_at"] is not None

    @pytest.mark.asyncio
    async def test_journey_not_found_returns_error(self):
        orch = JourneyOrchestrator()
        db   = AsyncMock()
        db.execute.return_value.fetchone.return_value = None

        result = await orch.execute_step("nonexistent-id", 0, db)

        assert "error" in result

    @pytest.mark.asyncio
    async def test_completed_journey_is_skipped(self):
        orch = JourneyOrchestrator()
        db   = AsyncMock()
        db.execute.return_value.fetchone.return_value = _make_journey_row(
            status="completed"
        )

        result = await orch.execute_step("test-uuid-001", 0, db)

        assert result.get("skipped") is True
