"""
Tests for src/services/redis_cache_service.py — Redis 缓存服务.

No real Redis needed: the Redis client is fully mocked.
src.core.config is pre-stubbed so Settings() is never instantiated.

Covers:
  - initialize: direct mode, sentinel mode, already-initialized skip,
                AuthenticationError, ConnectionError, generic Exception
  - close: with and without an active connection
  - get: cache hit (plain str), cache hit (JSON), cache miss (None),
         ConnectionError fallback, generic Exception fallback
  - set: string value, dict (JSON), non-str, expire=int, expire=timedelta,
         no expire, ConnectionError fallback, Exception fallback
  - delete: success, Exception fallback
  - exists: True, False, Exception fallback
  - expire: success, Exception fallback
  - ttl: returns seconds, Exception returns -2
  - incr: default amount, custom amount, Exception returns None
  - decr: default amount, custom amount, Exception returns None
  - hget: JSON value, plain str, None, Exception
  - hset: dict value, non-str, str value, Exception
  - hgetall: JSON values, mixed JSON/str, Exception
  - hdel: success, Exception
  - lpush: dict + str values, Exception
  - rpush: dict + str values, Exception
  - lrange: JSON items, plain str items, Exception
  - clear_pattern: keys found, no keys, Exception
  - global singleton: redis_cache is RedisCacheService instance
"""
import sys
import json
import pytest
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

# Pre-stub Settings validation before importing the module.
sys.modules.setdefault("src.core.config", MagicMock(settings=MagicMock(
    REDIS_URL="redis://localhost:6379/0",
    REDIS_SENTINEL_HOSTS="",
    REDIS_SENTINEL_PASSWORD="",
    REDIS_SENTINEL_MASTER="mymaster",
    REDIS_SENTINEL_DB=0,
)))

from src.services.redis_cache_service import RedisCacheService, redis_cache


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _svc(initialized: bool = True) -> RedisCacheService:
    """Build a RedisCacheService with a pre-mocked _redis client."""
    svc = RedisCacheService()
    svc._initialized = initialized
    if initialized:
        svc._redis = AsyncMock()
    return svc


# ===========================================================================
# initialize
# ===========================================================================

_DIRECT_SETTINGS = MagicMock(
    REDIS_URL="redis://localhost:6379/0",
    REDIS_SENTINEL_HOSTS="",      # empty → direct mode
    REDIS_SENTINEL_PASSWORD="",
    REDIS_SENTINEL_MASTER="mymaster",
    REDIS_SENTINEL_DB=0,
)


