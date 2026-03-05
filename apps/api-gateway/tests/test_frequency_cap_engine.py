"""
FrequencyCapEngine 单元测试

覆盖：
  - 纯函数：make_daily_key / make_weekly_key（格式验证）
  - 纯函数：is_quiet_hours（边界：22h / 9h / 勿扰段内 / 勿扰段外）
  - 纯函数：get_channel_daily_limit / get_channel_weekly_limit
  - 服务：can_send（允许 / 勿扰 / 日上限 / 周上限 / Redis 故障降级）
  - 服务：record_send（计数器递增 + TTL 设置）
  - 服务：get_counts（正常 + Redis 无数据）
"""

import os
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("APP_ENV", "test")

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.frequency_cap_engine import (
    FrequencyCapEngine,
    get_channel_daily_limit,
    get_channel_weekly_limit,
    is_quiet_hours,
    make_daily_key,
    make_weekly_key,
)


# ════════════════════════════════════════════════════════════════════════════════
# 纯函数：key 格式
# ════════════════════════════════════════════════════════════════════════════════

class TestMakeKeys:
    def test_daily_key_format(self):
        key = make_daily_key("P001", "S001", "wxwork")
        parts = key.split(":")
        assert parts[0] == "fc"
        assert parts[1] == "daily"
        assert parts[2] == "wxwork"
        assert parts[3] == "S001"
        assert parts[4] == "P001"
        assert len(parts[5]) == 8  # YYYYMMDD

    def test_weekly_key_format(self):
        key = make_weekly_key("P001", "S001", "wxwork")
        assert key.startswith("fc:weekly:wxwork:S001:P001:")
        assert "W" in key  # ISO week 包含 W

    def test_daily_key_changes_by_person(self):
        k1 = make_daily_key("P001", "S001", "wxwork")
        k2 = make_daily_key("P002", "S001", "wxwork")
        assert k1 != k2

    def test_daily_key_changes_by_channel(self):
        k1 = make_daily_key("P001", "S001", "wxwork")
        k2 = make_daily_key("P001", "S001", "sms")
        assert k1 != k2


# ════════════════════════════════════════════════════════════════════════════════
# 纯函数：is_quiet_hours
# ════════════════════════════════════════════════════════════════════════════════

class TestIsQuietHours:
    def test_midnight_is_quiet(self):
        assert is_quiet_hours(0) is True

    def test_before_9am_is_quiet(self):
        assert is_quiet_hours(8) is True

    def test_9am_not_quiet(self):
        assert is_quiet_hours(9) is False

    def test_midday_not_quiet(self):
        assert is_quiet_hours(12) is False

    def test_21_not_quiet(self):
        assert is_quiet_hours(21) is False

    def test_22_is_quiet(self):
        assert is_quiet_hours(22) is True

    def test_23_is_quiet(self):
        assert is_quiet_hours(23) is True


# ════════════════════════════════════════════════════════════════════════════════
# 纯函数：渠道上限
# ════════════════════════════════════════════════════════════════════════════════

class TestChannelLimits:
    def test_wxwork_daily_limit(self):
        assert get_channel_daily_limit("wxwork") == 1

    def test_wxwork_weekly_limit(self):
        assert get_channel_weekly_limit("wxwork") == 3

    def test_sms_daily_limit_lower(self):
        assert get_channel_daily_limit("sms") <= get_channel_weekly_limit("sms")

    def test_unknown_channel_defaults_to_1(self):
        assert get_channel_daily_limit("unknown") == 1


# ════════════════════════════════════════════════════════════════════════════════
# 服务：can_send
# ════════════════════════════════════════════════════════════════════════════════

