"""
StoreMemoryService 服务层单元测试

覆盖：
- _confidence_level: 天数分档（<14→low, 14-29→medium, ≥30→high）
- detect_anomaly: 非折扣动作 → None
- detect_anomaly: 金额≤5000分 → None
- detect_anomaly: 金额>5000分，无历史记忆 → 新建 AnomalyPattern
- detect_anomaly: 相同 pattern_type → occurrence_count 累加
- detect_anomaly: high severity 会覆盖 existing severity
- detect_anomaly: 写入 Redis（_store.save 被调用）
- get_memory: 无 Redis → 返回 None
- refresh_store_memory: 无 DB → 写入空 peak_patterns 的记忆并返回
- StoreMemoryStore.load: 无 Redis → 返回 None
- StoreMemoryStore.save: 无 Redis → 返回 False（不抛异常）
"""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from src.services.store_memory_service import StoreMemoryService, _confidence_level
from src.models.store_memory import (
    AnomalyPattern, PeakHourPattern, StoreMemory, StoreMemoryStore,
)


# ---------------------------------------------------------------------------
# _confidence_level
# ---------------------------------------------------------------------------

class TestConfidenceLevel:
    def test_less_than_14_days_is_low(self):
        assert _confidence_level(13) == "low"
        assert _confidence_level(0) == "low"

    def test_14_days_is_medium(self):
        assert _confidence_level(14) == "medium"

    def test_29_days_is_medium(self):
        assert _confidence_level(29) == "medium"

    def test_30_days_is_high(self):
        assert _confidence_level(30) == "high"

    def test_60_days_is_high(self):
        assert _confidence_level(60) == "high"


# ---------------------------------------------------------------------------
# detect_anomaly
# ---------------------------------------------------------------------------

class TestDetectAnomaly:
    def _svc(self, existing_memory=None):
        """创建带 mock StoreMemoryStore 的 service"""
        store = MagicMock(spec=StoreMemoryStore)
        store.load = AsyncMock(return_value=existing_memory)
        store.save = AsyncMock(return_value=True)
        return StoreMemoryService(memory_store=store), store

    @pytest.mark.asyncio
    async def test_non_discount_action_returns_none(self):
        svc, _ = self._svc()
        result = await svc.detect_anomaly("S1", {"action_type": "order_cancel", "amount": 9999})
        assert result is None

    @pytest.mark.asyncio
    async def test_amount_at_threshold_returns_none(self):
        svc, _ = self._svc()
        result = await svc.detect_anomaly("S1", {"action_type": "discount_apply", "amount": 5000})
        assert result is None

    @pytest.mark.asyncio
    async def test_amount_below_threshold_returns_none(self):
        svc, _ = self._svc()
        result = await svc.detect_anomaly("S1", {"action_type": "discount_apply", "amount": 4999})
        assert result is None

    @pytest.mark.asyncio
    async def test_amount_above_threshold_returns_pattern(self):
        svc, _ = self._svc()
        result = await svc.detect_anomaly("S1", {"action_type": "discount_apply", "amount": 5001})
        assert result is not None
        assert result.pattern_type == "discount_spike"

    @pytest.mark.asyncio
    async def test_new_anomaly_written_to_store(self):
        svc, store = self._svc()
        await svc.detect_anomaly("S1", {"action_type": "discount_apply", "amount": 8000})
        store.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_existing_memory_creates_new(self):
        svc, store = self._svc(existing_memory=None)
        await svc.detect_anomaly("S1", {"action_type": "discount_apply", "amount": 8000})
        saved_memory = store.save.call_args[0][0]
        assert saved_memory.store_id == "S1"
        assert len(saved_memory.anomaly_patterns) == 1

    @pytest.mark.asyncio
    async def test_existing_same_pattern_increments_count(self):
        now = datetime.utcnow()
        existing_pattern = AnomalyPattern(
            pattern_type="discount_spike",
            description="旧异常",
            first_seen=now,
            last_seen=now,
            occurrence_count=3,
            severity="medium",
        )
        memory = StoreMemory(
            store_id="S1",
            updated_at=now,
            anomaly_patterns=[existing_pattern],
        )
        svc, store = self._svc(existing_memory=memory)
        await svc.detect_anomaly("S1", {"action_type": "discount_apply", "amount": 6000})

        saved = store.save.call_args[0][0]
        pattern = saved.anomaly_patterns[0]
        assert pattern.occurrence_count == 4

    @pytest.mark.asyncio
    async def test_existing_pattern_does_not_duplicate(self):
        now = datetime.utcnow()
        existing_pattern = AnomalyPattern(
            pattern_type="discount_spike",
            description="旧异常",
            first_seen=now,
            last_seen=now,
            severity="medium",
        )
        memory = StoreMemory(store_id="S1", updated_at=now, anomaly_patterns=[existing_pattern])
        svc, store = self._svc(existing_memory=memory)
        await svc.detect_anomaly("S1", {"action_type": "discount_apply", "amount": 6000})

        saved = store.save.call_args[0][0]
        assert len(saved.anomaly_patterns) == 1

    @pytest.mark.asyncio
    async def test_high_amount_sets_high_severity(self):
        svc, store = self._svc()
        result = await svc.detect_anomaly("S1", {"action_type": "discount_apply", "amount": 20001})
        assert result.severity == "high"

    @pytest.mark.asyncio
    async def test_medium_amount_sets_medium_severity(self):
        svc, store = self._svc()
        result = await svc.detect_anomaly("S1", {"action_type": "discount_apply", "amount": 5001})
        assert result.severity == "medium"

    @pytest.mark.asyncio
    async def test_high_severity_overwrites_existing_medium(self):
        now = datetime.utcnow()
        existing_pattern = AnomalyPattern(
            pattern_type="discount_spike",
            description="旧异常",
            first_seen=now,
            last_seen=now,
            severity="medium",
        )
        memory = StoreMemory(store_id="S1", updated_at=now, anomaly_patterns=[existing_pattern])
        svc, store = self._svc(existing_memory=memory)
        await svc.detect_anomaly("S1", {"action_type": "discount_apply", "amount": 20001})

        saved = store.save.call_args[0][0]
        assert saved.anomaly_patterns[0].severity == "high"


