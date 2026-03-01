"""
GET /api/v1/menu/recommendations — HTTP 端点测试

覆盖：
- 正常请求 → 200，响应结构含 store_id / total / recommendations
- limit 下界违规（0）→ 400
- limit 上界违规（51）→ 400
- limit=1 正好合法 → 200
- limit=50 正好合法 → 200（截断 mock 返回值）
- MenuRanker.rank 抛出异常 → 500
- recommendations 字段包含 rank / dish_id / dish_name / scores.total
"""
import sys
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.modules.setdefault("src.services.agent_service", MagicMock())

from src.api.menu import router
from src.models.menu_rank import DishScore, RankedDish


# ---------------------------------------------------------------------------
# App fixture
# ---------------------------------------------------------------------------

_app = FastAPI()
_app.include_router(router)
client = TestClient(_app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ranked_dish(rank: int = 1, dish_id: str = "D001", name: str = "招牌红烧肉"):
    score = DishScore(
        dish_id=dish_id,
        dish_name=name,
        trend_score=0.8,
        margin_score=0.7,
        stock_score=0.9,
        time_slot_score=0.6,
        low_refund_score=0.95,
    ).compute_total()
    return RankedDish(
        rank=rank,
        dish_id=dish_id,
        dish_name=name,
        category="肉类",
        price=Decimal("68.00"),
        score=score,
        highlight="销量持续上升",
    )


def _mock_ranker(dishes=None):
    """Return a context-manager-compatible patch for MenuRanker."""
    ranker = MagicMock()
    ranker.rank = AsyncMock(return_value=dishes or [_make_ranked_dish()])
    return ranker


# ---------------------------------------------------------------------------
# 1. 正常请求 → 200
# ---------------------------------------------------------------------------

class TestSuccessResponse:
    def test_returns_200(self):
        with patch("src.api.menu.MenuRanker", return_value=_mock_ranker()):
            resp = client.get("/api/v1/menu/recommendations?store_id=STORE_001")
        assert resp.status_code == 200

    def test_response_has_store_id(self):
        with patch("src.api.menu.MenuRanker", return_value=_mock_ranker()):
            resp = client.get("/api/v1/menu/recommendations?store_id=STORE_001")
        assert resp.json()["store_id"] == "STORE_001"

    def test_response_has_total(self):
        with patch("src.api.menu.MenuRanker", return_value=_mock_ranker()):
            resp = client.get("/api/v1/menu/recommendations?store_id=STORE_001")
        assert resp.json()["total"] == 1

    def test_recommendations_has_rank_field(self):
        with patch("src.api.menu.MenuRanker", return_value=_mock_ranker()):
            resp = client.get("/api/v1/menu/recommendations?store_id=STORE_001")
        rec = resp.json()["recommendations"][0]
        assert rec["rank"] == 1

    def test_recommendations_has_scores_total(self):
        with patch("src.api.menu.MenuRanker", return_value=_mock_ranker()):
            resp = client.get("/api/v1/menu/recommendations?store_id=STORE_001")
        scores = resp.json()["recommendations"][0]["scores"]
        assert "total" in scores
        assert 0.0 <= scores["total"] <= 1.0

    def test_recommendations_has_all_score_factors(self):
        with patch("src.api.menu.MenuRanker", return_value=_mock_ranker()):
            resp = client.get("/api/v1/menu/recommendations?store_id=STORE_001")
        scores = resp.json()["recommendations"][0]["scores"]
        for key in ("trend", "margin", "stock", "time_slot", "low_refund"):
            assert key in scores

    def test_default_limit_is_10(self):
        dishes = [_make_ranked_dish(rank=i, dish_id=f"D{i:03d}", name=f"菜{i}") for i in range(1, 16)]
        ranker = MagicMock()
        # The endpoint passes limit=10 by default to ranker.rank
        ranker.rank = AsyncMock(return_value=dishes[:10])
        with patch("src.api.menu.MenuRanker", return_value=ranker):
            resp = client.get("/api/v1/menu/recommendations?store_id=S1")
        ranker.rank.assert_awaited_once_with(store_id="S1", limit=10)


# ---------------------------------------------------------------------------
# 2. limit 验证
# ---------------------------------------------------------------------------

class TestLimitValidation:
    def test_limit_zero_returns_400(self):
        resp = client.get("/api/v1/menu/recommendations?store_id=S1&limit=0")
        assert resp.status_code == 400

    def test_limit_51_returns_400(self):
        resp = client.get("/api/v1/menu/recommendations?store_id=S1&limit=51")
        assert resp.status_code == 400

    def test_limit_1_returns_200(self):
        with patch("src.api.menu.MenuRanker", return_value=_mock_ranker()):
            resp = client.get("/api/v1/menu/recommendations?store_id=S1&limit=1")
        assert resp.status_code == 200

    def test_limit_50_returns_200(self):
        with patch("src.api.menu.MenuRanker", return_value=_mock_ranker()):
            resp = client.get("/api/v1/menu/recommendations?store_id=S1&limit=50")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 3. MenuRanker 抛出异常 → 500
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_ranker_exception_returns_500(self):
        ranker = MagicMock()
        ranker.rank = AsyncMock(side_effect=RuntimeError("DB connection lost"))
        with patch("src.api.menu.MenuRanker", return_value=ranker):
            resp = client.get("/api/v1/menu/recommendations?store_id=S1")
        assert resp.status_code == 500

    def test_500_response_has_message(self):
        ranker = MagicMock()
        ranker.rank = AsyncMock(side_effect=RuntimeError("DB connection lost"))
        with patch("src.api.menu.MenuRanker", return_value=ranker):
            resp = client.get("/api/v1/menu/recommendations?store_id=S1")
        assert "message" in resp.json()["detail"]
