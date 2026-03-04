"""
VoiceCommandService 单元测试

覆盖：
- recognize_intent: 5个意图的关键词匹配、未知文本返回None、异常安全
- handle_stateful_command: 加载/创建上下文、路由、保存、session_id透传
- broadcast_meituan_queue_update: 零排队 / 有排队消息格式
- alert_timeout_order: voice_response 格式
- _handle_queue_status / _handle_order_reminder / _handle_inventory_query
- _handle_revenue_today / _handle_call_support (DB-backed private methods)
"""
import sys
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.modules.setdefault("src.services.agent_service", MagicMock())
sys.modules.setdefault("src.core.database", MagicMock())
sys.modules.setdefault("src.models.store", MagicMock())
sys.modules.setdefault("src.models.order", MagicMock())
sys.modules.setdefault("src.models.inventory", MagicMock())

from src.services.voice_command_service import VoiceCommandService, VoiceIntent
from src.models.conversation import ConversationContext
import src.services.voice_command_service as _vcs_mod


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


# ---------------------------------------------------------------------------
# recognize_intent — exception branch (line 143-145)
# ---------------------------------------------------------------------------

class TestRecognizeIntentException:
    def test_exception_in_re_search_returns_none(self):
        svc = _svc()
        with patch("src.services.voice_command_service.re.search", side_effect=RuntimeError("re err")):
            result = svc.recognize_intent("any text")
        assert result is None


# ---------------------------------------------------------------------------
# broadcast / alert exception paths
# ---------------------------------------------------------------------------

class TestBroadcastException:
    @pytest.mark.asyncio
    async def test_exception_returns_failure(self):
        svc = _svc()
        with patch.object(_vcs_mod, "logger") as mock_logger:
            mock_logger.info = MagicMock(side_effect=RuntimeError("log err"))
            result = await svc.broadcast_meituan_queue_update("S1", 3, 15)
        assert result["success"] is False
        assert "广播" in result["message"]


class TestAlertException:
    @pytest.mark.asyncio
    async def test_exception_returns_failure(self):
        svc = _svc()
        with patch.object(_vcs_mod, "logger") as mock_logger:
            mock_logger.warning = MagicMock(side_effect=RuntimeError("log err"))
            result = await svc.alert_timeout_order("S1", "T1", 30)
        assert result["success"] is False
        assert "告警" in result["message"]


# ---------------------------------------------------------------------------
# _handle_queue_status (lines 181-220)
# ---------------------------------------------------------------------------

class TestHandleQueueStatus:

    @staticmethod
    def _db_mock(count, avg_actual=None):
        db = AsyncMock()
        count_res = MagicMock()
        count_res.scalar = MagicMock(return_value=count)
        avg_res = MagicMock()
        avg_res.scalar = MagicMock(return_value=avg_actual)
        db.execute = AsyncMock(side_effect=[count_res, avg_res])
        return db

    @pytest.mark.asyncio
    async def test_zero_waiting(self):
        svc = _svc()
        db = AsyncMock()
        res = MagicMock()
        res.scalar = MagicMock(return_value=0)
        db.execute = AsyncMock(return_value=res)
        with patch.dict("sys.modules", {"src.models.queue": MagicMock()}), \
             patch.object(_vcs_mod, "select", MagicMock()), \
             patch.object(_vcs_mod, "sa_func", MagicMock()):
            result = await svc._handle_queue_status("S1", db)
        assert result["success"] is True
        assert "没有排队" in result["voice_response"]
        assert result["data"]["waiting_count"] == 0
        assert result["data"]["estimated_wait_time"] == 0

    @pytest.mark.asyncio
    async def test_nonzero_with_avg_actual(self):
        svc = _svc()
        db = self._db_mock(3, avg_actual=20)
        with patch.dict("sys.modules", {"src.models.queue": MagicMock()}), \
             patch.object(_vcs_mod, "select", MagicMock()), \
             patch.object(_vcs_mod, "sa_func", MagicMock()):
            result = await svc._handle_queue_status("S1", db)
        assert result["success"] is True
        assert "3" in result["voice_response"]
        assert result["data"]["waiting_count"] == 3
        assert result["data"]["estimated_wait_time"] == 60  # 3 * 20

    @pytest.mark.asyncio
    async def test_nonzero_no_avg_uses_env_default(self):
        svc = _svc()
        db = self._db_mock(2, avg_actual=None)
        with patch.dict("sys.modules", {"src.models.queue": MagicMock()}), \
             patch.object(_vcs_mod, "select", MagicMock()), \
             patch.object(_vcs_mod, "sa_func", MagicMock()), \
             patch.dict("os.environ", {"VOICE_DEFAULT_WAIT_MINUTES": "10"}):
            result = await svc._handle_queue_status("S1", db)
        assert "2" in result["voice_response"]
        assert result["data"]["estimated_wait_time"] == 20  # 2 * 10

    @pytest.mark.asyncio
    async def test_exception_returns_failure(self):
        svc = _svc()
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=RuntimeError("db error"))
        with patch.dict("sys.modules", {"src.models.queue": MagicMock()}), \
             patch.object(_vcs_mod, "select", MagicMock()), \
             patch.object(_vcs_mod, "sa_func", MagicMock()):
            result = await svc._handle_queue_status("S1", db)
        assert result["success"] is False


