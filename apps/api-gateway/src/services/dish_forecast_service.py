"""菜品销售预测引擎 — Phase 6 Month 7

基于近 N 期 dish_profitability_records，用加权移动平均 + 线性趋势因子
预测下期销量/营收，并用生命周期阶段做最终修正。
支持事后精度追踪（预测值 vs 实际值 JOIN 对比）。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# ── 常量 ───────────────────────────────────────────────────────────────────────
HISTORY_PERIODS = 6  # 最多使用近 6 期历史

# 生命周期阶段对预测的修正量
LIFECYCLE_ADJUSTMENT: dict[str, float] = {
    "launch": 0.15,  # 新品 +15%
    "growth": 0.10,  # 成长期 +10%
    "peak": 0.00,  # 成熟期不修正
    "decline": -0.08,  # 衰退期 -8%
    "exit": -0.20,  # 退出期 -20%
}


# ── 纯函数 ─────────────────────────────────────────────────────────────────────


def compute_weighted_avg(values: list[float], weights: list[float] | None = None) -> float:
    """
    加权平均。默认权重 [1, 2, …, n]（越近越重）。
    空列表返回 0.0。
    """
    if not values:
        return 0.0
    n = len(values)
    if weights is None or len(weights) != n:
        weights = list(range(1, n + 1))
    total_w = sum(weights)
    if total_w == 0:
        return 0.0
    return sum(v * w for v, w in zip(values, weights)) / total_w


def compute_trend_factor(values: list[float]) -> float:
    """
    简单线性回归斜率 / |均值| × 100，表示每期变化百分点。
    len < 2 返回 0.0；均值为 0 返回 0.0。
    """
    n = len(values)
    if n < 2:
        return 0.0
    mean_v = sum(values) / n
    if mean_v == 0:
        return 0.0
    x_mean = (n - 1) / 2.0
    numer = sum((i - x_mean) * (v - mean_v) for i, v in enumerate(values))
    denom = sum((i - x_mean) ** 2 for i in range(n))
    if denom == 0:
        return 0.0
    slope = numer / denom
    return round(slope / abs(mean_v) * 100.0, 2)


def apply_lifecycle_adjustment(base: float, lifecycle_phase: str) -> float:
    """按生命周期阶段对基础预测值做修正。"""
    adj = LIFECYCLE_ADJUSTMENT.get(lifecycle_phase, 0.0)
    return round(base * (1 + adj), 2)


def compute_confidence_interval(point: float, periods_used: int) -> tuple[float, float]:
    """
    对称置信区间 [low, high]。
    不确定度随历史期数增加而收窄：max(10%, 30% - periods_used × 4%)。
    low 最小为 0。
    """
    uncertainty = max(0.10, 0.30 - periods_used * 0.04)
    low = round(max(0.0, point * (1 - uncertainty)), 1)
    high = round(point * (1 + uncertainty), 1)
    return low, high


def build_forecast_record(
    store_id: str,
    forecast_period: str,
    base_period: str,
    dish_id: str,
    dish_name: str,
    category: Optional[str],
    history: list[dict],
    lifecycle_phase: str = "peak",
) -> Optional[dict]:
    """
    基于历史数据列表（按期间升序）构建单道菜的预测记录。
    history 每项需含: order_count, revenue_yuan, food_cost_rate, gross_profit_margin。
    history 为空返回 None。
    """
    if not history:
        return None

    n = len(history)
    weights = list(range(1, n + 1))

    orders_list = [float(h["order_count"]) for h in history]
    revenue_list = [float(h["revenue_yuan"]) for h in history]
    fcr_list = [float(h["food_cost_rate"]) for h in history]
    gpm_list = [float(h["gross_profit_margin"]) for h in history]

    base_orders = compute_weighted_avg(orders_list, weights)
    base_revenue = compute_weighted_avg(revenue_list, weights)
    avg_fcr = compute_weighted_avg(fcr_list, weights)
    avg_gpm = compute_weighted_avg(gpm_list, weights)

    trend_orders = compute_trend_factor(orders_list)
    trend_revenue = compute_trend_factor(revenue_list)

    # 趋势外推一期
    trended_orders = base_orders * (1 + trend_orders / 100.0)
    trended_revenue = base_revenue * (1 + trend_revenue / 100.0)

    # 生命周期修正
    pred_orders = apply_lifecycle_adjustment(trended_orders, lifecycle_phase)
    pred_revenue = apply_lifecycle_adjustment(trended_revenue, lifecycle_phase)

    pred_orders = max(0.0, pred_orders)
    pred_revenue = max(0.0, pred_revenue)

    o_low, o_high = compute_confidence_interval(pred_orders, n)
    r_low, r_high = compute_confidence_interval(pred_revenue, n)

    lc_adj_pct = round(LIFECYCLE_ADJUSTMENT.get(lifecycle_phase, 0.0) * 100.0, 1)

    return {
        "store_id": store_id,
        "forecast_period": forecast_period,
        "base_period": base_period,
        "dish_id": dish_id,
        "dish_name": dish_name,
        "category": category,
        "lifecycle_phase": lifecycle_phase,
        "periods_used": n,
        "hist_avg_orders": round(base_orders, 1),
        "hist_avg_revenue": round(base_revenue, 2),
        "trend_orders_pct": trend_orders,
        "trend_revenue_pct": trend_revenue,
        "lifecycle_adj_pct": lc_adj_pct,
        "predicted_order_count": round(pred_orders, 1),
        "predicted_order_low": o_low,
        "predicted_order_high": o_high,
        "predicted_revenue_yuan": round(pred_revenue, 2),
        "predicted_revenue_low": r_low,
        "predicted_revenue_high": r_high,
        "predicted_fcr": round(avg_fcr, 2),
        "predicted_gpm": round(avg_gpm, 2),
    }


# ── 期间辅助 ───────────────────────────────────────────────────────────────────


def _next_period(period: str) -> str:
    """返回下一个 YYYY-MM。"""
    year, month = int(period[:4]), int(period[5:7])
    if month == 12:
        return f"{year + 1:04d}-01"
    return f"{year:04d}-{month + 1:02d}"


def _start_period(period: str, n: int) -> str:
    year, month = int(period[:4]), int(period[5:7])
    total = year * 12 + (month - 1) - (n - 1)
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


# ── 数据库函数 ──────────────────────────────────────────────────────────────────


async def _fetch_all_dish_history(
    db: AsyncSession,
    store_id: str,
    up_to_period: str,
    n_periods: int = HISTORY_PERIODS,
) -> tuple[dict[str, list[dict]], dict[str, tuple]]:
    """
    批量拉取所有菜品近 n_periods 期的历史数据。
    返回 (by_dish_id, dish_meta)
      by_dish_id: {dish_id: [期间数据列表, 按期升序]}
      dish_meta:  {dish_id: (dish_name, category)}
    """
    start = _start_period(up_to_period, n_periods)
    sql = text("""
        SELECT dish_id, dish_name, category, period,
               order_count, revenue_yuan, food_cost_rate, gross_profit_margin
        FROM dish_profitability_records
        WHERE store_id = :store_id
          AND period >= :start AND period <= :up_to_period
        ORDER BY dish_id, period ASC
    """)
    rows = (await db.execute(sql, {"store_id": store_id, "start": start, "up_to_period": up_to_period})).fetchall()

    by_dish: dict[str, list[dict]] = defaultdict(list)
    dish_meta: dict[str, tuple] = {}
    for r in rows:
        dish_id = r[0]
        dish_meta[dish_id] = (r[1], r[2])  # (dish_name, category)
        by_dish[dish_id].append(
            {
                "period": r[3],
                "order_count": int(r[4] or 0),
                "revenue_yuan": float(r[5] or 0),
                "food_cost_rate": float(r[6] or 0),
                "gross_profit_margin": float(r[7] or 0),
            }
        )
    return dict(by_dish), dish_meta


async def _fetch_lifecycle_phases(db: AsyncSession, store_id: str, period: str) -> dict[str, str]:
    """拉取该期所有菜品的生命周期阶段。"""
    sql = text("""
        SELECT dish_id, phase
        FROM dish_lifecycle_records
        WHERE store_id = :store_id AND period = :period
    """)
    rows = (await db.execute(sql, {"store_id": store_id, "period": period})).fetchall()
    return {r[0]: r[1] for r in rows}


async def _upsert_forecast_record(db: AsyncSession, rec: dict) -> None:
    """幂等写入，全量覆盖。"""
    sql = text("""
        INSERT INTO dish_forecast_records (
            store_id, forecast_period, base_period, dish_id, dish_name, category,
            lifecycle_phase, periods_used,
            hist_avg_orders, hist_avg_revenue,
            trend_orders_pct, trend_revenue_pct, lifecycle_adj_pct,
            predicted_order_count, predicted_order_low, predicted_order_high,
            predicted_revenue_yuan, predicted_revenue_low, predicted_revenue_high,
            predicted_fcr, predicted_gpm,
            computed_at, updated_at
        ) VALUES (
            :store_id, :forecast_period, :base_period, :dish_id, :dish_name, :category,
            :lifecycle_phase, :periods_used,
            :hist_avg_orders, :hist_avg_revenue,
            :trend_orders_pct, :trend_revenue_pct, :lifecycle_adj_pct,
            :predicted_order_count, :predicted_order_low, :predicted_order_high,
            :predicted_revenue_yuan, :predicted_revenue_low, :predicted_revenue_high,
            :predicted_fcr, :predicted_gpm,
            NOW(), NOW()
        )
        ON CONFLICT (store_id, forecast_period, dish_id) DO UPDATE SET
            base_period            = EXCLUDED.base_period,
            dish_name              = EXCLUDED.dish_name,
            category               = EXCLUDED.category,
            lifecycle_phase        = EXCLUDED.lifecycle_phase,
            periods_used           = EXCLUDED.periods_used,
            hist_avg_orders        = EXCLUDED.hist_avg_orders,
            hist_avg_revenue       = EXCLUDED.hist_avg_revenue,
            trend_orders_pct       = EXCLUDED.trend_orders_pct,
            trend_revenue_pct      = EXCLUDED.trend_revenue_pct,
            lifecycle_adj_pct      = EXCLUDED.lifecycle_adj_pct,
            predicted_order_count  = EXCLUDED.predicted_order_count,
            predicted_order_low    = EXCLUDED.predicted_order_low,
            predicted_order_high   = EXCLUDED.predicted_order_high,
            predicted_revenue_yuan = EXCLUDED.predicted_revenue_yuan,
            predicted_revenue_low  = EXCLUDED.predicted_revenue_low,
            predicted_revenue_high = EXCLUDED.predicted_revenue_high,
            predicted_fcr          = EXCLUDED.predicted_fcr,
            predicted_gpm          = EXCLUDED.predicted_gpm,
            updated_at             = NOW()
    """)
    await db.execute(sql, rec)


async def generate_dish_forecasts(
    db: AsyncSession, store_id: str, base_period: str, forecast_period: Optional[str] = None
) -> dict:
    """
    生成门店所有菜品的下期预测。幂等。
    forecast_period 默认为 base_period 的下一期。
    返回 {dish_count, forecast_period, total_predicted_revenue, phase_counts}
    """
    if forecast_period is None:
        forecast_period = _next_period(base_period)

    by_dish, dish_meta = await _fetch_all_dish_history(db, store_id, base_period)
    if not by_dish:
        await db.commit()
        return {
            "store_id": store_id,
            "base_period": base_period,
            "forecast_period": forecast_period,
            "dish_count": 0,
            "total_predicted_revenue": 0.0,
            "phase_counts": {},
        }

    lifecycle_phases = await _fetch_lifecycle_phases(db, store_id, base_period)

    total_rev = 0.0
    phase_counts: dict[str, int] = {}

    for dish_id, history in by_dish.items():
        dish_name, category = dish_meta[dish_id]
        phase = lifecycle_phases.get(dish_id, "peak")  # default peak if no lifecycle data

        rec = build_forecast_record(store_id, forecast_period, base_period, dish_id, dish_name, category, history, phase)
        if rec is None:
            continue
        await _upsert_forecast_record(db, rec)
        total_rev += rec["predicted_revenue_yuan"]
        phase_counts[phase] = phase_counts.get(phase, 0) + 1

    await db.commit()
    return {
        "store_id": store_id,
        "base_period": base_period,
        "forecast_period": forecast_period,
        "dish_count": len(by_dish),
        "total_predicted_revenue": round(total_rev, 2),
        "phase_counts": phase_counts,
    }


async def get_dish_forecasts(
    db: AsyncSession, store_id: str, forecast_period: str, lifecycle_phase: Optional[str] = None, limit: int = 100
) -> list[dict]:
    """
    查询门店某预测期的菜品预测列表。
    L011合规：两路 text() 分支。
    """
    if lifecycle_phase:
        sql = text("""
            SELECT id, dish_id, dish_name, category, lifecycle_phase,
                   periods_used, hist_avg_orders, hist_avg_revenue,
                   trend_orders_pct, trend_revenue_pct, lifecycle_adj_pct,
                   predicted_order_count, predicted_order_low, predicted_order_high,
                   predicted_revenue_yuan, predicted_revenue_low, predicted_revenue_high,
                   predicted_fcr, predicted_gpm, base_period
            FROM dish_forecast_records
            WHERE store_id = :store_id AND forecast_period = :forecast_period
              AND lifecycle_phase = :lifecycle_phase
            ORDER BY predicted_revenue_yuan DESC
            LIMIT :limit
        """)
        params = {"store_id": store_id, "forecast_period": forecast_period, "lifecycle_phase": lifecycle_phase, "limit": limit}
    else:
        sql = text("""
            SELECT id, dish_id, dish_name, category, lifecycle_phase,
                   periods_used, hist_avg_orders, hist_avg_revenue,
                   trend_orders_pct, trend_revenue_pct, lifecycle_adj_pct,
                   predicted_order_count, predicted_order_low, predicted_order_high,
                   predicted_revenue_yuan, predicted_revenue_low, predicted_revenue_high,
                   predicted_fcr, predicted_gpm, base_period
            FROM dish_forecast_records
            WHERE store_id = :store_id AND forecast_period = :forecast_period
            ORDER BY predicted_revenue_yuan DESC
            LIMIT :limit
        """)
        params = {"store_id": store_id, "forecast_period": forecast_period, "limit": limit}

    rows = (await db.execute(sql, params)).fetchall()
    cols = [
        "id",
        "dish_id",
        "dish_name",
        "category",
        "lifecycle_phase",
        "periods_used",
        "hist_avg_orders",
        "hist_avg_revenue",
        "trend_orders_pct",
        "trend_revenue_pct",
        "lifecycle_adj_pct",
        "predicted_order_count",
        "predicted_order_low",
        "predicted_order_high",
        "predicted_revenue_yuan",
        "predicted_revenue_low",
        "predicted_revenue_high",
        "predicted_fcr",
        "predicted_gpm",
        "base_period",
    ]
    return [dict(zip(cols, r)) for r in rows]


async def get_forecast_summary(db: AsyncSession, store_id: str, forecast_period: str) -> dict:
    """按生命周期阶段聚合预测统计。"""
    sql = text("""
        SELECT
            lifecycle_phase,
            COUNT(*)                          AS dish_count,
            SUM(predicted_order_count)        AS total_orders,
            SUM(predicted_revenue_yuan)       AS total_revenue,
            AVG(trend_revenue_pct)            AS avg_trend,
            AVG(lifecycle_adj_pct)            AS avg_lc_adj,
            AVG(periods_used)                 AS avg_periods_used
        FROM dish_forecast_records
        WHERE store_id = :store_id AND forecast_period = :forecast_period
        GROUP BY lifecycle_phase
        ORDER BY lifecycle_phase
    """)
    rows = (await db.execute(sql, {"store_id": store_id, "forecast_period": forecast_period})).fetchall()

    by_phase = []
    total_dishes = 0
    total_revenue = 0.0

    for r in rows:
        item = {
            "lifecycle_phase": r[0],
            "dish_count": int(r[1]),
            "total_orders": float(r[2] or 0),
            "total_revenue": float(r[3] or 0),
            "avg_trend": float(r[4] or 0),
            "avg_lc_adj": float(r[5] or 0),
            "avg_periods_used": float(r[6] or 0),
        }
        by_phase.append(item)
        total_dishes += item["dish_count"]
        total_revenue += item["total_revenue"]

    return {
        "store_id": store_id,
        "forecast_period": forecast_period,
        "total_dishes": total_dishes,
        "total_revenue": round(total_revenue, 2),
        "by_phase": by_phase,
    }


async def get_forecast_accuracy(db: AsyncSession, store_id: str, forecast_period: str, limit: int = 50) -> list[dict]:
    """
    将预测值与实际值（dish_profitability_records）JOIN 对比，
    计算订单/营收预测误差百分比。
    仅在 forecast_period 的实际数据已入库后有结果。
    """
    sql = text("""
        SELECT
            f.dish_id,
            f.dish_name,
            f.category,
            f.lifecycle_phase,
            f.predicted_order_count,
            f.predicted_revenue_yuan,
            a.order_count                                    AS actual_orders,
            a.revenue_yuan                                   AS actual_revenue,
            CASE WHEN f.predicted_order_count > 0
                 THEN ROUND((a.order_count - f.predicted_order_count)
                            / f.predicted_order_count * 100, 1)
                 ELSE NULL END                               AS order_error_pct,
            CASE WHEN f.predicted_revenue_yuan > 0
                 THEN ROUND((a.revenue_yuan - f.predicted_revenue_yuan)
                            / f.predicted_revenue_yuan * 100, 1)
                 ELSE NULL END                               AS revenue_error_pct
        FROM dish_forecast_records f
        INNER JOIN dish_profitability_records a
            ON  a.store_id = f.store_id
            AND a.period   = f.forecast_period
            AND a.dish_id  = f.dish_id
        WHERE f.store_id = :store_id AND f.forecast_period = :forecast_period
        ORDER BY ABS(a.revenue_yuan - f.predicted_revenue_yuan) DESC
        LIMIT :limit
    """)
    rows = (await db.execute(sql, {"store_id": store_id, "forecast_period": forecast_period, "limit": limit})).fetchall()
    cols = [
        "dish_id",
        "dish_name",
        "category",
        "lifecycle_phase",
        "predicted_order_count",
        "predicted_revenue_yuan",
        "actual_orders",
        "actual_revenue",
        "order_error_pct",
        "revenue_error_pct",
    ]
    return [dict(zip(cols, r)) for r in rows]


async def get_dish_forecast_history(db: AsyncSession, store_id: str, dish_id: str, periods: int = 6) -> list[dict]:
    """某道菜近 N 期预测记录（可与实际对比追踪预测精度演进）。"""
    sql = text("""
        SELECT
            f.forecast_period,
            f.base_period,
            f.lifecycle_phase,
            f.predicted_order_count,
            f.predicted_order_low,
            f.predicted_order_high,
            f.predicted_revenue_yuan,
            f.predicted_revenue_low,
            f.predicted_revenue_high,
            f.trend_revenue_pct,
            f.lifecycle_adj_pct,
            f.periods_used,
            a.order_count   AS actual_orders,
            a.revenue_yuan  AS actual_revenue
        FROM dish_forecast_records f
        LEFT JOIN dish_profitability_records a
            ON  a.store_id = f.store_id
            AND a.period   = f.forecast_period
            AND a.dish_id  = f.dish_id
        WHERE f.store_id = :store_id AND f.dish_id = :dish_id
        ORDER BY f.forecast_period DESC
        LIMIT :periods
    """)
    rows = (await db.execute(sql, {"store_id": store_id, "dish_id": dish_id, "periods": periods})).fetchall()
    cols = [
        "forecast_period",
        "base_period",
        "lifecycle_phase",
        "predicted_order_count",
        "predicted_order_low",
        "predicted_order_high",
        "predicted_revenue_yuan",
        "predicted_revenue_low",
        "predicted_revenue_high",
        "trend_revenue_pct",
        "lifecycle_adj_pct",
        "periods_used",
        "actual_orders",
        "actual_revenue",
    ]
    return [dict(zip(cols, r)) for r in rows]
