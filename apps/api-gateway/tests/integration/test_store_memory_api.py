"""
门店记忆层 API 端点测试

覆盖：
GET  /api/v1/stores/{store_id}/memory
  - 缓存命中 → 200，响应含 store_id / updated_at / peak_patterns / anomaly_patterns
  - 缓存未命中（None）→ 404，detail.hint 包含 refresh URL
  - 服务异常 → 404（memory=None 时的正常分支，不是500）

POST /api/v1/stores/{store_id}/memory/refresh
  - 成功刷新 → 200，含 status=refreshed / confidence / data_coverage_days
  - lookback_days 参数透传
  - brand_id 参数透传
  - 服务抛出异常 → 500
"""
import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.modules.setdefault("src.services.agent_service", MagicMock())

from src.api.store_memory import router
from src.models.store_memory import (
    AnomalyPattern, DishHealth, PeakHourPattern, StaffProfile, StoreMemory,
)


# ---------------------------------------------------------------------------
# App fixture
# ---------------------------------------------------------------------------

_app = FastAPI()
_app.include_router(router)
client = TestClient(_app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_memory(store_id: str = "STORE_001", confidence: str = "high") -> StoreMemory:
    return StoreMemory(
        store_id=store_id,
        brand_id="BRAND_A",
        updated_at=datetime(2026, 3, 1, 2, 0, 0),
        confidence=confidence,
        data_coverage_days=30,
        peak_patterns=[
            PeakHourPattern(hour=12, avg_orders=3.5, avg_revenue=1200.0, avg_customers=8.0, is_peak=True)
        ],
        staff_profiles=[],
        dish_health=[],
        anomaly_patterns=[],
    )


def _mock_service(memory=None, refresh_memory=None):
    svc = MagicMock()
    svc.get_memory = AsyncMock(return_value=memory)
    svc.refresh_store_memory = AsyncMock(return_value=refresh_memory or _make_memory())
    return svc


# ---------------------------------------------------------------------------
# GET /api/v1/stores/{store_id}/memory
# ---------------------------------------------------------------------------

class TestGetMemory:
    def test_cache_hit_returns_200(self):
        with patch("src.api.store_memory.StoreMemoryService", return_value=_mock_service(_make_memory())):
            resp = client.get("/api/v1/stores/STORE_001/memory")
        assert resp.status_code == 200

    def test_response_contains_store_id(self):
        with patch("src.api.store_memory.StoreMemoryService", return_value=_mock_service(_make_memory())):
            resp = client.get("/api/v1/stores/STORE_001/memory")
        assert resp.json()["store_id"] == "STORE_001"

    def test_response_contains_updated_at(self):
        with patch("src.api.store_memory.StoreMemoryService", return_value=_mock_service(_make_memory())):
            resp = client.get("/api/v1/stores/STORE_001/memory")
        assert "updated_at" in resp.json()

    def test_response_contains_confidence(self):
        with patch("src.api.store_memory.StoreMemoryService", return_value=_mock_service(_make_memory())):
            resp = client.get("/api/v1/stores/STORE_001/memory")
        assert resp.json()["confidence"] == "high"

    def test_response_contains_peak_patterns(self):
        with patch("src.api.store_memory.StoreMemoryService", return_value=_mock_service(_make_memory())):
            resp = client.get("/api/v1/stores/STORE_001/memory")
        assert len(resp.json()["peak_patterns"]) == 1
        assert resp.json()["peak_patterns"][0]["hour"] == 12

    def test_cache_miss_returns_404(self):
        with patch("src.api.store_memory.StoreMemoryService", return_value=_mock_service(None)):
            resp = client.get("/api/v1/stores/STORE_404/memory")
        assert resp.status_code == 404

    def test_404_detail_contains_hint(self):
        with patch("src.api.store_memory.StoreMemoryService", return_value=_mock_service(None)):
            resp = client.get("/api/v1/stores/STORE_404/memory")
        detail = resp.json()["detail"]
        assert "hint" in detail
        assert "refresh" in detail["hint"]

    def test_empty_anomaly_patterns_is_list(self):
        with patch("src.api.store_memory.StoreMemoryService", return_value=_mock_service(_make_memory())):
            resp = client.get("/api/v1/stores/STORE_001/memory")
        assert isinstance(resp.json()["anomaly_patterns"], list)


# ---------------------------------------------------------------------------
# POST /api/v1/stores/{store_id}/memory/refresh
# ---------------------------------------------------------------------------

class TestRefreshMemory:
    def test_refresh_returns_200(self):
        with patch("src.api.store_memory.StoreMemoryService", return_value=_mock_service()):
            resp = client.post("/api/v1/stores/STORE_001/memory/refresh")
        assert resp.status_code == 200

    def test_refresh_status_is_refreshed(self):
        with patch("src.api.store_memory.StoreMemoryService", return_value=_mock_service()):
            resp = client.post("/api/v1/stores/STORE_001/memory/refresh")
        assert resp.json()["status"] == "refreshed"

    def test_refresh_response_has_confidence(self):
        with patch("src.api.store_memory.StoreMemoryService", return_value=_mock_service()):
            resp = client.post("/api/v1/stores/STORE_001/memory/refresh")
        assert resp.json()["confidence"] == "high"

    def test_refresh_response_has_data_coverage_days(self):
        with patch("src.api.store_memory.StoreMemoryService", return_value=_mock_service()):
            resp = client.post("/api/v1/stores/STORE_001/memory/refresh")
        assert resp.json()["data_coverage_days"] == 30

    def test_lookback_days_param_passed_to_service(self):
        svc = _mock_service()
        with patch("src.api.store_memory.StoreMemoryService", return_value=svc):
            client.post("/api/v1/stores/STORE_001/memory/refresh?lookback_days=60")
        svc.refresh_store_memory.assert_awaited_once_with(
            store_id="STORE_001", brand_id=None, lookback_days=60
        )

    def test_brand_id_param_passed_to_service(self):
        svc = _mock_service()
        with patch("src.api.store_memory.StoreMemoryService", return_value=svc):
            client.post("/api/v1/stores/STORE_001/memory/refresh?brand_id=BRAND_X")
        svc.refresh_store_memory.assert_awaited_once_with(
            store_id="STORE_001", brand_id="BRAND_X", lookback_days=30
        )

    def test_service_exception_returns_500(self):
        svc = MagicMock()
        svc.refresh_store_memory = AsyncMock(side_effect=RuntimeError("Redis down"))
        with patch("src.api.store_memory.StoreMemoryService", return_value=svc):
            resp = client.post("/api/v1/stores/STORE_001/memory/refresh")
        assert resp.status_code == 500

    def test_500_has_message(self):
        svc = MagicMock()
        svc.refresh_store_memory = AsyncMock(side_effect=RuntimeError("Redis down"))
        with patch("src.api.store_memory.StoreMemoryService", return_value=svc):
            resp = client.post("/api/v1/stores/STORE_001/memory/refresh")
        assert "message" in resp.json()["detail"]