class TestInitialize:
    @pytest.mark.asyncio
    async def test_already_initialized_skips(self):
        svc = _svc(initialized=True)
        original_redis = svc._redis
        await svc.initialize()
        assert svc._redis is original_redis  # unchanged

    @pytest.mark.asyncio
    async def test_direct_mode_sets_initialized(self):
        svc = _svc(initialized=False)
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock()
        import src.services.redis_cache_service as mod
        with patch.object(mod, "settings", _DIRECT_SETTINGS), \
             patch("src.services.redis_cache_service.redis") as mock_redis_mod:
            mock_redis_mod.from_url = AsyncMock(return_value=mock_client)
            mock_redis_mod.AuthenticationError = Exception
            mock_redis_mod.ConnectionError = Exception
            await svc.initialize()
        assert svc._initialized is True

    @pytest.mark.asyncio
    async def test_sentinel_mode_uses_sentinel(self):
        svc = _svc(initialized=False)
        sentinel_settings = MagicMock(
            REDIS_SENTINEL_HOSTS="sentinel1:26379,sentinel2:26379",
            REDIS_SENTINEL_PASSWORD="",
            REDIS_SENTINEL_MASTER="mymaster",
            REDIS_SENTINEL_DB=0,
        )
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock()
        mock_sentinel = MagicMock()
        mock_sentinel.master_for = MagicMock(return_value=mock_client)

        import src.services.redis_cache_service as mod
        import types
        sentinel_submod = types.ModuleType("redis.asyncio.sentinel")
        sentinel_submod.Sentinel = MagicMock(return_value=mock_sentinel)

        with patch.object(mod, "settings", sentinel_settings), \
             patch("src.services.redis_cache_service.redis") as mock_redis_mod, \
             patch.dict("sys.modules", {"redis.asyncio.sentinel": sentinel_submod}):
            mock_redis_mod.AuthenticationError = Exception
            mock_redis_mod.ConnectionError = Exception
            await svc.initialize()

        assert svc._initialized is True

    @pytest.mark.asyncio
    async def test_authentication_error_raises(self):
        svc = _svc(initialized=False)
        class FakeAuthError(Exception):
            pass
        import src.services.redis_cache_service as mod
        with patch.object(mod, "settings", _DIRECT_SETTINGS), \
             patch("src.services.redis_cache_service.redis") as mock_redis_mod:
            mock_redis_mod.from_url = AsyncMock(side_effect=FakeAuthError("bad auth"))
            mock_redis_mod.AuthenticationError = FakeAuthError
            mock_redis_mod.ConnectionError = ConnectionError
            with pytest.raises(FakeAuthError):
                await svc.initialize()
        assert svc._initialized is False

    @pytest.mark.asyncio
    async def test_connection_error_raises(self):
        svc = _svc(initialized=False)
        class FakeConnError(Exception):
            pass
        import src.services.redis_cache_service as mod
        with patch.object(mod, "settings", _DIRECT_SETTINGS), \
             patch("src.services.redis_cache_service.redis") as mock_redis_mod:
            mock_redis_mod.from_url = AsyncMock(side_effect=FakeConnError("no server"))
            mock_redis_mod.AuthenticationError = Exception
            mock_redis_mod.ConnectionError = FakeConnError
            with pytest.raises(FakeConnError):
                await svc.initialize()

    @pytest.mark.asyncio
    async def test_generic_exception_raises(self):
        svc = _svc(initialized=False)
        import src.services.redis_cache_service as mod
        with patch.object(mod, "settings", _DIRECT_SETTINGS), \
             patch("src.services.redis_cache_service.redis") as mock_redis_mod:
            mock_redis_mod.from_url = AsyncMock(side_effect=RuntimeError("oops"))
            mock_redis_mod.AuthenticationError = OSError
            mock_redis_mod.ConnectionError = OSError
            with pytest.raises(RuntimeError):
                await svc.initialize()


# ===========================================================================
# close
# ===========================================================================

class TestClose:
    @pytest.mark.asyncio
    async def test_close_with_connection(self):
        svc = _svc()
        await svc.close()
        svc._redis.close.assert_awaited_once()
        assert svc._initialized is False

    @pytest.mark.asyncio
    async def test_close_without_connection_is_noop(self):
        svc = _svc(initialized=False)
        svc._redis = None
        await svc.close()  # must not raise


# ===========================================================================
# get
# ===========================================================================

