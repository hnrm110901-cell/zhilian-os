"""
财务健康评分服务 — Phase 5 Month 5

职责:
  - 5维度综合评分（利润/现金/税务/结算/预算，总分100）
  - 生成门店文字洞察（insight_type + priority + content）
  - 历史评分趋势查询（finance_health_scores 多期）
  - 原始指标趋势查询（profit_attribution_results 多期）
  - 品牌汇总（多门店评分排行）

评分规则:
  profit_score  (0-30):  profit_margin_pct / 20 * 30，亏损→0
  cash_score    (0-20):  20 - cash_gap_days * 2，最低0
  tax_score     (0-20):  20 - avg_tax_deviation_pct，最低0
  settlement_score(0-15): 15 * (1 - high_risk_rate)，无记录→15(满分)
  budget_score  (0-15):  min(15, achievement_rate * 15)，无预算→7(中性)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# ── Grade thresholds ──────────────────────────────────────────────────────────

GRADE_THRESHOLDS = {"A": 80.0, "B": 60.0, "C": 40.0}
MAX_SCORES = {"profit": 30.0, "cash": 20.0, "tax": 20.0, "settlement": 15.0, "budget": 15.0}


# ── Helpers ───────────────────────────────────────────────────────────────────


def _safe_float(v: Any) -> float:
    if v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


# ── Pure scoring functions (testable without DB) ──────────────────────────────


def score_profit(profit_margin_pct: float, gross_profit_yuan: float) -> float:
    """
    0-30 pts.
    20% margin = full 30 pts.  Negative profit → 0 pts.
    """
    if gross_profit_yuan < 0:
        return 0.0
    return round(min(30.0, max(0.0, profit_margin_pct / 20.0 * 30.0)), 2)


def score_cash(cash_gap_days: int) -> float:
    """0-20 pts.  Each gap-day costs 2 pts."""
    return round(max(0.0, 20.0 - cash_gap_days * 2.0), 2)


def score_tax(avg_deviation_pct: float) -> float:
    """
    0-20 pts.
    1 pt deducted per 1% of average absolute tax deviation.
    """
    return round(max(0.0, 20.0 - avg_deviation_pct), 2)


def score_settlement(high_risk_count: int, total_count: int) -> float:
    """
    0-15 pts.
    No records → 15 (full score, no risk observed).
    """
    if total_count == 0:
        return 15.0
    rate = high_risk_count / total_count
    return round(max(0.0, 15.0 - rate * 15.0), 2)


def score_budget(revenue_actual: float, revenue_budget: float) -> float:
    """
    0-15 pts.
    No budget → 7 (neutral).  100% achievement → 15 pts.  Capped at 15.
    """
    if revenue_budget <= 0:
        return 7.0
    achievement = revenue_actual / revenue_budget
    return round(min(15.0, max(0.0, achievement * 15.0)), 2)


def compute_grade(total_score: float) -> str:
    if total_score >= GRADE_THRESHOLDS["A"]:
        return "A"
    if total_score >= GRADE_THRESHOLDS["B"]:
        return "B"
    if total_score >= GRADE_THRESHOLDS["C"]:
        return "C"
    return "D"


def generate_insights(
    profit_margin_pct: float,
    gross_profit_yuan: float,
    cash_gap_days: int,
    avg_tax_deviation: float,
    high_risk_settlement: int,
    total_settlement: int,
    revenue_actual: float,
    revenue_budget: float,
    scores: Dict[str, float],
) -> List[Dict]:
    """Generate structured text insights from raw metrics and dimension scores."""
    insights: List[Dict] = []

    # ── Profit ────────────────────────────────────────────────────────────────
    if gross_profit_yuan < 0:
        insights.append(
            {
                "insight_type": "profit",
                "priority": "high",
                "content": f"利润亏损预警：本期净亏损 ¥{abs(gross_profit_yuan):.0f}，需立即排查成本来源",
            }
        )
    elif scores["profit_score"] >= 24:
        insights.append(
            {
                "insight_type": "profit",
                "priority": "low",
                "content": f"利润健康：利润率 {profit_margin_pct:.1f}%，盈利能力良好",
            }
        )
    elif scores["profit_score"] < 12:
        insights.append(
            {
                "insight_type": "profit",
                "priority": "high",
                "content": f"利润偏低：利润率仅 {profit_margin_pct:.1f}%，建议检查成本结构",
            }
        )
    else:
        insights.append(
            {
                "insight_type": "profit",
                "priority": "medium",
                "content": f"利润一般：利润率 {profit_margin_pct:.1f}%，仍有提升空间",
            }
        )

    # ── Cash ──────────────────────────────────────────────────────────────────
    if cash_gap_days > 5:
        insights.append(
            {
                "insight_type": "cash",
                "priority": "high",
                "content": f"现金风险：预测期内 {cash_gap_days} 天余额为负，需关注资金头寸",
            }
        )
    elif cash_gap_days > 0:
        insights.append(
            {
                "insight_type": "cash",
                "priority": "medium",
                "content": f"现金提醒：预测期内 {cash_gap_days} 天余额偏低，建议提前备金",
            }
        )

    # ── Tax ───────────────────────────────────────────────────────────────────
    if avg_tax_deviation > 15:
        insights.append(
            {
                "insight_type": "tax",
                "priority": "high",
                "content": f"税务偏差大：平均偏差率 {avg_tax_deviation:.1f}%，建议立即核查税务申报",
            }
        )
    elif avg_tax_deviation > 5:
        insights.append(
            {
                "insight_type": "tax",
                "priority": "medium",
                "content": f"税务提示：平均偏差率 {avg_tax_deviation:.1f}%，建议复核计税数据",
            }
        )

    # ── Settlement ────────────────────────────────────────────────────────────
    if total_settlement > 0:
        high_rate = high_risk_settlement / total_settlement
        if high_rate > 0.20:
            insights.append(
                {
                    "insight_type": "settlement",
                    "priority": "high",
                    "content": (
                        f"结算风险：高风险结算占比 {high_rate*100:.0f}%"
                        f"（{high_risk_settlement}/{total_settlement} 笔），需及时处理"
                    ),
                }
            )
        elif high_rate > 0.05:
            insights.append(
                {
                    "insight_type": "settlement",
                    "priority": "medium",
                    "content": f"结算提示：{high_risk_settlement} 笔高风险待核销，请跟进",
                }
            )

    # ── Budget ────────────────────────────────────────────────────────────────
    if revenue_budget > 0:
        achievement = revenue_actual / revenue_budget
        if achievement >= 1.0:
            insights.append(
                {
                    "insight_type": "budget",
                    "priority": "low",
                    "content": f"预算超额：收入达成率 {achievement*100:.0f}%，超额完成预算目标",
                }
            )
        elif achievement < 0.80:
            insights.append(
                {
                    "insight_type": "budget",
                    "priority": "medium",
                    "content": f"预算未达：收入达成率 {achievement*100:.0f}%，距目标尚有 {(1-achievement)*100:.0f}% 差距",
                }
            )

    return insights


# ── DB operations ─────────────────────────────────────────────────────────────


async def _fetch_profit_data(
    db: AsyncSession,
    store_id: str,
    period: str,
) -> Optional[Dict]:
    res = await db.execute(
        text("""
        SELECT net_revenue_yuan, gross_profit_yuan, profit_margin_pct, food_cost_yuan
        FROM profit_attribution_results
        WHERE store_id = :sid AND period = :period
        ORDER BY calc_date DESC LIMIT 1
    """),
        {"sid": store_id, "period": period},
    )
    row = res.fetchone()
    if not row:
        return None
    return {
        "net_revenue_yuan": _safe_float(row[0]),
        "gross_profit_yuan": _safe_float(row[1]),
        "profit_margin_pct": _safe_float(row[2]),
        "food_cost_yuan": _safe_float(row[3]),
    }


async def _fetch_cash_gap_days(db: AsyncSession, store_id: str) -> int:
    today = datetime.now(timezone.utc).date().isoformat()
    res = await db.execute(
        text("""
        SELECT COUNT(*) FROM cashflow_forecasts
        WHERE store_id = :sid AND balance_yuan < 0 AND forecast_date >= :today
    """),
        {"sid": store_id, "today": today},
    )
    row = res.fetchone()
    return int(row[0]) if row else 0


async def _fetch_avg_tax_deviation(
    db: AsyncSession,
    store_id: str,
    period: str,
) -> float:
    res = await db.execute(
        text("""
        SELECT AVG(ABS(deviation_pct)) FROM tax_calculations
        WHERE store_id = :sid AND period = :period
    """),
        {"sid": store_id, "period": period},
    )
    row = res.fetchone()
    return _safe_float(row[0]) if row else 0.0


async def _fetch_settlement_counts(
    db: AsyncSession,
    store_id: str,
    period: str,
) -> tuple[int, int]:
    res = await db.execute(
        text("""
        SELECT
            COUNT(*),
            SUM(CASE WHEN risk_level IN ('high','critical') THEN 1 ELSE 0 END)
        FROM settlement_records
        WHERE store_id = :sid AND period = :period
    """),
        {"sid": store_id, "period": period},
    )
    row = res.fetchone()
    if not row:
        return 0, 0
    total = int(_safe_float(row[0]))
    high_risk = int(_safe_float(row[1]))
    return high_risk, total


async def _fetch_budget_data(
    db: AsyncSession,
    store_id: str,
    period: str,
    actual_revenue: float,
) -> tuple[float, float]:
    """Returns (actual_revenue, budget_revenue). budget_revenue=0 if no active plan."""
    res = await db.execute(
        text("""
        SELECT total_revenue_budget FROM budget_plans
        WHERE store_id = :sid AND period = :period AND status = 'active'
        LIMIT 1
    """),
        {"sid": store_id, "period": period},
    )
    row = res.fetchone()
    budget_revenue = _safe_float(row[0]) if row else 0.0
    return actual_revenue, budget_revenue


async def compute_health_score(
    db: AsyncSession,
    store_id: str,
    period: str,
) -> Dict:
    """
    Compute 5-dimension health score and upsert into finance_health_scores.
    Also regenerates finance_insights for the period.
    """
    profit_data = await _fetch_profit_data(db, store_id, period)
    cash_gap = await _fetch_cash_gap_days(db, store_id)
    avg_tax_dev = await _fetch_avg_tax_deviation(db, store_id, period)
    high_risk_sr, total_sr = await _fetch_settlement_counts(db, store_id, period)

    net_revenue = profit_data["net_revenue_yuan"] if profit_data else 0.0
    gross_profit = profit_data["gross_profit_yuan"] if profit_data else 0.0
    margin_pct = profit_data["profit_margin_pct"] if profit_data else 0.0

    actual_rev, budget_rev = await _fetch_budget_data(db, store_id, period, net_revenue)

    # Compute dimension scores
    p_score = score_profit(margin_pct, gross_profit)
    c_score = score_cash(cash_gap)
    t_score = score_tax(avg_tax_dev)
    s_score = score_settlement(high_risk_sr, total_sr)
    b_score = score_budget(actual_rev, budget_rev)

    total = round(p_score + c_score + t_score + s_score + b_score, 2)
    grade = compute_grade(total)

    budget_ach_pct = round(actual_rev / budget_rev * 100, 1) if budget_rev > 0 else None

    now = datetime.now(timezone.utc)

    # Upsert health score
    existing = await db.execute(
        text("""
        SELECT id FROM finance_health_scores
        WHERE store_id = :sid AND period = :period LIMIT 1
    """),
        {"sid": store_id, "period": period},
    )
    existing_row = existing.fetchone()

    if existing_row:
        score_id = existing_row[0]
        await db.execute(
            text("""
            UPDATE finance_health_scores
            SET total_score            = :total,
                grade                  = :grade,
                profit_score           = :p,
                cash_score             = :c,
                tax_score              = :t,
                settlement_score       = :s,
                budget_score           = :b,
                profit_margin_pct      = :margin,
                net_revenue_yuan       = :rev,
                cash_gap_days          = :gap,
                avg_tax_deviation_pct  = :tax_dev,
                high_risk_settlement   = :hr_sr,
                budget_achievement_pct = :bud_ach,
                computed_at            = :now
            WHERE id = :sid_id
        """),
            {
                "total": total,
                "grade": grade,
                "p": p_score,
                "c": c_score,
                "t": t_score,
                "s": s_score,
                "b": b_score,
                "margin": margin_pct,
                "rev": net_revenue,
                "gap": cash_gap,
                "tax_dev": avg_tax_dev,
                "hr_sr": high_risk_sr,
                "bud_ach": budget_ach_pct,
                "now": now,
                "sid_id": score_id,
            },
        )
    else:
        score_id = str(uuid.uuid4())
        await db.execute(
            text("""
            INSERT INTO finance_health_scores
                (id, store_id, period, total_score, grade,
                 profit_score, cash_score, tax_score, settlement_score, budget_score,
                 profit_margin_pct, net_revenue_yuan, cash_gap_days,
                 avg_tax_deviation_pct, high_risk_settlement, budget_achievement_pct,
                 computed_at)
            VALUES
                (:id, :sid, :period, :total, :grade,
                 :p, :c, :t, :s, :b,
                 :margin, :rev, :gap, :tax_dev, :hr_sr, :bud_ach, :now)
        """),
            {
                "id": score_id,
                "sid": store_id,
                "period": period,
                "total": total,
                "grade": grade,
                "p": p_score,
                "c": c_score,
                "t": t_score,
                "s": s_score,
                "b": b_score,
                "margin": margin_pct,
                "rev": net_revenue,
                "gap": cash_gap,
                "tax_dev": avg_tax_dev,
                "hr_sr": high_risk_sr,
                "bud_ach": budget_ach_pct,
                "now": now,
            },
        )

    # Regenerate insights: delete then insert
    await db.execute(
        text("""
        DELETE FROM finance_insights WHERE store_id = :sid AND period = :period
    """),
        {"sid": store_id, "period": period},
    )

    insight_list = generate_insights(
        profit_margin_pct=margin_pct,
        gross_profit_yuan=gross_profit,
        cash_gap_days=cash_gap,
        avg_tax_deviation=avg_tax_dev,
        high_risk_settlement=high_risk_sr,
        total_settlement=total_sr,
        revenue_actual=actual_rev,
        revenue_budget=budget_rev,
        scores={
            "profit_score": p_score,
            "cash_score": c_score,
            "tax_score": t_score,
            "settlement_score": s_score,
            "budget_score": b_score,
        },
    )
    for ins in insight_list:
        await db.execute(
            text("""
            INSERT INTO finance_insights (id, store_id, period, insight_type, priority, content, created_at)
            VALUES (:id, :sid, :period, :itype, :priority, :content, :now)
        """),
            {
                "id": str(uuid.uuid4()),
                "sid": store_id,
                "period": period,
                "itype": ins["insight_type"],
                "priority": ins["priority"],
                "content": ins["content"],
                "now": now,
            },
        )

    await db.commit()

    return {
        "store_id": store_id,
        "period": period,
        "total_score": total,
        "grade": grade,
        "dimensions": {
            "profit_score": p_score,
            "cash_score": c_score,
            "tax_score": t_score,
            "settlement_score": s_score,
            "budget_score": b_score,
        },
        "metrics": {
            "profit_margin_pct": margin_pct,
            "net_revenue_yuan": net_revenue,
            "cash_gap_days": cash_gap,
            "avg_tax_deviation_pct": avg_tax_dev,
            "high_risk_settlement": high_risk_sr,
            "budget_achievement_pct": budget_ach_pct,
        },
        "insights": insight_list,
    }


async def get_health_score(
    db: AsyncSession,
    store_id: str,
    period: str,
) -> Optional[Dict]:
    res = await db.execute(
        text("""
        SELECT id, store_id, period, total_score, grade,
               profit_score, cash_score, tax_score, settlement_score, budget_score,
               profit_margin_pct, net_revenue_yuan, cash_gap_days,
               avg_tax_deviation_pct, high_risk_settlement, budget_achievement_pct,
               computed_at
        FROM finance_health_scores
        WHERE store_id = :sid AND period = :period
    """),
        {"sid": store_id, "period": period},
    )
    row = res.fetchone()
    if not row:
        return None
    keys = [
        "id",
        "store_id",
        "period",
        "total_score",
        "grade",
        "profit_score",
        "cash_score",
        "tax_score",
        "settlement_score",
        "budget_score",
        "profit_margin_pct",
        "net_revenue_yuan",
        "cash_gap_days",
        "avg_tax_deviation_pct",
        "high_risk_settlement",
        "budget_achievement_pct",
        "computed_at",
    ]
    return dict(zip(keys, row))


async def get_health_trend(
    db: AsyncSession,
    store_id: str,
    periods: int = 6,
) -> List[Dict]:
    """Return ascending historical health scores (oldest → newest)."""
    res = await db.execute(
        text("""
        SELECT period, total_score, grade,
               profit_score, cash_score, tax_score, settlement_score, budget_score
        FROM finance_health_scores
        WHERE store_id = :sid
        ORDER BY period DESC LIMIT :n
    """),
        {"sid": store_id, "n": periods},
    )
    keys = ["period", "total_score", "grade", "profit_score", "cash_score", "tax_score", "settlement_score", "budget_score"]
    rows = [dict(zip(keys, r)) for r in res.fetchall()]
    return list(reversed(rows))  # ascending for charts


async def get_finance_insights(
    db: AsyncSession,
    store_id: str,
    period: str,
) -> List[Dict]:
    res = await db.execute(
        text("""
        SELECT id, insight_type, priority, content, created_at
        FROM finance_insights
        WHERE store_id = :sid AND period = :period
        ORDER BY
            CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
            created_at
    """),
        {"sid": store_id, "period": period},
    )
    keys = ["id", "insight_type", "priority", "content", "created_at"]
    return [dict(zip(keys, r)) for r in res.fetchall()]


async def get_profit_trend(
    db: AsyncSession,
    store_id: str,
    periods: int = 6,
) -> List[Dict]:
    """Raw profit metrics for the last N periods, ascending order."""
    res = await db.execute(
        text("""
        SELECT period, net_revenue_yuan, gross_profit_yuan, profit_margin_pct,
               food_cost_yuan, total_cost_yuan
        FROM profit_attribution_results
        WHERE store_id = :sid
        ORDER BY period DESC LIMIT :n
    """),
        {"sid": store_id, "n": periods},
    )
    keys = ["period", "net_revenue_yuan", "gross_profit_yuan", "profit_margin_pct", "food_cost_yuan", "total_cost_yuan"]
    rows = [dict(zip(keys, r)) for r in res.fetchall()]
    # Convert Decimals, reverse to ascending
    out = []
    for r in reversed(rows):
        out.append({k: _safe_float(v) if k != "period" else v for k, v in r.items()})
    return out


async def get_brand_health_summary(
    db: AsyncSession,
    brand_id: Optional[str],
    period: str,
) -> Dict:
    """Multi-store health ranking for CEO view."""
    if brand_id:
        res = await db.execute(
            text("""
            SELECT store_id, total_score, grade,
                   profit_score, cash_score, net_revenue_yuan, profit_margin_pct
            FROM finance_health_scores
            WHERE period = :period
              AND store_id IN (
                  SELECT store_id FROM profit_attribution_results
                  WHERE brand_id = :bid AND period = :period
              )
            ORDER BY total_score DESC
        """),
            {"period": period, "bid": brand_id},
        )
    else:
        res = await db.execute(
            text("""
            SELECT store_id, total_score, grade,
                   profit_score, cash_score, net_revenue_yuan, profit_margin_pct
            FROM finance_health_scores
            WHERE period = :period
            ORDER BY total_score DESC
            LIMIT 20
        """),
            {"period": period},
        )

    keys = ["store_id", "total_score", "grade", "profit_score", "cash_score", "net_revenue_yuan", "profit_margin_pct"]
    stores = [dict(zip(keys, r)) for r in res.fetchall()]

    if not stores:
        return {"period": period, "stores": [], "summary": None}

    scores = [_safe_float(s["total_score"]) for s in stores]
    avg_score = round(sum(scores) / len(scores), 1)
    grade_counts = {"A": 0, "B": 0, "C": 0, "D": 0}
    for s in stores:
        g = s.get("grade", "D")
        grade_counts[g] = grade_counts.get(g, 0) + 1

    return {
        "period": period,
        "stores": stores,
        "summary": {
            "store_count": len(stores),
            "avg_score": avg_score,
            "best_store": stores[0]["store_id"] if stores else None,
            "worst_store": stores[-1]["store_id"] if stores else None,
            "grade_dist": grade_counts,
        },
    }


async def get_finance_dashboard(
    db: AsyncSession,
    store_id: str,
    period: str,
) -> Dict:
    """BFF: score + insights + profit trend + health trend (all in one request)."""
    score = None
    insights = []
    profit_trend = []
    health_trend = []

    try:
        score = await get_health_score(db, store_id, period)
    except Exception as exc:
        logger.warning("finance_dashboard.health_score_failed", store_id=store_id, period=period, error=str(exc))

    try:
        insights = await get_finance_insights(db, store_id, period)
    except Exception as exc:
        logger.warning("finance_dashboard.insights_failed", store_id=store_id, period=period, error=str(exc))

    try:
        profit_trend = await get_profit_trend(db, store_id, periods=6)
    except Exception as exc:
        logger.warning("finance_dashboard.profit_trend_failed", store_id=store_id, error=str(exc))

    try:
        health_trend = await get_health_trend(db, store_id, periods=6)
    except Exception as exc:
        logger.warning("finance_dashboard.health_trend_failed", store_id=store_id, error=str(exc))

    return {
        "store_id": store_id,
        "period": period,
        "score": score,
        "insights": insights,
        "profit_trend": profit_trend,
        "health_trend": health_trend,
    }
