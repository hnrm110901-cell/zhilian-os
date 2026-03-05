"""
StoreHealthService 单元测试

覆盖：
  - 纯函数：compute_health_score / classify_health
  - 维度得分纯函数：_score_revenue_completion / _score_table_turnover /
                    _score_cost_rate / _score_complaint_rate / _score_staff_efficiency
  - 集成：StoreHealthService.get_store_score（mock DB）
         StoreHealthService.get_multi_store_scores（mock DB）
  - 缺失维度降级归一化
"""

import os
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("APP_ENV", "test")

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.store_health_service import (
    StoreHealthService,
    _score_complaint_rate,
    _score_cost_rate,
    _score_revenue_completion,
    _score_staff_efficiency,
    _score_table_turnover,
    classify_health,
    compute_health_score,
)

# ════════════════════════════════════════════════════════════════════════════════
# 纯函数测试
# ════════════════════════════════════════════════════════════════════════════════

class TestComputeHealthScore:
    def test_all_dimensions_perfect(self):
        scores = {k: 100.0 for k in
                  ["revenue_completion", "table_turnover", "cost_rate", "complaint_rate", "staff_efficiency"]}
        assert compute_health_score(scores) == 100.0

    def test_all_dimensions_zero(self):
        scores = {k: 0.0 for k in
                  ["revenue_completion", "table_turnover", "cost_rate", "complaint_rate", "staff_efficiency"]}
        assert compute_health_score(scores) == 0.0

    def test_all_none_returns_50(self):
        scores = {k: None for k in
                  ["revenue_completion", "table_turnover", "cost_rate", "complaint_rate", "staff_efficiency"]}
        assert compute_health_score(scores) == 50.0

    def test_partial_none_normalizes_correctly(self):
        # 只有 revenue_completion(30%) 和 cost_rate(25%) 有数据
        scores = {
            "revenue_completion": 100.0,
            "table_turnover":     None,
            "cost_rate":          0.0,
            "complaint_rate":     None,
            "staff_efficiency":   None,
        }
        # normalized: 100 * 0.30/(0.30+0.25) + 0 * 0.25/(0.30+0.25)
        expected = round(100.0 * 0.30 / 0.55, 1)
        assert compute_health_score(scores) == expected

    def test_single_dimension_returns_that_score(self):
        scores = {
            "revenue_completion": 78.0,
            "table_turnover":     None,
            "cost_rate":          None,
            "complaint_rate":     None,
            "staff_efficiency":   None,
        }
        assert compute_health_score(scores) == 78.0

    def test_mixed_scores_weighted(self):
        scores = {
            "revenue_completion": 80.0,   # weight 0.30
            "table_turnover":     60.0,   # weight 0.20
            "cost_rate":          100.0,  # weight 0.25
            "complaint_rate":     40.0,   # weight 0.15
            "staff_efficiency":   20.0,   # weight 0.10
        }
        expected = round(80*0.30 + 60*0.20 + 100*0.25 + 40*0.15 + 20*0.10, 1)
        assert compute_health_score(scores) == expected


class TestClassifyHealth:
    def test_excellent(self):
        assert classify_health(85.0) == "excellent"
        assert classify_health(100.0) == "excellent"

    def test_good(self):
        assert classify_health(70.0) == "good"
        assert classify_health(84.9) == "good"

    def test_warning(self):
        assert classify_health(50.0) == "warning"
        assert classify_health(69.9) == "warning"

    def test_critical(self):
        assert classify_health(0.0) == "critical"
        assert classify_health(49.9) == "critical"


