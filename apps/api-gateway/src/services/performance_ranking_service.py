"""多店财务对标排名引擎 — Phase 5 Month 9

核心功能：
  1. 排名计算：对每个财务指标，将所有门店按期排名（1=最优）
  2. 百分位：确定每个门店在全体中的位置（0-100）
  3. 层级分类：top(>=75) / above_avg(>=50) / below_avg(>=25) / laggard(<25)
  4. 环比变化：对比上期排名，判断 improved/declined/stable/new
  5. 差距分析：与中位数/头部四分位/最优门店的差距（%），折算¥潜力

4 个检测维度（与 Month 7/8 对齐）：
  revenue        — 月净收入 (¥)，越高越好
  food_cost_rate — 食材成本率 (%)，越低越好
  profit_margin  — 利润率 (%)，越高越好
  health_score   — 财务健康综合评分 (0-100)，越高越好
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

# ── 常量 ─────────────────────────────────────────────────────────────────────

METRICS = ("revenue", "food_cost_rate", "profit_margin", "health_score")

METRIC_LABELS = {
    "revenue": "月净收入",
    "food_cost_rate": "食材成本率",
    "profit_margin": "利润率",
    "health_score": "财务健康评分",
}

METRIC_UNITS = {
    "revenue": "¥",
    "food_cost_rate": "%",
    "profit_margin": "%",
    "health_score": "分",
}

# 值越低越好的指标（排名时反转）
LOWER_IS_BETTER = {"food_cost_rate"}

TIER_TOP = 75.0
TIER_ABOVE_AVG = 50.0
TIER_BELOW_AVG = 25.0

BENCHMARK_TYPES = ("median", "top_quartile", "best")


# ── 内部工具 ──────────────────────────────────────────────────────────────────


def _safe_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(Decimal(str(val)))
    except Exception:
        return None


def _to_float(val, default: float = 0.0) -> float:
    r = _safe_float(val)
    return r if r is not None else default


def _prev_period(period: str) -> str:
    year, month = map(int, period.split("-"))
    month -= 1
    if month == 0:
        month = 12
        year -= 1
    return f"{year:04d}-{month:02d}"


# ══════════════════════════════════════════════════════════════════════════════
# 纯函数层
# ══════════════════════════════════════════════════════════════════════════════


def compute_rank(
    value: float,
    all_values: List[float],
    higher_is_better: bool = True,
) -> int:
    """
    1-based 排名。higher_is_better=True → 值越大排名越靠前（rank=1）。
    相同值共享同一排名（dense rank）。
    """
    if not all_values:
        return 1
    if higher_is_better:
        better_count = sum(1 for v in all_values if v > value)
    else:
        better_count = sum(1 for v in all_values if v < value)
    return better_count + 1


def compute_percentile(
    value: float,
    all_values: List[float],
    higher_is_better: bool = True,
) -> float:
    """
    百分位分数 0-100。higher_is_better=True → 百分位越高越好。
    单值列表返回 100.0（仅此一家）。
    """
    if len(all_values) <= 1:
        return 100.0
    if higher_is_better:
        count_below = sum(1 for v in all_values if v < value)
    else:
        count_below = sum(1 for v in all_values if v > value)
    return round(count_below / (len(all_values) - 1) * 100, 1)


def classify_tier(percentile: float) -> str:
    """依百分位划分层级。"""
    if percentile >= TIER_TOP:
        return "top"
    if percentile >= TIER_ABOVE_AVG:
        return "above_avg"
    if percentile >= TIER_BELOW_AVG:
        return "below_avg"
    return "laggard"


def classify_rank_change(current_rank: int, prev_rank: Optional[int]) -> str:
    """环比排名变化。"""
    if prev_rank is None:
        return "new"
    if current_rank < prev_rank:
        return "improved"
    if current_rank > prev_rank:
        return "declined"
    return "stable"


def compute_benchmark_value(
    all_values: List[float],
    benchmark_type: str,
    higher_is_better: bool = True,
) -> Optional[float]:
    """
    计算基准值：
      median       — 中位数
      top_quartile — 头部四分位（前25%的分界线）
      best         — 最优值
    """
    if not all_values:
        return None
    sorted_v = sorted(all_values)
    n = len(sorted_v)

    if benchmark_type == "median":
        mid = n // 2
        return (sorted_v[mid - 1] + sorted_v[mid]) / 2 if n % 2 == 0 else sorted_v[mid]

    if benchmark_type == "top_quartile":
        # 头部四分位阈值：高者优先取 75th 百分位，低者优先取 25th 百分位
        if higher_is_better:
            idx = min(int(n * 0.75), n - 1)
            return sorted_v[idx]
        else:
            idx = max(0, int(n * 0.25) - 1) if n > 1 else 0
            return sorted_v[idx]

    if benchmark_type == "best":
        return sorted_v[-1] if higher_is_better else sorted_v[0]

    return None


def compute_gap_pct(store_value: float, benchmark_value: float) -> float:
    """
    (store - benchmark) / |benchmark| × 100。
    benchmark = 0 → 0.0。
    """
    if benchmark_value == 0.0:
        return 0.0
    return (store_value - benchmark_value) / abs(benchmark_value) * 100.0


def compute_gap_direction(
    gap_pct: float,
    higher_is_better: bool,
) -> str:
    """
    'above' / 'below' / 'equal'。
    对于 higher_is_better 指标：gap_pct > 0 → above（好）
    对于 lower_is_better：gap_pct < 0 → above（好，成本更低）
    """
    if abs(gap_pct) < 0.01:
        return "equal"
    if higher_is_better:
        return "above" if gap_pct > 0 else "below"
    else:
        return "above" if gap_pct < 0 else "below"


def compute_yuan_potential(
    metric: str,
    store_value: float,
    benchmark_value: float,
    revenue: float,
) -> Optional[float]:
    """
    若门店达到基准水平，每月可多赚/省多少 ¥。
    revenue 指标：直接差值。
    food_cost_rate/profit_margin：rate_diff * revenue / 100。
    health_score：无直接¥换算，返回 None。
    """
    if metric == "revenue":
        return benchmark_value - store_value  # 正数 = 还差多少

    if metric in ("food_cost_rate", "profit_margin") and revenue > 0:
        # food_cost_rate: 降低 → 节省（benchmark < store → potential = (store-benchmark)/100*revenue）
        # profit_margin:  提升 → 增收（benchmark > store → potential = (benchmark-store)/100*revenue）
        return abs(benchmark_value - store_value) / 100.0 * revenue

    return None


def build_ranking_row(
    store_id: str,
    period: str,
    metric: str,
    value: float,
    all_values: List[float],
    prev_rank: Optional[int],
) -> Dict[str, Any]:
    """构造单条排名记录（纯函数，不访问 DB）。"""
    higher = metric not in LOWER_IS_BETTER
    rank = compute_rank(value, all_values, higher)
    percentile = compute_percentile(value, all_values, higher)
    tier = classify_tier(percentile)
    change = classify_rank_change(rank, prev_rank)
    return {
        "store_id": store_id,
        "period": period,
        "metric": metric,
        "value": value,
        "rank": rank,
        "total_stores": len(all_values),
        "percentile": percentile,
        "tier": tier,
        "prev_rank": prev_rank,
        "rank_change": change,
    }


def build_gap_rows(
    store_id: str,
    period: str,
    metric: str,
    store_value: float,
    all_values: List[float],
    revenue: float = 0.0,
) -> List[Dict[str, Any]]:
    """构造对标差距行（3种基准类型）。"""
    higher = metric not in LOWER_IS_BETTER
    rows = []
    for btype in BENCHMARK_TYPES:
        bv = compute_benchmark_value(all_values, btype, higher)
        if bv is None:
            continue
        gap_pct = compute_gap_pct(store_value, bv)
        direction = compute_gap_direction(gap_pct, higher)
        potential = compute_yuan_potential(metric, store_value, bv, revenue)
        rows.append(
            {
                "store_id": store_id,
                "period": period,
                "metric": metric,
                "benchmark_type": btype,
                "store_value": store_value,
                "benchmark_value": bv,
                "gap_pct": round(gap_pct, 2),
                "gap_direction": direction,
                "yuan_potential": round(potential, 2) if potential is not None else None,
            }
        )
    return rows


# ══════════════════════════════════════════════════════════════════════════════
# DB 函数层
# ══════════════════════════════════════════════════════════════════════════════


async def _upsert_ranking(db: AsyncSession, row: Dict[str, Any]) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.execute(
        text("""
            INSERT INTO store_performance_rankings
                (store_id, period, metric, value, rank, total_stores,
                 percentile, tier, prev_rank, rank_change, computed_at, updated_at)
            VALUES
                (:sid, :period, :metric, :value, :rank, :total,
                 :pct, :tier, :prev, :change, :now, :now)
            ON CONFLICT (store_id, period, metric) DO UPDATE SET
                value        = EXCLUDED.value,
                rank         = EXCLUDED.rank,
                total_stores = EXCLUDED.total_stores,
                percentile   = EXCLUDED.percentile,
                tier         = EXCLUDED.tier,
                prev_rank    = EXCLUDED.prev_rank,
                rank_change  = EXCLUDED.rank_change,
                updated_at   = EXCLUDED.updated_at
        """),
        {
            "sid": row["store_id"],
            "period": row["period"],
            "metric": row["metric"],
            "value": round(row["value"], 4),
            "rank": row["rank"],
            "total": row["total_stores"],
            "pct": row["percentile"],
            "tier": row["tier"],
            "prev": row["prev_rank"],
            "change": row["rank_change"],
            "now": now,
        },
    )


async def _upsert_gap(db: AsyncSession, row: Dict[str, Any]) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.execute(
        text("""
            INSERT INTO store_benchmark_gaps
                (store_id, period, metric, benchmark_type,
                 store_value, benchmark_value, gap_pct,
                 gap_direction, yuan_potential, computed_at)
            VALUES
                (:sid, :period, :metric, :btype,
                 :sv, :bv, :gap,
                 :dir, :pot, :now)
            ON CONFLICT (store_id, period, metric, benchmark_type) DO UPDATE SET
                store_value     = EXCLUDED.store_value,
                benchmark_value = EXCLUDED.benchmark_value,
                gap_pct         = EXCLUDED.gap_pct,
                gap_direction   = EXCLUDED.gap_direction,
                yuan_potential  = EXCLUDED.yuan_potential,
                computed_at     = EXCLUDED.computed_at
        """),
        {
            "sid": row["store_id"],
            "period": row["period"],
            "metric": row["metric"],
            "btype": row["benchmark_type"],
            "sv": round(row["store_value"], 4),
            "bv": round(row["benchmark_value"], 4),
            "gap": row["gap_pct"],
            "dir": row["gap_direction"],
            "pot": row["yuan_potential"],
            "now": now,
        },
    )


async def _fetch_metric_snapshot(
    db: AsyncSession,
    period: str,
    metric: str,
) -> List[Tuple[str, float]]:
    """拉取该期所有门店的指标值，返回 [(store_id, value), ...]。"""
    if metric in ("revenue", "food_cost_rate", "profit_margin"):
        rows = await db.execute(
            text("""
                SELECT store_id, net_revenue_yuan, food_cost_yuan, profit_margin_pct
                FROM profit_attribution_results
                WHERE period = :period
                ORDER BY store_id
            """),
            {"period": period},
        )
        result = []
        for r in rows.fetchall():
            sid, rev, fc, pm = r[0], _to_float(r[1]), _to_float(r[2]), _to_float(r[3])
            if metric == "revenue":
                result.append((sid, rev))
            elif metric == "food_cost_rate":
                result.append((sid, fc / rev * 100 if rev > 0 else 0.0))
            else:
                result.append((sid, pm))
        return result

    # health_score
    rows = await db.execute(
        text("""
            SELECT store_id, total_score
            FROM finance_health_scores
            WHERE period = :period
            ORDER BY store_id
        """),
        {"period": period},
    )
    return [(r[0], _to_float(r[1])) for r in rows.fetchall()]


async def _fetch_prev_ranks(
    db: AsyncSession,
    period: str,
    metric: str,
) -> Dict[str, int]:
    """上期排名 {store_id: rank}。"""
    prev = _prev_period(period)
    rows = await db.execute(
        text("""
            SELECT store_id, rank FROM store_performance_rankings
            WHERE period = :period AND metric = :metric
        """),
        {"period": prev, "metric": metric},
    )
    return {r[0]: r[1] for r in rows.fetchall()}


async def _fetch_store_revenue(db: AsyncSession, store_id: str, period: str) -> float:
    """获取门店当期收入（用于¥潜力计算）。"""
    row = await db.execute(
        text("""
            SELECT net_revenue_yuan FROM profit_attribution_results
            WHERE store_id = :sid AND period = :period LIMIT 1
        """),
        {"sid": store_id, "period": period},
    )
    row = row.fetchone()
    return _to_float(row[0]) if row else 0.0


async def compute_period_rankings(
    db: AsyncSession,
    period: str,
) -> Dict[str, Any]:
    """
    计算指定期所有门店所有指标的排名 + 对标差距，写入 DB。
    返回汇总统计。
    """
    total_rows = 0
    total_gaps = 0
    store_count = 0

    for metric in METRICS:
        snapshot = await _fetch_metric_snapshot(db, period, metric)
        if not snapshot:
            continue

        store_count = max(store_count, len(snapshot))
        prev_ranks = await _fetch_prev_ranks(db, period, metric)
        all_values = [v for _, v in snapshot]

        for store_id, value in snapshot:
            row = build_ranking_row(
                store_id,
                period,
                metric,
                value,
                all_values,
                prev_ranks.get(store_id),
            )
            await _upsert_ranking(db, row)
            total_rows += 1

            # 对标差距（需要收入做¥换算）
            revenue = value if metric == "revenue" else await _fetch_store_revenue(db, store_id, period)
            gaps = build_gap_rows(store_id, period, metric, value, all_values, revenue)
            for g in gaps:
                await _upsert_gap(db, g)
            total_gaps += len(gaps)

    await db.commit()
    return {
        "period": period,
        "store_count": store_count,
        "ranking_rows": total_rows,
        "gap_rows": total_gaps,
    }


async def get_store_ranking(
    db: AsyncSession,
    store_id: str,
    period: str,
) -> Optional[Dict[str, Any]]:
    """获取门店当期全量排名快照（4个指标）。"""
    rows = await db.execute(
        text("""
            SELECT metric, value, rank, total_stores, percentile,
                   tier, prev_rank, rank_change
            FROM store_performance_rankings
            WHERE store_id = :sid AND period = :period
            ORDER BY metric
        """),
        {"sid": store_id, "period": period},
    )
    records = rows.fetchall()
    if not records:
        return None

    metrics_data = {}
    for r in records:
        metrics_data[r[0]] = {
            "metric": r[0],
            "label": METRIC_LABELS.get(r[0], r[0]),
            "value": _safe_float(r[1]),
            "rank": r[2],
            "total_stores": r[3],
            "percentile": _safe_float(r[4]),
            "tier": r[5],
            "prev_rank": r[6],
            "rank_change": r[7],
        }
    return {
        "store_id": store_id,
        "period": period,
        "metrics": metrics_data,
    }


async def get_leaderboard(
    db: AsyncSession,
    period: str,
    metric: str,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """获取指标排行榜（前 N 名）。"""
    rows = await db.execute(
        text("""
            SELECT store_id, value, rank, total_stores, percentile, tier, rank_change
            FROM store_performance_rankings
            WHERE period = :period AND metric = :metric
            ORDER BY rank ASC
            LIMIT :lim
        """),
        {"period": period, "metric": metric, "lim": limit},
    )
    return [
        {
            "store_id": r[0],
            "value": _safe_float(r[1]),
            "rank": r[2],
            "total_stores": r[3],
            "percentile": _safe_float(r[4]),
            "tier": r[5],
            "rank_change": r[6],
            "label": METRIC_LABELS.get(metric, metric),
        }
        for r in rows.fetchall()
    ]


async def get_benchmark_gaps(
    db: AsyncSession,
    store_id: str,
    period: str,
) -> List[Dict[str, Any]]:
    """获取门店当期各指标对标差距（3种基准 × 4指标 = 最多12条）。"""
    rows = await db.execute(
        text("""
            SELECT metric, benchmark_type, store_value, benchmark_value,
                   gap_pct, gap_direction, yuan_potential
            FROM store_benchmark_gaps
            WHERE store_id = :sid AND period = :period
            ORDER BY metric, benchmark_type
        """),
        {"sid": store_id, "period": period},
    )
    return [
        {
            "metric": r[0],
            "label": METRIC_LABELS.get(r[0], r[0]),
            "benchmark_type": r[1],
            "store_value": _safe_float(r[2]),
            "benchmark_value": _safe_float(r[3]),
            "gap_pct": _safe_float(r[4]),
            "gap_direction": r[5],
            "yuan_potential": _safe_float(r[6]),
        }
        for r in rows.fetchall()
    ]


async def get_ranking_trend(
    db: AsyncSession,
    store_id: str,
    metric: str,
    periods: int = 6,
) -> List[Dict[str, Any]]:
    """返回门店指定指标近 N 期排名趋势，升序。"""
    rows = await db.execute(
        text("""
            SELECT period, rank, total_stores, percentile, tier, rank_change
            FROM store_performance_rankings
            WHERE store_id = :sid AND metric = :metric
            ORDER BY period DESC
            LIMIT :lim
        """),
        {"sid": store_id, "metric": metric, "lim": periods},
    )
    records = [
        {
            "period": r[0],
            "rank": r[1],
            "total_stores": r[2],
            "percentile": _safe_float(r[3]),
            "tier": r[4],
            "rank_change": r[5],
        }
        for r in rows.fetchall()
    ]
    return list(reversed(records))


async def get_brand_ranking_summary(
    db: AsyncSession,
    brand_id: str,
    period: str,
) -> Dict[str, Any]:
    """
    品牌级排名汇总：各层级门店数量、每指标最优/最差门店。
    注：brand_id 参数当前版本保留，按 period 全量汇总。
    """
    rows = await db.execute(
        text("""
            SELECT store_id, metric, rank, total_stores, percentile, tier, value
            FROM store_performance_rankings
            WHERE period = :period
            ORDER BY metric, rank ASC
        """),
        {"period": period},
    )
    records = rows.fetchall()

    by_metric: Dict[str, List] = {}
    tier_counts: Dict[str, int] = {"top": 0, "above_avg": 0, "below_avg": 0, "laggard": 0}
    seen_tiers: set = set()

    for r in records:
        sid, metric, rank, total, pct, tier, val = r
        by_metric.setdefault(metric, []).append(
            {
                "store_id": sid,
                "rank": rank,
                "total": total,
                "percentile": _safe_float(pct),
                "tier": tier,
                "value": _safe_float(val),
            }
        )
        # 每个门店只计一次层级（用 health_score 作为代表）
        key = (sid, "health_score")
        if metric == "health_score" and key not in seen_tiers:
            seen_tiers.add(key)
            tier_counts[tier] = tier_counts.get(tier, 0) + 1

    metric_summary = {}
    for metric, entries in by_metric.items():
        if not entries:
            continue
        metric_summary[metric] = {
            "best_store": entries[0]["store_id"],
            "worst_store": entries[-1]["store_id"],
            "best_value": entries[0]["value"],
            "worst_value": entries[-1]["value"],
            "total_stores": entries[0]["total"],
        }

    return {
        "brand_id": brand_id,
        "period": period,
        "tier_counts": tier_counts,
        "total_stores": len(seen_tiers),
        "by_metric": metric_summary,
    }
