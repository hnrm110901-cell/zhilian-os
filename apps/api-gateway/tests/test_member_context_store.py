"""
MemberContextStore 单元测试

覆盖：
  - make_context_key（纯函数）
  - MemberContextStore.get（命中 / 未命中 / Redis 失败）
  - MemberContextStore.set（正常写入 / Redis 失败）
  - MemberContextStore.invalidate（正常删除 / Redis 失败）
  - MemberContextStore.invalidate_store（批量删除 / Redis 失败）
  - journey_orchestrator._get_member_profile（缓存命中 / DB fallback + 写透 / 无缓存无DB）
"""

import os
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("APP_ENV", "test")

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.member_context_store import (
    MemberContextStore,
    make_context_key,
    reset_context_store,
)


# ════════════════════════════════════════════════════════════════════════════════
# make_context_key
# ════════════════════════════════════════════════════════════════════════════════

class TestMakeContextKey:
    def test_format(self):
        assert make_context_key("S001", "C001") == "member_ctx:S001:C001"

    def test_different_store_different_key(self):
        assert make_context_key("S001", "C001") != make_context_key("S002", "C001")

    def test_different_customer_different_key(self):
        assert make_context_key("S001", "C001") != make_context_key("S001", "C002")


# ════════════════════════════════════════════════════════════════════════════════
# MemberContextStore.get
# ════════════════════════════════════════════════════════════════════════════════

class TestMemberContextStoreGet:
    @pytest.mark.asyncio
    async def test_cache_hit_returns_dict(self):
        """Redis 有值 → 解析 JSON 返回。"""
        redis = AsyncMock()
        data = {"frequency": 3, "monetary": 15000, "maslow_level": 3}
        redis.get.return_value = json.dumps(data)

        store = MemberContextStore(redis)
        result = await store.get("S001", "C001")

        assert result == data
        redis.get.assert_called_once_with("member_ctx:S001:C001")

    @pytest.mark.asyncio
    async def test_cache_miss_returns_none(self):
        redis = AsyncMock()
        redis.get.return_value = None

        store = MemberContextStore(redis)
        result = await store.get("S001", "C001")

        assert result is None

    @pytest.mark.asyncio
    async def test_redis_error_returns_none(self):
        """Redis 抛异常 → 静默返回 None。"""
        redis = AsyncMock()
        redis.get.side_effect = Exception("connection refused")

        store = MemberContextStore(redis)
        result = await store.get("S001", "C001")

        assert result is None

    @pytest.mark.asyncio
    async def test_none_redis_returns_none(self):
        store = MemberContextStore(None)
        result = await store.get("S001", "C001")
        assert result is None


# ════════════════════════════════════════════════════════════════════════════════
# MemberContextStore.set
# ════════════════════════════════════════════════════════════════════════════════

class TestMemberContextStoreSet:
    @pytest.mark.asyncio
    async def test_set_calls_setex_with_json(self):
        redis = AsyncMock()
        store = MemberContextStore(redis)
        data = {"frequency": 5, "monetary": 25000}

        await store.set("S001", "C001", data)

        redis.setex.assert_called_once()
        args = redis.setex.call_args.args
        assert args[0] == "member_ctx:S001:C001"
        assert json.loads(args[2]) == data

    @pytest.mark.asyncio
    async def test_set_uses_custom_ttl(self):
        redis = AsyncMock()
        store = MemberContextStore(redis)

        await store.set("S001", "C001", {}, ttl=3600)

        args = redis.setex.call_args.args
        assert args[1] == 3600

    @pytest.mark.asyncio
    async def test_redis_error_does_not_raise(self):
        redis = AsyncMock()
        redis.setex.side_effect = Exception("timeout")
        store = MemberContextStore(redis)

        # 不应抛异常
        await store.set("S001", "C001", {"frequency": 1})

    @pytest.mark.asyncio
    async def test_none_redis_is_noop(self):
        store = MemberContextStore(None)
        await store.set("S001", "C001", {"frequency": 1})  # 不抛异常


# ════════════════════════════════════════════════════════════════════════════════
# MemberContextStore.invalidate
# ════════════════════════════════════════════════════════════════════════════════

