"""
Tests for ARCH-003/FEAT-002/INFRA-002 Celery tasks:
  - update_store_memory
  - realtime_anomaly_check
  - push_daily_forecast
  - retry_failed_wechat_messages

All tasks use asyncio.run(_run()) internally.  We call them synchronously
with a mock `self` and intercept lazy imports via patch.dict(sys.modules).
"""
import asyncio
import sys
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

# ---- Block src.core.celery_app BEFORE importing celery_tasks ----
# celery_tasks.py does `from .celery_app import celery_app` at module level.
# We provide a fake that preserves the original decorated functions.
if "src.core.celery_app" not in sys.modules:
    class _FakeCelery:
        def task(self, *args, **kwargs):
            """Decorator factory that returns the original function unchanged."""
            def wrap(fn):
                fn.delay = MagicMock()
                fn.apply_async = MagicMock()
                return fn
            # @celery_app.task(bind=True, ...)  → args=(), kwargs={...}
            # @celery_app.task                  → args=(fn,), kwargs={}
            return wrap(args[0]) if (len(args) == 1 and callable(args[0])) else wrap

        def autodiscover_tasks(self, *a, **kw):
            pass

    _fake_celery_mod = MagicMock()
    _fake_celery_mod.celery_app = _FakeCelery()
    sys.modules["src.core.celery_app"] = _fake_celery_mod

# Ensure src.core.config is available (needed by wechat_service transitive import)
if "src.core.config" not in sys.modules:
    _cfg_mod = MagicMock()
    _cfg_mod.settings = MagicMock()
    sys.modules["src.core.config"] = _cfg_mod

from src.core.celery_tasks import (  # noqa: E402 — must come after sys.modules setup
    update_store_memory,
    realtime_anomaly_check,
    push_daily_forecast,
    retry_failed_wechat_messages,
)


# ---------------------------------------------------------------------------
# Event-loop guard
# ---------------------------------------------------------------------------
# Celery tasks call asyncio.run() internally, which calls set_event_loop(None)
# after completing.  If any session-scoped event loop is already active (because
# async tests from earlier test modules ran first), that clears it and breaks all
# subsequent async tests.  This autouse fixture restores the loop after each call.

@pytest.fixture(autouse=True)
def _restore_event_loop(event_loop):
    """After sync tests that call asyncio.run(), restore the session event loop."""
    yield
    asyncio.set_event_loop(event_loop)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _async_ctx(return_value):
    """Build a MagicMock that works as `async with ... as return_value:`."""
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=return_value)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return ctx


def _mock_self():
    """Bound Celery task `self`.  retry() raises so unexpected calls are visible."""
    m = MagicMock()
    m.retry = MagicMock(side_effect=RuntimeError("celery_retry"))
    return m


# ===========================================================================
# ARCH-003  update_store_memory
# ===========================================================================

class TestUpdateStoreMemory:
    """
    Three paths:
    1. Single store_id  → calls refresh_store_memory once with correct args
    2. No store_id      → iterates DB rows and calls refresh N times
    3. Per-store error  → swallowed by inner try/except, task does not raise
    """

    @staticmethod
    def _build_modules(service, result_rows=None):
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            return_value=MagicMock(all=MagicMock(return_value=(result_rows or [])))
        )
        mock_db_mod = MagicMock()
        mock_db_mod.get_db_session = MagicMock(return_value=_async_ctx(mock_db))

        mock_mem_mod = MagicMock()
        mock_mem_mod.StoreMemoryService = MagicMock(return_value=service)

        return {
            "src.core.database": mock_db_mod,
            "src.services.store_memory_service": mock_mem_mod,
            "src.models.store": MagicMock(),
            "sqlalchemy": MagicMock(),
        }

    def test_single_store_calls_refresh_with_correct_args(self):
        """store_id provided → refresh_store_memory called once with correct args"""
        service = AsyncMock()
        modules = self._build_modules(service)

        with patch.dict("sys.modules", modules):
            update_store_memory(_mock_self(), store_id="S1", brand_id="B1")

        service.refresh_store_memory.assert_awaited_once_with(
            store_id="S1", brand_id="B1"
        )

    def test_all_stores_calls_refresh_for_each_row(self):
        """store_id=None → iterates all DB rows, calls refresh for each"""
        service = AsyncMock()
        row_a = MagicMock(); row_a.id = "SA"; row_a.brand_id = "BA"
        row_b = MagicMock(); row_b.id = "SB"; row_b.brand_id = None
        modules = self._build_modules(service, result_rows=[row_a, row_b])

        with patch.dict("sys.modules", modules):
            update_store_memory(_mock_self(), store_id=None)

        assert service.refresh_store_memory.await_count == 2

    def test_per_store_failure_swallowed_task_does_not_raise(self):
        """Exception in one store's refresh is caught; task completes normally"""
        service = AsyncMock()
        service.refresh_store_memory = AsyncMock(side_effect=RuntimeError("db down"))
        row_a = MagicMock(); row_a.id = "SA"; row_a.brand_id = None
        modules = self._build_modules(service, result_rows=[row_a])

        m_self = _mock_self()
        with patch.dict("sys.modules", modules):
            update_store_memory(m_self, store_id=None)  # must not raise

        m_self.retry.assert_not_called()


