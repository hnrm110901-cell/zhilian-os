"""菜品盈利能力分析引擎 — Phase 6 Month 1

BCG 四象限菜单工程：
  star          — 高人气 + 高毛利率（明星菜，主推）
  cash_cow      — 高人气 + 低毛利率（金牛菜，提价或降本）
  question_mark — 低人气 + 高毛利率（问题菜，加强推广）
  dog           — 低人气 + 低毛利率（瘦狗菜，考虑下架）

分类依据：
  人气百分位  ≥ 50 → 高人气；< 50 → 低人气
  毛利率百分位 ≥ 50 → 高毛利；< 50 → 低毛利

核心指标：
  food_cost_rate    = food_cost_yuan / revenue_yuan × 100
  gross_profit      = revenue_yuan − food_cost_yuan
  gross_profit_margin = gross_profit / revenue_yuan × 100
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# ── 常量 ─────────────────────────────────────────────────────────────────────

BCG_QUADRANTS = ("star", "cash_cow", "question_mark", "dog")

BCG_LABELS = {
    "star": "明星菜",
    "cash_cow": "金牛菜",
    "question_mark": "问题菜",
    "dog": "瘦狗菜",
}

BCG_ACTIONS = {
    "star": "主推爆款，保持曝光，维持食材成本稳定",
    "cash_cow": "分析成本结构，适度提价或压缩食材成本，保量增利",
    "question_mark": "加强推广（搭配套餐/促销），提升点单率",
    "dog": "评估保留价值，逐步缩减份量或考虑下架",
}

BCG_COLORS = {
    "star": "#52c41a",
    "cash_cow": "#1677ff",
    "question_mark": "#fa8c16",
    "dog": "#ff4d4f",
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


def _prev_period(period: str) -> str:
    year, month = map(int, period.split("-"))
    month -= 1
    if month == 0:
        month, year = 12, year - 1
    return f"{year:04d}-{month:02d}"


# ══════════════════════════════════════════════════════════════════════════════
# 纯函数层
# ══════════════════════════════════════════════════════════════════════════════


def compute_food_cost_rate(revenue: float, food_cost: float) -> float:
    """food_cost / revenue × 100。revenue = 0 → 0.0。"""
    if revenue <= 0:
        return 0.0
    return food_cost / revenue * 100.0


def compute_gross_profit(revenue: float, food_cost: float) -> float:
    return revenue - food_cost


def compute_gross_profit_margin(revenue: float, food_cost: float) -> float:
    """(revenue - food_cost) / revenue × 100。revenue = 0 → 0.0。"""
    if revenue <= 0:
        return 0.0
    return (revenue - food_cost) / revenue * 100.0


def compute_avg_selling_price(revenue: float, order_count: int) -> float:
    if order_count <= 0:
        return 0.0
    return revenue / order_count


def compute_rank(value: float, all_values: List[float], higher_is_better: bool = True) -> int:
    """1-based dense rank。"""
    if not all_values:
        return 1
    if higher_is_better:
        return sum(1 for v in all_values if v > value) + 1
    return sum(1 for v in all_values if v < value) + 1


def compute_percentile(value: float, all_values: List[float], higher_is_better: bool = True) -> float:
    """0-100 百分位。单值→100。"""
    if len(all_values) <= 1:
        return 100.0
    if higher_is_better:
        below = sum(1 for v in all_values if v < value)
    else:
        below = sum(1 for v in all_values if v > value)
    return round(below / (len(all_values) - 1) * 100.0, 1)


def classify_bcg_quadrant(popularity_pct: float, profit_pct: float) -> str:
    """
    BCG 四象限分类（分界线 = 50th 百分位）：
      high pop + high profit → star
      high pop + low  profit → cash_cow
      low  pop + high profit → question_mark
      low  pop + low  profit → dog
    """
    high_pop = popularity_pct >= 50.0
    high_profit = profit_pct >= 50.0
    if high_pop and high_profit:
        return "star"
    if high_pop and not high_profit:
        return "cash_cow"
    if not high_pop and high_profit:
        return "question_mark"
    return "dog"


def generate_dish_insight(
    dish_name: str,
    bcg_quadrant: str,
    food_cost_rate: float,
    gross_profit_margin: float,
    order_count: int,
    revenue_yuan: float,
) -> str:
    """生成菜品分析描述（≤150字）。"""
    label = BCG_LABELS.get(bcg_quadrant, bcg_quadrant)
    action = BCG_ACTIONS.get(bcg_quadrant, "")
    parts = [
        f"【{label}】{dish_name}：",
        f"月销 {order_count} 份，收入 ¥{revenue_yuan:,.0f}，",
        f"毛利率 {gross_profit_margin:.1f}%，食材成本率 {food_cost_rate:.1f}%。",
        f"建议：{action}。",
    ]
    return "".join(parts)[:150]


def build_dish_records(
    store_id: str,
    period: str,
    raw_dishes: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    输入：每道菜的 {dish_id, dish_name, category, order_count, revenue_yuan, food_cost_yuan}
    输出：完整的分析记录列表（含排名/百分位/BCG）。
    纯函数，无 DB 依赖。
    """
    if not raw_dishes:
        return []

    # 计算衍生指标
    dishes: List[Dict[str, Any]] = []
    for d in raw_dishes:
        rev = _to_float(d.get("revenue_yuan"))
        fc = _to_float(d.get("food_cost_yuan"))
        cnt = int(d.get("order_count", 0))
        dishes.append(
            {
                "dish_id": d.get("dish_id", ""),
                "dish_name": d.get("dish_name", ""),
                "category": d.get("category", ""),
                "order_count": cnt,
                "revenue_yuan": rev,
                "food_cost_yuan": fc,
                "avg_selling_price": compute_avg_selling_price(rev, cnt),
                "food_cost_rate": compute_food_cost_rate(rev, fc),
                "gross_profit_yuan": compute_gross_profit(rev, fc),
                "gross_profit_margin": compute_gross_profit_margin(rev, fc),
            }
        )

    all_counts = [d["order_count"] for d in dishes]
    all_margins = [d["gross_profit_margin"] for d in dishes]

    results: List[Dict[str, Any]] = []
    for d in dishes:
        pop_rank = compute_rank(d["order_count"], all_counts, higher_is_better=True)
        prof_rank = compute_rank(d["gross_profit_margin"], all_margins, higher_is_better=True)
        pop_pct = compute_percentile(d["order_count"], all_counts, higher_is_better=True)
        prof_pct = compute_percentile(d["gross_profit_margin"], all_margins, higher_is_better=True)
        quadrant = classify_bcg_quadrant(pop_pct, prof_pct)

        results.append(
            {
                "store_id": store_id,
                "period": period,
                "dish_id": d["dish_id"],
                "dish_name": d["dish_name"],
                "category": d["category"],
                "order_count": d["order_count"],
                "avg_selling_price": round(d["avg_selling_price"], 2),
                "revenue_yuan": round(d["revenue_yuan"], 2),
                "food_cost_yuan": round(d["food_cost_yuan"], 2),
                "food_cost_rate": round(d["food_cost_rate"], 2),
                "gross_profit_yuan": round(d["gross_profit_yuan"], 2),
                "gross_profit_margin": round(d["gross_profit_margin"], 2),
                "popularity_rank": pop_rank,
                "profitability_rank": prof_rank,
                "popularity_percentile": pop_pct,
                "profit_percentile": prof_pct,
                "bcg_quadrant": quadrant,
                "insight": generate_dish_insight(
                    d["dish_name"],
                    quadrant,
                    d["food_cost_rate"],
                    d["gross_profit_margin"],
                    d["order_count"],
                    d["revenue_yuan"],
                ),
            }
        )
    return results