# ---------------------------------------------------------------------------
# _handle_order_reminder (lines 228-272)
# ---------------------------------------------------------------------------

class TestHandleOrderReminder:

    @staticmethod
    def _db_mock(orders):
        db = AsyncMock()
        res = MagicMock()
        res.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=orders)))
        db.execute = AsyncMock(return_value=res)
        return db

    @staticmethod
    def _make_order(wait_minutes=35):
        order = MagicMock()
        order.id = "O1"
        order.table_number = "T1"
        order.created_at = datetime.utcnow() - timedelta(minutes=wait_minutes)
        return order

    @pytest.mark.asyncio
    async def test_no_timeout_orders(self):
        svc = _svc()
        db = self._db_mock([])
        with patch.object(_vcs_mod, "select", MagicMock()), \
             patch.dict("os.environ", {"VOICE_ORDER_TIMEOUT_MINUTES": "30"}):
            result = await svc._handle_order_reminder("S1", db)
        assert result["success"] is True
        assert "没有超时" in result["voice_response"]
        assert result["data"]["timeout_count"] == 0

    @pytest.mark.asyncio
    async def test_with_timeout_orders(self):
        svc = _svc()
        orders = [self._make_order(45), self._make_order(60)]
        db = self._db_mock(orders)
        with patch.object(_vcs_mod, "select", MagicMock()), \
             patch.dict("os.environ", {"VOICE_ORDER_TIMEOUT_MINUTES": "30"}):
            result = await svc._handle_order_reminder("S1", db)
        assert result["success"] is True
        assert "2" in result["voice_response"]
        assert result["data"]["timeout_count"] == 2

    @pytest.mark.asyncio
    async def test_timeout_orders_capped_at_five(self):
        svc = _svc()
        orders = [self._make_order(35 + i) for i in range(8)]
        db = self._db_mock(orders)
        with patch.object(_vcs_mod, "select", MagicMock()), \
             patch.dict("os.environ", {"VOICE_ORDER_TIMEOUT_MINUTES": "30"}):
            result = await svc._handle_order_reminder("S1", db)
        assert len(result["data"]["timeout_orders"]) <= 5

    @pytest.mark.asyncio
    async def test_exception_returns_failure(self):
        svc = _svc()
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=RuntimeError("db err"))
        with patch.object(_vcs_mod, "select", MagicMock()):
            result = await svc._handle_order_reminder("S1", db)
        assert result["success"] is False


# ---------------------------------------------------------------------------
# _handle_inventory_query (lines 285-324)
# ---------------------------------------------------------------------------

class TestHandleInventoryQuery:

    @staticmethod
    def _db_mock(items):
        db = AsyncMock()
        res = MagicMock()
        res.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=items)))
        db.execute = AsyncMock(return_value=res)
        return db

    @staticmethod
    def _make_item(name="猪肉", qty=2, min_qty=10):
        item = MagicMock()
        item.id = "I1"
        item.name = name
        item.quantity = qty
        item.min_quantity = min_qty
        return item

    @staticmethod
    def _inv_cls_mock():
        """InventoryItem mock whose column attrs support the < operator."""
        cls = MagicMock()
        qty_col = MagicMock()
        type(qty_col).__lt__ = MagicMock(return_value=MagicMock())
        cls.quantity = qty_col
        cls.min_quantity = MagicMock()
        return cls

    @pytest.mark.asyncio
    async def test_sufficient_stock(self):
        svc = _svc()
        db = self._db_mock([])
        with patch.object(_vcs_mod, "select", MagicMock()), \
             patch.object(_vcs_mod, "InventoryItem", self._inv_cls_mock()):
            result = await svc._handle_inventory_query("S1", "库存查询", db)
        assert result["success"] is True
        assert "充足" in result["voice_response"]
        assert result["data"]["low_stock_count"] == 0

    @pytest.mark.asyncio
    async def test_low_stock_items(self):
        svc = _svc()
        items = [self._make_item("猪肉"), self._make_item("鸡肉"), self._make_item("牛肉")]
        db = self._db_mock(items)
        with patch.object(_vcs_mod, "select", MagicMock()), \
             patch.object(_vcs_mod, "InventoryItem", self._inv_cls_mock()):
            result = await svc._handle_inventory_query("S1", "库存", db)
        assert result["success"] is True
        assert result["data"]["low_stock_count"] == 3
        assert "猪肉" in result["voice_response"]

    @pytest.mark.asyncio
    async def test_exception_returns_failure(self):
        svc = _svc()
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=RuntimeError("db err"))
        with patch.object(_vcs_mod, "select", MagicMock()), \
             patch.object(_vcs_mod, "InventoryItem", self._inv_cls_mock()):
            result = await svc._handle_inventory_query("S1", "查库存", db)
        assert result["success"] is False