# ===========================================================================
# ARCH-003  realtime_anomaly_check
# ===========================================================================

class TestRealtimeAnomalyCheck:
    """
    1. Happy path  → detect_anomaly called with correct store_id + event
    2. Exception   → self.retry() is called (task retries on failure)
    """

    @staticmethod
    def _build_modules(service):
        mock_db = AsyncMock()
        mock_db_mod = MagicMock()
        mock_db_mod.get_db_session = MagicMock(return_value=_async_ctx(mock_db))

        mock_mem_mod = MagicMock()
        mock_mem_mod.StoreMemoryService = MagicMock(return_value=service)

        return {
            "src.core.database": mock_db_mod,
            "src.services.store_memory_service": mock_mem_mod,
        }

    def test_calls_detect_anomaly_with_correct_args(self):
        """Service.detect_anomaly is awaited with the given store_id and event dict"""
        service = AsyncMock()
        event = {"action_type": "discount_apply", "amount": 5000}

        with patch.dict("sys.modules", self._build_modules(service)):
            realtime_anomaly_check(_mock_self(), store_id="S1", event=event)

        service.detect_anomaly.assert_awaited_once_with(store_id="S1", event=event)

    def test_exception_triggers_retry(self):
        """detect_anomaly failure → self.retry() raised; task schedules retry"""
        service = AsyncMock()
        service.detect_anomaly = AsyncMock(side_effect=RuntimeError("db lost"))

        m_self = _mock_self()
        with pytest.raises(RuntimeError, match="celery_retry"):
            with patch.dict("sys.modules", self._build_modules(service)):
                realtime_anomaly_check(m_self, store_id="S1", event={})

        m_self.retry.assert_called_once()


# ===========================================================================
# FEAT-002  push_daily_forecast
# ===========================================================================