# ---------------------------------------------------------------------------
# get_memory
# ---------------------------------------------------------------------------

class TestGetMemory:
    @pytest.mark.asyncio
    async def test_no_redis_returns_none(self):
        svc = StoreMemoryService()  # no memory_store passed
        result = await svc.get_memory("S1")
        assert result is None

    @pytest.mark.asyncio
    async def test_store_load_called_with_store_id(self):
        store = MagicMock(spec=StoreMemoryStore)
        store.load = AsyncMock(return_value=None)
        svc = StoreMemoryService(memory_store=store)
        await svc.get_memory("STORE_XYZ")
        store.load.assert_awaited_once_with("STORE_XYZ")


# ---------------------------------------------------------------------------
# refresh_store_memory
# ---------------------------------------------------------------------------

class TestRefreshStoreMemory:
    @pytest.mark.asyncio
    async def test_no_db_returns_memory_with_empty_peaks(self):
        store = MagicMock(spec=StoreMemoryStore)
        store.save = AsyncMock(return_value=True)
        svc = StoreMemoryService(memory_store=store)
        memory = await svc.refresh_store_memory("S1", lookback_days=30)
        assert memory.store_id == "S1"
        assert memory.peak_patterns == []

    @pytest.mark.asyncio
    async def test_no_db_confidence_matches_lookback(self):
        store = MagicMock(spec=StoreMemoryStore)
        store.save = AsyncMock(return_value=True)
        svc = StoreMemoryService(memory_store=store)
        memory = await svc.refresh_store_memory("S1", lookback_days=30)
        assert memory.confidence == "high"

    @pytest.mark.asyncio
    async def test_refresh_saves_to_store(self):
        store = MagicMock(spec=StoreMemoryStore)
        store.save = AsyncMock(return_value=True)
        svc = StoreMemoryService(memory_store=store)
        await svc.refresh_store_memory("S1")
        store.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_brand_id_stored_in_memory(self):
        store = MagicMock(spec=StoreMemoryStore)
        store.save = AsyncMock(return_value=True)
        svc = StoreMemoryService(memory_store=store)
        memory = await svc.refresh_store_memory("S1", brand_id="BRAND_A")
        assert memory.brand_id == "BRAND_A"


# ---------------------------------------------------------------------------
# StoreMemoryStore (无 Redis 时的守卫行为)
# ---------------------------------------------------------------------------

class TestStoreMemoryStoreNoRedis:
    @pytest.mark.asyncio
    async def test_load_without_redis_returns_none(self):
        store = StoreMemoryStore(redis_client=None)
        result = await store.load("S1")
        assert result is None

    @pytest.mark.asyncio
    async def test_save_without_redis_returns_false(self):
        store = StoreMemoryStore(redis_client=None)
        memory = StoreMemory(store_id="S1", updated_at=datetime.utcnow())
        result = await store.save(memory)
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_without_redis_returns_false(self):
        store = StoreMemoryStore(redis_client=None)
        result = await store.delete("S1")
        assert result is False
