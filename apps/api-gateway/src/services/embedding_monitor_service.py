"""
Embedding Model 降级监控服务

监控向量搜索质量指标，检测模型漂移/降级。

核心指标：
1. 平均余弦相似度（query→top_k results 的平均 sim）
2. 空结果率（搜索返回0条结果的比例）
3. 延迟 P50/P99
4. 模型一致性检查（同一 query 的结果是否稳定）

设计原则：
- 核心逻辑为纯函数（可单元测试）
- 仅计算和判断，不依赖外部服务
"""

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class SearchMetric:
    """单次搜索指标"""

    query_id: str
    timestamp: str
    top_k_sim_scores: list[float]  # 返回结果的相似度分数
    latency_ms: float
    result_count: int


@dataclass
class EmbeddingHealthReport:
    """模型健康报告"""

    period_start: str
    period_end: str
    total_queries: int
    avg_similarity: float
    empty_rate: float  # 空结果率 0-1
    latency_p50_ms: float
    latency_p99_ms: float
    degradation_detected: bool
    degradation_reasons: list[str]
    health_score: int  # 0-100


# ── 阈值配置 ────────────────────────────────────────────────────────────────

DEFAULT_THRESHOLDS = {
    "min_avg_similarity": 0.65,  # 平均相似度低于此值→降级
    "max_empty_rate": 0.15,  # 空结果率超过此值→降级
    "max_latency_p99_ms": 500,  # P99延迟超过此值→降级
    "min_health_score": 60,  # 健康分低于此值→告警
}


# ── 纯函数 ──────────────────────────────────────────────────────────────────


def compute_avg_similarity(metrics: list[SearchMetric]) -> float:
    """计算所有搜索结果的平均余弦相似度。"""
    if not metrics:
        return 0.0
    all_scores = []
    for m in metrics:
        all_scores.extend(m.top_k_sim_scores)
    if not all_scores:
        return 0.0
    return round(sum(all_scores) / len(all_scores), 4)


def compute_empty_rate(metrics: list[SearchMetric]) -> float:
    """计算空结果率。"""
    if not metrics:
        return 0.0
    empty = sum(1 for m in metrics if m.result_count == 0)
    return round(empty / len(metrics), 4)


def compute_latency_percentile(metrics: list[SearchMetric], percentile: float) -> float:
    """计算延迟百分位数。"""
    if not metrics:
        return 0.0
    latencies = sorted(m.latency_ms for m in metrics)
    idx = int(math.ceil(percentile / 100.0 * len(latencies))) - 1
    idx = max(0, min(idx, len(latencies) - 1))
    return round(latencies[idx], 2)


def detect_degradation(
    avg_similarity: float,
    empty_rate: float,
    latency_p99_ms: float,
    thresholds: Optional[dict[str, float]] = None,
) -> tuple[bool, list[str]]:
    """
    检测模型是否降级。
    返回 (is_degraded, reasons)。
    """
    t = thresholds or DEFAULT_THRESHOLDS
    reasons = []

    if avg_similarity < t["min_avg_similarity"]:
        reasons.append(f"平均相似度 {avg_similarity:.3f} 低于阈值 {t['min_avg_similarity']}")
    if empty_rate > t["max_empty_rate"]:
        reasons.append(f"空结果率 {empty_rate:.1%} 超过阈值 {t['max_empty_rate']:.1%}")
    if latency_p99_ms > t["max_latency_p99_ms"]:
        reasons.append(f"P99延迟 {latency_p99_ms:.0f}ms 超过阈值 {t['max_latency_p99_ms']}ms")

    return (len(reasons) > 0, reasons)


def compute_health_score(
    avg_similarity: float,
    empty_rate: float,
    latency_p99_ms: float,
    thresholds: Optional[dict[str, float]] = None,
) -> int:
    """
    计算嵌入模型健康分（0-100）。
    三个维度各占权重：
    - 相似度质量 50%
    - 空结果率 30%
    - 延迟性能 20%
    """
    t = thresholds or DEFAULT_THRESHOLDS

    # 相似度得分：0.65 → 0分, 1.0 → 100分
    sim_min = t["min_avg_similarity"]
    sim_score = max(0, min(100, (avg_similarity - sim_min) / (1.0 - sim_min) * 100))

    # 空结果率得分：0% → 100分, 15% → 0分
    er_max = t["max_empty_rate"]
    er_score = max(0, min(100, (1 - empty_rate / er_max) * 100)) if er_max > 0 else 100

    # 延迟得分：0ms → 100分, 500ms → 0分
    lat_max = t["max_latency_p99_ms"]
    lat_score = max(0, min(100, (1 - latency_p99_ms / lat_max) * 100)) if lat_max > 0 else 100

    score = int(sim_score * 0.5 + er_score * 0.3 + lat_score * 0.2)
    return max(0, min(100, score))


def generate_health_report(
    metrics: list[SearchMetric],
    period_start: str,
    period_end: str,
    thresholds: Optional[dict[str, float]] = None,
) -> EmbeddingHealthReport:
    """
    从搜索指标列表生成健康报告。
    """
    avg_sim = compute_avg_similarity(metrics)
    empty_rate = compute_empty_rate(metrics)
    p50 = compute_latency_percentile(metrics, 50)
    p99 = compute_latency_percentile(metrics, 99)

    degraded, reasons = detect_degradation(avg_sim, empty_rate, p99, thresholds)
    score = compute_health_score(avg_sim, empty_rate, p99, thresholds)

    return EmbeddingHealthReport(
        period_start=period_start,
        period_end=period_end,
        total_queries=len(metrics),
        avg_similarity=avg_sim,
        empty_rate=empty_rate,
        latency_p50_ms=p50,
        latency_p99_ms=p99,
        degradation_detected=degraded,
        degradation_reasons=reasons,
        health_score=score,
    )


def check_result_stability(
    baseline_ids: list[str],
    current_ids: list[str],
) -> float:
    """
    检查搜索结果稳定性（相同 query 两次搜索的 top-k 结果重叠率）。
    返回 0-1 之间的重叠率。
    """
    if not baseline_ids and not current_ids:
        return 1.0
    if not baseline_ids or not current_ids:
        return 0.0
    overlap = len(set(baseline_ids) & set(current_ids))
    union = len(set(baseline_ids) | set(current_ids))
    return round(overlap / union, 4) if union > 0 else 0.0
