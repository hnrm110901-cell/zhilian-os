"""财务异常检测引擎 — Phase 5 Month 8

双引擎检测：
  1. Z-score 引擎：将当期值与近 N 期历史均值±标准差比较
  2. 预测偏差引擎：将实际值与 financial_forecasts 预测值比较

4个检测维度（与 Month 7 预测引擎对齐）：
  revenue        — 月净收入 (¥)
  food_cost_rate — 食材成本率 (%)
  profit_margin  — 利润率 (%)
  health_score   — 财务健康综合评分 (0-100)

严重度分级：
  normal   — |Z| ≤ 1.5 且 |deviation| ≤ 10%
  mild     — 1.5 < |Z| ≤ 2.0 或 10% < |deviation| ≤ 20%
  moderate — 2.0 < |Z| ≤ 3.0 或 20% < |deviation| ≤ 30%
  severe   — |Z| > 3.0 或 |deviation| > 30%
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import structlog
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# ── 常量 ─────────────────────────────────────────────────────────────────────

HISTORY_PERIODS = 6
MIN_HISTORY = 3  # 计算 Z-score 至少需要 3 期

# Z-score 阈值
Z_MILD = 1.5
Z_MODERATE = 2.0
Z_SEVERE = 3.0

# 预测偏差阈值（绝对值 %）
DEV_MILD = 10.0
DEV_MODERATE = 20.0
DEV_SEVERE = 30.0

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

# 成本率和健康评分方向：偏高/偏低的"好坏"语义不同
LOWER_IS_BETTER = {"food_cost_rate"}  # 成本率越低越好


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


def _prev_periods(target_period: str, n: int) -> List[str]:
    year, month = map(int, target_period.split("-"))
    periods: List[str] = []
    for _ in range(n):
        month -= 1
        if month == 0:
            month = 12
            year -= 1
        periods.append(f"{year:04d}-{month:02d}")
    return list(reversed(periods))


# ══════════════════════════════════════════════════════════════════════════════
# 纯函数层
# ══════════════════════════════════════════════════════════════════════════════


def compute_mean_std(values: List[float]) -> Tuple[float, float]:
    """返回 (mean, std)。n < 2 时 std = 0。"""
    if not values:
        return (0.0, 0.0)
    n = len(values)
    mean = sum(values) / n
    if n < 2:
        return (mean, 0.0)
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
    return (mean, math.sqrt(variance))


def compute_z_score(value: float, mean: float, std: float) -> float:
    """标准化 Z-score。std = 0 时返回 0（无法区分）。"""
    if std == 0.0:
        return 0.0
    return (value - mean) / std


def compute_iqr_bounds(values: List[float]) -> Tuple[float, float]:
    """
    Tukey 内围栏：(Q1 - 1.5*IQR, Q3 + 1.5*IQR)。
    n < 4 时退化为 (min, max)。
    """
    if len(values) < 4:
        return (min(values), max(values)) if values else (0.0, 0.0)
    sorted_v = sorted(values)
    n = len(sorted_v)
    q1 = sorted_v[n // 4]
    q3 = sorted_v[3 * n // 4]
    iqr = q3 - q1
    return (q1 - 1.5 * iqr, q3 + 1.5 * iqr)


def is_iqr_anomaly(value: float, lower_fence: float, upper_fence: float) -> bool:
    return value < lower_fence or value > upper_fence


def compute_deviation_pct(actual: float, expected: float) -> float:
    """(actual - expected) / |expected| × 100。expected = 0 时返回 0。"""
    if expected == 0.0:
        return 0.0
    return (actual - expected) / abs(expected) * 100.0


def classify_severity_z(z_score: float) -> str:
    """基于 Z-score 绝对值分级。"""
    abs_z = abs(z_score)
    if abs_z > Z_SEVERE:
        return "severe"
    if abs_z > Z_MODERATE:
        return "moderate"
    if abs_z > Z_MILD:
        return "mild"
    return "normal"


def classify_severity_deviation(deviation_pct: float) -> str:
    """基于偏差百分比绝对值分级。"""
    abs_dev = abs(deviation_pct)
    if abs_dev > DEV_SEVERE:
        return "severe"
    if abs_dev > DEV_MODERATE:
        return "moderate"
    if abs_dev > DEV_MILD:
        return "mild"
    return "normal"


def merge_severity(s1: str, s2: str) -> str:
    """取两个严重度中较高者。"""
    order = {"normal": 0, "mild": 1, "moderate": 2, "severe": 3}
    return s1 if order.get(s1, 0) >= order.get(s2, 0) else s2


def generate_anomaly_description(
    metric: str,
    actual: float,
    expected: float,
    deviation_pct: float,
    z_score: float,
    severity: str,
    yuan_impact: Optional[float] = None,
) -> str:
    """
    生成中文异常描述（≤200字）。纯函数，无 DB 依赖。

    语义规则：
      - food_cost_rate 偏高 → 警示；偏低 → 良好
      - revenue/profit_margin/health_score 偏低 → 警示；偏高 → 良好
    """
    if severity == "normal":
        return ""

    label = METRIC_LABELS.get(metric, metric)
    unit = METRIC_UNITS.get(metric, "")

    # 方向描述
    if deviation_pct > 0:
        dir_word = "偏高" if metric in LOWER_IS_BETTER else "偏高"
        concern = "需关注" if metric in LOWER_IS_BETTER else "表现良好"
    else:
        dir_word = "偏低"
        concern = "表现良好" if metric in LOWER_IS_BETTER else "需关注"

    # 数值展示
    if unit == "¥":
        actual_str = f"¥{actual:,.0f}"
        expected_str = f"¥{expected:,.0f}"
    else:
        actual_str = f"{actual:.1f}{unit}"
        expected_str = f"{expected:.1f}{unit}"

    severity_label = {"mild": "轻微", "moderate": "明显", "severe": "严重"}.get(severity, "")

    parts = [
        f"{label}当期 {actual_str}，参考值 {expected_str}，",
        f"偏差 {deviation_pct:+.1f}%（{severity_label}{dir_word}，{concern}）。",
    ]

    if abs(z_score) >= Z_MILD:
        parts.append(f"Z-score={z_score:.2f}，超出历史均值 {abs(z_score):.1f} 个标准差。")

    if yuan_impact is not None and metric != "revenue":
        parts.append(f"折合收入影响约 ¥{abs(yuan_impact):,.0f}。")

    return "".join(parts)[:200]


def compute_yuan_impact(
    metric: str,
    actual: float,
    expected: float,
    revenue: float,
) -> Optional[float]:
    """
    将非收入指标的偏差折算为 ¥ 影响。
      food_cost_rate / profit_margin：rate_diff * revenue / 100
      health_score / revenue：直接为收入偏差 or None
    """
    if metric == "revenue":
        return actual - expected
    if metric in ("food_cost_rate", "profit_margin") and revenue > 0:
        return (actual - expected) / 100.0 * revenue
    return None


# ══════════════════════════════════════════════════════════════════════════════
# DB 函数层
# ══════════════════════════════════════════════════════════════════════════════


async def _upsert_anomaly(
    db: AsyncSession,
    store_id: str,
    period: str,
    metric: str,
    actual: float,
    expected: float,
    deviation_pct: float,
    z_score: float,
    is_anomaly: bool,
    severity: str,
    method: str,
    description: str,
    yuan_impact: Optional[float],
) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.execute(
        text("""
            INSERT INTO financial_anomaly_records
                (store_id, period, metric, actual_value, expected_value,
                 deviation_pct, z_score, is_anomaly, severity,
                 detection_method, description, yuan_impact,
                 resolved, detected_at, updated_at)
            VALUES
                (:sid, :period, :metric, :actual, :expected,
                 :dev, :z, :anom, :sev,
                 :method, :desc, :impact,
                 false, :now, :now)
            ON CONFLICT (store_id, period, metric) DO UPDATE SET
                actual_value      = EXCLUDED.actual_value,
                expected_value    = EXCLUDED.expected_value,
                deviation_pct     = EXCLUDED.deviation_pct,
                z_score           = EXCLUDED.z_score,
                is_anomaly        = EXCLUDED.is_anomaly,
                severity          = EXCLUDED.severity,
                detection_method  = EXCLUDED.detection_method,
                description       = EXCLUDED.description,
                yuan_impact       = EXCLUDED.yuan_impact,
                updated_at        = EXCLUDED.updated_at
        """),
        {
            "sid": store_id,
            "period": period,
            "metric": metric,
            "actual": round(actual, 4),
            "expected": round(expected, 4),
            "dev": round(deviation_pct, 2),
            "z": round(z_score, 3),
            "anom": is_anomaly,
            "sev": severity,
            "method": method,
            "desc": description,
            "impact": round(yuan_impact, 2) if yuan_impact is not None else None,
            "now": now,
        },
    )


async def _fetch_metric_history(
    db: AsyncSession,
    store_id: str,
    periods: List[str],
    metric: str,
) -> List[Tuple[str, float]]:
    """拉取历史期数据，返回 [(period, value), ...] 升序。"""
    if metric in ("revenue", "food_cost_rate", "profit_margin"):
        stmt = text("""
            SELECT period, net_revenue_yuan, food_cost_yuan, profit_margin_pct
            FROM profit_attribution_results
            WHERE store_id = :sid AND period IN :periods
            ORDER BY period ASC
        """).bindparams(bindparam("periods", expanding=True))
        rows = await db.execute(stmt, {"sid": store_id, "periods": periods})
        result = []
        for r in rows.fetchall():
            if metric == "revenue":
                result.append((r[0], _to_float(r[1])))
            elif metric == "food_cost_rate":
                rev = _to_float(r[1])
                fc = _to_float(r[2])
                result.append((r[0], fc / rev * 100 if rev > 0 else 0.0))
            else:  # profit_margin
                result.append((r[0], _to_float(r[3])))
        return result

    # health_score
    stmt = text("""
        SELECT period, total_score
        FROM finance_health_scores
        WHERE store_id = :sid AND period IN :periods
        ORDER BY period ASC
    """).bindparams(bindparam("periods", expanding=True))
    rows = await db.execute(stmt, {"sid": store_id, "periods": periods})
    return [(r[0], _to_float(r[1])) for r in rows.fetchall()]


async def _get_forecast_expected(
    db: AsyncSession,
    store_id: str,
    period: str,
    metric: str,
) -> Optional[float]:
    """从 financial_forecasts 取预测值（如有）。"""
    row = await db.execute(
        text("""
            SELECT predicted_value FROM financial_forecasts
            WHERE store_id = :sid AND target_period = :tp AND forecast_type = :ft
            LIMIT 1
        """),
        {"sid": store_id, "tp": period, "ft": metric},
    )
    row = row.fetchone()
    return _safe_float(row[0]) if row else None


async def detect_metric_anomaly(
    db: AsyncSession,
    store_id: str,
    period: str,
    metric: str,
    actual_value: float,
    revenue_for_impact: float = 0.0,
) -> Dict[str, Any]:
    """
    对单个 metric 执行双引擎检测，upsert 结果，返回检测摘要。
    """
    hist_periods = _prev_periods(period, HISTORY_PERIODS)
    history = await _fetch_metric_history(db, store_id, hist_periods, metric)
    hist_values = [v for _, v in history]

    # --- 引擎1：Z-score ---
    severity_z = "normal"
    z_score = 0.0
    expected_z = 0.0
    if len(hist_values) >= MIN_HISTORY:
        mean, std = compute_mean_std(hist_values)
        z_score = compute_z_score(actual_value, mean, std)
        severity_z = classify_severity_z(z_score)
        expected_z = mean
    else:
        mean = sum(hist_values) / len(hist_values) if hist_values else actual_value
        expected_z = mean

    # --- 引擎2：预测偏差 ---
    severity_dev = "normal"
    deviation = 0.0
    expected_dev: Optional[float] = await _get_forecast_expected(db, store_id, period, metric)
    method = "z_score"
    if expected_dev is not None:
        deviation = compute_deviation_pct(actual_value, expected_dev)
        severity_dev = classify_severity_deviation(deviation)
        method = "forecast_deviation"

    # --- 合并：取较严重者 ---
    final_severity = merge_severity(severity_z, severity_dev)
    expected_final = expected_dev if expected_dev is not None else expected_z
    if expected_dev is None:
        deviation = compute_deviation_pct(actual_value, expected_z)

    is_anom = final_severity != "normal"
    impact = compute_yuan_impact(metric, actual_value, expected_final, revenue_for_impact)
    desc = generate_anomaly_description(
        metric,
        actual_value,
        expected_final,
        deviation,
        z_score,
        final_severity,
        impact,
    )

    await _upsert_anomaly(
        db,
        store_id,
        period,
        metric,
        actual_value,
        expected_final,
        deviation,
        z_score,
        is_anom,
        final_severity,
        method,
        desc,
        impact,
    )

    return {
        "metric": metric,
        "actual_value": actual_value,
        "expected_value": expected_final,
        "deviation_pct": round(deviation, 2),
        "z_score": round(z_score, 3),
        "is_anomaly": is_anom,
        "severity": final_severity,
        "detection_method": method,
        "description": desc,
        "yuan_impact": round(impact, 2) if impact is not None else None,
        "label": METRIC_LABELS.get(metric, metric),
    }


async def detect_store_anomalies(
    db: AsyncSession,
    store_id: str,
    period: str,
) -> Dict[str, Any]:
    """
    拉取当期实际数据，对4个维度执行检测，返回汇总。
    """
    # 读当期实际值
    profit_row = await db.execute(
        text("""
            SELECT net_revenue_yuan, food_cost_yuan, profit_margin_pct
            FROM profit_attribution_results
            WHERE store_id = :sid AND period = :period LIMIT 1
        """),
        {"sid": store_id, "period": period},
    )
    profit_row = profit_row.fetchone()

    health_row = await db.execute(
        text("""
            SELECT total_score FROM finance_health_scores
            WHERE store_id = :sid AND period = :period LIMIT 1
        """),
        {"sid": store_id, "period": period},
    )
    health_row = health_row.fetchone()

    results: List[Dict[str, Any]] = []
    revenue = 0.0

    if profit_row:
        revenue = _to_float(profit_row[0])
        fc = _to_float(profit_row[1])
        pm = _to_float(profit_row[2])
        fcr = fc / revenue * 100 if revenue > 0 else 0.0

        for metric, value in [
            ("revenue", revenue),
            ("food_cost_rate", fcr),
            ("profit_margin", pm),
        ]:
            try:
                r = await detect_metric_anomaly(db, store_id, period, metric, value, revenue)
                results.append(r)
            except Exception as exc:
                logger.warning("anomaly_detect_failed", store_id=store_id, metric=metric, error=str(exc))

    if health_row:
        try:
            r = await detect_metric_anomaly(
                db,
                store_id,
                period,
                "health_score",
                _to_float(health_row[0]),
                revenue,
            )
            results.append(r)
        except Exception as exc:
            logger.warning("anomaly_detect_failed", store_id=store_id, metric="health_score", error=str(exc))

    await db.commit()

    anomalies = [r for r in results if r["is_anomaly"]]
    severity_counts = {"severe": 0, "moderate": 0, "mild": 0, "normal": 0}
    for r in results:
        severity_counts[r["severity"]] = severity_counts.get(r["severity"], 0) + 1

    return {
        "store_id": store_id,
        "period": period,
        "metrics_checked": len(results),
        "anomaly_count": len(anomalies),
        "severity_counts": severity_counts,
        "anomalies": anomalies,
        "all_results": results,
    }


async def get_anomaly_records(
    db: AsyncSession,
    store_id: str,
    only_anomalies: bool = True,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """返回门店历史异常记录，默认只返回 is_anomaly=true 的。"""
    if only_anomalies:
        rows = await db.execute(
            text("""
                SELECT metric, period, actual_value, expected_value,
                       deviation_pct, z_score, severity, description,
                       yuan_impact, resolved, detected_at
                FROM financial_anomaly_records
                WHERE store_id = :sid AND is_anomaly = true
                ORDER BY detected_at DESC
                LIMIT :lim
            """),
            {"sid": store_id, "lim": limit},
        )
    else:
        rows = await db.execute(
            text("""
                SELECT metric, period, actual_value, expected_value,
                       deviation_pct, z_score, severity, description,
                       yuan_impact, resolved, detected_at
                FROM financial_anomaly_records
                WHERE store_id = :sid
                ORDER BY detected_at DESC
                LIMIT :lim
            """),
            {"sid": store_id, "lim": limit},
        )
    return [
        {
            "metric": r[0],
            "period": r[1],
            "actual_value": _safe_float(r[2]),
            "expected_value": _safe_float(r[3]),
            "deviation_pct": _safe_float(r[4]),
            "z_score": _safe_float(r[5]),
            "severity": r[6],
            "description": r[7],
            "yuan_impact": _safe_float(r[8]),
            "resolved": r[9],
            "detected_at": r[10].isoformat() if r[10] else None,
            "label": METRIC_LABELS.get(r[0], r[0]),
        }
        for r in rows.fetchall()
    ]


async def resolve_anomaly(
    db: AsyncSession,
    store_id: str,
    period: str,
    metric: str,
) -> Dict[str, Any]:
    """标记异常为已解决。"""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    result = await db.execute(
        text("""
            UPDATE financial_anomaly_records
            SET resolved = true, resolved_at = :now, updated_at = :now
            WHERE store_id = :sid AND period = :period AND metric = :metric
            RETURNING id
        """),
        {"sid": store_id, "period": period, "metric": metric, "now": now},
    )
    row = result.fetchone()
    await db.commit()
    return {"resolved": row is not None, "store_id": store_id, "period": period, "metric": metric}


async def get_anomaly_trend(
    db: AsyncSession,
    store_id: str,
    periods: int = 6,
) -> List[Dict[str, Any]]:
    """
    返回最近 N 期的每期异常计数（按 severity 分组），升序。
    """
    rows = await db.execute(
        text("""
            SELECT period, severity, COUNT(*) AS cnt
            FROM financial_anomaly_records
            WHERE store_id = :sid AND is_anomaly = true
            GROUP BY period, severity
            ORDER BY period ASC
            LIMIT :lim
        """),
        {"sid": store_id, "lim": periods * 4},
    )
    # 聚合为 {period → {severity: count}}
    by_period: Dict[str, Dict[str, int]] = {}
    for r in rows.fetchall():
        p, sev, cnt = r[0], r[1], int(r[2])
        if p not in by_period:
            by_period[p] = {"severe": 0, "moderate": 0, "mild": 0}
        by_period[p][sev] = cnt

    return [{"period": p, **counts} for p, counts in sorted(by_period.items())]


async def get_brand_anomaly_summary(
    db: AsyncSession,
    brand_id: str,
    period: str,
) -> Dict[str, Any]:
    """品牌级当期异常汇总（所有门店合并）。"""
    rows = await db.execute(
        text("""
            SELECT store_id, metric, severity, is_anomaly, description, yuan_impact
            FROM financial_anomaly_records
            WHERE period = :period AND is_anomaly = true
            ORDER BY store_id, severity DESC
        """),
        {"period": period},
    )
    rows = rows.fetchall()

    by_store: Dict[str, List[Dict]] = {}
    total_yuan_impact = 0.0
    severity_counts = {"severe": 0, "moderate": 0, "mild": 0}

    for r in rows:
        sid, metric, sev, _, desc, impact = r[0], r[1], r[2], r[3], r[4], r[5]
        if sid not in by_store:
            by_store[sid] = []
        by_store[sid].append(
            {
                "metric": metric,
                "severity": sev,
                "description": desc,
                "yuan_impact": _safe_float(impact),
            }
        )
        severity_counts[sev] = severity_counts.get(sev, 0) + 1
        if impact is not None:
            total_yuan_impact += abs(_to_float(impact))

    return {
        "brand_id": brand_id,
        "period": period,
        "total_anomalies": len(rows),
        "affected_stores": len(by_store),
        "severity_counts": severity_counts,
        "total_yuan_impact": round(total_yuan_impact, 2),
        "by_store": [{"store_id": s, "anomalies": a} for s, a in by_store.items()],
    }
