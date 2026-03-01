"""
IntentRouter 及各 Handler 单元测试

覆盖：
- IntentRouter: 意图解析（关键词匹配）、权限拒绝、未知意图
- IntentRouter: pending_intent 上下文感知（确认词继续上轮意图）
- QueryRevenueHandler: 无DB降级、有DB查询结果、DB异常降级
- QueryQueueHandler: 无等位、有等位、DB异常降级
- InventoryQueryHandler: 库存充足、有不足食材、DB异常降级
- ApplyDiscountHandler: 金额解析（减X元/打X折/抹零）、无法解析时设pending_intent、
  executor执行成功、executor失败降级
- CallSupportHandler: 正常响应（不依赖wechat）、日志记录
"""
import sys
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.modules.setdefault("src.services.agent_service", MagicMock())

from src.models.conversation import ConversationContext, ConversationTurn
from src.services.intent_router import (
    ApplyDiscountHandler,
    CallSupportHandler,
    InventoryQueryHandler,
    IntentRouter,
    QueryQueueHandler,
    QueryRevenueHandler,
    INTENT_MAP,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx(store_id: str = "S1", user_id: str = "U1") -> ConversationContext:
    return ConversationContext(store_id=store_id, user_id=user_id)


def _scalar_db(value):
    """Mock DB that returns a scalar result."""
    db = MagicMock()
    result = MagicMock()
    result.scalar = MagicMock(return_value=value)
    db.execute = AsyncMock(return_value=result)
    return db


def _rows_db(rows):
    """Mock DB that returns .all() rows."""
    db = MagicMock()
    result = MagicMock()
    result.all = MagicMock(return_value=rows)
    db.execute = AsyncMock(return_value=result)
    return db


def _one_db(row):
    """Mock DB that returns .one() row."""
    db = MagicMock()
    result = MagicMock()
    result.one = MagicMock(return_value=row)
    db.execute = AsyncMock(return_value=result)
    return db


# ---------------------------------------------------------------------------
# IntentRouter: intent detection
# ---------------------------------------------------------------------------

class TestIntentDetection:
    @pytest.mark.asyncio
    async def test_keyword_営収_matches_query_revenue(self):
        router = IntentRouter()
        ctx = _ctx()
        result = await router.route("今日营收多少", ctx, actor_role="store_manager")
        assert result["intent"] == "query_revenue"

    @pytest.mark.asyncio
    async def test_keyword_排队_matches_query_queue(self):
        router = IntentRouter()
        result = await router.route("现在排队有多少桌", _ctx(), actor_role="waiter")
        assert result["intent"] == "query_queue"

    @pytest.mark.asyncio
    async def test_keyword_库存_matches_inventory_query(self):
        router = IntentRouter()
        result = await router.route("查一下库存", _ctx(), actor_role="waiter")
        assert result["intent"] == "inventory_query"

    @pytest.mark.asyncio
    async def test_keyword_折扣_matches_apply_discount(self):
        router = IntentRouter()
        result = await router.route("帮这桌打折，减20元", _ctx(), actor_role="store_manager")
        assert result["intent"] == "apply_discount"

    @pytest.mark.asyncio
    async def test_keyword_支援_matches_call_support(self):
        router = IntentRouter()
        result = await router.route("人手不足，需要支援", _ctx(), actor_role="waiter")
        assert result["intent"] == "call_support"

    @pytest.mark.asyncio
    async def test_unknown_text_returns_success_false(self):
        router = IntentRouter()
        result = await router.route("我想要一杯茶", _ctx())
        assert result["success"] is False
        assert result["intent"] is None

    @pytest.mark.asyncio
    async def test_unknown_text_adds_turn_to_context(self):
        router = IntentRouter()
        ctx = _ctx()
        await router.route("无法识别的输入", ctx)
        assert len(ctx.turns) == 1

    @pytest.mark.asyncio
    async def test_pending_intent_resolved_by_confirmation(self):
        router = IntentRouter()
        ctx = _ctx()
        ctx.pending_intent = "apply_discount"
        ctx.add_turn(ConversationTurn(user_input="打折", intent="apply_discount", response="请说金额"))
        result = await router.route("好的", ctx, actor_role="store_manager")
        assert result["intent"] == "apply_discount"


# ---------------------------------------------------------------------------
# IntentRouter: permission check
# ---------------------------------------------------------------------------

class TestPermissionCheck:
    @pytest.mark.asyncio
    async def test_insufficient_role_returns_success_false(self):
        router = IntentRouter()
        result = await router.route("今日营收多少", _ctx(), actor_role="waiter")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_permission_denied_message_contains_role(self):
        router = IntentRouter()
        result = await router.route("今日营收多少", _ctx(), actor_role="waiter")
        assert "waiter" in result["message"]

    @pytest.mark.asyncio
    async def test_super_admin_bypasses_restriction(self):
        router = IntentRouter()
        result = await router.route("今日营收多少", _ctx(), actor_role="super_admin")
        assert result["success"] is True
        assert result["intent"] == "query_revenue"


# ---------------------------------------------------------------------------
# QueryRevenueHandler
# ---------------------------------------------------------------------------

class TestQueryRevenueHandler:
    handler = QueryRevenueHandler()

    @pytest.mark.asyncio
    async def test_no_db_returns_degraded_message(self):
        result = await self.handler.handle("营收", "S1", _ctx(), db=None)
        assert "无法" in result["message"]

    @pytest.mark.asyncio
    async def test_with_db_returns_yuan_amount(self):
        db = _scalar_db(150000)  # 1500元
        result = await self.handler.handle("营收", "S1", _ctx(), db=db)
        assert "1,500.00" in result["message"]

    @pytest.mark.asyncio
    async def test_zero_revenue_shows_zero(self):
        db = _scalar_db(0)
        result = await self.handler.handle("营收", "S1", _ctx(), db=db)
        assert "0.00" in result["message"]

    @pytest.mark.asyncio
    async def test_result_has_data_field(self):
        db = _scalar_db(50000)
        result = await self.handler.handle("营收", "S1", _ctx(), db=db)
        assert "data" in result
        assert result["data"]["total_yuan"] == pytest.approx(500.0)

    @pytest.mark.asyncio
    async def test_db_exception_returns_error_message(self):
        db = MagicMock()
        db.execute = AsyncMock(side_effect=RuntimeError("DB down"))
        result = await self.handler.handle("营收", "S1", _ctx(), db=db)
        assert "失败" in result["message"]


# ---------------------------------------------------------------------------
# QueryQueueHandler
# ---------------------------------------------------------------------------

class TestQueryQueueHandler:
    handler = QueryQueueHandler()

    @pytest.mark.asyncio
    async def test_no_db_returns_degraded_message(self):
        result = await self.handler.handle("排队", "S1", _ctx(), db=None)
        assert "无法" in result["message"]

    @pytest.mark.asyncio
    async def test_no_queue_message(self):
        row = MagicMock()
        row.waiting_tables = 0
        row.waiting_people = 0
        db = _one_db(row)
        result = await self.handler.handle("排队", "S1", _ctx(), db=db)
        assert "没有" in result["message"]

    @pytest.mark.asyncio
    async def test_queue_count_in_message(self):
        row = MagicMock()
        row.waiting_tables = 3
        row.waiting_people = 10
        db = _one_db(row)
        result = await self.handler.handle("排队", "S1", _ctx(), db=db)
        assert "3" in result["message"]
        assert "10" in result["message"]

    @pytest.mark.asyncio
    async def test_result_has_data_field(self):
        row = MagicMock()
        row.waiting_tables = 2
        row.waiting_people = 6
        db = _one_db(row)
        result = await self.handler.handle("排队", "S1", _ctx(), db=db)
        assert result["data"]["waiting_tables"] == 2

    @pytest.mark.asyncio
    async def test_db_exception_returns_error_message(self):
        db = MagicMock()
        db.execute = AsyncMock(side_effect=RuntimeError("DB down"))
        result = await self.handler.handle("排队", "S1", _ctx(), db=db)
        assert "失败" in result["message"]


# ---------------------------------------------------------------------------
# InventoryQueryHandler
# ---------------------------------------------------------------------------

class TestInventoryQueryHandler:
    handler = InventoryQueryHandler()

    @pytest.mark.asyncio
    async def test_no_db_returns_degraded_message(self):
        result = await self.handler.handle("库存", "S1", _ctx(), db=None)
        assert "无法" in result["message"]

    @pytest.mark.asyncio
    async def test_all_sufficient_returns_normal_message(self):
        db = _rows_db([])
        result = await self.handler.handle("库存", "S1", _ctx(), db=db)
        assert "充足" in result["message"]

    @pytest.mark.asyncio
    async def test_low_stock_items_in_message(self):
        item = MagicMock()
        item.name = "猪肉"
        item.current_quantity = 1.5
        item.unit = "kg"
        item.status = MagicMock(value="low")
        db = _rows_db([item])
        result = await self.handler.handle("库存", "S1", _ctx(), db=db)
        assert "猪肉" in result["message"]

    @pytest.mark.asyncio
    async def test_result_has_low_stock_items_list(self):
        item = MagicMock()
        item.name = "猪肉"
        item.current_quantity = 0.5
        item.unit = "kg"
        item.status = MagicMock(value="critical")
        db = _rows_db([item])
        result = await self.handler.handle("库存", "S1", _ctx(), db=db)
        assert len(result["data"]["low_stock_items"]) == 1

    @pytest.mark.asyncio
    async def test_db_exception_returns_error_message(self):
        db = MagicMock()
        db.execute = AsyncMock(side_effect=RuntimeError("DB down"))
        result = await self.handler.handle("库存", "S1", _ctx(), db=db)
        assert "失败" in result["message"]


# ---------------------------------------------------------------------------
# ApplyDiscountHandler
# ---------------------------------------------------------------------------

class TestApplyDiscountHandler:
    handler = ApplyDiscountHandler()

    def test_parse_yuan_amount(self):
        assert self.handler._parse_amount_fen("减20元") == 2000

    def test_parse_youhui_yuan(self):
        assert self.handler._parse_amount_fen("优惠50元") == 5000

    def test_parse_zhejiu(self):
        # 打9折 → 10% off → 1000 fen (based on 100元 base)
        assert self.handler._parse_amount_fen("打9折") == 1000

    def test_parse_moling(self):
        assert self.handler._parse_amount_fen("抹零") == 500

    def test_unknown_text_returns_none(self):
        assert self.handler._parse_amount_fen("没有折扣信息") is None

    @pytest.mark.asyncio
    async def test_no_amount_sets_pending_intent(self):
        ctx = _ctx()
        result = await self.handler.handle("给这桌打折", "S1", ctx)
        assert ctx.pending_intent == "apply_discount"
        assert "请说明" in result["message"]

    @pytest.mark.asyncio
    async def test_parsed_amount_calls_executor(self):
        ctx = _ctx()
        with patch("src.core.trusted_executor.TrustedExecutor") as MockExec:
            mock_instance = MagicMock()
            mock_instance.execute = AsyncMock(return_value={"status": "completed"})
            MockExec.return_value = mock_instance
            result = await self.handler.handle("减20元", "S1", ctx, actor_role="store_manager")
        mock_instance.execute.assert_awaited_once()
        assert result["intent"] == "apply_discount"

    @pytest.mark.asyncio
    async def test_executor_failure_returns_fallback(self):
        ctx = _ctx()
        with patch("src.core.trusted_executor.TrustedExecutor") as MockExec:
            mock_instance = MagicMock()
            mock_instance.execute = AsyncMock(side_effect=RuntimeError("executor down"))
            MockExec.return_value = mock_instance
            result = await self.handler.handle("减20元", "S1", ctx)
        assert "申请已记录" in result["message"]


# ---------------------------------------------------------------------------
# CallSupportHandler
# ---------------------------------------------------------------------------

class TestCallSupportHandler:
    handler = CallSupportHandler()

    @pytest.mark.asyncio
    async def test_returns_acknowledgment(self):
        result = await self.handler.handle("人手不足", "S1", _ctx())
        assert result["intent"] == "call_support"
        assert "发送" in result["voice_response"]

    @pytest.mark.asyncio
    async def test_data_contains_requested_by(self):
        ctx = _ctx(user_id="USER_99")
        result = await self.handler.handle("支援", "S1", ctx)
        assert result["data"]["requested_by"] == "USER_99"

    @pytest.mark.asyncio
    async def test_wechat_failure_does_not_raise(self):
        # wechat_service import inside try block may fail (no env vars in test env).
        # Either way, the except clause must swallow it and the handler must return.
        result = await self.handler.handle("支援", "S1", _ctx())
        assert result["intent"] == "call_support"
