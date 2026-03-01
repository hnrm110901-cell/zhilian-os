"""
StoreMemoryService.detect_anomaly() 单元测试

覆盖：
- 非折扣类 action_type → 无异常返回 None
- 折扣金额 <= 50元 → 无异常返回 None
- 折扣金额 > 50元, < 200元 → medium severity
- 折扣金额 >= 200元 → high severity
- 重复触发相同 pattern_type → occurrence_count 累加
- 严重级别可由 medium 升级为 high（不降级）
- Redis 不可用时 → 降级处理，仍返回 AnomalyPattern
"""
import sys
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

# agent_service.py has a module-level `agent_service = AgentService()` singleton
# that tries to do relative imports and fails outside the package runtime context.
# Pre-stub the module so importing src.services.* doesn't trigger it.
sys.modules.setdefault("src.services.agent_service", MagicMock())

from src.services.store_memory_service import StoreMemoryService
from src.models.store_memory import AnomalyPattern, StoreMemory, StoreMemoryStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(action_type: str = "discount_apply", amount_fen: int = 10000) -> dict:
    return {
        "action_type": action_type,
        "amount": amount_fen,
        "store_id": "STORE_001",
        "brand_id": "BRAND_A",
    }


def _make_service(memory: StoreMemory = None) -> StoreMemoryService:
    """服务实例，Redis 操作使用 AsyncMock"""
    store = MagicMock(spec=StoreMemoryStore)
    store.load = AsyncMock(return_value=memory)
    store.save = AsyncMock(return_value=True)
    return StoreMemoryService(db_session=None, memory_store=store)


# ---------------------------------------------------------------------------
# 非折扣事件 → None
# ---------------------------------------------------------------------------

class TestNonDiscountEvents:
    @pytest.mark.asyncio
    async def test_non_discount_action_returns_none(self):
        svc = _make_service()
        result = await svc.detect_anomaly("STORE_001", _make_event("shift_report"))
        assert result is None

    @pytest.mark.asyncio
    async def test_stock_alert_returns_none(self):
        svc = _make_service()
        result = await svc.detect_anomaly("STORE_001", _make_event("stock_alert", 999999))
        assert result is None

    @pytest.mark.asyncio
    async def test_no_action_type_returns_none(self):
        svc = _make_service()
        result = await svc.detect_anomaly("STORE_001", {})
        assert result is None


# ---------------------------------------------------------------------------
# 折扣金额阈值检测
# ---------------------------------------------------------------------------

class TestDiscountThreshold:
    @pytest.mark.asyncio
    async def test_below_threshold_returns_none(self):
        # 5000分 = 50元，刚好等于阈值 → 不触发
        svc = _make_service()
        result = await svc.detect_anomaly("STORE_001", _make_event(amount_fen=5000))
        assert result is None

    @pytest.mark.asyncio
    async def test_exactly_at_threshold_returns_none(self):
        svc = _make_service()
        result = await svc.detect_anomaly("STORE_001", _make_event(amount_fen=4999))
        assert result is None

    @pytest.mark.asyncio
    async def test_above_threshold_returns_anomaly(self):
        svc = _make_service()
        result = await svc.detect_anomaly("STORE_001", _make_event(amount_fen=5001))
        assert isinstance(result, AnomalyPattern)

    @pytest.mark.asyncio
    async def test_pattern_type_is_discount_spike(self):
        svc = _make_service()
        result = await svc.detect_anomaly("STORE_001", _make_event(amount_fen=10000))
        assert result.pattern_type == "discount_spike"


# ---------------------------------------------------------------------------
# 严重级别
# ---------------------------------------------------------------------------

class TestSeverityLevels:
    @pytest.mark.asyncio
    async def test_medium_severity_below_200_yuan(self):
        # 5100分 = 51元 → medium
        svc = _make_service()
        result = await svc.detect_anomaly("STORE_001", _make_event(amount_fen=5100))
        assert result.severity == "medium"

    @pytest.mark.asyncio
    async def test_high_severity_at_200_yuan(self):
        # 20000分 = 200元 → high
        svc = _make_service()
        result = await svc.detect_anomaly("STORE_001", _make_event(amount_fen=20000))
        assert result.severity == "high"

    @pytest.mark.asyncio
    async def test_high_severity_above_200_yuan(self):
        svc = _make_service()
        result = await svc.detect_anomaly("STORE_001", _make_event(amount_fen=99999))
        assert result.severity == "high"


