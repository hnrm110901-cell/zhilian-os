"""
Tests for src/models/conversation.py — ConversationContext and ConversationStore.

Covers:
  - add_turn: trimming when exceeds MAX_TURNS (line 49)
  - get_context_summary: with turns (lines 58-64)
  - ConversationStore._key: key format (line 81)
  - ConversationStore.load: redis hit, redis miss, exception (lines 85-94)
  - ConversationStore.save: success, no redis, exception (lines 98-107)
  - ConversationStore.expire: success, no redis, exception (lines 111-118)
  - ConversationStore.get_or_create: existing session, new session (lines 127-132)
"""
import json
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from src.models.conversation import (
    ConversationContext,
    ConversationStore,
    ConversationTurn,
    CONVERSATION_TTL,
)


def _turn(user_input="hello", response="world") -> ConversationTurn:
    return ConversationTurn(user_input=user_input, response=response)


def _ctx(store_id="S1", user_id="U1") -> ConversationContext:
    return ConversationContext(store_id=store_id, user_id=user_id)


# ===========================================================================
# ConversationContext.add_turn — trimming
# ===========================================================================

class TestAddTurnTrimming:
    def test_adding_more_than_max_turns_trims_oldest(self):
        ctx = _ctx()
        for i in range(4):  # MAX_TURNS=3, so 4th push trims
            ctx.add_turn(_turn(user_input=f"msg{i}", response=f"rsp{i}"))
        assert len(ctx.turns) == 3  # line 49 executed
        assert ctx.turns[0].user_input == "msg1"  # oldest trimmed

    def test_adding_exactly_max_turns_does_not_trim(self):
        ctx = _ctx()
        for i in range(3):
            ctx.add_turn(_turn(user_input=f"msg{i}", response=f"rsp{i}"))
        assert len(ctx.turns) == 3

    def test_add_turn_updates_last_active(self):
        ctx = _ctx()
        before = ctx.last_active
        ctx.add_turn(_turn())
        assert ctx.last_active >= before


# ===========================================================================
# ConversationContext.get_context_summary
# ===========================================================================

class TestGetContextSummary:
    def test_no_turns_returns_empty_string(self):
        ctx = _ctx()
        assert ctx.get_context_summary() == ""

    def test_with_turns_returns_formatted_string(self):
        ctx = _ctx()
        ctx.add_turn(_turn(user_input="你好", response="您好，有什么可以帮助您？"))
        summary = ctx.get_context_summary()
        assert "用户: 你好" in summary
        assert "系统: 您好" in summary

    def test_long_response_truncated_to_100_chars(self):
        ctx = _ctx()
        long_resp = "x" * 200
        ctx.add_turn(_turn(response=long_resp))
        summary = ctx.get_context_summary()
        # Response in summary should be at most 100 chars
        for line in summary.split("\n"):
            if line.startswith("系统:"):
                assert len(line) <= len("系统: ") + 100


# ===========================================================================
# ConversationStore
# ===========================================================================

class TestConversationStoreKey:
    def test_key_format(self):
        store = ConversationStore()
        assert store._key("SID123") == "conversation:SID123"


class TestConversationStoreLoad:
    @pytest.mark.asyncio
    async def test_load_no_redis_returns_none(self):
        store = ConversationStore(redis_client=None)
        result = await store.load("any-session")
        assert result is None

    @pytest.mark.asyncio
    async def test_load_redis_miss_returns_none(self):
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        store = ConversationStore(redis_client=mock_redis)
        result = await store.load("missing-session")
        assert result is None

    @pytest.mark.asyncio
    async def test_load_redis_hit_returns_context(self):
        ctx = _ctx(store_id="S99", user_id="U99")
        raw = ctx.model_dump_json()
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=raw)
        store = ConversationStore(redis_client=mock_redis)
        result = await store.load(ctx.session_id)
        assert result is not None
        assert result.store_id == "S99"

    @pytest.mark.asyncio
    async def test_load_redis_exception_returns_none(self):
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=RuntimeError("redis down"))
        store = ConversationStore(redis_client=mock_redis)
        result = await store.load("session-id")
        assert result is None


class TestConversationStoreSave:
    @pytest.mark.asyncio
    async def test_save_no_redis_returns_false(self):
        store = ConversationStore(redis_client=None)
        ctx = _ctx()
        result = await store.save(ctx)
        assert result is False

    @pytest.mark.asyncio
    async def test_save_success_returns_true(self):
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()
        store = ConversationStore(redis_client=mock_redis)
        ctx = _ctx()
        result = await store.save(ctx)
        assert result is True
        mock_redis.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_save_redis_exception_returns_false(self):
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(side_effect=RuntimeError("save failed"))
        store = ConversationStore(redis_client=mock_redis)
        result = await store.save(_ctx())
        assert result is False


class TestConversationStoreExpire:
    @pytest.mark.asyncio
    async def test_expire_no_redis_returns_false(self):
        store = ConversationStore(redis_client=None)
        result = await store.expire("session-id")
        assert result is False

    @pytest.mark.asyncio
    async def test_expire_success_returns_true(self):
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock()
        store = ConversationStore(redis_client=mock_redis)
        result = await store.expire("session-id")
        assert result is True

    @pytest.mark.asyncio
    async def test_expire_exception_returns_false(self):
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(side_effect=RuntimeError("delete failed"))
        store = ConversationStore(redis_client=mock_redis)
        result = await store.expire("session-id")
        assert result is False


class TestConversationStoreGetOrCreate:
    @pytest.mark.asyncio
    async def test_get_or_create_no_session_id_creates_new(self):
        store = ConversationStore(redis_client=None)
        result = await store.get_or_create(None, "S1", "U1")
        assert result.store_id == "S1"
        assert result.user_id == "U1"

    @pytest.mark.asyncio
    async def test_get_or_create_with_existing_session_returns_it(self):
        ctx = _ctx(store_id="S42", user_id="U42")
        raw = ctx.model_dump_json()
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=raw)
        store = ConversationStore(redis_client=mock_redis)
        result = await store.get_or_create(ctx.session_id, "S1", "U1")
        assert result.store_id == "S42"

    @pytest.mark.asyncio
    async def test_get_or_create_session_not_found_creates_new(self):
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        store = ConversationStore(redis_client=mock_redis)
        result = await store.get_or_create("stale-session-id", "S1", "U1")
        assert result.store_id == "S1"
