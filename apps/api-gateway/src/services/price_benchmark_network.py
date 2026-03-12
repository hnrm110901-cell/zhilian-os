"""
跨客户食材价格基准网络 — Price Benchmark Network

核心理念：
  "您买贵了"这句话的价值 > 100个AI功能。

  通过匿名聚合多客户的食材采购价格，构建行业价格基准，
  让每个客户知道自己买得贵还是便宜，并推荐更优供应商。

数据安全：
  - 所有数据脱敏聚合，不暴露单个客户的具体价格
  - 只输出分位数（P25/P50/P75）和匿名排名
  - 聚合最少需要5家客户的数据才输出基准

设计原则：
  - 纯函数，可单元测试
  - 金额单位：分/基本单位
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PriceDataPoint:
    """单条匿名采购价格数据"""
    ingredient_name: str            # 标准化食材名称
    category: str                   # 分类：seafood/meat/vegetable/dry_goods/oil/seasoning
    city: str                       # 城市
    unit: str                       # 基本单位（kg/piece/bottle）
    unit_cost_fen: int              # 单价（分/基本单位）
    purchase_date: str              # YYYY-MM
    quality_grade: str = "standard" # standard/premium/economy


@dataclass
class PriceBenchmarkResult:
    """单个食材的价格基准"""
    ingredient_name: str
    category: str
    city: str
    unit: str
    your_price_fen: int
    p25_fen: int                    # 低价区间（前25%的价格）
    p50_fen: int                    # 中位数
    p75_fen: int                    # 高价区间
    sample_count: int               # 参与聚合的客户数
    percentile_rank: float          # 你在所有客户中的排名百分位 (0-100, 100=最贵)
    saving_potential_fen: int       # 如果降到P25能省多少/单位
    verdict: str                    # cheap/fair/expensive/very_expensive


@dataclass
class SupplierSuggestion:
    """匿名供应商推荐"""
    ingredient_name: str
    current_price_fen: int
    benchmark_p25_fen: int
    saving_pct: float
    suggestion: str
    anonymous_source: str           # "同城3家客户在用更优供应商"


# ── 辅助函数 ────────────────────────────────────────────────────────────────

def _yuan(fen: int) -> float:
    return round((fen or 0) / 100, 2)


def _percentile(sorted_values: list[int], pct: float) -> int:
    """计算百分位数"""
    if not sorted_values:
        return 0
    n = len(sorted_values)
    idx = int(math.ceil(pct / 100 * n)) - 1
    idx = max(0, min(idx, n - 1))
    return sorted_values[idx]


def _rank_percentile(your_value: int, sorted_values: list[int]) -> float:
    """你在排序数组中的百分位排名 (0=最便宜, 100=最贵)"""
    if not sorted_values:
        return 50.0
    below = sum(1 for v in sorted_values if v < your_value)
    equal = sum(1 for v in sorted_values if v == your_value)
    return round((below + equal * 0.5) / len(sorted_values) * 100, 1)


def classify_price(percentile_rank: float) -> str:
    """
    根据百分位排名分类：
      ≤25 → cheap（低于行业均价）
      25-60 → fair（合理区间）
      60-85 → expensive（偏贵）
      >85 → very_expensive（明显偏贵）
    """
    if percentile_rank <= 25:
        return "cheap"
    elif percentile_rank <= 60:
        return "fair"
    elif percentile_rank <= 85:
        return "expensive"
    else:
        return "very_expensive"


# ── 核心纯函数 ──────────────────────────────────────────────────────────────

MIN_SAMPLE_COUNT = 5  # 最少5家客户才输出基准（隐私保护）


def aggregate_price_benchmark(
    all_prices: list[PriceDataPoint],
    your_prices: list[PriceDataPoint],
    min_samples: int = MIN_SAMPLE_COUNT,
) -> list[PriceBenchmarkResult]:
    """
    聚合全网价格数据，生成每种食材的基准对比。

    参数：
      all_prices — 全网匿名价格（含你自己的）
      your_prices — 你的价格
      min_samples — 最少参与客户数（隐私阈值）
    """
    # 按 (ingredient_name, city, unit) 分组
    groups: dict[tuple, list[int]] = {}
    for p in all_prices:
        key = (p.ingredient_name, p.city, p.unit, p.category)
        groups.setdefault(key, []).append(p.unit_cost_fen)

    # 你的价格索引
    your_index: dict[tuple, int] = {}
    for p in your_prices:
        key = (p.ingredient_name, p.city, p.unit, p.category)
        your_index[key] = p.unit_cost_fen

    results = []
    for key, prices in groups.items():
        name, city, unit, category = key
        if len(prices) < min_samples:
            continue  # 样本不足，不输出（隐私保护）

        if key not in your_index:
            continue  # 你没买这个食材

        sorted_prices = sorted(prices)
        your_price = your_index[key]

        p25 = _percentile(sorted_prices, 25)
        p50 = _percentile(sorted_prices, 50)
        p75 = _percentile(sorted_prices, 75)
        rank = _rank_percentile(your_price, sorted_prices)
        verdict = classify_price(rank)
        saving = max(0, your_price - p25)

        results.append(PriceBenchmarkResult(
            ingredient_name=name,
            category=category,
            city=city,
            unit=unit,
            your_price_fen=your_price,
            p25_fen=p25,
            p50_fen=p50,
            p75_fen=p75,
            sample_count=len(prices),
            percentile_rank=rank,
            saving_potential_fen=saving,
            verdict=verdict,
        ))

    # 按节省潜力降序排列
    results.sort(key=lambda r: r.saving_potential_fen, reverse=True)
    return results


def generate_supplier_suggestions(
    benchmarks: list[PriceBenchmarkResult],
    top_n: int = 5,
) -> list[SupplierSuggestion]:
    """
    从基准对比结果中生成供应商优化建议。
    仅对 expensive/very_expensive 的食材生成建议。
    """
    suggestions = []
    for b in benchmarks:
        if b.verdict not in ("expensive", "very_expensive"):
            continue
        if b.saving_potential_fen <= 0:
            continue

        saving_pct = round(b.saving_potential_fen / max(b.your_price_fen, 1) * 100, 1)

        cheaper_count = max(1, int(b.sample_count * (1 - b.percentile_rank / 100)))

        suggestions.append(SupplierSuggestion(
            ingredient_name=b.ingredient_name,
            current_price_fen=b.your_price_fen,
            benchmark_p25_fen=b.p25_fen,
            saving_pct=saving_pct,
            suggestion=(
                f"{b.ingredient_name}当前采购价 ¥{_yuan(b.your_price_fen)}/{b.unit}，"
                f"同城P25价格 ¥{_yuan(b.p25_fen)}/{b.unit}，"
                f"切换供应商预计节省 {saving_pct:.0f}%"
            ),
            anonymous_source=f"同城{cheaper_count}家客户在用更优价供应商",
        ))

    suggestions.sort(key=lambda s: s.saving_pct, reverse=True)
    return suggestions[:top_n]


def compute_total_saving_potential(
    benchmarks: list[PriceBenchmarkResult],
    monthly_purchase_qty: dict[str, float] | None = None,
) -> dict:
    """
    计算总节省潜力（如果所有食材都降到P25）。

    参数：
      monthly_purchase_qty — {ingredient_name: monthly_qty}
    """
    if not monthly_purchase_qty:
        # 没有用量数据时只返回单价节省
        expensive = [b for b in benchmarks if b.verdict in ("expensive", "very_expensive")]
        return {
            "expensive_count": len(expensive),
            "total_items": len(benchmarks),
            "top_saving_item": expensive[0].ingredient_name if expensive else None,
            "top_saving_per_unit_yuan": _yuan(expensive[0].saving_potential_fen) if expensive else 0,
        }

    total_saving_fen = 0
    item_savings = []
    for b in benchmarks:
        qty = monthly_purchase_qty.get(b.ingredient_name, 0)
        if qty <= 0 or b.saving_potential_fen <= 0:
            continue
        monthly_save = int(b.saving_potential_fen * qty)
        total_saving_fen += monthly_save
        item_savings.append({
            "name": b.ingredient_name,
            "monthly_saving_yuan": _yuan(monthly_save),
            "unit_saving_yuan": _yuan(b.saving_potential_fen),
            "monthly_qty": qty,
        })

    item_savings.sort(key=lambda x: x["monthly_saving_yuan"], reverse=True)

    return {
        "total_monthly_saving_yuan": _yuan(total_saving_fen),
        "total_annual_saving_yuan": _yuan(total_saving_fen * 12),
        "item_count": len(item_savings),
        "top_items": item_savings[:5],
    }


def generate_price_report(
    all_prices: list[PriceDataPoint],
    your_prices: list[PriceDataPoint],
    monthly_purchase_qty: dict[str, float] | None = None,
) -> dict:
    """
    生成完整的价格基准报告（端到端入口）。
    """
    benchmarks = aggregate_price_benchmark(all_prices, your_prices)
    suggestions = generate_supplier_suggestions(benchmarks)
    saving = compute_total_saving_potential(benchmarks, monthly_purchase_qty)

    cheap = sum(1 for b in benchmarks if b.verdict == "cheap")
    fair = sum(1 for b in benchmarks if b.verdict == "fair")
    expensive = sum(1 for b in benchmarks if b.verdict == "expensive")
    very_expensive = sum(1 for b in benchmarks if b.verdict == "very_expensive")

    return {
        "summary": {
            "total_items": len(benchmarks),
            "cheap": cheap,
            "fair": fair,
            "expensive": expensive,
            "very_expensive": very_expensive,
            "score": round((cheap * 100 + fair * 70 + expensive * 30) / max(len(benchmarks), 1)),
        },
        "saving_potential": saving,
        "benchmarks": [
            {
                "name": b.ingredient_name,
                "category": b.category,
                "your_price_yuan": _yuan(b.your_price_fen),
                "p25_yuan": _yuan(b.p25_fen),
                "p50_yuan": _yuan(b.p50_fen),
                "p75_yuan": _yuan(b.p75_fen),
                "percentile_rank": b.percentile_rank,
                "verdict": b.verdict,
                "saving_yuan": _yuan(b.saving_potential_fen),
                "sample_count": b.sample_count,
            }
            for b in benchmarks
        ],
        "suggestions": [
            {
                "ingredient": s.ingredient_name,
                "current_yuan": _yuan(s.current_price_fen),
                "benchmark_yuan": _yuan(s.benchmark_p25_fen),
                "saving_pct": s.saving_pct,
                "suggestion": s.suggestion,
                "source": s.anonymous_source,
            }
            for s in suggestions
        ],
    }
