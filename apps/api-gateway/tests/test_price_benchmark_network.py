"""
跨客户食材价格基准网络 — 单元测试

覆盖：
  - _percentile / _rank_percentile: 边界条件
  - classify_price: 4级分类
  - aggregate_price_benchmark: 聚合/隐私阈值/排序
  - generate_supplier_suggestions: 仅expensive+生成/排序
  - compute_total_saving_potential: 有/无用量
  - generate_price_report: 端到端
"""
import os
for _k, _v in {
    "DATABASE_URL":          "postgresql+asyncpg://test:test@localhost/test",
    "REDIS_URL":             "redis://localhost:6379/0",
    "CELERY_BROKER_URL":     "redis://localhost:6379/0",
    "CELERY_RESULT_BACKEND": "redis://localhost:6379/0",
    "SECRET_KEY":            "test-secret-key",
    "JWT_SECRET":            "test-jwt-secret",
}.items():
    os.environ.setdefault(_k, _v)

import pytest
from src.services.price_benchmark_network import (
    PriceDataPoint,
    _percentile,
    _rank_percentile,
    classify_price,
    aggregate_price_benchmark,
    generate_supplier_suggestions,
    compute_total_saving_potential,
    generate_price_report,
)


def _dp(name="鲈鱼", city="上海", unit="kg", cost=1800, cat="seafood", date="2026-03"):
    return PriceDataPoint(
        ingredient_name=name, category=cat, city=city,
        unit=unit, unit_cost_fen=cost, purchase_date=date,
    )


# ── _percentile ──

class TestPercentile:
    def test_empty(self):
        assert _percentile([], 50) == 0

    def test_single(self):
        assert _percentile([100], 50) == 100

    def test_p25(self):
        vals = [10, 20, 30, 40, 50, 60, 70, 80]
        p25 = _percentile(vals, 25)
        assert p25 == 20

    def test_p50(self):
        vals = [10, 20, 30, 40, 50, 60, 70, 80]
        p50 = _percentile(vals, 50)
        assert p50 == 40

    def test_p75(self):
        vals = [10, 20, 30, 40, 50, 60, 70, 80]
        p75 = _percentile(vals, 75)
        assert p75 == 60


# ── _rank_percentile ──

class TestRankPercentile:
    def test_empty(self):
        assert _rank_percentile(100, []) == 50.0

    def test_cheapest(self):
        rank = _rank_percentile(10, [10, 20, 30, 40, 50])
        assert rank < 20

    def test_most_expensive(self):
        rank = _rank_percentile(50, [10, 20, 30, 40, 50])
        assert rank > 80


# ── classify_price ──

class TestClassifyPrice:
    def test_cheap(self):
        assert classify_price(10) == "cheap"

    def test_cheap_boundary(self):
        assert classify_price(25) == "cheap"

    def test_fair(self):
        assert classify_price(40) == "fair"

    def test_fair_boundary(self):
        assert classify_price(60) == "fair"

    def test_expensive(self):
        assert classify_price(70) == "expensive"

    def test_expensive_boundary(self):
        assert classify_price(85) == "expensive"

    def test_very_expensive(self):
        assert classify_price(95) == "very_expensive"


# ── aggregate_price_benchmark ──

class TestAggregateBenchmark:
    def _make_pool(self, n=8, base_cost=1800, name="鲈鱼"):
        """生成 n 条匿名价格数据"""
        return [_dp(name=name, cost=base_cost + i * 100) for i in range(n)]

    def test_basic_aggregation(self):
        pool = self._make_pool(8)
        your = [_dp(cost=2200)]
        results = aggregate_price_benchmark(pool, your)
        assert len(results) == 1
        r = results[0]
        assert r.ingredient_name == "鲈鱼"
        assert r.sample_count == 8
        assert r.p25_fen > 0
        assert r.p50_fen > 0
        assert r.p75_fen > 0

    def test_privacy_threshold(self):
        """少于5家客户不输出"""
        pool = self._make_pool(4)
        your = [_dp(cost=2000)]
        results = aggregate_price_benchmark(pool, your)
        assert len(results) == 0

    def test_custom_min_samples(self):
        pool = self._make_pool(3)
        your = [_dp(cost=2000)]
        results = aggregate_price_benchmark(pool, your, min_samples=3)
        assert len(results) == 1

    def test_no_your_ingredient(self):
        """你没买的食材不输出"""
        pool = self._make_pool(8, name="鲈鱼")
        your = [_dp(name="五花肉", cost=1500, cat="meat")]
        results = aggregate_price_benchmark(pool, your)
        assert len(results) == 0

    def test_sorted_by_saving(self):
        pool_a = self._make_pool(8, base_cost=1000, name="A")
        pool_b = self._make_pool(8, base_cost=500, name="B")
        your = [_dp(name="A", cost=2000), _dp(name="B", cost=2000)]
        results = aggregate_price_benchmark(pool_a + pool_b, your)
        assert len(results) == 2
        assert results[0].saving_potential_fen >= results[1].saving_potential_fen

    def test_verdict_assigned(self):
        pool = self._make_pool(8)
        your = [_dp(cost=2500)]  # very expensive
        results = aggregate_price_benchmark(pool, your)
        assert results[0].verdict in ("cheap", "fair", "expensive", "very_expensive")

    def test_multiple_cities_separate(self):
        """不同城市分开聚合"""
        pool_sh = [_dp(city="上海", cost=1800 + i * 100) for i in range(6)]
        pool_bj = [_dp(city="北京", cost=2000 + i * 100) for i in range(6)]
        your = [_dp(city="上海", cost=2200)]
        results = aggregate_price_benchmark(pool_sh + pool_bj, your)
        assert len(results) == 1
        assert results[0].city == "上海"


