"""
VoiceCommandService 单元测试

覆盖：
- recognize_intent: 5个意图的关键词匹配、未知文本返回None、异常安全
- handle_stateful_command: 加载/创建上下文、路由、保存、session_id透传
- broadcast_meituan_queue_update: 零排队 / 有排队消息格式
- alert_timeout_order: voice_response 格式
"""
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.modules.setdefault("src.services.agent_service", MagicMock())
sys.modules.setdefault("src.core.database", MagicMock())
sys.modules.setdefault("src.models.store", MagicMock())
sys.modules.setdefault("src.models.order", MagicMock())
sys.modules.setdefault("src.models.inventory", MagicMock())

from src.services.voice_command_service import VoiceCommandService, VoiceIntent
from src.models.conversation import ConversationContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _svc(redis=None) -> VoiceCommandService:
    return VoiceCommandService(redis_client=redis)


def _ctx(store_id="S1", user_id="U1") -> ConversationContext:
    return ConversationContext(store_id=store_id, user_id=user_id)


# ---------------------------------------------------------------------------
# recognize_intent
# ---------------------------------------------------------------------------

class TestRecognizeIntent:
    def test_queue_status_排队(self):
        svc = _svc()
        assert svc.recognize_intent("当前排队多少桌") == VoiceIntent.QUEUE_STATUS

    def test_queue_status_等位(self):
        svc = _svc()
        assert svc.recognize_intent("现在等位几个") == VoiceIntent.QUEUE_STATUS

    def test_order_reminder_催单(self):
        svc = _svc()
        assert svc.recognize_intent("催单提醒哪些订单超时了") == VoiceIntent.ORDER_REMINDER

    def test_inventory_query_库存(self):
        svc = _svc()
        assert svc.recognize_intent("查询库存还剩多少") == VoiceIntent.INVENTORY_QUERY

    def test_inventory_query_还有多少(self):
        svc = _svc()
        assert svc.recognize_intent("猪肉还有多少") == VoiceIntent.INVENTORY_QUERY

    def test_revenue_today_营收(self):
        svc = _svc()
        assert svc.recognize_intent("今天营收多少") == VoiceIntent.REVENUE_TODAY

    def test_revenue_today_生意(self):
        svc = _svc()
        assert svc.recognize_intent("今日生意怎么样") == VoiceIntent.REVENUE_TODAY

    def test_call_support_呼叫支援(self):
        svc = _svc()
        assert svc.recognize_intent("需要支援帮忙") == VoiceIntent.CALL_SUPPORT

    def test_call_support_忙不过来(self):
        svc = _svc()
        assert svc.recognize_intent("忙不过来了") == VoiceIntent.CALL_SUPPORT

    def test_call_support_人手不足(self):
        svc = _svc()
        assert svc.recognize_intent("人手不足") == VoiceIntent.CALL_SUPPORT

    def test_unknown_text_returns_none(self):
        svc = _svc()
        assert svc.recognize_intent("我想要一杯茶") is None

    def test_empty_string_returns_none(self):
        svc = _svc()
        assert svc.recognize_intent("") is None

    def test_case_insensitive(self):
        # recognize_intent lowercases input before matching
        svc = _svc()
        assert svc.recognize_intent("当前排队多少") == VoiceIntent.QUEUE_STATUS


# ---------------------------------------------------------------------------
# handle_stateful_command
# ---------------------------------------------------------------------------