class TestMemberContextStoreInvalidate:
    @pytest.mark.asyncio
    async def test_invalidate_deletes_correct_key(self):
        redis = AsyncMock()
        store = MemberContextStore(redis)

        await store.invalidate("S001", "C001")

        redis.delete.assert_called_once_with("member_ctx:S001:C001")

    @pytest.mark.asyncio
    async def test_redis_error_does_not_raise(self):
        redis = AsyncMock()
        redis.delete.side_effect = Exception("timeout")
        store = MemberContextStore(redis)

        await store.invalidate("S001", "C001")  # 不抛异常

    @pytest.mark.asyncio
    async def test_none_redis_is_noop(self):
        store = MemberContextStore(None)
        await store.invalidate("S001", "C001")


# ════════════════════════════════════════════════════════════════════════════════
# MemberContextStore.invalidate_store
# ════════════════════════════════════════════════════════════════════════════════

class TestMemberContextStoreInvalidateStore:
    @pytest.mark.asyncio
    async def test_deletes_all_matching_keys(self):
        redis = AsyncMock()

        async def mock_scan_iter(match, count):
            keys = ["member_ctx:S001:C001", "member_ctx:S001:C002"]
            for k in keys:
                yield k

        redis.scan_iter = mock_scan_iter

        store = MemberContextStore(redis)
        deleted = await store.invalidate_store("S001")

        assert deleted == 2
        assert redis.delete.call_count == 2

    @pytest.mark.asyncio
    async def test_returns_zero_for_none_redis(self):
        store = MemberContextStore(None)
        result = await store.invalidate_store("S001")
        assert result == 0

    @pytest.mark.asyncio
    async def test_redis_error_returns_zero(self):
        redis = AsyncMock()
        redis.scan_iter.side_effect = Exception("error")
        store = MemberContextStore(redis)

        result = await store.invalidate_store("S001")
        assert result == 0


# ════════════════════════════════════════════════════════════════════════════════
# journey_orchestrator._get_member_profile（缓存集成）
# ════════════════════════════════════════════════════════════════════════════════

class TestGetMemberProfileWithCache:
    def setup_method(self):
        reset_context_store()

    @pytest.mark.asyncio
    async def test_cache_hit_skips_db(self):
        """Redis 有缓存 → 不查 DB。"""
        from src.services.journey_orchestrator import JourneyOrchestrator

        cached_data = {
            "frequency": 5, "monetary": 30000,
            "recency_days": 7, "lifecycle_state": "repeat",
        }
        mock_store = AsyncMock()
        mock_store.get.return_value = cached_data

        db = AsyncMock()
        orch = JourneyOrchestrator()

        with patch("src.services.member_context_store.get_context_store",
                   return_value=mock_store):
            profile = await orch._get_member_profile("C001", "S001", db)

        assert profile is not None
        assert profile.frequency == 5
        assert profile.lifecycle_state == "repeat"
        db.execute.assert_not_called()  # DB 未被调用

    @pytest.mark.asyncio
    async def test_cache_miss_queries_db_and_writes_through(self):
        """Redis miss → 查 DB → 写透缓存。"""
        from src.services.journey_orchestrator import JourneyOrchestrator

        mock_store = AsyncMock()
        mock_store.get.return_value = None  # cache miss

        db = AsyncMock()
        row = MagicMock()
        row.__getitem__ = lambda self, i: [3, 18000, 10, "repeat"][i]
        db.execute.return_value.fetchone.return_value = row

        orch = JourneyOrchestrator()

        with patch("src.services.member_context_store.get_context_store",
                   return_value=mock_store):
            profile = await orch._get_member_profile("C001", "S001", db)

        assert profile is not None
        assert profile.frequency == 3
        assert profile.monetary == 18000
        # 写透 set 被调用
        mock_store.set.assert_called_once()
        call_kwargs = mock_store.set.call_args
        assert call_kwargs.args[0] == "S001"
        assert call_kwargs.args[1] == "C001"
        cached = call_kwargs.args[2]
        assert cached["frequency"] == 3
        assert "maslow_level" in cached  # maslow_level 预计算写入

    @pytest.mark.asyncio
    async def test_cache_unavailable_falls_back_to_db(self):
        """Redis 不可用（返回 None store）→ 直接查 DB，不报错。"""
        from src.services.journey_orchestrator import JourneyOrchestrator

        db = AsyncMock()
        row = MagicMock()
        row.__getitem__ = lambda self, i: [1, 5000, 30, "first_order_pending"][i]
        db.execute.return_value.fetchone.return_value = row

        orch = JourneyOrchestrator()

        with patch("src.services.member_context_store.get_context_store",
                   return_value=None):
            profile = await orch._get_member_profile("C001", "S001", db)

        assert profile is not None
        assert profile.frequency == 1
        db.execute.assert_called_once()