class TestScoreRevenuCompletion:
    def test_on_target(self):
        # monthly_target=30000 yuan, month with 30 days → daily_target=1000 yuan = 100000 fen
        s = _score_revenue_completion(100_000.0, 30_000.0, date(2026, 3, 15))
        assert s is not None
        assert abs(s - 100.0) < 0.1

    def test_half_target(self):
        s = _score_revenue_completion(50_000.0, 30_000.0, date(2026, 3, 15))
        assert s is not None
        assert abs(s - 50.0) < 1.0

    def test_over_target_capped_at_100(self):
        s = _score_revenue_completion(999_999.0, 30_000.0, date(2026, 3, 15))
        assert s == 100.0

    def test_no_target_returns_none(self):
        assert _score_revenue_completion(10_000.0, None, date(2026, 3, 15)) is None
        assert _score_revenue_completion(10_000.0, 0.0, date(2026, 3, 15)) is None


class TestScoreTableTurnover:
    def test_meets_target(self):
        # 2 distinct tables, 1 seat → turns=2 → 100%
        s = _score_table_turnover(2, 1)
        assert s == 100.0

    def test_below_target(self):
        # 1 turn out of 2 target → 50%
        s = _score_table_turnover(1, 1)
        assert s is not None and s < 100.0

    def test_no_seats_returns_none(self):
        assert _score_table_turnover(3, None) is None
        assert _score_table_turnover(3, 0) is None

    def test_capped_at_100(self):
        assert _score_table_turnover(1000, 1) == 100.0


class TestScoreCostRate:
    def test_ok_is_100(self):
        assert _score_cost_rate("ok") == 100.0

    def test_warning_is_60(self):
        assert _score_cost_rate("warning") == 60.0

    def test_critical_is_20(self):
        assert _score_cost_rate("critical") == 20.0

    def test_none_returns_none(self):
        assert _score_cost_rate(None) is None

    def test_unknown_status_returns_50(self):
        assert _score_cost_rate("unknown_xyz") == 50.0


class TestScoreComplaintRate:
    def test_no_complaints(self):
        assert _score_complaint_rate(0, 10) == 100.0

    def test_half_complaints(self):
        # fail_rate=0.5 → 100 - 0.5*200 = 0
        assert _score_complaint_rate(5, 10) == 0.0

    def test_clamped_at_zero(self):
        # fail_rate=1.0 → 100 - 200 = -100 → clamped to 0
        assert _score_complaint_rate(10, 10) == 0.0

    def test_no_inspections_returns_none(self):
        assert _score_complaint_rate(0, 0) is None


class TestScoreStaffEfficiency:
    def test_meets_target(self):
        # 500 yuan revenue, 1 staff → rev_per_staff=500 → score=100
        s = _score_staff_efficiency(500.0, 1)
        assert s == 100.0

    def test_half_target(self):
        s = _score_staff_efficiency(250.0, 1)
        assert s is not None and abs(s - 50.0) < 0.1

    def test_no_staff_returns_none(self):
        assert _score_staff_efficiency(500.0, 0) is None

    def test_no_revenue_returns_none(self):
        assert _score_staff_efficiency(0.0, 5) is None

    def test_capped_at_100(self):
        assert _score_staff_efficiency(999_999.0, 1) == 100.0


# ════════════════════════════════════════════════════════════════════════════════
# 集成测试（mock DB）
# ════════════════════════════════════════════════════════════════════════════════

def _make_store(store_id="S001", monthly_revenue_target=30000.0, seats=20):
    store = MagicMock()
    store.id = store_id
    store.name = f"测试门店{store_id}"
    store.monthly_revenue_target = monthly_revenue_target
    store.seats = seats
    store.is_active = True
    return store


def _make_db_mock(store, revenue_fen=120000.0, distinct_tables=10,
                  staff_count=5, fc_status="ok", qi_total=20, qi_fail=1):
    db = AsyncMock()

    # db.get(Store, store_id) → store
    db.get = AsyncMock(return_value=store)

    # orders 查询（revenue_fen + distinct_tables）
    rev_row = MagicMock()
    rev_row.revenue_fen = revenue_fen
    rev_row.distinct_tables = distinct_tables
    rev_result = MagicMock()
    rev_result.one = MagicMock(return_value=rev_row)

    # employees 查询（staff_count）
    staff_result = MagicMock()
    staff_result.scalar = MagicMock(return_value=staff_count)

    # quality_inspections 查询（qi_total + qi_fail）
    qi_row = MagicMock()
    qi_row.total = qi_total
    qi_row.fail_count = qi_fail
    qi_result = MagicMock()
    qi_result.one = MagicMock(return_value=qi_row)

    # execute 返回顺序：orders → employees → qi（中间 FoodCostService 单独 mock）
    db.execute = AsyncMock(side_effect=[rev_result, staff_result, qi_result])

    return db, fc_status


