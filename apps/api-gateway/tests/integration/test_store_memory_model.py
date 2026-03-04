"""
Tests for src/models/store_memory.py — StoreMemoryStore.

Covers:
  - StoreMemoryStore._key: key format (line 93)
  - StoreMemoryStore.load: no redis (line 97-99), redis miss (line 103-104),
    redis hit (lines 105-106), exception (lines 107-109)
  - StoreMemoryStore.save: no redis (lines 113-115), success (lines 117-122),
    exception (lines 123-125)
  - StoreMemoryStore.delete: no redis (lines 129-130), success (lines 131-133),
    exception (lines 134-136)
"""
import json
import pytest
from datetime import datetime
from unittest.mock import AsyncMock

from src.models.store_memory import (
    StoreMemory,
    StoreMemoryStore,
)


def _memory(store_id: str = "STORE1", brand_id: str = "BRAND1") -> StoreMemory:
    return StoreMemory(store_id=store_id, brand_id=brand_id)


# ===========================================================================
# StoreMemoryStore._key
# ===========================================================================

class TestStoreMemoryStoreKey:
    def test_key_format(self):
        store = StoreMemoryStore()
        assert store._key("STORE123") == "store_memory:STORE123"


# ===========================================================================
# StoreMemoryStore.load
# ===========================================================================

class TestStoreMemoryStoreLoad:
    @pytest.mark.asyncio
    async def test_load_no_redis_returns_none(self):
        store = StoreMemoryStore(redis_client=None)
        result = await store.load("any-store")
        assert result is None

    @pytest.mark.asyncio
    async def test_load_redis_miss_returns_none(self):
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        store = StoreMemoryStore(redis_client=mock_redis)
        result = await store.load("missing-store")
        assert result is None

    @pytest.mark.asyncio
    async def test_load_redis_hit_returns_store_memory(self):
        memory = _memory(store_id="STORE99", brand_id="BRAND99")
        raw = memory.model_dump_json()
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=raw)
        store = StoreMemoryStore(redis_client=mock_redis)
        result = await store.load("STORE99")
        assert result is not None
        assert result.store_id == "STORE99"
        assert result.brand_id == "BRAND99"

    @pytest.mark.asyncio
    async def test_load_redis_exception_returns_none(self):
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=RuntimeError("redis down"))
        store = StoreMemoryStore(redis_client=mock_redis)
        result = await store.load("STORE1")
        assert result is None

    @pytest.mark.asyncio
    async def test_load_calls_correct_key(self):
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        store = StoreMemoryStore(redis_client=mock_redis)
        await store.load("MY_STORE")
        mock_redis.get.assert_awaited_once_with("store_memory:MY_STORE")


# ===========================================================================
# StoreMemoryStore.save
# ===========================================================================

class TestStoreMemoryStoreSave:
    @pytest.mark.asyncio
    async def test_save_no_redis_returns_false(self):
        store = StoreMemoryStore(redis_client=None)
        result = await store.save(_memory())
        assert result is False

    @pytest.mark.asyncio
    async def test_save_success_returns_true(self):
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()
        store = StoreMemoryStore(redis_client=mock_redis)
        memory = _memory(store_id="STORE1")
        result = await store.save(memory)
        assert result is True
        mock_redis.set.assert_awaited_once()
        # Verify key and TTL args
        call_args = mock_redis.set.call_args
        assert call_args[0][0] == "store_memory:STORE1"
        assert call_args[1].get("ex") == StoreMemoryStore.DEFAULT_TTL

    @pytest.mark.asyncio
    async def test_save_redis_exception_returns_false(self):
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(side_effect=RuntimeError("write failed"))
        store = StoreMemoryStore(redis_client=mock_redis)
        result = await store.save(_memory())
        assert result is False


# ===========================================================================
# StoreMemoryStore.delete
# ===========================================================================

class TestStoreMemoryStoreDelete:
    @pytest.mark.asyncio
    async def test_delete_no_redis_returns_false(self):
        store = StoreMemoryStore(redis_client=None)
        result = await store.delete("STORE1")
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_success_returns_true(self):
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock()
        store = StoreMemoryStore(redis_client=mock_redis)
        result = await store.delete("STORE1")
        assert result is True
        mock_redis.delete.assert_awaited_once_with("store_memory:STORE1")

    @pytest.mark.asyncio
    async def test_delete_redis_exception_returns_false(self):
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(side_effect=RuntimeError("delete failed"))
        store = StoreMemoryStore(redis_client=mock_redis)
        result = await store.delete("STORE1")
        assert result is False