class TestGet:
    @pytest.mark.asyncio
    async def test_cache_miss_returns_none(self):
        svc = _svc()
        svc._redis.get = AsyncMock(return_value=None)
        result = await svc.get("missing_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_plain_string_value_returned(self):
        svc = _svc()
        svc._redis.get = AsyncMock(return_value="hello")
        result = await svc.get("k")
        assert result == "hello"

    @pytest.mark.asyncio
    async def test_json_string_deserialized(self):
        svc = _svc()
        svc._redis.get = AsyncMock(return_value=json.dumps({"a": 1}))
        result = await svc.get("k")
        assert result == {"a": 1}

    @pytest.mark.asyncio
    async def test_connection_error_returns_none(self):
        svc = _svc()
        import redis.asyncio as redis_mod
        svc._redis.get = AsyncMock(side_effect=redis_mod.ConnectionError("lost"))
        result = await svc.get("k")
        assert result is None

    @pytest.mark.asyncio
    async def test_generic_exception_returns_none(self):
        svc = _svc()
        svc._redis.get = AsyncMock(side_effect=RuntimeError("bad"))
        result = await svc.get("k")
        assert result is None

    @pytest.mark.asyncio
    async def test_not_initialized_triggers_initialize(self):
        svc = _svc(initialized=False)
        svc.initialize = AsyncMock(side_effect=lambda: setattr(svc, "_initialized", True) or setattr(svc, "_redis", AsyncMock(get=AsyncMock(return_value=None))))
        result = await svc.get("k")
        svc.initialize.assert_awaited_once()


# ===========================================================================
# set
# ===========================================================================

class TestSet:
    @pytest.mark.asyncio
    async def test_string_value_without_expire(self):
        svc = _svc()
        svc._redis.set = AsyncMock()
        result = await svc.set("k", "v")
        assert result is True
        svc._redis.set.assert_awaited_once_with("k", "v")

    @pytest.mark.asyncio
    async def test_dict_value_json_serialized(self):
        svc = _svc()
        svc._redis.set = AsyncMock()
        await svc.set("k", {"x": 1})
        call_args = svc._redis.set.call_args[0]
        assert json.loads(call_args[1]) == {"x": 1}

    @pytest.mark.asyncio
    async def test_non_str_value_converted(self):
        svc = _svc()
        svc._redis.set = AsyncMock()
        await svc.set("k", 42)
        call_args = svc._redis.set.call_args[0]
        assert call_args[1] == "42"

    @pytest.mark.asyncio
    async def test_int_expire_uses_setex(self):
        svc = _svc()
        svc._redis.setex = AsyncMock()
        result = await svc.set("k", "v", expire=60)
        assert result is True
        svc._redis.setex.assert_awaited_once_with("k", 60, "v")

    @pytest.mark.asyncio
    async def test_timedelta_expire_converted_to_seconds(self):
        svc = _svc()
        svc._redis.setex = AsyncMock()
        await svc.set("k", "v", expire=timedelta(minutes=5))
        svc._redis.setex.assert_awaited_once_with("k", 300, "v")

    @pytest.mark.asyncio
    async def test_connection_error_returns_false(self):
        svc = _svc()
        import redis.asyncio as redis_mod
        svc._redis.set = AsyncMock(side_effect=redis_mod.ConnectionError("lost"))
        result = await svc.set("k", "v")
        assert result is False

    @pytest.mark.asyncio
    async def test_generic_exception_returns_false(self):
        svc = _svc()
        svc._redis.set = AsyncMock(side_effect=RuntimeError("fail"))
        result = await svc.set("k", "v")
        assert result is False


# ===========================================================================
# delete
# ===========================================================================

class TestDelete:
    @pytest.mark.asyncio
    async def test_delete_returns_true(self):
        svc = _svc()
        svc._redis.delete = AsyncMock()
        result = await svc.delete("k")
        assert result is True
        svc._redis.delete.assert_awaited_once_with("k")

    @pytest.mark.asyncio
    async def test_exception_returns_false(self):
        svc = _svc()
        svc._redis.delete = AsyncMock(side_effect=RuntimeError("err"))
        result = await svc.delete("k")
        assert result is False


# ===========================================================================
# exists
# ===========================================================================

class TestExists:
    @pytest.mark.asyncio
    async def test_key_present_returns_true(self):
        svc = _svc()
        svc._redis.exists = AsyncMock(return_value=1)
        assert await svc.exists("k") is True

    @pytest.mark.asyncio
    async def test_key_absent_returns_false(self):
        svc = _svc()
        svc._redis.exists = AsyncMock(return_value=0)
        assert await svc.exists("k") is False

    @pytest.mark.asyncio
    async def test_exception_returns_false(self):
        svc = _svc()
        svc._redis.exists = AsyncMock(side_effect=RuntimeError("err"))
        assert await svc.exists("k") is False


# ===========================================================================
# expire
# ===========================================================================

class TestExpire:
    @pytest.mark.asyncio
    async def test_expire_returns_redis_result(self):
        svc = _svc()
        svc._redis.expire = AsyncMock(return_value=True)
        assert await svc.expire("k", 300) is True

    @pytest.mark.asyncio
    async def test_exception_returns_false(self):
        svc = _svc()
        svc._redis.expire = AsyncMock(side_effect=RuntimeError("err"))
        assert await svc.expire("k", 60) is False


# ===========================================================================
# ttl
# ===========================================================================

class TestTTL:
    @pytest.mark.asyncio
    async def test_returns_remaining_seconds(self):
        svc = _svc()
        svc._redis.ttl = AsyncMock(return_value=120)
        assert await svc.ttl("k") == 120

    @pytest.mark.asyncio
    async def test_no_expiry_returns_minus_one(self):
        svc = _svc()
        svc._redis.ttl = AsyncMock(return_value=-1)
        assert await svc.ttl("k") == -1

    @pytest.mark.asyncio
    async def test_exception_returns_minus_two(self):
        svc = _svc()
        svc._redis.ttl = AsyncMock(side_effect=RuntimeError("err"))
        assert await svc.ttl("k") == -2


# ===========================================================================
# incr / decr
# ===========================================================================

class TestIncrDecr:
    @pytest.mark.asyncio
    async def test_incr_default_amount(self):
        svc = _svc()
        svc._redis.incrby = AsyncMock(return_value=1)
        result = await svc.incr("counter")
        svc._redis.incrby.assert_awaited_once_with("counter", 1)
        assert result == 1

    @pytest.mark.asyncio
    async def test_incr_custom_amount(self):
        svc = _svc()
        svc._redis.incrby = AsyncMock(return_value=5)
        await svc.incr("counter", 5)
        svc._redis.incrby.assert_awaited_once_with("counter", 5)

    @pytest.mark.asyncio
    async def test_incr_exception_returns_none(self):
        svc = _svc()
        svc._redis.incrby = AsyncMock(side_effect=RuntimeError("err"))
        assert await svc.incr("counter") is None

    @pytest.mark.asyncio
    async def test_decr_default_amount(self):
        svc = _svc()
        svc._redis.decrby = AsyncMock(return_value=-1)
        result = await svc.decr("counter")
        svc._redis.decrby.assert_awaited_once_with("counter", 1)
        assert result == -1

    @pytest.mark.asyncio
    async def test_decr_custom_amount(self):
        svc = _svc()
        svc._redis.decrby = AsyncMock(return_value=-3)
        await svc.decr("counter", 3)
        svc._redis.decrby.assert_awaited_once_with("counter", 3)

    @pytest.mark.asyncio
    async def test_decr_exception_returns_none(self):
        svc = _svc()
        svc._redis.decrby = AsyncMock(side_effect=RuntimeError("err"))
        assert await svc.decr("counter") is None


# ===========================================================================
# hget / hset / hgetall / hdel
# ===========================================================================

class TestHashOperations:
    @pytest.mark.asyncio
    async def test_hget_json_value_deserialized(self):
        svc = _svc()
        svc._redis.hget = AsyncMock(return_value=json.dumps({"score": 99}))
        result = await svc.hget("hash", "field")
        assert result == {"score": 99}

    @pytest.mark.asyncio
    async def test_hget_plain_string_returned(self):
        svc = _svc()
        svc._redis.hget = AsyncMock(return_value="plain")
        assert await svc.hget("hash", "f") == "plain"

    @pytest.mark.asyncio
    async def test_hget_none_returned_when_missing(self):
        svc = _svc()
        svc._redis.hget = AsyncMock(return_value=None)
        assert await svc.hget("hash", "f") is None

    @pytest.mark.asyncio
    async def test_hget_exception_returns_none(self):
        svc = _svc()
        svc._redis.hget = AsyncMock(side_effect=RuntimeError("err"))
        assert await svc.hget("hash", "f") is None

    @pytest.mark.asyncio
    async def test_hset_dict_value_json_serialized(self):
        svc = _svc()
        svc._redis.hset = AsyncMock()
        await svc.hset("hash", "f", {"k": "v"})
        call_args = svc._redis.hset.call_args[0]
        assert json.loads(call_args[2]) == {"k": "v"}

    @pytest.mark.asyncio
    async def test_hset_non_str_converted(self):
        svc = _svc()
        svc._redis.hset = AsyncMock()
        await svc.hset("hash", "f", 123)
        call_args = svc._redis.hset.call_args[0]
        assert call_args[2] == "123"

    @pytest.mark.asyncio
    async def test_hset_returns_true_on_success(self):
        svc = _svc()
        svc._redis.hset = AsyncMock()
        assert await svc.hset("hash", "f", "v") is True

    @pytest.mark.asyncio
    async def test_hset_exception_returns_false(self):
        svc = _svc()
        svc._redis.hset = AsyncMock(side_effect=RuntimeError("err"))
        assert await svc.hset("hash", "f", "v") is False

    @pytest.mark.asyncio
    async def test_hgetall_json_values_deserialized(self):
        svc = _svc()
        svc._redis.hgetall = AsyncMock(return_value={
            "f1": json.dumps({"x": 1}),
            "f2": "plain",
        })
        result = await svc.hgetall("hash")
        assert result["f1"] == {"x": 1}
        assert result["f2"] == "plain"

    @pytest.mark.asyncio
    async def test_hgetall_exception_returns_empty_dict(self):
        svc = _svc()
        svc._redis.hgetall = AsyncMock(side_effect=RuntimeError("err"))
        assert await svc.hgetall("hash") == {}

    @pytest.mark.asyncio
    async def test_hdel_returns_true(self):
        svc = _svc()
        svc._redis.hdel = AsyncMock()
        assert await svc.hdel("hash", "f1", "f2") is True
        svc._redis.hdel.assert_awaited_once_with("hash", "f1", "f2")

    @pytest.mark.asyncio
    async def test_hdel_exception_returns_false(self):
        svc = _svc()
        svc._redis.hdel = AsyncMock(side_effect=RuntimeError("err"))
        assert await svc.hdel("hash", "f") is False


# ===========================================================================
# lpush / rpush / lrange
# ===========================================================================

class TestListOperations:
    @pytest.mark.asyncio
    async def test_lpush_dict_serialized(self):
        svc = _svc()
        svc._redis.lpush = AsyncMock(return_value=2)
        result = await svc.lpush("list", {"a": 1}, "plain")
        assert result == 2
        call_args = svc._redis.lpush.call_args[0]
        # First extra arg should be JSON of dict
        assert json.loads(call_args[1]) == {"a": 1}
        # Second should be plain string
        assert call_args[2] == "plain"

    @pytest.mark.asyncio
    async def test_lpush_exception_returns_none(self):
        svc = _svc()
        svc._redis.lpush = AsyncMock(side_effect=RuntimeError("err"))
        assert await svc.lpush("list", "v") is None

    @pytest.mark.asyncio
    async def test_rpush_str_values(self):
        svc = _svc()
        svc._redis.rpush = AsyncMock(return_value=3)
        result = await svc.rpush("list", "a", "b")
        assert result == 3

    @pytest.mark.asyncio
    async def test_rpush_exception_returns_none(self):
        svc = _svc()
        svc._redis.rpush = AsyncMock(side_effect=RuntimeError("err"))
        assert await svc.rpush("list", "v") is None

    @pytest.mark.asyncio
    async def test_lrange_json_items_deserialized(self):
        svc = _svc()
        svc._redis.lrange = AsyncMock(return_value=[
            json.dumps({"n": 1}),
            "plain",
        ])
        result = await svc.lrange("list")
        assert result[0] == {"n": 1}
        assert result[1] == "plain"

    @pytest.mark.asyncio
    async def test_lrange_custom_bounds(self):
        svc = _svc()
        svc._redis.lrange = AsyncMock(return_value=[])
        await svc.lrange("list", start=2, end=5)
        svc._redis.lrange.assert_awaited_once_with("list", 2, 5)

    @pytest.mark.asyncio
    async def test_lrange_exception_returns_empty_list(self):
        svc = _svc()
        svc._redis.lrange = AsyncMock(side_effect=RuntimeError("err"))
        assert await svc.lrange("list") == []


# ===========================================================================
# clear_pattern
# ===========================================================================

class TestClearPattern:
    @pytest.mark.asyncio
    async def test_deletes_matching_keys(self):
        svc = _svc()

        async def _scan(*args, **kwargs):
            for k in ["store:1", "store:2"]:
                yield k

        svc._redis.scan_iter = _scan
        svc._redis.delete = AsyncMock()
        count = await svc.clear_pattern("store:*")
        assert count == 2
        svc._redis.delete.assert_awaited_once_with("store:1", "store:2")

    @pytest.mark.asyncio
    async def test_no_matching_keys_returns_zero(self):
        svc = _svc()

        async def _empty(*args, **kwargs):
            return
            yield  # make it an async generator

        svc._redis.scan_iter = _empty
        svc._redis.delete = AsyncMock()
        count = await svc.clear_pattern("ghost:*")
        assert count == 0
        svc._redis.delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_exception_returns_zero(self):
        svc = _svc()
        svc._redis.scan_iter = MagicMock(side_effect=RuntimeError("scan failed"))
        count = await svc.clear_pattern("*")
        assert count == 0


# ===========================================================================
# Global singleton
# ===========================================================================

class TestGlobalSingleton:
    def test_redis_cache_is_instance(self):
        assert isinstance(redis_cache, RedisCacheService)

    def test_redis_cache_not_initialized(self):
        # Module-level singleton starts uninitialized
        assert redis_cache._initialized is False


# ===========================================================================
# initialize: sentinel with password (line 42)
# ===========================================================================
class TestInitializeSentinelWithPassword:
    @pytest.mark.asyncio
    async def test_sentinel_with_password_sets_kwargs(self):
        """Line 42: sentinel_kwargs['password'] is set when REDIS_SENTINEL_PASSWORD is truthy."""
        svc = _svc(initialized=False)
        sentinel_settings = MagicMock(
            REDIS_SENTINEL_HOSTS="sentinel1:26379,sentinel2:26379",
            REDIS_SENTINEL_PASSWORD="s3cr3t",  # non-empty → line 42 executes
            REDIS_SENTINEL_MASTER="mymaster",
            REDIS_SENTINEL_DB=0,
        )
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock()
        mock_sentinel = MagicMock()
        mock_sentinel.master_for = MagicMock(return_value=mock_client)

        import src.services.redis_cache_service as mod
        import types
        sentinel_submod = types.ModuleType("redis.asyncio.sentinel")
        captured_kwargs = {}

        def capture_sentinel(sentinels, sentinel_kwargs=None, **kw):
            captured_kwargs.update(sentinel_kwargs or {})
            return mock_sentinel

        sentinel_submod.Sentinel = capture_sentinel

        with patch.object(mod, "settings", sentinel_settings), \
             patch("src.services.redis_cache_service.redis") as mock_redis_mod, \
             patch.dict("sys.modules", {"redis.asyncio.sentinel": sentinel_submod}):
            mock_redis_mod.AuthenticationError = Exception
            mock_redis_mod.ConnectionError = Exception
            await svc.initialize()

        assert captured_kwargs.get("password") == "s3cr3t"
        assert svc._initialized is True


# ===========================================================================
# initialize: ConnectionError (lines 71-72)
# ===========================================================================
class TestInitializeConnectionError:
    @pytest.mark.asyncio
    async def test_connection_error_is_re_raised(self):
        """Lines 71-72: redis.ConnectionError handler logs and re-raises."""
        svc = _svc(initialized=False)

        class FakeConnError(Exception):
            pass

        import src.services.redis_cache_service as mod
        with patch.object(mod, "settings", _DIRECT_SETTINGS), \
             patch("src.services.redis_cache_service.redis") as mock_redis_mod:
            mock_redis_mod.from_url = AsyncMock(side_effect=FakeConnError("refused"))
            mock_redis_mod.AuthenticationError = OSError  # different type
            mock_redis_mod.ConnectionError = FakeConnError  # maps to our error
            with pytest.raises(FakeConnError):
                await svc.initialize()

        assert svc._initialized is False


# ===========================================================================
# Auto-initialize on first call for each method
# (lines 134, 172, 193, 214, 234, 255, 276, 297, 326, 352, 382, 404, 432, 437, 461, 490)
# ===========================================================================
class TestAutoInitializeOnFirstCall:
    """
    Each service method checks `if not self._initialized: await self.initialize()`.
    We patch svc.initialize as an AsyncMock that sets _initialized=True and
    _redis=mock_redis, then call the method and assert initialize was awaited once.
    """

    def _uninit_svc_with_mock_redis(self):
        """Return (svc, mock_redis) with svc not yet initialized."""
        svc = _svc(initialized=False)
        mock_redis = AsyncMock()
        # Patch initialize to set up the redis mock inline
        async def fake_initialize():
            svc._initialized = True
            svc._redis = mock_redis
        svc.initialize = AsyncMock(side_effect=fake_initialize)
        return svc, mock_redis

    @pytest.mark.asyncio
    async def test_set_auto_initializes(self):  # line 172
        svc, mock_redis = self._uninit_svc_with_mock_redis()
        mock_redis.set = AsyncMock()
        await svc.set("k", "v")
        svc.initialize.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_auto_initializes(self):  # line 193
        svc, mock_redis = self._uninit_svc_with_mock_redis()
        mock_redis.delete = AsyncMock()
        await svc.delete("k")
        svc.initialize.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_exists_auto_initializes(self):  # line 214
        svc, mock_redis = self._uninit_svc_with_mock_redis()
        mock_redis.exists = AsyncMock(return_value=0)
        await svc.exists("k")
        svc.initialize.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_expire_auto_initializes(self):  # line 234
        svc, mock_redis = self._uninit_svc_with_mock_redis()
        mock_redis.expire = AsyncMock(return_value=True)
        await svc.expire("k", 60)
        svc.initialize.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ttl_auto_initializes(self):  # line 255
        svc, mock_redis = self._uninit_svc_with_mock_redis()
        mock_redis.ttl = AsyncMock(return_value=100)
        await svc.ttl("k")
        svc.initialize.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_incr_auto_initializes(self):  # line 276
        svc, mock_redis = self._uninit_svc_with_mock_redis()
        mock_redis.incrby = AsyncMock(return_value=1)
        await svc.incr("k")
        svc.initialize.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_decr_auto_initializes(self):  # line 297
        svc, mock_redis = self._uninit_svc_with_mock_redis()
        mock_redis.decrby = AsyncMock(return_value=-1)
        await svc.decr("k")
        svc.initialize.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_hget_auto_initializes(self):  # line 326
        svc, mock_redis = self._uninit_svc_with_mock_redis()
        mock_redis.hget = AsyncMock(return_value=None)
        await svc.hget("h", "f")
        svc.initialize.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_hset_auto_initializes(self):  # line 352
        svc, mock_redis = self._uninit_svc_with_mock_redis()
        mock_redis.hset = AsyncMock()
        await svc.hset("h", "f", "v")
        svc.initialize.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_hgetall_auto_initializes(self):  # line 382
        svc, mock_redis = self._uninit_svc_with_mock_redis()
        mock_redis.hgetall = AsyncMock(return_value={})
        await svc.hgetall("h")
        svc.initialize.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_hdel_auto_initializes(self):  # line 404
        svc, mock_redis = self._uninit_svc_with_mock_redis()
        mock_redis.hdel = AsyncMock()
        await svc.hdel("h", "f")
        svc.initialize.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_lpush_auto_initializes(self):  # line 432
        svc, mock_redis = self._uninit_svc_with_mock_redis()
        mock_redis.lpush = AsyncMock(return_value=1)
        await svc.lpush("list", "v")
        svc.initialize.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rpush_auto_initializes(self):  # line 461
        svc, mock_redis = self._uninit_svc_with_mock_redis()
        mock_redis.rpush = AsyncMock(return_value=1)
        await svc.rpush("list", "v")
        svc.initialize.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_lrange_auto_initializes(self):  # line 490 (approx)
        svc, mock_redis = self._uninit_svc_with_mock_redis()
        mock_redis.lrange = AsyncMock(return_value=[])
        await svc.lrange("list")
        svc.initialize.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_clear_pattern_auto_initializes(self):  # line 437 (approx)
        svc, mock_redis = self._uninit_svc_with_mock_redis()

        async def empty_scan(*args, **kwargs):
            return
            yield

        mock_redis.scan_iter = empty_scan
        mock_redis.delete = AsyncMock()
        await svc.clear_pattern("*")
        svc.initialize.assert_awaited_once()


# ===========================================================================
# rpush with dict value serialization (line 437)
# ===========================================================================
class TestRpushDictSerialization:
    @pytest.mark.asyncio
    async def test_rpush_dict_value_json_serialized(self):
        """Line 437: rpush with a dict value triggers json.dumps path."""
        svc = _svc()
        svc._redis.rpush = AsyncMock(return_value=1)
        result = await svc.rpush("list", {"key": "value"})
        assert result == 1
        call_args = svc._redis.rpush.call_args[0]
        # The dict should be JSON serialized
        assert json.loads(call_args[1]) == {"key": "value"}
