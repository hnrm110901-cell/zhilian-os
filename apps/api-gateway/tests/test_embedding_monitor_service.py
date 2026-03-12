"""
Embedding Model 降级监控 单元测试

覆盖：
  - compute_avg_similarity: 正常/空/单条
  - compute_empty_rate: 全空/全有/混合
  - compute_latency_percentile: P50/P99
  - detect_degradation: 各条件/无降级
  - compute_health_score: 满分/低分/中间值
  - generate_health_report: 端到端
  - check_result_stability: 完全重叠/完全不同/部分重叠
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
from src.services.embedding_monitor_service import (
    SearchMetric,
    compute_avg_similarity,
    compute_empty_rate,
    compute_latency_percentile,
    detect_degradation,
    compute_health_score,
    generate_health_report,
    check_result_stability,
)


def _make_metric(sim_scores=None, latency=50.0, result_count=5, query_id="q1"):
    return SearchMetric(
        query_id=query_id,
        timestamp="2026-03-12T10:00:00",
        top_k_sim_scores=[0.85, 0.80, 0.75] if sim_scores is None else sim_scores,
        latency_ms=latency,
        result_count=result_count,
    )


class TestComputeAvgSimilarity:

    def test_normal(self):
        metrics = [_make_metric([0.9, 0.8]), _make_metric([0.7, 0.6])]
        assert compute_avg_similarity(metrics) == pytest.approx(0.75, abs=0.01)

    def test_empty_list(self):
        assert compute_avg_similarity([]) == 0.0

    def test_empty_scores(self):
        assert compute_avg_similarity([_make_metric([])]) == 0.0

    def test_single_score(self):
        assert compute_avg_similarity([_make_metric([0.95])]) == 0.95


class TestComputeEmptyRate:

    def test_no_empty(self):
        metrics = [_make_metric(result_count=5), _make_metric(result_count=3)]
        assert compute_empty_rate(metrics) == 0.0

    def test_all_empty(self):
        metrics = [_make_metric(result_count=0), _make_metric(result_count=0)]
        assert compute_empty_rate(metrics) == 1.0

    def test_mixed(self):
        metrics = [
            _make_metric(result_count=5),
            _make_metric(result_count=0),
            _make_metric(result_count=3),
            _make_metric(result_count=0),
        ]
        assert compute_empty_rate(metrics) == 0.5

    def test_empty_list(self):
        assert compute_empty_rate([]) == 0.0


class TestComputeLatencyPercentile:

    def test_p50(self):
        metrics = [_make_metric(latency=i * 10) for i in range(1, 11)]
        # latencies: 10, 20, 30, ..., 100 → P50 = 50
        assert compute_latency_percentile(metrics, 50) == 50.0

    def test_p99(self):
        metrics = [_make_metric(latency=i) for i in range(1, 101)]
        # 100 values, P99 = value at index 99 = 99
        assert compute_latency_percentile(metrics, 99) == 99.0

    def test_single_metric(self):
        assert compute_latency_percentile([_make_metric(latency=42)], 50) == 42.0

    def test_empty(self):
        assert compute_latency_percentile([], 50) == 0.0


class TestDetectDegradation:

    def test_no_degradation(self):
        degraded, reasons = detect_degradation(0.85, 0.05, 200)
        assert degraded is False
        assert reasons == []

    def test_low_similarity(self):
        degraded, reasons = detect_degradation(0.50, 0.05, 200)
        assert degraded is True
        assert any("相似度" in r for r in reasons)

    def test_high_empty_rate(self):
        degraded, reasons = detect_degradation(0.85, 0.25, 200)
        assert degraded is True
        assert any("空结果率" in r for r in reasons)

    def test_high_latency(self):
        degraded, reasons = detect_degradation(0.85, 0.05, 800)
        assert degraded is True
        assert any("延迟" in r for r in reasons)

    def test_multiple_reasons(self):
        degraded, reasons = detect_degradation(0.40, 0.30, 900)
        assert degraded is True
        assert len(reasons) == 3

    def test_custom_thresholds(self):
        thresholds = {
            "min_avg_similarity": 0.90,
            "max_empty_rate": 0.01,
            "max_latency_p99_ms": 100,
        }
        degraded, reasons = detect_degradation(0.85, 0.05, 200, thresholds)
        assert degraded is True  # 0.85 < 0.90, 0.05 > 0.01, 200 > 100


class TestComputeHealthScore:

    def test_perfect_health(self):
        score = compute_health_score(1.0, 0.0, 0.0)
        assert score == 100

    def test_terrible_health(self):
        score = compute_health_score(0.65, 0.15, 500)
        assert score == 0

    def test_medium_health(self):
        score = compute_health_score(0.80, 0.08, 250)
        assert 30 < score < 80

    def test_only_similarity_bad(self):
        score = compute_health_score(0.65, 0.0, 0.0)
        # sim=0, er=100, lat=100 → 0*0.5 + 100*0.3 + 100*0.2 = 50
        assert score == 50


class TestGenerateHealthReport:

    def test_healthy_report(self):
        metrics = [_make_metric([0.9, 0.85], latency=30, result_count=5) for _ in range(20)]
        report = generate_health_report(metrics, "2026-03-12", "2026-03-12")

        assert report.total_queries == 20
        assert report.avg_similarity > 0.8
        assert report.empty_rate == 0.0
        assert report.degradation_detected is False
        assert report.health_score > 60

    def test_degraded_report(self):
        metrics = [_make_metric([0.3], latency=600, result_count=0) for _ in range(10)]
        report = generate_health_report(metrics, "2026-03-12", "2026-03-12")

        assert report.degradation_detected is True
        assert len(report.degradation_reasons) >= 2
        assert report.health_score < 30


class TestCheckResultStability:

    def test_identical(self):
        assert check_result_stability(["a", "b", "c"], ["a", "b", "c"]) == 1.0

    def test_completely_different(self):
        assert check_result_stability(["a", "b"], ["c", "d"]) == 0.0

    def test_partial_overlap(self):
        result = check_result_stability(["a", "b", "c"], ["b", "c", "d"])
        # overlap=2, union=4 → 0.5
        assert result == 0.5

    def test_both_empty(self):
        assert check_result_stability([], []) == 1.0

    def test_one_empty(self):
        assert check_result_stability(["a"], []) == 0.0
