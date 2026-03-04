"""
Tests for src/core/clock.py — time abstraction layer.

Covers:
  - IClock.now_local() / today()
  - MockClock: default init (None), naive datetime init, set() with naive, advance()
  - get_clock() / set_clock(None)
  - now_local() / today_local() convenience functions
"""
from datetime import datetime, timezone, date
import pytest

from src.core.clock import (
    IClock,
    MockClock,
    SystemClock,
    get_clock,
    now_local,
    now_utc,
    set_clock,
    today_local,
    utcnow_naive,
)


class TestIClock:
    def test_now_local_returns_aware_datetime(self):
        mc = MockClock(datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc))
        result = mc.now_local()
        assert result.tzinfo is not None

    def test_today_returns_date(self):
        mc = MockClock(datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc))
        result = mc.today()
        assert isinstance(result, date)


class TestMockClock:
    def test_default_init_returns_fixed_datetime(self):
        mc = MockClock()
        assert mc.now() == datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    def test_naive_datetime_gets_utc_tzinfo(self):
        naive = datetime(2024, 3, 1, 12, 0, 0)
        mc = MockClock(fixed_time=naive)
        assert mc.now().tzinfo == timezone.utc

    def test_set_naive_datetime_adds_utc(self):
        mc = MockClock()
        mc.set(datetime(2025, 1, 1, 8, 0, 0))  # naive
        assert mc.now().tzinfo == timezone.utc
        assert mc.now().year == 2025

    def test_set_aware_datetime_preserved(self):
        mc = MockClock()
        target = datetime(2025, 6, 1, 9, 0, 0, tzinfo=timezone.utc)
        mc.set(target)
        assert mc.now() == target

    def test_advance_moves_time_forward(self):
        mc = MockClock(datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc))
        mc.advance(hours=2)
        assert mc.now().hour == 2

    def test_advance_minutes(self):
        mc = MockClock(datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc))
        mc.advance(minutes=30)
        assert mc.now().minute == 30


class TestGetSetClock:
    def test_get_clock_returns_current(self):
        mc = MockClock()
        set_clock(mc)
        try:
            assert get_clock() is mc
        finally:
            set_clock(None)

    def test_set_clock_none_restores_system_clock(self):
        set_clock(MockClock())
        set_clock(None)
        assert isinstance(get_clock(), SystemClock)

    def test_now_utc_returns_datetime(self):
        mc = MockClock(datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc))
        set_clock(mc)
        try:
            result = now_utc()
            assert result == datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        finally:
            set_clock(None)

    def test_now_local_convenience(self):
        mc = MockClock(datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc))
        set_clock(mc)
        try:
            result = now_local()
            assert result.tzinfo is not None
        finally:
            set_clock(None)

    def test_today_local_convenience(self):
        mc = MockClock(datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc))
        set_clock(mc)
        try:
            result = today_local()
            assert isinstance(result, date)
        finally:
            set_clock(None)

    def test_utcnow_naive_no_tzinfo(self):
        mc = MockClock(datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc))
        set_clock(mc)
        try:
            result = utcnow_naive()
            assert result.tzinfo is None
        finally:
            set_clock(None)
