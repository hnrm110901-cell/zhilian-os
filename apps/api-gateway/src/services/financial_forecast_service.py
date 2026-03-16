"""智能财务预测引擎 — Phase 5 Month 7

基于近6期月度历史数据，对4个财务维度进行前瞻预测：
  - revenue        : 门店月净收入 (¥)
  - food_cost_rate : 食材成本率 (%)
  - profit_margin  : 利润率 (%)
  - health_score   : 财务健康综合评分 (0-100)

算法：加权移动平均（WMA）作为点估计，线性趋势辅助判断方向。
置信区间：基于历史波动的 ±1.96σ（95% CI）。
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

HISTORY_PERIODS = 6  # 默认使用最近6期历史
MIN_PERIODS = 2  # 最少需要2期才能预测
FORECAST_TYPES = ("revenue", "food_cost_rate", "profit_margin", "health_score")

FORECAST_TYPE_LABELS = {
    "revenue": "月净收入 (¥)",
    "food_cost_rate": "食材成本率 (%)",
    "profit_margin": "利润率 (%)",
    "health_score": "健康评分",
}

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
    """返回 target_period 之前的 n 个月份，升序排列。"""
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
# 纯函数层（无 DB 依赖，全部可直接单元测试）
# ══════════════════════════════════════════════════════════════════════════════


def linear_trend(
    values: List[float],
    periods_ahead: int = 1,
) -> Tuple[float, float, float]:
    """
    最小二乘线性趋势预测。

    Returns:
        (predicted, lower_95, upper_95)

    边界处理：
    - n < 2 → 返回最后一个值 ±10%
    - n = 2 → 斜率计算但无残差，用10%作为std_err
    """
    n = len(values)
    if n == 0:
        return (0.0, 0.0, 0.0)
    if n == 1:
        v = values[0]
        margin = abs(v) * 0.1 + 1e-6
        return (v, v - margin, v + margin)

    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n

    num = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
    den = sum((i - x_mean) ** 2 for i in range(n))
    slope = num / den if den > 0 else 0.0
    intercept = y_mean - slope * x_mean

    x_pred = n - 1 + periods_ahead
    predicted = intercept + slope * x_pred

    # 残差标准误差
    residuals = [values[i] - (intercept + slope * i) for i in range(n)]
    if n > 2:
        se = math.sqrt(sum(r**2 for r in residuals) / (n - 2))
    else:
        se = abs(values[-1] - values[0]) * 0.1 + 1e-6

    return (predicted, predicted - 1.96 * se, predicted + 1.96 * se)


def weighted_moving_avg(
    values: List[float],
    periods_ahead: int = 1,
) -> float:
    """
    线性加权移动平均（最近一期权重最高）。
    多步预测：递归将预测值追加到序列尾部后再计算。
    """
    if not values:
        return 0.0

    n = len(values)
    weights = list(range(1, n + 1))  # [1, 2, ..., n]
    total_w = sum(weights)
    wma = sum(weights[i] * values[i] for i in range(n)) / total_w

    if periods_ahead <= 1:
        return wma

    # 递归多步预测
    return weighted_moving_avg(values[1:] + [wma], periods_ahead - 1)


def compute_forecast_accuracy(predicted: float, actual: float) -> float:
    """
    MAPE 为基础的精度分 (0-100)。
    accuracy = max(0, 100 - |predicted-actual|/|actual| * 100)
    actual=0 时：predicted=0 → 100，否则 → 0。
    """
    if actual == 0.0:
        return 100.0 if predicted == 0.0 else 0.0
    mape = abs(predicted - actual) / abs(actual) * 100.0
    return round(max(0.0, 100.0 - mape), 2)


def confidence_interval(
    values: List[float],
    predicted: float,
    z: float = 1.96,
) -> Tuple[float, float]:
    """
    基于历史标准差计算 95% CI。
    n < 2 时：返回 predicted ±10%。
    """
    if len(values) < 2:
        margin = abs(predicted) * 0.1 + 1e-6
        return (predicted - margin, predicted + margin)
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    std = math.sqrt(variance)
    return (predicted - z * std, predicted + z * std)


def trend_direction(values: List[float]) -> str:
    """返回趋势方向：'up' / 'down' / 'flat'（基于线性回归斜率）。"""
    if len(values) < 2:
        return "flat"
    _, _, _ = (0, 0, 0)
    slope = linear_trend(values)[0] - values[-1]
    pct = slope / (abs(values[-1]) + 1e-9) * 100
    if pct > 1.0:
        return "up"
    if pct < -1.0:
        return "down"
    return "flat"


# ══════════════════════════════════════════════════════════════════════════════
# DB 函数层
# ══════════════════════════════════════════════════════════════════════════════


async def _upsert_forecast(
    db: AsyncSession,
    store_id: str,
    target_period: str,
    forecast_type: str,
    predicted: float,
    lower: float,
    upper: float,
    method: str,
    n_periods: int,
) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.execute(
        text("""
            INSERT INTO financial_forecasts
                (store_id, target_period, forecast_type, predicted_value,
                 lower_bound, upper_bound, confidence_pct, method,
                 based_on_periods, computed_at, updated_at)
            VALUES
                (:sid, :tp, :ft, :pv, :lb, :ub, 95.0, :method, :np, :now, :now)
            ON CONFLICT (store_id, target_period, forecast_type) DO UPDATE SET
                predicted_value  = EXCLUDED.predicted_value,
                lower_bound      = EXCLUDED.lower_bound,
                upper_bound      = EXCLUDED.upper_bound,
                method           = EXCLUDED.method,
                based_on_periods = EXCLUDED.based_on_periods,
                updated_at       = EXCLUDED.updated_at
        """),
        {
            "sid": store_id,
            "tp": target_period,
            "ft": forecast_type,
            "pv": round(predicted, 4),
            "lb": round(lower, 4),
            "ub": round(upper, 4),
            "method": method,
            "np": n_periods,
            "now": now,
        },
    )


async def _fetch_profit_history(
    db: AsyncSession,
    store_id: str,
    periods: List[str],
) -> List[Dict[str, Any]]:
    """从 profit_attribution_results 拉取多期数据（只取有匹配的期）。"""
    stmt = text("""
        SELECT period, net_revenue_yuan, food_cost_yuan, profit_margin_pct
        FROM profit_attribution_results
        WHERE store_id = :sid AND period IN :periods
        ORDER BY period ASC
    """).bindparams(bindparam("periods", expanding=True))
    rows = await db.execute(stmt, {"sid": store_id, "periods": periods})
    return [
        {
            "period": r[0],
            "net_revenue_yuan": _to_float(r[1]),
            "food_cost_yuan": _to_float(r[2]),
            "profit_margin_pct": _to_float(r[3]),
        }
        for r in rows.fetchall()
    ]


async def _fetch_health_history(
    db: AsyncSession,
    store_id: str,
    periods: List[str],
) -> List[Dict[str, Any]]:
    """从 finance_health_scores 拉取多期健康评分。"""
    stmt = text("""
        SELECT period, total_score
        FROM finance_health_scores
        WHERE store_id = :sid AND period IN :periods
        ORDER BY period ASC
    """).bindparams(bindparam("periods", expanding=True))
    rows = await db.execute(stmt, {"sid": store_id, "periods": periods})
    return [{"period": r[0], "total_score": _to_float(r[1])} for r in rows.fetchall()]


def _make_forecast_result(
    forecast_type: str,
    values: List[float],
    target_period: str,
    hist_periods: List[str],
) -> Optional[Dict[str, Any]]:
    """
    通用预测结果构造器（纯函数部分，供 compute_* 函数调用）。
    values 已按时间升序排列。
    """
    if len(values) < MIN_PERIODS:
        return None

    predicted = weighted_moving_avg(values)
    lower, upper = confidence_interval(values, predicted)
    _, lt_lower, lt_upper = linear_trend(values)
    direction = trend_direction(values)

    return {
        "forecast_type": forecast_type,
        "target_period": target_period,
        "predicted_value": round(predicted, 4),
        "lower_bound": round(lower, 4),
        "upper_bound": round(upper, 4),
        "confidence_pct": 95.0,
        "method": "weighted_moving_avg",
        "based_on_periods": len(values),
        "trend_direction": direction,
        "history": [{"period": p, "value": v} for p, v in zip(hist_periods[-len(values) :], values)],
        "label": FORECAST_TYPE_LABELS.get(forecast_type, forecast_type),
    }


async def compute_revenue_forecast(
    db: AsyncSession,
    store_id: str,
    target_period: str,
    n: int = HISTORY_PERIODS,
) -> Optional[Dict[str, Any]]:
    periods = _prev_periods(target_period, n)
    history = await _fetch_profit_history(db, store_id, periods)
    values = [r["net_revenue_yuan"] for r in history]
    result = _make_forecast_result("revenue", values, target_period, periods)
    if result:
        await _upsert_forecast(
            db,
            store_id,
            target_period,
            "revenue",
            result["predicted_value"],
            result["lower_bound"],
            result["upper_bound"],
            "weighted_moving_avg",
            len(values),
        )
    return result


async def compute_food_cost_rate_forecast(
    db: AsyncSession,
    store_id: str,
    target_period: str,
    n: int = HISTORY_PERIODS,
) -> Optional[Dict[str, Any]]:
    periods = _prev_periods(target_period, n)
    history = await _fetch_profit_history(db, store_id, periods)
    values = []
    for r in history:
        if r["net_revenue_yuan"] > 0:
            rate = r["food_cost_yuan"] / r["net_revenue_yuan"] * 100
        else:
            rate = 0.0
        values.append(round(rate, 2))
    result = _make_forecast_result("food_cost_rate", values, target_period, periods)
    if result:
        await _upsert_forecast(
            db,
            store_id,
            target_period,
            "food_cost_rate",
            result["predicted_value"],
            result["lower_bound"],
            result["upper_bound"],
            "weighted_moving_avg",
            len(values),
        )
    return result


async def compute_profit_margin_forecast(
    db: AsyncSession,
    store_id: str,
    target_period: str,
    n: int = HISTORY_PERIODS,
) -> Optional[Dict[str, Any]]:
    periods = _prev_periods(target_period, n)
    history = await _fetch_profit_history(db, store_id, periods)
    values = [r["profit_margin_pct"] for r in history]
    result = _make_forecast_result("profit_margin", values, target_period, periods)
    if result:
        await _upsert_forecast(
            db,
            store_id,
            target_period,
            "profit_margin",
            result["predicted_value"],
            result["lower_bound"],
            result["upper_bound"],
            "weighted_moving_avg",
            len(values),
        )
    return result


async def compute_health_score_forecast(
    db: AsyncSession,
    store_id: str,
    target_period: str,
    n: int = HISTORY_PERIODS,
) -> Optional[Dict[str, Any]]:
    periods = _prev_periods(target_period, n)
    history = await _fetch_health_history(db, store_id, periods)
    values = [r["total_score"] for r in history]
    result = _make_forecast_result("health_score", values, target_period, periods)
    if result:
        await _upsert_forecast(
            db,
            store_id,
            target_period,
            "health_score",
            result["predicted_value"],
            result["lower_bound"],
            result["upper_bound"],
            "weighted_moving_avg",
            len(values),
        )
    return result


async def compute_all_forecasts(
    db: AsyncSession,
    store_id: str,
    target_period: str,
) -> Dict[str, Any]:
    """
    计算全部 4 个预测类型，各自 upsert，返回汇总 dict。
    子任务独立 try/except：单个失败不影响整体。
    """
    results: Dict[str, Any] = {
        "store_id": store_id,
        "target_period": target_period,
    }
    for fn, key in [
        (compute_revenue_forecast, "revenue"),
        (compute_food_cost_rate_forecast, "food_cost_rate"),
        (compute_profit_margin_forecast, "profit_margin"),
        (compute_health_score_forecast, "health_score"),
    ]:
        try:
            results[key] = await fn(db, store_id, target_period)
        except Exception as exc:
            logger.warning("forecast_compute_failed", store_id=store_id, forecast_type=key, error=str(exc))
            results[key] = None

    await db.commit()
    return results


async def get_forecast(
    db: AsyncSession,
    store_id: str,
    target_period: str,
) -> Optional[Dict[str, Any]]:
    """返回已计算的预测快照（无则返回 None）。"""
    rows = await db.execute(
        text("""
            SELECT forecast_type, predicted_value, lower_bound, upper_bound,
                   confidence_pct, method, based_on_periods,
                   actual_value, accuracy_pct, computed_at
            FROM financial_forecasts
            WHERE store_id = :sid AND target_period = :tp
            ORDER BY forecast_type
        """),
        {"sid": store_id, "tp": target_period},
    )
    rows = rows.fetchall()
    if not rows:
        return None

    result = {"store_id": store_id, "target_period": target_period, "forecasts": []}
    for r in rows:
        result["forecasts"].append(
            {
                "forecast_type": r[0],
                "predicted_value": _safe_float(r[1]),
                "lower_bound": _safe_float(r[2]),
                "upper_bound": _safe_float(r[3]),
                "confidence_pct": _safe_float(r[4]),
                "method": r[5],
                "based_on_periods": r[6],
                "actual_value": _safe_float(r[7]),
                "accuracy_pct": _safe_float(r[8]),
                "computed_at": r[9].isoformat() if r[9] else None,
                "label": FORECAST_TYPE_LABELS.get(r[0], r[0]),
            }
        )
    return result


async def get_forecast_accuracy_history(
    db: AsyncSession,
    store_id: str,
    periods: int = 6,
) -> List[Dict[str, Any]]:
    """
    查询近 periods 期内有实际值的历史预测，计算并返回精度记录。
    结果按 (forecast_type, target_period) 升序。
    """
    rows = await db.execute(
        text("""
            SELECT forecast_type, target_period, predicted_value, actual_value, accuracy_pct
            FROM financial_forecasts
            WHERE store_id = :sid
              AND actual_value IS NOT NULL
            ORDER BY forecast_type, target_period DESC
            LIMIT :lim
        """),
        {"sid": store_id, "lim": periods * len(FORECAST_TYPES)},
    )
    return [
        {
            "forecast_type": r[0],
            "target_period": r[1],
            "predicted_value": _safe_float(r[2]),
            "actual_value": _safe_float(r[3]),
            "accuracy_pct": _safe_float(r[4]),
            "label": FORECAST_TYPE_LABELS.get(r[0], r[0]),
        }
        for r in rows.fetchall()
    ]


async def backfill_actual_values(
    db: AsyncSession,
    store_id: str,
    period: str,
) -> Dict[str, int]:
    """
    将已有实际数据回填到预测记录的 actual_value 字段，并计算 accuracy_pct。
    调用时机：当某期实际数据入库后（例如月末结算）。
    """
    updated = 0

    # 1. revenue & food_cost_rate & profit_margin — from profit_attribution_results
    profit_row = await db.execute(
        text("""
            SELECT net_revenue_yuan, food_cost_yuan, profit_margin_pct
            FROM profit_attribution_results
            WHERE store_id = :sid AND period = :period
            LIMIT 1
        """),
        {"sid": store_id, "period": period},
    )
    profit_row = profit_row.fetchone()

    if profit_row:
        rev = _to_float(profit_row[0])
        fc = _to_float(profit_row[1])
        pm = _to_float(profit_row[2])
        fcr = fc / rev * 100 if rev > 0 else 0.0

        for ft, actual in [("revenue", rev), ("food_cost_rate", fcr), ("profit_margin", pm)]:
            pred_row = await db.execute(
                text("""
                    SELECT predicted_value FROM financial_forecasts
                    WHERE store_id = :sid AND target_period = :tp AND forecast_type = :ft
                """),
                {"sid": store_id, "tp": period, "ft": ft},
            )
            pred_row = pred_row.fetchone()
            if pred_row and pred_row[0] is not None:
                acc = compute_forecast_accuracy(_to_float(pred_row[0]), actual)
                await db.execute(
                    text("""
                        UPDATE financial_forecasts
                        SET actual_value = :av, accuracy_pct = :ap, updated_at = :now
                        WHERE store_id = :sid AND target_period = :tp AND forecast_type = :ft
                    """),
                    {
                        "av": round(actual, 4),
                        "ap": acc,
                        "now": datetime.now(timezone.utc).replace(tzinfo=None),
                        "sid": store_id,
                        "tp": period,
                        "ft": ft,
                    },
                )
                updated += 1

    # 2. health_score — from finance_health_scores
    health_row = await db.execute(
        text("""
            SELECT total_score FROM finance_health_scores
            WHERE store_id = :sid AND period = :period LIMIT 1
        """),
        {"sid": store_id, "period": period},
    )
    health_row = health_row.fetchone()

    if health_row:
        actual_score = _to_float(health_row[0])
        pred_row2 = await db.execute(
            text("""
                SELECT predicted_value FROM financial_forecasts
                WHERE store_id = :sid AND target_period = :tp AND forecast_type = 'health_score'
            """),
            {"sid": store_id, "tp": period},
        )
        pred_row2 = pred_row2.fetchone()
        if pred_row2 and pred_row2[0] is not None:
            acc = compute_forecast_accuracy(_to_float(pred_row2[0]), actual_score)
            await db.execute(
                text("""
                    UPDATE financial_forecasts
                    SET actual_value = :av, accuracy_pct = :ap, updated_at = :now
                    WHERE store_id = :sid AND target_period = :tp AND forecast_type = 'health_score'
                """),
                {
                    "av": round(actual_score, 4),
                    "ap": acc,
                    "now": datetime.now(timezone.utc).replace(tzinfo=None),
                    "sid": store_id,
                    "tp": period,
                },
            )
            updated += 1

    await db.commit()
    return {"updated": updated}


async def get_brand_forecast_summary(
    db: AsyncSession,
    brand_id: str,
    target_period: str,
) -> Dict[str, Any]:
    """
    品牌级预测汇总：各门店预测值的均值/最大/最小。
    （当前无 brand→store 映射表，查询全部门店的 target_period 预测记录。）
    """
    rows = await db.execute(
        text("""
            SELECT store_id, forecast_type, predicted_value
            FROM financial_forecasts
            WHERE target_period = :tp
            ORDER BY forecast_type, store_id
        """),
        {"tp": target_period},
    )
    rows = rows.fetchall()

    by_type: Dict[str, List[float]] = {}
    for r in rows:
        ft = r[1]
        if ft not in by_type:
            by_type[ft] = []
        v = _safe_float(r[2])
        if v is not None:
            by_type[ft].append(v)

    summary = {"brand_id": brand_id, "target_period": target_period, "by_type": {}}
    for ft, vals in by_type.items():
        if vals:
            summary["by_type"][ft] = {
                "avg": round(sum(vals) / len(vals), 4),
                "min": round(min(vals), 4),
                "max": round(max(vals), 4),
                "count": len(vals),
                "label": FORECAST_TYPE_LABELS.get(ft, ft),
            }
    return summary