# ── generate_supplier_suggestions ──

class TestSupplierSuggestions:
    def _benchmarks(self):
        pool = [_dp(cost=1000 + i * 200) for i in range(10)]
        your = [_dp(cost=2800)]
        return aggregate_price_benchmark(pool, your)

    def test_generates_for_expensive(self):
        benchmarks = self._benchmarks()
        suggestions = generate_supplier_suggestions(benchmarks)
        assert len(suggestions) >= 1
        assert suggestions[0].saving_pct > 0

    def test_no_suggestions_for_cheap(self):
        pool = [_dp(cost=1800 + i * 100) for i in range(10)]
        your = [_dp(cost=1800)]  # cheapest
        benchmarks = aggregate_price_benchmark(pool, your)
        suggestions = generate_supplier_suggestions(benchmarks)
        assert len(suggestions) == 0

    def test_top_n_limit(self):
        benchmarks = self._benchmarks()
        suggestions = generate_supplier_suggestions(benchmarks, top_n=1)
        assert len(suggestions) <= 1

    def test_suggestion_text(self):
        benchmarks = self._benchmarks()
        suggestions = generate_supplier_suggestions(benchmarks)
        if suggestions:
            assert "鲈鱼" in suggestions[0].suggestion
            assert "节省" in suggestions[0].suggestion


# ── compute_total_saving_potential ──

class TestTotalSaving:
    def _benchmarks(self):
        pool = [_dp(cost=1000 + i * 200) for i in range(10)]
        your = [_dp(cost=2800)]
        return aggregate_price_benchmark(pool, your)

    def test_without_qty(self):
        benchmarks = self._benchmarks()
        result = compute_total_saving_potential(benchmarks)
        assert "expensive_count" in result
        assert "total_items" in result

    def test_with_qty(self):
        benchmarks = self._benchmarks()
        result = compute_total_saving_potential(benchmarks, {"鲈鱼": 100})
        assert "total_monthly_saving_yuan" in result
        assert "total_annual_saving_yuan" in result
        assert result["total_monthly_saving_yuan"] > 0
        assert result["total_annual_saving_yuan"] == result["total_monthly_saving_yuan"] * 12

    def test_zero_qty(self):
        benchmarks = self._benchmarks()
        result = compute_total_saving_potential(benchmarks, {"鲈鱼": 0})
        assert result["total_monthly_saving_yuan"] == 0


# ── generate_price_report ──

class TestPriceReport:
    def test_full_report(self):
        pool = [_dp(cost=1000 + i * 200) for i in range(10)]
        your = [_dp(cost=2800)]
        report = generate_price_report(pool, your, {"鲈鱼": 50})
        assert "summary" in report
        assert "saving_potential" in report
        assert "benchmarks" in report
        assert "suggestions" in report
        assert report["summary"]["total_items"] == 1

    def test_empty_report(self):
        report = generate_price_report([], [])
        assert report["summary"]["total_items"] == 0
        assert report["benchmarks"] == []
        assert report["suggestions"] == []

    def test_score_calculation(self):
        pool = [_dp(cost=1000 + i * 200) for i in range(10)]
        your = [_dp(cost=1000)]  # cheapest
        report = generate_price_report(pool, your)
        assert report["summary"]["score"] > 0