class TestPushDailyForecast:
    """
    1. Single store  → forecaster.predict + wechat.send_templated_message called
    2. Low-confidence note included in wechat message data
    3. All stores    → DB queried, predict + send called N times
    4. Per-store error is swallowed; task does not raise
    """

    @staticmethod
    def _build_modules(forecaster, wechat, result_rows=None):
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            return_value=MagicMock(all=MagicMock(return_value=(result_rows or [])))
        )
        mock_db_mod = MagicMock()
        mock_db_mod.get_db_session = MagicMock(return_value=_async_ctx(mock_db))

        mock_demand_mod = MagicMock()
        mock_demand_mod.DemandForecaster = MagicMock(return_value=forecaster)

        mock_wechat_mod = MagicMock()
        mock_wechat_mod.wechat_service = wechat

        return {
            "src.core.database": mock_db_mod,
            "src.services.demand_forecaster": mock_demand_mod,
            "src.services.wechat_service": mock_wechat_mod,
            "src.models.store": MagicMock(),
            "sqlalchemy": MagicMock(),
        }

    @staticmethod
    def _make_forecast(note=None, confidence="medium"):
        r = MagicMock()
        r.target_date = date.today() + timedelta(days=1)
        r.estimated_revenue = 4000.0
        r.confidence = confidence
        r.basis = "statistical"
        r.note = note
        r.items = []
        return r

    def test_single_store_calls_predict_and_wechat(self):
        """Single store: predict called with store_id, wechat called with daily_forecast template"""
        forecaster = AsyncMock()
        forecaster.predict = AsyncMock(return_value=self._make_forecast())
        wechat = AsyncMock()
        wechat.send_templated_message = AsyncMock(return_value={"status": "sent"})

        with patch.dict("sys.modules", self._build_modules(forecaster, wechat)):
            push_daily_forecast(_mock_self(), store_id="S1")

        forecaster.predict.assert_awaited_once()
        assert forecaster.predict.call_args[1]["store_id"] == "S1"

        wechat.send_templated_message.assert_awaited_once()
        call_kw = wechat.send_templated_message.call_args[1]
        assert call_kw["template"] == "daily_forecast"
        assert call_kw["to_user_id"] == "store_S1"

    def test_low_confidence_note_included_in_message_data(self):
        """ForecastResult.note and confidence are forwarded to wechat message data"""
        forecaster = AsyncMock()
        forecaster.predict = AsyncMock(
            return_value=self._make_forecast(note="数据积累中", confidence="low")
        )
        wechat = AsyncMock()
        wechat.send_templated_message = AsyncMock(return_value={"status": "sent"})

        with patch.dict("sys.modules", self._build_modules(forecaster, wechat)):
            push_daily_forecast(_mock_self(), store_id="S1")

        data_arg = wechat.send_templated_message.call_args[1]["data"]
        assert data_arg["note"] == "数据积累中"
        assert data_arg["confidence"] == "low"

    def test_all_stores_iterates_db_and_calls_predict_per_store(self):
        """store_id=None → queries DB for all store IDs, predict+send called once per store"""
        row1 = MagicMock(); row1.id = "SA"
        row2 = MagicMock(); row2.id = "SB"

        forecaster = AsyncMock()
        forecaster.predict = AsyncMock(return_value=self._make_forecast())
        wechat = AsyncMock()
        wechat.send_templated_message = AsyncMock(return_value={"status": "sent"})

        with patch.dict("sys.modules", self._build_modules(forecaster, wechat, [row1, row2])):
            push_daily_forecast(_mock_self(), store_id=None)

        assert forecaster.predict.await_count == 2
        assert wechat.send_templated_message.await_count == 2

    def test_per_store_failure_swallowed_task_does_not_raise(self):
        """forecaster.predict raising is caught per-store; task completes normally"""
        forecaster = AsyncMock()
        forecaster.predict = AsyncMock(side_effect=RuntimeError("forecast failed"))
        wechat = AsyncMock()

        m_self = _mock_self()
        with patch.dict("sys.modules", self._build_modules(forecaster, wechat)):
            push_daily_forecast(m_self, store_id="S1")  # must not raise

        m_self.retry.assert_not_called()


# ===========================================================================
# INFRA-002  retry_failed_wechat_messages
# ===========================================================================

class TestRetryFailedWechatMessages:
    """
    1. Happy path  → wechat_service.retry_failed_messages(max_retries=3, batch_size=10)
    2. Exception   → logged as warning; self.retry() NOT called (different from other tasks)
    """

    @staticmethod
    def _build_modules(wechat):
        mock_mod = MagicMock()
        mock_mod.wechat_service = wechat
        return {"src.services.wechat_service": mock_mod}

    def test_calls_retry_failed_messages_with_correct_params(self):
        """retry_failed_messages is called with max_retries=3 and batch_size=10"""
        wechat = AsyncMock()
        wechat.retry_failed_messages = AsyncMock(return_value={"retried": 2, "succeeded": 2})

        with patch.dict("sys.modules", self._build_modules(wechat)):
            retry_failed_wechat_messages(_mock_self())

        wechat.retry_failed_messages.assert_awaited_once_with(max_retries=3, batch_size=10)

    def test_exception_is_logged_not_retried(self):
        """Exception from wechat service is caught with logger.warning; retry NOT called"""
        wechat = AsyncMock()
        wechat.retry_failed_messages = AsyncMock(side_effect=RuntimeError("net error"))

        m_self = _mock_self()
        # Must not raise — exception is swallowed by `except Exception: logger.warning(...)`
        with patch.dict("sys.modules", self._build_modules(wechat)):
            retry_failed_wechat_messages(m_self)

        # Unlike other tasks, retry_failed_wechat_messages does NOT call self.retry()
        m_self.retry.assert_not_called()
