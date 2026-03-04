"""
EdgeNodeService 离线查询测试（v2.0 P0：断网可用）

覆盖：
  - query_revenue_offline：缓存命中 / 历史均值估算 / 无缓存兜底
  - query_inventory_offline：缓存命中 / 无缓存兜底
  - update_revenue_cache / update_inventory_cache：写入验证
"""

import pytest
from datetime import datetime

from src.services.edge_node_service import EdgeNodeService


@pytest.fixture
def svc():
    return EdgeNodeService()


# ── query_revenue_offline ─────────────────────────────────────────────────────

class TestQueryRevenueOffline:
    @pytest.mark.asyncio
    async def test_returns_cached_revenue(self, svc):
        await svc.cache_data("revenue:S001:2026-03-04", {
            "revenue_yuan": 12345.0,
            "is_estimate": False,
            "cached_at": "2026-03-04T22:00:00",
        })
        result = await svc.query_revenue_offline("S001", "2026-03-04")
        assert result["revenue_yuan"] == 12345.0
        assert result["is_estimate"] is False
        assert result["source"] == "local_cache"
        assert result["mode"] == "offline"

    @pytest.mark.asyncio
    async def test_falls_back_to_historical_avg(self, svc):
        await svc.cache_data("revenue_avg:S001", {"avg_yuan": 8000.0})
        result = await svc.query_revenue_offline("S001", "2099-01-01")
        assert result["revenue_yuan"] == 8000.0
        assert result["is_estimate"] is True
        assert result["source"] == "historical_avg"

    @pytest.mark.asyncio
    async def test_no_cache_returns_zero_estimate(self, svc):
        result = await svc.query_revenue_offline("S999", "2099-01-01")
        assert result["revenue_yuan"] == 0.0
        assert result["is_estimate"] is True
        assert result["mode"] == "offline"

    @pytest.mark.asyncio
    async def test_defaults_to_today_when_no_date(self, svc):
        result = await svc.query_revenue_offline("S001")
        today_str = datetime.utcnow().strftime("%Y-%m-%d")
        assert result["date"] == today_str


# ── query_inventory_offline ───────────────────────────────────────────────────

class TestQueryInventoryOffline:
    @pytest.mark.asyncio
    async def test_returns_cached_snapshot(self, svc):
        items = [
            {"item_id": "I1", "name": "鸡腿", "status": "low"},
            {"item_id": "I2", "name": "猪肉", "status": "out_of_stock"},
            {"item_id": "I3", "name": "白菜", "status": "normal"},
        ]
        await svc.cache_data("inventory_snapshot:S001", {
            "items": items,
            "snapshot_at": "2026-03-04T20:00:00",
        })
        result = await svc.query_inventory_offline("S001")
        assert result["item_count"] == 3
        assert result["low_stock_count"] == 1
        assert result["out_of_stock_count"] == 1
        assert result["source"] == "local_cache"
        assert result["mode"] == "offline"

    @pytest.mark.asyncio
    async def test_no_cache_returns_empty(self, svc):
        result = await svc.query_inventory_offline("S999_NOCACHE")
        assert result["item_count"] == 0
        assert result["items"] == []
        assert result["source"] == "no_cache"

    @pytest.mark.asyncio
    async def test_counts_critical_as_low_stock(self, svc):
        items = [
            {"item_id": "I1", "status": "critical"},
            {"item_id": "I2", "status": "critical"},
            {"item_id": "I3", "status": "low"},
        ]
        await svc.cache_data("inventory_snapshot:S002", {
            "items": items, "snapshot_at": "2026-03-04T18:00:00"
        })
        result = await svc.query_inventory_offline("S002")
        assert result["low_stock_count"] == 3   # critical + low 都计入


# ── update_revenue_cache / update_inventory_cache ────────────────────────────

class TestUpdateCache:
    @pytest.mark.asyncio
    async def test_update_revenue_cache_then_query(self, svc):
        await svc.update_revenue_cache("S003", "2026-03-04", revenue_yuan=9876.5)
        result = await svc.query_revenue_offline("S003", "2026-03-04")
        assert result["revenue_yuan"] == 9876.5
        assert result["is_estimate"] is False

    @pytest.mark.asyncio
    async def test_update_inventory_cache_then_query(self, svc):
        items = [{"item_id": "X1", "status": "out_of_stock"}]
        await svc.update_inventory_cache("S004", items)
        result = await svc.query_inventory_offline("S004")
        assert result["item_count"] == 1
        assert result["out_of_stock_count"] == 1
