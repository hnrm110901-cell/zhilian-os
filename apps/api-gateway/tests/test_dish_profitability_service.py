"""Tests for dish_profitability_service.py — Phase 6 Month 1"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock
import sys

mock_settings = MagicMock()
mock_settings.database_url = "postgresql+asyncpg://x:x@localhost/x"
mock_config_mod = MagicMock()
mock_config_mod.settings = mock_settings
sys.modules.setdefault("src.core.config", mock_config_mod)

from src.services.dish_profitability_service import (  # noqa: E402
    compute_food_cost_rate,
    compute_gross_profit,
    compute_gross_profit_margin,
    compute_avg_selling_price,
    compute_rank,
    compute_percentile,
    classify_bcg_quadrant,
    generate_dish_insight,
    build_dish_records,
    summarize_bcg,
    compute_dish_profitability,
    get_dish_profitability,
    get_bcg_summary,
    get_top_dishes,
    get_dish_trend,
    get_category_summary,
    BCG_QUADRANTS,
)


# ══════════════════════════════════════════════════════════════════════════════
# compute_food_cost_rate
# ══════════════════════════════════════════════════════════════════════════════

class TestComputeFoodCostRate:
    def test_normal(self):
        assert abs(compute_food_cost_rate(100, 38) - 38.0) < 1e-9

    def test_zero_revenue(self):
        assert compute_food_cost_rate(0, 38) == 0.0

    def test_zero_cost(self):
        assert compute_food_cost_rate(100, 0) == 0.0

    def test_full_cost(self):
        assert abs(compute_food_cost_rate(100, 100) - 100.0) < 1e-9


# ══════════════════════════════════════════════════════════════════════════════
# compute_gross_profit / compute_gross_profit_margin
# ══════════════════════════════════════════════════════════════════════════════

class TestComputeGrossProfit:
    def test_gross_profit(self):
        assert compute_gross_profit(100, 38) == 62.0

    def test_negative(self):
        assert compute_gross_profit(50, 80) == -30.0

    def test_margin_normal(self):
        assert abs(compute_gross_profit_margin(100, 38) - 62.0) < 1e-9

    def test_margin_zero_revenue(self):
        assert compute_gross_profit_margin(0, 38) == 0.0


# ══════════════════════════════════════════════════════════════════════════════
# compute_avg_selling_price
# ══════════════════════════════════════════════════════════════════════════════

class TestComputeAvgSellingPrice:
    def test_normal(self):
        assert abs(compute_avg_selling_price(1000, 40) - 25.0) < 1e-9

    def test_zero_count(self):
        assert compute_avg_selling_price(1000, 0) == 0.0


# ══════════════════════════════════════════════════════════════════════════════
# compute_rank / compute_percentile
# ══════════════════════════════════════════════════════════════════════════════

class TestComputeRank:
    def test_best(self):
        assert compute_rank(100, [60, 70, 80, 90, 100]) == 1

    def test_worst(self):
        assert compute_rank(60, [60, 70, 80, 90, 100]) == 5

    def test_empty(self):
        assert compute_rank(50, []) == 1

    def test_lower_is_better(self):
        # food_cost_rate: 30% is rank 1
        assert compute_rank(30, [30, 35, 40], higher_is_better=False) == 1
        assert compute_rank(40, [30, 35, 40], higher_is_better=False) == 3


class TestComputePercentile:
    def test_best_is_100(self):
        assert compute_percentile(100, [60, 70, 80, 90, 100]) == 100.0

    def test_worst_is_0(self):
        assert compute_percentile(60, [60, 70, 80, 90, 100]) == 0.0

    def test_single(self):
        assert compute_percentile(50, [50]) == 100.0

    def test_lower_better_best(self):
        assert compute_percentile(30, [30, 35, 40], higher_is_better=False) == 100.0


# ══════════════════════════════════════════════════════════════════════════════
# classify_bcg_quadrant
# ══════════════════════════════════════════════════════════════════════════════

class TestClassifyBcgQuadrant:
    def test_star(self):
        assert classify_bcg_quadrant(80.0, 80.0) == "star"

    def test_cash_cow(self):
        assert classify_bcg_quadrant(80.0, 20.0) == "cash_cow"

    def test_question_mark(self):
        assert classify_bcg_quadrant(20.0, 80.0) == "question_mark"

    def test_dog(self):
        assert classify_bcg_quadrant(20.0, 20.0) == "dog"

    def test_boundary_50(self):
        # Exactly at 50th percentile → high
        assert classify_bcg_quadrant(50.0, 50.0) == "star"

    def test_just_below_50(self):
        assert classify_bcg_quadrant(49.9, 49.9) == "dog"


# ══════════════════════════════════════════════════════════════════════════════
# generate_dish_insight
# ══════════════════════════════════════════════════════════════════════════════

class TestGenerateDishInsight:
    def test_contains_dish_name(self):
        insight = generate_dish_insight("红烧肉", "star", 35.0, 65.0, 120, 3600)
        assert "红烧肉" in insight

    def test_contains_label(self):
        insight = generate_dish_insight("炒青菜", "dog", 55.0, 45.0, 20, 400)
        assert "瘦狗菜" in insight or "dog" in insight.lower()

    def test_length_limit(self):
        insight = generate_dish_insight("非常非常长的菜品名称" * 5, "cash_cow", 40.0, 60.0, 50, 1500)
        assert len(insight) <= 150

    def test_all_quadrants(self):
        for q in BCG_QUADRANTS:
            insight = generate_dish_insight("测试菜", q, 38.0, 62.0, 100, 3000)
            assert isinstance(insight, str)
            assert len(insight) > 5


# ══════════════════════════════════════════════════════════════════════════════
# build_dish_records
# ══════════════════════════════════════════════════════════════════════════════

class TestBuildDishRecords:
    DISHES = [
        {"dish_id": "D001", "dish_name": "红烧肉", "category": "热菜",
         "order_count": 150, "revenue_yuan": 7500.0, "food_cost_yuan": 2625.0},
        {"dish_id": "D002", "dish_name": "炒青菜", "category": "素菜",
         "order_count": 50,  "revenue_yuan": 1000.0, "food_cost_yuan": 300.0},
        {"dish_id": "D003", "dish_name": "松露炒蛋", "category": "热菜",
         "order_count": 10,  "revenue_yuan": 800.0,  "food_cost_yuan": 480.0},
        {"dish_id": "D004", "dish_name": "白水煮菜", "category": "素菜",
         "order_count": 20,  "revenue_yuan": 400.0,  "food_cost_yuan": 240.0},
    ]

    def test_returns_correct_count(self):
        records = build_dish_records("S001", "2024-07", self.DISHES)
        assert len(records) == 4

    def test_food_cost_rate_computed(self):
        records = build_dish_records("S001", "2024-07", self.DISHES[:1])
        # 2625/7500 = 35%
        assert abs(records[0]["food_cost_rate"] - 35.0) < 0.1

    def test_bcg_assigned(self):
        records = build_dish_records("S001", "2024-07", self.DISHES)
        for r in records:
            assert r["bcg_quadrant"] in BCG_QUADRANTS

    def test_star_is_highest_pop_and_profit(self):
        # 红烧肉: highest order_count (150) + high margin (65%) → should be star
        records = build_dish_records("S001", "2024-07", self.DISHES)
        hongshao = next(r for r in records if r["dish_id"] == "D001")
        assert hongshao["bcg_quadrant"] == "star"

    def test_empty_input(self):
        assert build_dish_records("S001", "2024-07", []) == []

    def test_rank_1_is_best(self):
        records = build_dish_records("S001", "2024-07", self.DISHES)
        hongshao = next(r for r in records if r["dish_id"] == "D001")
        assert hongshao["popularity_rank"] == 1

    def test_insight_generated(self):
        records = build_dish_records("S001", "2024-07", self.DISHES[:1])
        assert isinstance(records[0]["insight"], str)
        assert len(records[0]["insight"]) > 0


# ══════════════════════════════════════════════════════════════════════════════
# summarize_bcg
# ══════════════════════════════════════════════════════════════════════════════

class TestSummarizeBcg:
    def test_all_quadrants_present(self):
        records = [
            {"bcg_quadrant": "star",          "revenue_yuan": 5000, "gross_profit_yuan": 3000},
            {"bcg_quadrant": "cash_cow",       "revenue_yuan": 3000, "gross_profit_yuan": 1200},
            {"bcg_quadrant": "question_mark",  "revenue_yuan": 1000, "gross_profit_yuan": 700},
            {"bcg_quadrant": "dog",            "revenue_yuan": 500,  "gross_profit_yuan": 100},
        ]
        summary = summarize_bcg(records)
        for q in BCG_QUADRANTS:
            assert q in summary

    def test_revenue_share(self):
        records = [
            {"bcg_quadrant": "star",    "revenue_yuan": 8000, "gross_profit_yuan": 5000},
            {"bcg_quadrant": "cash_cow","revenue_yuan": 2000, "gross_profit_yuan": 600},
        ]
        summary = summarize_bcg(records)
        assert abs(summary["star"]["revenue_share_pct"] - 80.0) < 0.1

    def test_empty(self):
        summary = summarize_bcg([])
        for q in BCG_QUADRANTS:
            assert summary[q]["count"] == 0


# ══════════════════════════════════════════════════════════════════════════════
# DB 层
# ══════════════════════════════════════════════════════════════════════════════

def _make_db(calls: list):
    call_idx = [0]

    async def mock_execute(stmt, params=None):
        idx = call_idx[0]
        call_idx[0] += 1
        val = calls[idx] if idx < len(calls) else []
        r = MagicMock()
        if val is None or val == []:
            r.fetchone.return_value = None
            r.fetchall.return_value = []
        elif isinstance(val, list):
            r.fetchall.return_value = val
            r.fetchone.return_value = val[0] if val else None
        else:
            r.fetchone.return_value = val
            r.fetchall.return_value = [val]
        return r

    db = MagicMock()
    db.execute = mock_execute
    db.commit = AsyncMock()
    return db


class TestComputeDishProfitability:
    @pytest.mark.asyncio
    async def test_no_data(self):
        db = _make_db([[]])
        result = await compute_dish_profitability(db, "S001", "2024-07")
        assert result["dish_count"] == 0

    @pytest.mark.asyncio
    async def test_two_dishes(self):
        # Raw data: (dish_id, dish_name, category, order_count, revenue_yuan, food_cost_yuan)
        raw = [
            ("D001", "红烧肉", "热菜", 150, 7500.0, 2625.0),
            ("D002", "炒青菜", "素菜",  50, 1000.0,  300.0),
        ]
        # 1 fetch + 2 upserts
        db = _make_db([raw, None, None])
        result = await compute_dish_profitability(db, "S001", "2024-07")
        assert result["dish_count"] == 2
        assert "bcg_summary" in result


class TestGetDishProfitability:
    @pytest.mark.asyncio
    async def test_returns_list(self):
        rows = [
            ("D001", "红烧肉", "热菜", 150, 50.0, 7500.0,
             2625.0, 35.0, 4875.0, 65.0, 1, 1, 100.0, 100.0, "star"),
        ]
        db = _make_db([rows])
        dishes = await get_dish_profitability(db, "S001", "2024-07")
        assert len(dishes) == 1
        assert dishes[0]["dish_id"] == "D001"
        assert dishes[0]["bcg_quadrant"] == "star"
        assert dishes[0]["bcg_label"] == "明星菜"

    @pytest.mark.asyncio
    async def test_empty(self):
        db = _make_db([[]])
        dishes = await get_dish_profitability(db, "S001", "2024-07")
        assert dishes == []


class TestGetBcgSummary:
    @pytest.mark.asyncio
    async def test_returns_quadrants(self):
        rows = [
            ("star",         5, 8000.0, 5200.0, 65.0, 35.0),
            ("cash_cow",     3, 4000.0, 1600.0, 40.0, 60.0),
            ("question_mark",2, 1500.0, 1050.0, 70.0, 30.0),
            ("dog",          4,  500.0,  150.0, 30.0, 70.0),
        ]
        db = _make_db([rows])
        summary = await get_bcg_summary(db, "S001", "2024-07")
        assert len(summary["by_quadrant"]) == 4
        star = next(q for q in summary["by_quadrant"] if q["quadrant"] == "star")
        assert star["dish_count"] == 5
        assert abs(star["avg_gpm"] - 65.0) < 0.1

    @pytest.mark.asyncio
    async def test_fills_missing_quadrants(self):
        rows = [("star", 3, 5000.0, 3000.0, 60.0, 40.0)]
        db = _make_db([rows])
        summary = await get_bcg_summary(db, "S001", "2024-07")
        quadrant_keys = {q["quadrant"] for q in summary["by_quadrant"]}
        assert quadrant_keys == set(BCG_QUADRANTS)


class TestGetTopDishes:
    @pytest.mark.asyncio
    async def test_returns_top_list(self):
        rows = [
            ("D001", "红烧肉", "热菜", 150, 50.0, 7500.0,
             2625.0, 35.0, 4875.0, 65.0, 1, 1, 100.0, 100.0, "star"),
            ("D002", "炒青菜", "素菜",  50, 20.0, 1000.0,
              300.0, 30.0,  700.0, 70.0, 2, 2,  50.0,  75.0, "question_mark"),
        ]
        db = _make_db([rows])
        dishes = await get_top_dishes(db, "S001", "2024-07", metric="gross_profit_yuan", limit=5)
        assert len(dishes) == 2


class TestGetDishTrend:
    @pytest.mark.asyncio
    async def test_returns_ascending(self):
        rows = [
            ("2024-07", 150, 7500.0, 35.0, 4875.0, 65.0, "star", 1, 1),
            ("2024-06", 130, 6500.0, 36.0, 4160.0, 64.0, "star", 1, 2),
            ("2024-05", 120, 6000.0, 37.0, 3780.0, 63.0, "cash_cow", 1, 3),
        ]
        db = _make_db([rows])
        trend = await get_dish_trend(db, "S001", "D001", periods=6)
        assert trend[0]["period"] == "2024-05"  # reversed to ascending
        assert trend[-1]["period"] == "2024-07"

    @pytest.mark.asyncio
    async def test_empty(self):
        db = _make_db([[]])
        trend = await get_dish_trend(db, "S001", "D999")
        assert trend == []


class TestGetCategorySummary:
    @pytest.mark.asyncio
    async def test_returns_categories(self):
        rows = [
            ("热菜", 8, 500, 20000.0, 13000.0, 65.0, 35.0),
            ("素菜", 5, 200,  4000.0,  2800.0, 70.0, 30.0),
        ]
        db = _make_db([rows])
        cats = await get_category_summary(db, "S001", "2024-07")
        assert len(cats) == 2
        assert cats[0]["category"] == "热菜"
        assert cats[0]["total_revenue"] == 20000.0

    @pytest.mark.asyncio
    async def test_empty(self):
        db = _make_db([[]])
        cats = await get_category_summary(db, "S001", "2024-07")
        assert cats == []
