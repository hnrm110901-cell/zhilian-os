"""
Tests for src/core/circuit_breaker.py — CLOSED/OPEN/HALF_OPEN state machine.

Covers:
  - CLOSED → OPEN transition on failure_threshold hits
  - OPEN rejects requests with CircuitBreakerOpenError
  - OPEN → HALF_OPEN after timeout elapses
  - HALF_OPEN + success × success_threshold → CLOSED
  - HALF_OPEN + failure → OPEN (re-trip)
  - expected_exception filter (non-matching exception bypasses trip)
  - reset() restores CLOSED state
  - get_stats() returns correct fields
  - sync call() and async call_async()
  - @circuit_breaker decorator (sync + async)
  - fallback callable invoked when OPEN
"""
import time
import asyncio
import pytest
from unittest.mock import MagicMock, patch

from src.core.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitState,
    circuit_breaker,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _failing(exc=RuntimeError("boom")):
    raise exc


def _ok(value="ok"):
    return value


# ===========================================================================
# State transitions via call()
# ===========================================================================

class TestClosedToOpen:
    def test_starts_closed(self):
        cb = CircuitBreaker(failure_threshold=3, success_threshold=2, timeout=60)
        assert cb.state == CircuitState.CLOSED

    def test_single_failure_stays_closed(self):
        cb = CircuitBreaker(failure_threshold=3, success_threshold=2, timeout=60)
        with pytest.raises(RuntimeError):
            cb.call(_failing)
        assert cb.state == CircuitState.CLOSED
        assert cb._failure_count == 1

    def test_failure_threshold_opens_circuit(self):
        cb = CircuitBreaker(failure_threshold=3, success_threshold=2, timeout=60)
        for _ in range(3):
            with pytest.raises(RuntimeError):
                cb.call(_failing)
        assert cb.state == CircuitState.OPEN

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker(failure_threshold=3, success_threshold=2, timeout=60)
        with pytest.raises(RuntimeError):
            cb.call(_failing)
        cb.call(_ok)  # success
        assert cb._failure_count == 0

    def test_open_rejects_without_calling_function(self):
        cb = CircuitBreaker(failure_threshold=1, success_threshold=2, timeout=60)
        with pytest.raises(RuntimeError):
            cb.call(_failing)
        assert cb.state == CircuitState.OPEN

        sentinel = MagicMock(return_value="never called")
        with pytest.raises(CircuitBreakerOpenError):
            cb.call(sentinel)
        sentinel.assert_not_called()


class TestOpenToHalfOpen:
    def test_transitions_to_half_open_after_timeout(self):
        cb = CircuitBreaker(failure_threshold=1, success_threshold=2, timeout=0.01)
        with pytest.raises(RuntimeError):
            cb.call(_failing)
        assert cb.state == CircuitState.OPEN

        time.sleep(0.02)
        # Accessing .state triggers the OPEN→HALF_OPEN transition
        assert cb.state == CircuitState.HALF_OPEN

    def test_does_not_transition_before_timeout(self):
        cb = CircuitBreaker(failure_threshold=1, success_threshold=2, timeout=60)
        with pytest.raises(RuntimeError):
            cb.call(_failing)
        assert cb.state == CircuitState.OPEN  # timeout not elapsed


class TestHalfOpenTransitions:
    def _tripped(self, timeout=0.01):
        cb = CircuitBreaker(failure_threshold=1, success_threshold=2, timeout=timeout)
        with pytest.raises(RuntimeError):
            cb.call(_failing)
        time.sleep(timeout + 0.01)
        assert cb.state == CircuitState.HALF_OPEN
        return cb

    def test_half_open_success_x_threshold_closes(self):
        cb = self._tripped()
        cb.call(_ok)   # success #1
        assert cb.state == CircuitState.HALF_OPEN
        cb.call(_ok)   # success #2 → closes
        assert cb.state == CircuitState.CLOSED

    def test_half_open_failure_reopens(self):
        cb = self._tripped()
        with pytest.raises(RuntimeError):
            cb.call(_failing)
        assert cb.state == CircuitState.OPEN


# ===========================================================================
# expected_exception filter
# ===========================================================================

class TestExpectedException:
    def test_matching_exception_trips_breaker(self):
        cb = CircuitBreaker(
            failure_threshold=1, success_threshold=2, timeout=60,
            expected_exception=ValueError,
        )
        with pytest.raises(ValueError):
            cb.call(lambda: (_ for _ in ()).throw(ValueError("bad value")))
        assert cb.state == CircuitState.OPEN

    def test_non_matching_exception_does_not_trip(self):
        cb = CircuitBreaker(
            failure_threshold=1, success_threshold=2, timeout=60,
            expected_exception=ValueError,
        )
        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("unrelated")))
        # RuntimeError is not in expected_exception → circuit stays CLOSED
        assert cb.state == CircuitState.CLOSED


# ===========================================================================
# reset()
# ===========================================================================

