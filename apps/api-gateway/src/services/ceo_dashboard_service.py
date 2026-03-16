"""
多门店驾驶舱聚合服务 — Phase 5 Month 3

职责：
  CEO 视角：跨门店利润排名 / 综合风险热力 / 现金流状态
  区域负责人：区域内门店对比 / 落后门店预警 / 税务偏差汇总
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


def _safe_float(v: Any) -> float:
    if v is None:
        return 0.0
    if isinstance(v, Decimal):
        return float(v)
    return float(v)


async def get_ceo_dashboard(
    db: AsyncSession,
    brand_id: Optional[str],
    period: str,
) -> Dict[str, Any]:
    """
    CEO 多门店驾驶舱（BFF）。
    聚合：利润排行 / 风险热力 / 税务偏差 / Agent动作摘要。
    """
    today = date.today().isoformat()

    # ── 1. 门店利润排行（TOP 10） ──────────────────────────────────────────
    profit_rank: List[Dict[str, Any]] = []
    try:
        rows = (
            await db.execute(
                text("""
            SELECT store_id, net_revenue_yuan, gross_profit_yuan, profit_margin_pct,
                   total_cost_yuan
            FROM profit_attribution_results
            WHERE period = :period
            ORDER BY gross_profit_yuan DESC
            LIMIT 10
        """),
                {"period": period},
            )
        ).fetchall()
        for i, r in enumerate(rows, 1):
            profit_rank.append(
                {
                    "rank": i,
                    "store_id": r.store_id,
                    "net_revenue_yuan": _safe_float(r.net_revenue_yuan),
                    "gross_profit_yuan": _safe_float(r.gross_profit_yuan),
                    "profit_margin_pct": _safe_float(r.profit_margin_pct),
                    "total_cost_yuan": _safe_float(r.total_cost_yuan),
                }
            )
    except Exception:
        logger.warning("ceo_dashboard_profit_rank_failed")

    # ── 2. 品牌汇总（收入/利润/成本合计） ─────────────────────────────────
    brand_summary: Optional[Dict[str, Any]] = None
    try:
        q = """
            SELECT COUNT(DISTINCT store_id) AS store_count,
                   SUM(net_revenue_yuan)    AS total_revenue,
                   SUM(gross_profit_yuan)   AS total_profit,
                   SUM(total_cost_yuan)     AS total_cost,
                   AVG(profit_margin_pct)   AS avg_margin
            FROM profit_attribution_results
            WHERE period = :period
        """
        params: Dict[str, Any] = {"period": period}
        if brand_id:
            q += " AND store_id IN (SELECT id FROM stores WHERE brand_id = :bid)"
            params["bid"] = brand_id
        row = (await db.execute(text(q), params)).fetchone()
        if row and row.store_count:
            brand_summary = {
                "store_count": row.store_count,
                "total_revenue_yuan": _safe_float(row.total_revenue),
                "total_profit_yuan": _safe_float(row.total_profit),
                "total_cost_yuan": _safe_float(row.total_cost),
                "avg_margin_pct": _safe_float(row.avg_margin),
            }
    except Exception:
        logger.warning("ceo_dashboard_brand_summary_failed")

    # ── 3. 风险热力（各门店风险任务汇总） ─────────────────────────────────
    risk_heat: List[Dict[str, Any]] = []
    try:
        rows = (
            await db.execute(
                text("""
            SELECT store_id,
                   COUNT(*) AS total_open,
                   COUNT(CASE WHEN severity IN ('high','critical') THEN 1 END) AS high_count,
                   MAX(severity) AS max_severity
            FROM risk_tasks
            WHERE status = 'open'
            GROUP BY store_id
            ORDER BY high_count DESC, total_open DESC
            LIMIT 10
        """),
                {},
            )
        ).fetchall()
        risk_heat = [
            {
                "store_id": r.store_id,
                "open_total": r.total_open,
                "high_count": r.high_count,
                "max_severity": r.max_severity,
            }
            for r in rows
        ]
    except Exception:
        logger.warning("ceo_dashboard_risk_heat_failed")

    # ── 4. 税务偏差告警门店 ────────────────────────────────────────────────
    tax_alerts: List[Dict[str, Any]] = []
    try:
        rows = (
            await db.execute(
                text("""
            SELECT store_id, tax_type, tax_name,
                   deviation_yuan, deviation_pct, risk_level
            FROM tax_calculations
            WHERE period = :period
              AND risk_level IN ('high', 'critical')
            ORDER BY ABS(deviation_yuan) DESC
            LIMIT 10
        """),
                {"period": period},
            )
        ).fetchall()
        tax_alerts = [
            {
                "store_id": r.store_id,
                "tax_type": r.tax_type,
                "tax_name": r.tax_name,
                "deviation_yuan": _safe_float(r.deviation_yuan),
                "deviation_pct": _safe_float(r.deviation_pct),
                "risk_level": r.risk_level,
            }
            for r in rows
        ]
    except Exception:
        logger.warning("ceo_dashboard_tax_alerts_failed")

    # ── 5. 现金流缺口门店 ─────────────────────────────────────────────────
    cash_gap_stores: List[Dict[str, Any]] = []
    try:
        rows = (
            await db.execute(
                text("""
            SELECT cf.store_id,
                   COUNT(*)          AS gap_days,
                   MIN(balance_yuan) AS min_balance
            FROM cashflow_forecasts cf
            WHERE balance_yuan < 0
              AND generated_on = (
                  SELECT MAX(generated_on) FROM cashflow_forecasts
                  WHERE store_id = cf.store_id
              )
            GROUP BY cf.store_id
            ORDER BY min_balance
            LIMIT 5
        """),
                {},
            )
        ).fetchall()
        cash_gap_stores = [
            {
                "store_id": r.store_id,
                "gap_days": r.gap_days,
                "min_balance_yuan": _safe_float(r.min_balance),
            }
            for r in rows
        ]
    except Exception:
        logger.warning("ceo_dashboard_cash_gap_failed")

    # ── 6. 结算异常汇总 ───────────────────────────────────────────────────
    settlement_issues: List[Dict[str, Any]] = []
    try:
        rows = (
            await db.execute(
                text("""
            SELECT store_id, platform, period,
                   deviation_yuan, risk_level, settle_date
            FROM settlement_records
            WHERE status = 'pending'
              AND risk_level IN ('high', 'critical')
            ORDER BY ABS(deviation_yuan) DESC
            LIMIT 5
        """),
                {},
            )
        ).fetchall()
        settlement_issues = [
            {
                "store_id": r.store_id,
                "platform": r.platform,
                "period": r.period,
                "deviation_yuan": _safe_float(r.deviation_yuan),
                "risk_level": r.risk_level,
                "settle_date": str(r.settle_date),
            }
            for r in rows
        ]
    except Exception:
        logger.warning("ceo_dashboard_settlement_failed")

    # ── 7. Pending L2 Agent 动作数 ────────────────────────────────────────
    pending_l2 = 0
    try:
        pending_l2 = (
            (
                await db.execute(
                    text("""
            SELECT COUNT(*) FROM agent_action_log
            WHERE action_level IN ('L2','L3') AND status = 'pending'
        """),
                    {},
                )
            ).scalar()
            or 0
        )
    except Exception as exc:
        logger.warning("ceo_dashboard.pending_l2_query_failed", error=str(exc))

    return {
        "period": period,
        "as_of": today,
        "brand_summary": brand_summary,
        "profit_rank": profit_rank,
        "risk_heat": risk_heat,
        "tax_alerts": tax_alerts,
        "cash_gap_stores": cash_gap_stores,
        "settlement_issues": settlement_issues,
        "pending_l2_actions": pending_l2,
    }


async def get_region_dashboard(
    db: AsyncSession,
    store_ids: List[str],
    period: str,
) -> Dict[str, Any]:
    """
    区域负责人仪表盘（BFF）。
    只聚合传入的 store_ids 门店数据。
    """
    if not store_ids:
        return {"period": period, "stores": [], "summary": None}

    today = date.today().isoformat()

    # 利润对比
    profit_rows = (
        await db.execute(
            text("""
        SELECT store_id, net_revenue_yuan, gross_profit_yuan,
               profit_margin_pct, food_cost_yuan, waste_cost_yuan
        FROM profit_attribution_results
        WHERE period = :period
          AND store_id = ANY(:sids)
        ORDER BY gross_profit_yuan DESC
    """),
            {"period": period, "sids": store_ids},
        )
    ).fetchall()

    stores_data = [
        {
            "store_id": r.store_id,
            "net_revenue_yuan": _safe_float(r.net_revenue_yuan),
            "gross_profit_yuan": _safe_float(r.gross_profit_yuan),
            "profit_margin_pct": _safe_float(r.profit_margin_pct),
            "food_cost_yuan": _safe_float(r.food_cost_yuan),
            "waste_cost_yuan": _safe_float(r.waste_cost_yuan),
        }
        for r in profit_rows
    ]

    # 区域汇总
    if stores_data:
        summary = {
            "store_count": len(stores_data),
            "total_revenue_yuan": round(sum(s["net_revenue_yuan"] for s in stores_data), 2),
            "total_profit_yuan": round(sum(s["gross_profit_yuan"] for s in stores_data), 2),
            "avg_margin_pct": round(sum(s["profit_margin_pct"] for s in stores_data) / len(stores_data), 2),
            "best_store_id": stores_data[0]["store_id"] if stores_data else None,
            "worst_store_id": stores_data[-1]["store_id"] if len(stores_data) > 1 else None,
        }
    else:
        summary = None

    # 各门店开放风险数
    risk_rows = (
        await db.execute(
            text("""
        SELECT store_id, COUNT(*) AS open_count,
               COUNT(CASE WHEN severity IN ('high','critical') THEN 1 END) AS high_count
        FROM risk_tasks
        WHERE status = 'open' AND store_id = ANY(:sids)
        GROUP BY store_id
    """),
            {"sids": store_ids},
        )
    ).fetchall()
    risk_by_store = {r.store_id: {"open": r.open_count, "high": r.high_count} for r in risk_rows}

    for s in stores_data:
        s["risk"] = risk_by_store.get(s["store_id"], {"open": 0, "high": 0})

    return {
        "period": period,
        "as_of": today,
        "summary": summary,
        "stores": stores_data,
    }