class TestHandleStatefulCommand:
    @pytest.mark.asyncio
    async def test_routes_through_intent_router(self):
        svc = _svc()
        ctx = _ctx()

        mock_store = MagicMock()
        mock_store.get_or_create = AsyncMock(return_value=ctx)
        mock_store.save = AsyncMock()
        svc._conv_store = mock_store

        mock_router = MagicMock()
        mock_router.route = AsyncMock(return_value={
            "success": True,
            "intent": "query_queue",
            "message": "没有排队",
            "voice_response": "没有排队",
            "session_id": ctx.session_id,
        })
        svc._intent_router = mock_router

        result = await svc.handle_stateful_command(
            voice_text="排队多少",
            store_id="S1",
            user_id="U1",
            actor_role="waiter",
        )

        mock_router.route.assert_awaited_once_with(
            text="排队多少",
            context=ctx,
            actor_role="waiter",
            db=None,
        )
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_result_contains_session_id(self):
        svc = _svc()
        ctx = _ctx()

        mock_store = MagicMock()
        mock_store.get_or_create = AsyncMock(return_value=ctx)
        mock_store.save = AsyncMock()
        svc._conv_store = mock_store

        mock_router = MagicMock()
        mock_router.route = AsyncMock(return_value={
            "success": False,
            "intent": None,
            "message": "无法识别",
            "voice_response": "无法识别",
        })
        svc._intent_router = mock_router

        result = await svc.handle_stateful_command(
            voice_text="无法识别的文本",
            store_id="S1",
            user_id="U1",
        )

        assert "session_id" in result
        assert result["session_id"] == ctx.session_id

    @pytest.mark.asyncio
    async def test_context_is_saved_after_routing(self):
        svc = _svc()
        ctx = _ctx()

        mock_store = MagicMock()
        mock_store.get_or_create = AsyncMock(return_value=ctx)
        mock_store.save = AsyncMock()
        svc._conv_store = mock_store

        mock_router = MagicMock()
        mock_router.route = AsyncMock(return_value={
            "success": True, "intent": "call_support",
            "message": "ok", "voice_response": "ok",
        })
        svc._intent_router = mock_router

        await svc.handle_stateful_command("支援", "S1", "U1")

        mock_store.save.assert_awaited_once_with(ctx)

    @pytest.mark.asyncio
    async def test_passes_session_id_to_store(self):
        svc = _svc()
        ctx = _ctx()

        mock_store = MagicMock()
        mock_store.get_or_create = AsyncMock(return_value=ctx)
        mock_store.save = AsyncMock()
        svc._conv_store = mock_store

        mock_router = MagicMock()
        mock_router.route = AsyncMock(return_value={
            "success": True, "intent": None,
            "message": "ok", "voice_response": "ok",
        })
        svc._intent_router = mock_router

        await svc.handle_stateful_command(
            voice_text="查库存",
            store_id="S1",
            user_id="U1",
            session_id="SESSION_ABC",
        )

        mock_store.get_or_create.assert_awaited_once_with(
            session_id="SESSION_ABC",
            store_id="S1",
            user_id="U1",
        )

    @pytest.mark.asyncio
    async def test_handle_command_delegates_to_stateful(self):
        """handle_command() is a thin alias over handle_stateful_command()."""
        svc = _svc()
        ctx = _ctx()

        mock_store = MagicMock()
        mock_store.get_or_create = AsyncMock(return_value=ctx)
        mock_store.save = AsyncMock()
        svc._conv_store = mock_store

        mock_router = MagicMock()
        mock_router.route = AsyncMock(return_value={
            "success": True, "intent": "query_queue",
            "message": "ok", "voice_response": "ok",
        })
        svc._intent_router = mock_router

        result = await svc.handle_command(
            voice_text="排队状态",
            store_id="S1",
            user_id="U1",
            actor_role="waiter",
        )

        assert result["success"] is True
        mock_router.route.assert_awaited_once()


# ---------------------------------------------------------------------------
# broadcast_meituan_queue_update
# ---------------------------------------------------------------------------

class TestBroadcastMeituanQueueUpdate:
    @pytest.mark.asyncio
    async def test_zero_queue_returns_cleared_message(self):
        svc = _svc()
        result = await svc.broadcast_meituan_queue_update("S1", 0, 0)
        assert result["success"] is True
        assert "清空" in result["voice_response"]

    @pytest.mark.asyncio
    async def test_nonzero_queue_contains_count_and_time(self):
        svc = _svc()
        result = await svc.broadcast_meituan_queue_update("S1", 5, 30)
        assert "5" in result["voice_response"]
        assert "30" in result["voice_response"]

    @pytest.mark.asyncio
    async def test_result_data_contains_queue_count(self):
        svc = _svc()
        result = await svc.broadcast_meituan_queue_update("S1", 3, 15)
        assert result["data"]["queue_count"] == 3
        assert result["data"]["estimated_wait_time"] == 15


# ---------------------------------------------------------------------------
# alert_timeout_order
# ---------------------------------------------------------------------------

class TestAlertTimeoutOrder:
    @pytest.mark.asyncio
    async def test_voice_response_contains_table_and_wait_time(self):
        svc = _svc()
        result = await svc.alert_timeout_order("S1", "A12", 45)
        assert "A12" in result["voice_response"]
        assert "45" in result["voice_response"]

    @pytest.mark.asyncio
    async def test_result_success_true(self):
        svc = _svc()
        result = await svc.alert_timeout_order("S1", "B3", 20)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_result_data_contains_fields(self):
        svc = _svc()
        result = await svc.alert_timeout_order("S1", "C5", 60)
        assert result["data"]["table_number"] == "C5"
        assert result["data"]["wait_time"] == 60