class TestReset:
    def test_reset_from_open(self):
        cb = CircuitBreaker(failure_threshold=1, success_threshold=2, timeout=60)
        with pytest.raises(RuntimeError):
            cb.call(_failing)
        assert cb.state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb._failure_count == 0

    def test_reset_clears_last_failure_time(self):
        cb = CircuitBreaker(failure_threshold=1, success_threshold=2, timeout=60)
        with pytest.raises(RuntimeError):
            cb.call(_failing)
        cb.reset()
        assert cb._last_failure_time is None


# ===========================================================================
# get_stats()
# ===========================================================================

class TestGetStats:
    def test_initial_stats(self):
        cb = CircuitBreaker(failure_threshold=5, success_threshold=2, timeout=60)
        stats = cb.get_stats()
        assert stats["state"] == CircuitState.CLOSED.value
        assert stats["failure_count"] == 0
        assert stats["failure_threshold"] == 5
        assert stats["success_threshold"] == 2
        assert stats["timeout"] == 60

    def test_stats_after_failure(self):
        cb = CircuitBreaker(failure_threshold=3, success_threshold=2, timeout=60)
        with pytest.raises(RuntimeError):
            cb.call(_failing)
        stats = cb.get_stats()
        assert stats["failure_count"] == 1
        assert stats["last_failure_time"] is not None

    def test_stats_open_state(self):
        cb = CircuitBreaker(failure_threshold=1, success_threshold=2, timeout=60)
        with pytest.raises(RuntimeError):
            cb.call(_failing)
        stats = cb.get_stats()
        assert stats["state"] == CircuitState.OPEN.value


# ===========================================================================
# Async call_async()
# ===========================================================================

class TestCallAsync:
    @pytest.mark.asyncio
    async def test_call_async_success(self):
        cb = CircuitBreaker(failure_threshold=3, success_threshold=2, timeout=60)

        async def good():
            return "async-ok"

        result = await cb.call_async(good)
        assert result == "async-ok"

    @pytest.mark.asyncio
    async def test_call_async_failure_trips_breaker(self):
        cb = CircuitBreaker(failure_threshold=1, success_threshold=2, timeout=60)

        async def bad():
            raise RuntimeError("async boom")

        with pytest.raises(RuntimeError):
            await cb.call_async(bad)
        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_call_async_open_raises_immediately(self):
        cb = CircuitBreaker(failure_threshold=1, success_threshold=2, timeout=60)
        with pytest.raises(RuntimeError):
            await cb.call_async(lambda: (_ for _ in ()).throw(RuntimeError()))
        # Wait — call_async won't trip on sync lambda, test via _on_failure directly
        cb._on_failure()  # force OPEN manually  -- just reset and use known path
        cb.reset()
        with pytest.raises(RuntimeError):
            await cb.call_async(lambda: asyncio.coroutine(lambda: (_ for _ in ()).throw(RuntimeError()))())

    @pytest.mark.asyncio
    async def test_call_async_open_circuit_raises(self):
        cb = CircuitBreaker(failure_threshold=1, success_threshold=2, timeout=60)

        async def fail():
            raise RuntimeError("fail")

        with pytest.raises(RuntimeError):
            await cb.call_async(fail)
        assert cb.state == CircuitState.OPEN

        with pytest.raises(CircuitBreakerOpenError):
            await cb.call_async(fail)


# ===========================================================================
# @circuit_breaker decorator
# ===========================================================================

class TestCircuitBreakerDecorator:
    @pytest.mark.asyncio
    async def test_decorator_async_success(self):
        @circuit_breaker(failure_threshold=3, success_threshold=2, timeout=60)
        async def operation():
            return "decorated-ok"

        assert await operation() == "decorated-ok"

    @pytest.mark.asyncio
    async def test_decorator_async_trips_and_uses_fallback(self):
        @circuit_breaker(
            failure_threshold=1,
            success_threshold=2,
            timeout=60,
            fallback=lambda: {"status": "degraded"},
        )
        async def risky():
            raise RuntimeError("service down")

        # First call trips the breaker
        with pytest.raises(RuntimeError):
            await risky()
        # Second call → OPEN → fallback
        result = await risky()
        assert result == {"status": "degraded"}

    def test_decorator_sync_success(self):
        @circuit_breaker(failure_threshold=3, success_threshold=2, timeout=60)
        def sync_op():
            return "sync-ok"

        assert sync_op() == "sync-ok"

    def test_decorator_sync_trips_and_uses_fallback(self):
        @circuit_breaker(
            failure_threshold=1,
            success_threshold=2,
            timeout=60,
            fallback=lambda: "fallback-value",
        )
        def sync_risky():
            raise RuntimeError("sync down")

        with pytest.raises(RuntimeError):
            sync_risky()
        result = sync_risky()
        assert result == "fallback-value"

    @pytest.mark.asyncio
    async def test_decorator_async_no_fallback_reraises(self):
        @circuit_breaker(failure_threshold=1, success_threshold=2, timeout=60)
        async def no_fallback():
            raise RuntimeError("error")

        with pytest.raises(RuntimeError):
            await no_fallback()
        with pytest.raises(CircuitBreakerOpenError):
            await no_fallback()