@pytest.mark.asyncio
async def test_get_store_score_returns_valid_structure():
    """get_store_score 返回含所有必需字段的 dict"""
    store = _make_store()
    db, fc_status = _make_db_mock(store)

    with patch(
        "src.services.store_health_service.FoodCostService.get_store_food_cost_variance",
        new_callable=AsyncMock,
        return_value={"variance_status": "ok"},
    ):
        result = await StoreHealthService.get_store_score("S001", date(2026, 3, 5), db)

    assert "score" in result
    assert "level" in result
    assert "dimensions" in result
    assert "weakest_dimension" in result
    assert "revenue_yuan" in result
    assert 0.0 <= result["score"] <= 100.0
    assert result["level"] in ("excellent", "good", "warning", "critical")


@pytest.mark.asyncio
async def test_get_store_score_store_not_found():
    """门店不存在时返回默认兜底结果（score=50, level=warning）"""
    db = AsyncMock()
    db.get = AsyncMock(return_value=None)

    result = await StoreHealthService.get_store_score("UNKNOWN", date(2026, 3, 5), db)

    assert result["score"] == 50.0
    assert result["level"] == "warning"


@pytest.mark.asyncio
async def test_get_store_score_cost_failure_degrades_gracefully():
    """FoodCostService 失败时成本率维度为 None，仍返回有效评分"""
    store = _make_store()
    db, _ = _make_db_mock(store)

    with patch(
        "src.services.store_health_service.FoodCostService.get_store_food_cost_variance",
        new_callable=AsyncMock,
        side_effect=RuntimeError("DB 超时"),
    ):
        result = await StoreHealthService.get_store_score("S001", date(2026, 3, 5), db)

    assert isinstance(result["score"], float)
    assert result["dimensions"]["cost_rate"]["score"] is None


@pytest.mark.asyncio
async def test_get_multi_store_scores_ranked():
    """get_multi_store_scores 返回按分数降序排名的列表"""
    store_a = _make_store("SA", monthly_revenue_target=30000.0, seats=20)
    store_b = _make_store("SB", monthly_revenue_target=30000.0, seats=20)

    calls = []

    async def mock_get_score(store_id, target_date, db):
        if store_id == "SA":
            return {"store_id": "SA", "score": 90.0, "level": "excellent"}
        return {"store_id": "SB", "score": 55.0, "level": "warning"}

    db = AsyncMock()
    with patch.object(StoreHealthService, "get_store_score", side_effect=mock_get_score):
        results = await StoreHealthService.get_multi_store_scores(
            ["SA", "SB"], date(2026, 3, 5), db
        )

    assert results[0]["store_id"] == "SA"
    assert results[0]["rank"] == 1
    assert results[1]["store_id"] == "SB"
    assert results[1]["rank"] == 2


@pytest.mark.asyncio
async def test_get_multi_store_scores_skips_failed_store():
    """单店查询失败时静默跳过，不影响其他门店"""
    async def mock_get_score(store_id, target_date, db):
        if store_id == "S_BAD":
            raise RuntimeError("模拟失败")
        return {"store_id": store_id, "score": 80.0, "level": "good"}

    db = AsyncMock()
    with patch.object(StoreHealthService, "get_store_score", side_effect=mock_get_score):
        results = await StoreHealthService.get_multi_store_scores(
            ["S001", "S_BAD", "S002"], date(2026, 3, 5), db
        )

    # S_BAD 被静默跳过
    assert len(results) == 2
    store_ids = [r["store_id"] for r in results]
    assert "S_BAD" not in store_ids