class TestCanSend:
    @pytest.mark.asyncio
    async def test_allows_first_send(self):
        redis = AsyncMock()
        redis.get.return_value = None  # 计数器为空
        engine = FrequencyCapEngine(redis)

        with patch("src.services.frequency_cap_engine.is_quiet_hours", return_value=False):
            result = await engine.can_send("P001", "S001", "wxwork")

        assert result is True

    @pytest.mark.asyncio
    async def test_blocks_in_quiet_hours(self):
        engine = FrequencyCapEngine(AsyncMock())

        with patch("src.services.frequency_cap_engine.is_quiet_hours", return_value=True):
            result = await engine.can_send("P001", "S001", "wxwork")

        assert result is False

    @pytest.mark.asyncio
    async def test_blocks_when_daily_limit_reached(self):
        redis = AsyncMock()
        redis.get.side_effect = [b"1", b"1"]  # daily=1 (limit=1), weekly=1
        engine = FrequencyCapEngine(redis)

        with patch("src.services.frequency_cap_engine.is_quiet_hours", return_value=False):
            result = await engine.can_send("P001", "S001", "wxwork")

        assert result is False

    @pytest.mark.asyncio
    async def test_blocks_when_weekly_limit_reached(self):
        redis = AsyncMock()
        redis.get.side_effect = [b"0", b"3"]  # daily=0, weekly=3 (limit=3)
        engine = FrequencyCapEngine(redis)

        with patch("src.services.frequency_cap_engine.is_quiet_hours", return_value=False):
            result = await engine.can_send("P001", "S001", "wxwork")

        assert result is False

    @pytest.mark.asyncio
    async def test_redis_failure_degrades_to_allow(self):
        redis = AsyncMock()
        redis.get.side_effect = Exception("Redis connection failed")
        engine = FrequencyCapEngine(redis)

        with patch("src.services.frequency_cap_engine.is_quiet_hours", return_value=False):
            result = await engine.can_send("P001", "S001", "wxwork")

        assert result is True  # 降级允许，不阻断业务

    @pytest.mark.asyncio
    async def test_no_redis_allows_send(self):
        engine = FrequencyCapEngine(None)

        with patch("src.services.frequency_cap_engine.is_quiet_hours", return_value=False):
            result = await engine.can_send("P001", "S001", "wxwork")

        assert result is True

    @pytest.mark.asyncio
    async def test_can_skip_quiet_hours_check(self):
        engine = FrequencyCapEngine(AsyncMock())
        engine._redis.get.return_value = None

        # 强制勿扰时段，但 respect_quiet_hours=False 时应允许
        with patch("src.services.frequency_cap_engine.is_quiet_hours", return_value=True):
            result = await engine.can_send("P001", "S001", "wxwork", respect_quiet_hours=False)

        assert result is True


# ════════════════════════════════════════════════════════════════════════════════
# 服务：record_send
# ════════════════════════════════════════════════════════════════════════════════

class TestRecordSend:
    @pytest.mark.asyncio
    async def test_increments_daily_and_weekly(self):
        redis = AsyncMock()
        engine = FrequencyCapEngine(redis)

        await engine.record_send("P001", "S001", "wxwork")

        assert redis.incr.call_count == 2   # daily + weekly
        assert redis.expire.call_count == 2

    @pytest.mark.asyncio
    async def test_sets_correct_ttl(self):
        redis = AsyncMock()
        engine = FrequencyCapEngine(redis)

        await engine.record_send("P001", "S001", "wxwork")

        expire_calls = redis.expire.call_args_list
        ttls = {call.args[1] for call in expire_calls}
        assert 86400  in ttls  # day TTL
        assert 604800 in ttls  # week TTL

    @pytest.mark.asyncio
    async def test_no_redis_is_noop(self):
        engine = FrequencyCapEngine(None)
        # 不应抛出异常
        await engine.record_send("P001", "S001", "wxwork")

    @pytest.mark.asyncio
    async def test_redis_error_is_logged_not_raised(self):
        redis = AsyncMock()
        redis.incr.side_effect = Exception("Redis down")
        engine = FrequencyCapEngine(redis)
        # 不应抛出异常
        await engine.record_send("P001", "S001", "wxwork")


# ════════════════════════════════════════════════════════════════════════════════
# 服务：get_counts
# ════════════════════════════════════════════════════════════════════════════════

class TestGetCounts:
    @pytest.mark.asyncio
    async def test_returns_counts_from_redis(self):
        redis = AsyncMock()
        redis.get.side_effect = [b"1", b"2"]  # daily=1, weekly=2
        engine = FrequencyCapEngine(redis)

        counts = await engine.get_counts("P001", "S001", "wxwork")

        assert counts["daily"]  == 1
        assert counts["weekly"] == 2
        assert counts["daily_limit"]  == get_channel_daily_limit("wxwork")
        assert counts["weekly_limit"] == get_channel_weekly_limit("wxwork")

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_redis(self):
        engine = FrequencyCapEngine(None)

        counts = await engine.get_counts("P001", "S001", "wxwork")

        assert counts["daily"]  == 0
        assert counts["weekly"] == 0

    @pytest.mark.asyncio
    async def test_returns_zero_when_redis_has_no_keys(self):
        redis = AsyncMock()
        redis.get.return_value = None
        engine = FrequencyCapEngine(redis)

        counts = await engine.get_counts("P001", "S001", "miniapp")

        assert counts["daily"]  == 0
        assert counts["weekly"] == 0
        assert counts["daily_limit"] == get_channel_daily_limit("miniapp")