def summarize_bcg(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """统计 BCG 四象限分布及每象限的收入/毛利贡献。"""
    summary: Dict[str, Any] = {q: {"count": 0, "revenue_yuan": 0.0, "gross_profit_yuan": 0.0} for q in BCG_QUADRANTS}
    total_rev = 0.0
    for r in records:
        q = r.get("bcg_quadrant", "dog")
        if q not in summary:
            q = "dog"
        summary[q]["count"] += 1
        summary[q]["revenue_yuan"] += r.get("revenue_yuan", 0)
        summary[q]["gross_profit_yuan"] += r.get("gross_profit_yuan", 0)
        total_rev += r.get("revenue_yuan", 0)

    for q in BCG_QUADRANTS:
        rev = summary[q]["revenue_yuan"]
        summary[q]["revenue_share_pct"] = round(rev / total_rev * 100, 1) if total_rev > 0 else 0.0
        summary[q]["label"] = BCG_LABELS[q]
        summary[q]["action"] = BCG_ACTIONS[q]
        summary[q]["color"] = BCG_COLORS[q]
    return summary


# ══════════════════════════════════════════════════════════════════════════════
# DB 函数层
# ══════════════════════════════════════════════════════════════════════════════


async def _upsert_dish_record(db: AsyncSession, rec: Dict[str, Any]) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.execute(
        text("""
            INSERT INTO dish_profitability_records
                (store_id, period, dish_id, dish_name, category,
                 order_count, avg_selling_price, revenue_yuan, food_cost_yuan,
                 food_cost_rate, gross_profit_yuan, gross_profit_margin,
                 popularity_rank, profitability_rank,
                 popularity_percentile, profit_percentile,
                 bcg_quadrant, computed_at, updated_at)
            VALUES
                (:sid, :period, :did, :dname, :cat,
                 :cnt, :asp, :rev, :fc,
                 :fcr, :gp, :gpm,
                 :pop_rank, :prof_rank,
                 :pop_pct, :prof_pct,
                 :bcg, :now, :now)
            ON CONFLICT (store_id, period, dish_id) DO UPDATE SET
                dish_name             = EXCLUDED.dish_name,
                category              = EXCLUDED.category,
                order_count           = EXCLUDED.order_count,
                avg_selling_price     = EXCLUDED.avg_selling_price,
                revenue_yuan          = EXCLUDED.revenue_yuan,
                food_cost_yuan        = EXCLUDED.food_cost_yuan,
                food_cost_rate        = EXCLUDED.food_cost_rate,
                gross_profit_yuan     = EXCLUDED.gross_profit_yuan,
                gross_profit_margin   = EXCLUDED.gross_profit_margin,
                popularity_rank       = EXCLUDED.popularity_rank,
                profitability_rank    = EXCLUDED.profitability_rank,
                popularity_percentile = EXCLUDED.popularity_percentile,
                profit_percentile     = EXCLUDED.profit_percentile,
                bcg_quadrant          = EXCLUDED.bcg_quadrant,
                updated_at            = EXCLUDED.updated_at
        """),
        {
            "sid": rec["store_id"],
            "period": rec["period"],
            "did": rec["dish_id"],
            "dname": rec["dish_name"],
            "cat": rec["category"],
            "cnt": rec["order_count"],
            "asp": rec["avg_selling_price"],
            "rev": rec["revenue_yuan"],
            "fc": rec["food_cost_yuan"],
            "fcr": rec["food_cost_rate"],
            "gp": rec["gross_profit_yuan"],
            "gpm": rec["gross_profit_margin"],
            "pop_rank": rec["popularity_rank"],
            "prof_rank": rec["profitability_rank"],
            "pop_pct": rec["popularity_percentile"],
            "prof_pct": rec["profit_percentile"],
            "bcg": rec["bcg_quadrant"],
            "now": now,
        },
    )


async def _fetch_raw_dish_sales(
    db: AsyncSession,
    store_id: str,
    period: str,
) -> List[Dict[str, Any]]:
    """
    从 order_items + dishes + bom (food_cost) 拉取当期菜品销售数据。
    当前版本从 order_items 聚合，食材成本从 dish_master 的 standard_cost 估算。
    """
    rows = await db.execute(
        text("""
            SELECT
                oi.dish_id,
                COALESCE(d.name, oi.dish_id)  AS dish_name,
                COALESCE(d.category, '其他')   AS category,
                COUNT(*)                       AS order_count,
                SUM(oi.unit_price * oi.qty)    AS revenue_yuan,
                SUM(COALESCE(d.standard_cost, 0) * oi.qty) AS food_cost_yuan
            FROM order_items oi
            LEFT JOIN dish_master d ON d.dish_id = oi.dish_id
                AND d.store_id = :sid
            WHERE oi.store_id = :sid
              AND TO_CHAR(oi.created_at, 'YYYY-MM') = :period
              AND oi.status NOT IN ('cancelled', 'refunded')
            GROUP BY oi.dish_id, d.name, d.category
            HAVING COUNT(*) > 0
        """),
        {"sid": store_id, "period": period},
    )
    return [
        {
            "dish_id": r[0],
            "dish_name": r[1],
            "category": r[2],
            "order_count": int(r[3]),
            "revenue_yuan": _to_float(r[4]),
            "food_cost_yuan": _to_float(r[5]),
        }
        for r in rows.fetchall()
    ]


async def compute_dish_profitability(
    db: AsyncSession,
    store_id: str,
    period: str,
) -> Dict[str, Any]:
    """
    计算门店当期菜品盈利能力，写入 dish_profitability_records，返回汇总。
    """
    raw = await _fetch_raw_dish_sales(db, store_id, period)
    if not raw:
        return {"store_id": store_id, "period": period, "dish_count": 0, "records": []}

    records = build_dish_records(store_id, period, raw)
    for rec in records:
        await _upsert_dish_record(db, rec)
    await db.commit()

    bcg_summary = summarize_bcg(records)
    return {
        "store_id": store_id,
        "period": period,
        "dish_count": len(records),
        "bcg_summary": bcg_summary,
        "records": records,
    }


async def get_dish_profitability(
    db: AsyncSession,
    store_id: str,
    period: str,
    bcg_quadrant: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """获取菜品盈利能力列表，支持按 BCG 象限过滤。"""
    if bcg_quadrant:
        rows = await db.execute(
            text("""
                SELECT dish_id, dish_name, category,
                       order_count, avg_selling_price, revenue_yuan,
                       food_cost_yuan, food_cost_rate,
                       gross_profit_yuan, gross_profit_margin,
                       popularity_rank, profitability_rank,
                       popularity_percentile, profit_percentile,
                       bcg_quadrant
                FROM dish_profitability_records
                WHERE store_id = :sid AND period = :period
                  AND bcg_quadrant = :bcg
                ORDER BY gross_profit_yuan DESC
                LIMIT :lim
            """),
            {"sid": store_id, "period": period, "bcg": bcg_quadrant, "lim": limit},
        )
    else:
        rows = await db.execute(
            text("""
                SELECT dish_id, dish_name, category,
                       order_count, avg_selling_price, revenue_yuan,
                       food_cost_yuan, food_cost_rate,
                       gross_profit_yuan, gross_profit_margin,
                       popularity_rank, profitability_rank,
                       popularity_percentile, profit_percentile,
                       bcg_quadrant
                FROM dish_profitability_records
                WHERE store_id = :sid AND period = :period
                ORDER BY gross_profit_yuan DESC
                LIMIT :lim
            """),
            {"sid": store_id, "period": period, "lim": limit},
        )
    return [_row_to_dict(r) for r in rows.fetchall()]


def _row_to_dict(r) -> Dict[str, Any]:
    return {
        "dish_id": r[0],
        "dish_name": r[1],
        "category": r[2],
        "order_count": r[3],
        "avg_selling_price": _safe_float(r[4]),
        "revenue_yuan": _safe_float(r[5]),
        "food_cost_yuan": _safe_float(r[6]),
        "food_cost_rate": _safe_float(r[7]),
        "gross_profit_yuan": _safe_float(r[8]),
        "gross_profit_margin": _safe_float(r[9]),
        "popularity_rank": r[10],
        "profitability_rank": r[11],
        "popularity_percentile": _safe_float(r[12]),
        "profit_percentile": _safe_float(r[13]),
        "bcg_quadrant": r[14],
        "bcg_label": BCG_LABELS.get(r[14], r[14]),
        "bcg_action": BCG_ACTIONS.get(r[14], ""),
    }


async def get_bcg_summary(
    db: AsyncSession,
    store_id: str,
    period: str,
) -> Dict[str, Any]:
    """获取 BCG 四象限汇总统计。"""
    rows = await db.execute(
        text("""
            SELECT bcg_quadrant,
                   COUNT(*)                    AS dish_count,
                   SUM(revenue_yuan)            AS total_revenue,
                   SUM(gross_profit_yuan)       AS total_gp,
                   AVG(gross_profit_margin)     AS avg_gpm,
                   AVG(food_cost_rate)          AS avg_fcr
            FROM dish_profitability_records
            WHERE store_id = :sid AND period = :period
            GROUP BY bcg_quadrant
        """),
        {"sid": store_id, "period": period},
    )

    total_rev = 0.0
    raw: Dict[str, Any] = {}
    for r in rows.fetchall():
        q = r[0] or "dog"
        rev = _to_float(r[2])
        total_rev += rev
        raw[q] = {
            "quadrant": q,
            "label": BCG_LABELS.get(q, q),
            "action": BCG_ACTIONS.get(q, ""),
            "color": BCG_COLORS.get(q, "#8c8c8c"),
            "dish_count": int(r[1]),
            "revenue_yuan": round(rev, 2),
            "gross_profit_yuan": round(_to_float(r[3]), 2),
            "avg_gpm": round(_to_float(r[4]), 2),
            "avg_fcr": round(_to_float(r[5]), 2),
        }

    for q, v in raw.items():
        v["revenue_share_pct"] = round(v["revenue_yuan"] / total_rev * 100, 1) if total_rev > 0 else 0.0

    # 补全缺失象限
    for q in BCG_QUADRANTS:
        if q not in raw:
            raw[q] = {
                "quadrant": q,
                "label": BCG_LABELS[q],
                "action": BCG_ACTIONS[q],
                "color": BCG_COLORS[q],
                "dish_count": 0,
                "revenue_yuan": 0.0,
                "gross_profit_yuan": 0.0,
                "avg_gpm": 0.0,
                "avg_fcr": 0.0,
                "revenue_share_pct": 0.0,
            }
    return {
        "store_id": store_id,
        "period": period,
        "total_revenue": round(total_rev, 2),
        "by_quadrant": [raw[q] for q in BCG_QUADRANTS],
    }


async def get_top_dishes(
    db: AsyncSession,
    store_id: str,
    period: str,
    metric: str = "gross_profit_yuan",
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """按指定指标排序返回 Top N 菜品。"""
    safe_metric = (
        metric
        if metric
        in (
            "gross_profit_yuan",
            "revenue_yuan",
            "order_count",
            "gross_profit_margin",
            "food_cost_rate",
        )
        else "gross_profit_yuan"
    )
    order = "ASC" if safe_metric == "food_cost_rate" else "DESC"

    rows = await db.execute(
        text(f"""
            SELECT dish_id, dish_name, category,
                   order_count, avg_selling_price, revenue_yuan,
                   food_cost_yuan, food_cost_rate,
                   gross_profit_yuan, gross_profit_margin,
                   popularity_rank, profitability_rank,
                   popularity_percentile, profit_percentile,
                   bcg_quadrant
            FROM dish_profitability_records
            WHERE store_id = :sid AND period = :period
            ORDER BY {safe_metric} {order} NULLS LAST
            LIMIT :lim
        """),
        {"sid": store_id, "period": period, "lim": limit},
    )
    return [_row_to_dict(r) for r in rows.fetchall()]


async def get_dish_trend(
    db: AsyncSession,
    store_id: str,
    dish_id: str,
    periods: int = 6,
) -> List[Dict[str, Any]]:
    """获取菜品近 N 期历史趋势（升序）。"""
    rows = await db.execute(
        text("""
            SELECT period, order_count, revenue_yuan, food_cost_rate,
                   gross_profit_yuan, gross_profit_margin, bcg_quadrant,
                   popularity_rank, profitability_rank
            FROM dish_profitability_records
            WHERE store_id = :sid AND dish_id = :did
            ORDER BY period DESC
            LIMIT :lim
        """),
        {"sid": store_id, "did": dish_id, "lim": periods},
    )
    records = [
        {
            "period": r[0],
            "order_count": r[1],
            "revenue_yuan": _safe_float(r[2]),
            "food_cost_rate": _safe_float(r[3]),
            "gross_profit_yuan": _safe_float(r[4]),
            "gross_profit_margin": _safe_float(r[5]),
            "bcg_quadrant": r[6],
            "bcg_label": BCG_LABELS.get(r[6], r[6]),
            "popularity_rank": r[7],
            "profitability_rank": r[8],
        }
        for r in rows.fetchall()
    ]
    return list(reversed(records))


async def get_category_summary(
    db: AsyncSession,
    store_id: str,
    period: str,
) -> List[Dict[str, Any]]:
    """按菜品分类汇总盈利能力。"""
    rows = await db.execute(
        text("""
            SELECT category,
                   COUNT(*)                 AS dish_count,
                   SUM(order_count)         AS total_orders,
                   SUM(revenue_yuan)        AS total_revenue,
                   SUM(gross_profit_yuan)   AS total_gp,
                   AVG(gross_profit_margin) AS avg_gpm,
                   AVG(food_cost_rate)      AS avg_fcr
            FROM dish_profitability_records
            WHERE store_id = :sid AND period = :period
            GROUP BY category
            ORDER BY total_revenue DESC
        """),
        {"sid": store_id, "period": period},
    )
    return [
        {
            "category": r[0] or "其他",
            "dish_count": int(r[1]),
            "total_orders": int(r[2]),
            "total_revenue": round(_to_float(r[3]), 2),
            "total_gp": round(_to_float(r[4]), 2),
            "avg_gpm": round(_to_float(r[5]), 2),
            "avg_fcr": round(_to_float(r[6]), 2),
        }
        for r in rows.fetchall()
    ]
