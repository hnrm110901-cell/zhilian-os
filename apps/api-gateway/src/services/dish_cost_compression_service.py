"""菜品成本压缩机会引擎 — Phase 6 Month 11

逐道菜量化食材成本率（FCR）超标缺口，排序出可节省¥最大的机会列表。

目标 FCR = store_avg_fcr − target_fcr_reduction（默认降低 2 个百分点）
         下限：20.0%（餐饮行业合理底线）

FCR 缺口 = current_fcr − target_fcr
压缩机会（¥）= revenue_yuan × fcr_gap / 100
年化预期节省 = 压缩机会 × 12（月→年）

验证：所有菜品 compression_opportunity_yuan 合计
    = 总营收 × (store_avg_fcr − target_fcr) / 100   ✓（近似）
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_FCR_FLOOR = 20.0  # FCR 目标下限（%），低于此不再强制压缩
_MONTHS_PER_YEAR = 12


# ── 期间辅助 ───────────────────────────────────────────────────────────────────


def _prev_period(period: str) -> str:
    year, month = int(period[:4]), int(period[5:7])
    if month == 1:
        return f"{year - 1:04d}-12"
    return f"{year:04d}-{month - 1:02d}"


# ── 纯函数 ─────────────────────────────────────────────────────────────────────


def compute_target_fcr(store_avg_fcr: float, reduction_pp: float = 2.0) -> float:
    """门店目标 FCR = 当前均值 − reduction_pp，最低 _FCR_FLOOR。"""
    return round(max(_FCR_FLOOR, store_avg_fcr - reduction_pp), 2)


def compute_fcr_gap(current_fcr: float, target_fcr: float) -> float:
    """FCR 超标缺口。正值 = 超标 = 有压缩机会；负值 = 已低于目标。"""
    return round(current_fcr - target_fcr, 2)


def compute_compression_opportunity(revenue_yuan: float, fcr_gap: float) -> float:
    """可节省金额 = revenue × fcr_gap / 100。fcr_gap≤0 返回 0.0。"""
    if fcr_gap <= 0:
        return 0.0
    return round(revenue_yuan * fcr_gap / 100, 2)


def compute_expected_saving(compression_opportunity: float, months: int = _MONTHS_PER_YEAR) -> float:
    """年化预期节省（默认 ×12）。"""
    return round(compression_opportunity * months, 2)


def classify_fcr_trend(current_fcr: float, prev_fcr: Optional[float]) -> str:
    """
    improving : current_fcr 比上期下降 > 1 pp（成本率下降 = 好）
    worsening : current_fcr 比上期上升 > 1 pp（成本率上升 = 坏）
    stable    : 变化 ≤ 1 pp 或无上期数据
    """
    if prev_fcr is None:
        return "stable"
    diff = current_fcr - prev_fcr
    if diff < -1.0:
        return "improving"
    if diff > 1.0:
        return "worsening"
    return "stable"


def determine_compression_action(fcr_gap: float, fcr_trend: str) -> str:
    """
    renegotiate   : fcr_gap > 5 pp 且趋势恶化 → 重新谈判供应商价格
    reformulate   : fcr_gap > 3 pp             → 调整配方/原料比例
    adjust_portion: fcr_gap > 1 pp             → 微调份量/用量标准
    monitor       : fcr_gap ≤ 1 pp 或已达目标  → 持续监控
    """
    if fcr_gap <= 0:
        return "monitor"
    if fcr_gap > 5.0 and fcr_trend == "worsening":
        return "renegotiate"
    if fcr_gap > 3.0:
        return "reformulate"
    if fcr_gap > 1.0:
        return "adjust_portion"
    return "monitor"


def determine_priority(compression_opportunity: float, fcr_trend: str) -> str:
    """
    high  : 机会 > ¥1000，或机会 > ¥500 且趋势恶化
    medium: 机会 > ¥200
    low   : 其他
    """
    if compression_opportunity > 1000.0 or (compression_opportunity > 500.0 and fcr_trend == "worsening"):
        return "high"
    if compression_opportunity > 200.0:
        return "medium"
    return "low"


def build_compression_record(
    store_id: str,
    period: str,
    dish_id: str,
    dish_name: str,
    category: Optional[str],
    revenue_yuan: float,
    order_count: int,
    current_fcr: float,
    current_gpm: Optional[float],
    target_fcr: float,
    store_avg_fcr: float,
    prev_fcr: Optional[float],
) -> dict:
    """构建单道菜的成本压缩机会记录。"""
    fcr_gap = compute_fcr_gap(current_fcr, target_fcr)
    opp = compute_compression_opportunity(revenue_yuan, fcr_gap)
    saving = compute_expected_saving(opp)
    trend = classify_fcr_trend(current_fcr, prev_fcr)
    action = determine_compression_action(fcr_gap, trend)
    priority = determine_priority(opp, trend)

    return {
        "store_id": store_id,
        "period": period,
        "dish_id": dish_id,
        "dish_name": dish_name,
        "category": category,
        "revenue_yuan": revenue_yuan,
        "order_count": order_count,
        "current_fcr": current_fcr,
        "current_gpm": current_gpm,
        "target_fcr": target_fcr,
        "store_avg_fcr": store_avg_fcr,
        "fcr_gap": fcr_gap,
        "compression_opportunity_yuan": opp,
        "expected_saving_yuan": saving,
        "prev_fcr": prev_fcr,
        "fcr_trend": trend,
        "compression_action": action,
        "action_priority": priority,
    }


# ── 数据库函数 ──────────────────────────────────────────────────────────────────


async def _fetch_profitability(db: AsyncSession, store_id: str, period: str) -> list:
    """拉取指定期的菜品盈利数据（含 FCR & GPM）。"""
    sql = text("""
        SELECT dish_id, dish_name, category,
               order_count, revenue_yuan,
               food_cost_rate, gpm
        FROM dish_profitability_records
        WHERE store_id = :store_id AND period = :period
        ORDER BY dish_id
    """)
    return (await db.execute(sql, {"store_id": store_id, "period": period})).fetchall()


async def _upsert_compression_record(db: AsyncSession, rec: dict) -> None:
    sql = text("""
        INSERT INTO dish_cost_compression (
            store_id, period, dish_id, dish_name, category,
            revenue_yuan, order_count, current_fcr, current_gpm,
            target_fcr, store_avg_fcr,
            fcr_gap, compression_opportunity_yuan, expected_saving_yuan,
            prev_fcr, fcr_trend,
            compression_action, action_priority,
            computed_at, updated_at
        ) VALUES (
            :store_id, :period, :dish_id, :dish_name, :category,
            :revenue_yuan, :order_count, :current_fcr, :current_gpm,
            :target_fcr, :store_avg_fcr,
            :fcr_gap, :compression_opportunity_yuan, :expected_saving_yuan,
            :prev_fcr, :fcr_trend,
            :compression_action, :action_priority,
            NOW(), NOW()
        )
        ON CONFLICT (store_id, period, dish_id) DO UPDATE SET
            dish_name              = EXCLUDED.dish_name,
            category               = EXCLUDED.category,
            revenue_yuan           = EXCLUDED.revenue_yuan,
            order_count            = EXCLUDED.order_count,
            current_fcr            = EXCLUDED.current_fcr,
            current_gpm            = EXCLUDED.current_gpm,
            target_fcr             = EXCLUDED.target_fcr,
            store_avg_fcr          = EXCLUDED.store_avg_fcr,
            fcr_gap                = EXCLUDED.fcr_gap,
            compression_opportunity_yuan = EXCLUDED.compression_opportunity_yuan,
            expected_saving_yuan   = EXCLUDED.expected_saving_yuan,
            prev_fcr               = EXCLUDED.prev_fcr,
            fcr_trend              = EXCLUDED.fcr_trend,
            compression_action     = EXCLUDED.compression_action,
            action_priority        = EXCLUDED.action_priority,
            updated_at             = NOW()
    """)
    await db.execute(sql, rec)


async def compute_cost_compression(
    db: AsyncSession,
    store_id: str,
    period: str,
    target_fcr_reduction: float = 2.0,
) -> dict:
    """
    计算全菜品成本压缩机会并幂等写入。
    返回 {dish_count, store_avg_fcr, target_fcr, total_opportunity_yuan,
          total_expected_saving_yuan, action_counts, priority_counts, worsening_count}
    """
    prev_period_str = _prev_period(period)
    curr_rows = await _fetch_profitability(db, store_id, period)
    prev_rows = await _fetch_profitability(db, store_id, prev_period_str)

    prev_fcr_map: dict[str, float] = {r[0]: float(r[5] or 0) for r in prev_rows if r[5] is not None}

    if not curr_rows:
        await db.commit()
        return {
            "store_id": store_id,
            "period": period,
            "dish_count": 0,
            "store_avg_fcr": 0.0,
            "target_fcr": 0.0,
            "total_opportunity_yuan": 0.0,
            "total_expected_saving_yuan": 0.0,
            "action_counts": {},
            "priority_counts": {},
            "worsening_count": 0,
        }

    # 计算门店平均 FCR（剔除 FCR=0 的菜品，即无成本数据）
    valid_fcr = [float(r[5] or 0) for r in curr_rows if r[5] and float(r[5]) > 0]
    store_avg_fcr = round(sum(valid_fcr) / len(valid_fcr), 2) if valid_fcr else 0.0
    target_fcr = compute_target_fcr(store_avg_fcr, target_fcr_reduction)

    total_opp = 0.0
    total_saving = 0.0
    action_counts: dict[str, int] = {}
    priority_counts: dict[str, int] = {}
    worsening_cnt = 0

    for r in curr_rows:
        dish_id = r[0]
        current_fcr = float(r[5] or 0)
        current_gpm = float(r[6] or 0) if r[6] is not None else None

        rec = build_compression_record(
            store_id,
            period,
            dish_id,
            r[1],
            r[2],
            float(r[4] or 0),
            int(r[3] or 0),
            current_fcr,
            current_gpm,
            target_fcr,
            store_avg_fcr,
            prev_fcr_map.get(dish_id),
        )
        await _upsert_compression_record(db, rec)

        total_opp += rec["compression_opportunity_yuan"]
        total_saving += rec["expected_saving_yuan"]
        action_counts[rec["compression_action"]] = action_counts.get(rec["compression_action"], 0) + 1
        priority_counts[rec["action_priority"]] = priority_counts.get(rec["action_priority"], 0) + 1
        if rec["fcr_trend"] == "worsening":
            worsening_cnt += 1

    await db.commit()
    return {
        "store_id": store_id,
        "period": period,
        "dish_count": len(curr_rows),
        "store_avg_fcr": store_avg_fcr,
        "target_fcr": target_fcr,
        "target_fcr_reduction_pp": target_fcr_reduction,
        "total_opportunity_yuan": round(total_opp, 2),
        "total_expected_saving_yuan": round(total_saving, 2),
        "action_counts": action_counts,
        "priority_counts": priority_counts,
        "worsening_count": worsening_cnt,
    }


async def get_cost_compression(
    db: AsyncSession,
    store_id: str,
    period: str,
    action: Optional[str] = None,
    priority: Optional[str] = None,
    limit: int = 100,
) -> list[dict]:
    """查询压缩机会明细。L011 三路分支。"""
    _cols = """
        id, dish_id, dish_name, category,
        revenue_yuan, order_count,
        current_fcr, current_gpm, target_fcr, store_avg_fcr,
        fcr_gap, compression_opportunity_yuan, expected_saving_yuan,
        prev_fcr, fcr_trend, compression_action, action_priority
    """
    base = "FROM dish_cost_compression WHERE store_id = :store_id AND period = :period"
    params: dict = {"store_id": store_id, "period": period, "limit": limit}

    if action:
        sql = text(
            f"SELECT {_cols} {base} AND compression_action = :action "
            "ORDER BY compression_opportunity_yuan DESC LIMIT :limit"
        )
        params["action"] = action
    elif priority:
        sql = text(
            f"SELECT {_cols} {base} AND action_priority = :priority " "ORDER BY compression_opportunity_yuan DESC LIMIT :limit"
        )
        params["priority"] = priority
    else:
        sql = text(f"SELECT {_cols} {base} " "ORDER BY compression_opportunity_yuan DESC LIMIT :limit")

    rows = (await db.execute(sql, params)).fetchall()
    cols = [
        "id",
        "dish_id",
        "dish_name",
        "category",
        "revenue_yuan",
        "order_count",
        "current_fcr",
        "current_gpm",
        "target_fcr",
        "store_avg_fcr",
        "fcr_gap",
        "compression_opportunity_yuan",
        "expected_saving_yuan",
        "prev_fcr",
        "fcr_trend",
        "compression_action",
        "action_priority",
    ]
    return [dict(zip(cols, r)) for r in rows]


async def get_compression_summary(db: AsyncSession, store_id: str, period: str) -> dict:
    """按行动类型和趋势聚合统计。"""
    sql_action = text("""
        SELECT
            compression_action,
            COUNT(*)                                AS dish_count,
            SUM(compression_opportunity_yuan)       AS total_opportunity,
            SUM(expected_saving_yuan)               AS total_saving,
            AVG(fcr_gap)                            AS avg_fcr_gap,
            COUNT(CASE WHEN action_priority='high' THEN 1 END) AS high_cnt
        FROM dish_cost_compression
        WHERE store_id = :store_id AND period = :period
        GROUP BY compression_action
        ORDER BY SUM(compression_opportunity_yuan) DESC
    """)
    sql_trend = text("""
        SELECT
            fcr_trend,
            COUNT(*)                          AS dish_count,
            SUM(compression_opportunity_yuan) AS total_opportunity,
            AVG(current_fcr)                  AS avg_current_fcr,
            AVG(fcr_gap)                      AS avg_fcr_gap
        FROM dish_cost_compression
        WHERE store_id = :store_id AND period = :period
        GROUP BY fcr_trend
        ORDER BY fcr_trend
    """)
    params = {"store_id": store_id, "period": period}
    action_rows = (await db.execute(sql_action, params)).fetchall()
    trend_rows = (await db.execute(sql_trend, params)).fetchall()

    by_action = [
        {
            "compression_action": r[0],
            "dish_count": int(r[1]),
            "total_opportunity": round(float(r[2] or 0), 2),
            "total_saving": round(float(r[3] or 0), 2),
            "avg_fcr_gap": round(float(r[4] or 0), 2),
            "high_priority_dishes": int(r[5]),
        }
        for r in action_rows
    ]
    by_trend = [
        {
            "fcr_trend": r[0],
            "dish_count": int(r[1]),
            "total_opportunity": round(float(r[2] or 0), 2),
            "avg_current_fcr": round(float(r[3] or 0), 2),
            "avg_fcr_gap": round(float(r[4] or 0), 2),
        }
        for r in trend_rows
    ]

    total_opp = sum(x["total_opportunity"] for x in by_action)
    total_saving = sum(x["total_saving"] for x in by_action)

    return {
        "store_id": store_id,
        "period": period,
        "total_opportunity_yuan": round(total_opp, 2),
        "total_expected_saving_yuan": round(total_saving, 2),
        "by_action": by_action,
        "by_trend": by_trend,
    }


async def get_top_opportunities(db: AsyncSession, store_id: str, period: str, limit: int = 10) -> list[dict]:
    """压缩机会最大的 Top-N 菜品。"""
    sql = text("""
        SELECT
            dish_id, dish_name, category,
            current_fcr, target_fcr, fcr_gap,
            compression_opportunity_yuan, expected_saving_yuan,
            fcr_trend, compression_action, action_priority,
            revenue_yuan
        FROM dish_cost_compression
        WHERE store_id = :store_id AND period = :period
          AND compression_opportunity_yuan > 0
        ORDER BY compression_opportunity_yuan DESC
        LIMIT :limit
    """)
    rows = (
        await db.execute(
            sql,
            {
                "store_id": store_id,
                "period": period,
                "limit": limit,
            },
        )
    ).fetchall()
    cols = [
        "dish_id",
        "dish_name",
        "category",
        "current_fcr",
        "target_fcr",
        "fcr_gap",
        "compression_opportunity_yuan",
        "expected_saving_yuan",
        "fcr_trend",
        "compression_action",
        "action_priority",
        "revenue_yuan",
    ]
    return [dict(zip(cols, r)) for r in rows]


async def get_dish_fcr_history(db: AsyncSession, store_id: str, dish_id: str, periods: int = 6) -> list[dict]:
    """某道菜近 N 期的 FCR 变化历史。"""
    sql = text("""
        SELECT
            period,
            current_fcr, prev_fcr, fcr_gap, target_fcr, store_avg_fcr,
            fcr_trend, compression_action, action_priority,
            compression_opportunity_yuan, expected_saving_yuan,
            revenue_yuan
        FROM dish_cost_compression
        WHERE store_id = :store_id AND dish_id = :dish_id
        ORDER BY period DESC
        LIMIT :periods
    """)
    rows = (
        await db.execute(
            sql,
            {
                "store_id": store_id,
                "dish_id": dish_id,
                "periods": periods,
            },
        )
    ).fetchall()
    cols = [
        "period",
        "current_fcr",
        "prev_fcr",
        "fcr_gap",
        "target_fcr",
        "store_avg_fcr",
        "fcr_trend",
        "compression_action",
        "action_priority",
        "compression_opportunity_yuan",
        "expected_saving_yuan",
        "revenue_yuan",
    ]
    return [dict(zip(cols, r)) for r in rows]