# ---------------------------------------------------------------------------
# _handle_revenue_today (lines 332-384)
# ---------------------------------------------------------------------------

class TestHandleRevenueToday:

    @staticmethod
    def _db_mock(today_rev, yesterday_rev):
        db = AsyncMock()
        today_res = MagicMock()
        today_res.scalar = MagicMock(return_value=today_rev)
        yest_res = MagicMock()
        yest_res.scalar = MagicMock(return_value=yesterday_rev)
        db.execute = AsyncMock(side_effect=[today_res, yest_res])
        return db

    @pytest.mark.asyncio
    async def test_growth_vs_yesterday(self):
        svc = _svc()
        db = self._db_mock(1100, 1000)
        with patch.object(_vcs_mod, "select", MagicMock()):
            result = await svc._handle_revenue_today("S1", db)
        assert result["success"] is True
        assert "增长" in result["voice_response"]
        assert result["data"]["today_revenue"] == 1100
        assert result["data"]["growth_rate"] > 0

    @pytest.mark.asyncio
    async def test_decline_vs_yesterday(self):
        svc = _svc()
        db = self._db_mock(800, 1000)
        with patch.object(_vcs_mod, "select", MagicMock()):
            result = await svc._handle_revenue_today("S1", db)
        assert result["success"] is True
        assert "下降" in result["voice_response"]
        assert result["data"]["growth_rate"] < 0

    @pytest.mark.asyncio
    async def test_no_yesterday_data(self):
        svc = _svc()
        db = self._db_mock(800, 0)
        with patch.object(_vcs_mod, "select", MagicMock()):
            result = await svc._handle_revenue_today("S1", db)
        assert result["success"] is True
        assert "昨天无营收" in result["voice_response"]
        assert result["data"]["growth_rate"] is None

    @pytest.mark.asyncio
    async def test_exception_returns_failure(self):
        svc = _svc()
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=RuntimeError("db err"))
        with patch.object(_vcs_mod, "select", MagicMock()):
            result = await svc._handle_revenue_today("S1", db)
        assert result["success"] is False


# ---------------------------------------------------------------------------
# _handle_call_support (lines 397-440)
# ---------------------------------------------------------------------------

class TestHandleCallSupport:

    @staticmethod
    def _db_mock(store):
        db = AsyncMock()
        res = MagicMock()
        res.scalar_one_or_none = MagicMock(return_value=store)
        db.execute = AsyncMock(return_value=res)
        return db

    @pytest.mark.asyncio
    async def test_store_not_found_returns_failure(self):
        svc = _svc()
        db = self._db_mock(None)
        with patch.object(_vcs_mod, "select", MagicMock()):
            result = await svc._handle_call_support("S1", "U1", db)
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_store_found_returns_success(self):
        svc = _svc()
        store = MagicMock()
        store.name = "Test Store"
        db = self._db_mock(store)
        mock_wechat = AsyncMock()
        mock_wechat.send_text_message = AsyncMock()
        mock_wechat_mod = MagicMock()
        mock_wechat_mod.WeChatWorkMessageService = MagicMock(return_value=mock_wechat)
        with patch.object(_vcs_mod, "select", MagicMock()), \
             patch.dict("sys.modules", {
                 "src.services.wechat_work_message_service": mock_wechat_mod,
             }):
            result = await svc._handle_call_support("S1", "U1", db)
        assert result["success"] is True
        assert result["data"]["store_name"] == "Test Store"
        assert result["data"]["requester_id"] == "U1"

    @pytest.mark.asyncio
    async def test_wechat_failure_is_swallowed(self):
        """WeChatWork error inside inner try/except does not prevent success."""
        svc = _svc()
        store = MagicMock()
        store.name = "Store"
        db = self._db_mock(store)
        mock_wechat = AsyncMock()
        mock_wechat.send_text_message = AsyncMock(side_effect=RuntimeError("net err"))
        mock_wechat_mod = MagicMock()
        mock_wechat_mod.WeChatWorkMessageService = MagicMock(return_value=mock_wechat)
        with patch.object(_vcs_mod, "select", MagicMock()), \
             patch.dict("sys.modules", {
                 "src.services.wechat_work_message_service": mock_wechat_mod,
             }):
            result = await svc._handle_call_support("S1", "U1", db)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_db_exception_returns_failure(self):
        svc = _svc()
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=RuntimeError("db err"))
        with patch.object(_vcs_mod, "select", MagicMock()):
            result = await svc._handle_call_support("S1", "U1", db)
        assert result["success"] is False