# ---------------------------------------------------------------------------
# 异常累加（相同 pattern_type 时 occurrence_count 递增）
# ---------------------------------------------------------------------------

class TestAnomalyAccumulation:
    @pytest.mark.asyncio
    async def test_occurrence_count_increments_on_repeat(self):
        existing = AnomalyPattern(
            pattern_type="discount_spike",
            description="first",
            first_seen=datetime(2024, 1, 1),
            last_seen=datetime(2024, 1, 1),
            occurrence_count=3,
            severity="medium",
        )
        memory = StoreMemory(
            store_id="STORE_001",
            anomaly_patterns=[existing],
        )
        svc = _make_service(memory)
        await svc.detect_anomaly("STORE_001", _make_event(amount_fen=10000))

        # save должен был вызваться с обновлённой памятью
        saved_memory: StoreMemory = svc._store.save.call_args[0][0]
        pattern = next(p for p in saved_memory.anomaly_patterns if p.pattern_type == "discount_spike")
        assert pattern.occurrence_count == 4

    @pytest.mark.asyncio
    async def test_severity_upgrades_from_medium_to_high(self):
        existing = AnomalyPattern(
            pattern_type="discount_spike",
            description="first",
            first_seen=datetime(2024, 1, 1),
            last_seen=datetime(2024, 1, 1),
            severity="medium",
        )
        memory = StoreMemory(store_id="STORE_001", anomaly_patterns=[existing])
        svc = _make_service(memory)
        # 高金额触发 high severity
        await svc.detect_anomaly("STORE_001", _make_event(amount_fen=20000))

        saved_memory: StoreMemory = svc._store.save.call_args[0][0]
        pattern = next(p for p in saved_memory.anomaly_patterns if p.pattern_type == "discount_spike")
        assert pattern.severity == "high"

    @pytest.mark.asyncio
    async def test_high_severity_does_not_downgrade_to_medium(self):
        existing = AnomalyPattern(
            pattern_type="discount_spike",
            description="first",
            first_seen=datetime(2024, 1, 1),
            last_seen=datetime(2024, 1, 1),
            severity="high",
        )
        memory = StoreMemory(store_id="STORE_001", anomaly_patterns=[existing])
        svc = _make_service(memory)
        # 低金额触发 medium severity，不应降级
        await svc.detect_anomaly("STORE_001", _make_event(amount_fen=6000))

        saved_memory: StoreMemory = svc._store.save.call_args[0][0]
        pattern = next(p for p in saved_memory.anomaly_patterns if p.pattern_type == "discount_spike")
        assert pattern.severity == "high"

    @pytest.mark.asyncio
    async def test_new_pattern_appended_if_not_exists(self):
        memory = StoreMemory(store_id="STORE_001", anomaly_patterns=[])
        svc = _make_service(memory)
        await svc.detect_anomaly("STORE_001", _make_event(amount_fen=10000))

        saved_memory: StoreMemory = svc._store.save.call_args[0][0]
        assert len(saved_memory.anomaly_patterns) == 1
        assert saved_memory.anomaly_patterns[0].pattern_type == "discount_spike"


# ---------------------------------------------------------------------------
# Redis 不可用降级
# ---------------------------------------------------------------------------

class TestRedisUnavailable:
    @pytest.mark.asyncio
    async def test_still_returns_pattern_when_redis_unavailable(self):
        """Redis load 返回 None → 仍能创建新记忆并尝试写入"""
        svc = _make_service(memory=None)  # load returns None
        result = await svc.detect_anomaly("STORE_001", _make_event(amount_fen=10000))
        assert isinstance(result, AnomalyPattern)
        # save 应被调用（即使可能失败）
        svc._store.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_below_threshold_even_without_redis(self):
        svc = _make_service(memory=None)
        result = await svc.detect_anomaly("STORE_001", _make_event(amount_fen=100))
        assert result is None
