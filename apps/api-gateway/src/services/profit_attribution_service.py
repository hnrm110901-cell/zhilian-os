"""
利润归因服务 — Phase 5 Month 1

实现公式：利润 = 销售 - 食材成本 - 损耗 - 平台抽佣 - 人工 - 其他费用

数据来源：business_events 表（经营事件流水）
输出：profit_attribution_results 缓存 + 实时归因明细
"""

from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal
from typing import Any, Dict, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


# ── 利润归因公式 ──────────────────────────────────────────────────────────────
#
#  净收入     = 销售额 - 退款额
#  总成本     = 食材成本 + 损耗 + 平台抽佣 + 人工 + 其他费用
#  毛利润     = 净收入 - 总成本
#  利润率(%) = 毛利润 / 净收入 × 100
#
# event_type → 归因维度映射：
#   sale        → gross_revenue（正值）
#   refund      → refund（正值，减收入）
#   purchase    → food_cost（原料采购）
#   receipt     → food_cost（入库修正，叠加计算）
#   waste       → waste_cost
#   settlement  → platform_commission（外卖平台抽佣）
#   expense     → other_expense（含人工）
#   payment     → other_expense（对外付款）
#   invoice     → 不直接影响利润（仅记录票据）
#   collection  → 不影响利润（收款确认）


def _safe_float(v: Any) -> float:
    if v is None:
        return 0.0
    if isinstance(v, Decimal):
        return float(v)
    return float(v)


def _pct(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator * 100, 2)


def build_attribution_detail(
    gross_revenue: float,
    refund: float,
    net_revenue: float,
    food_cost: float,
    waste_cost: float,
    platform_commission: float,
    labor_cost: float,
    other_expense: float,
    total_cost: float,
    gross_profit: float,
) -> Dict[str, Any]:
    """构建归因明细 JSON（各成本项占净收入比）"""
    return {
        "revenue_breakdown": {
            "gross_revenue_yuan": round(gross_revenue, 2),
            "refund_yuan": round(refund, 2),
            "net_revenue_yuan": round(net_revenue, 2),
            "refund_rate_pct": _pct(refund, gross_revenue),
        },
        "cost_breakdown": {
            "food_cost": {"yuan": round(food_cost, 2), "pct_of_revenue": _pct(food_cost, net_revenue)},
            "waste_cost": {"yuan": round(waste_cost, 2), "pct_of_revenue": _pct(waste_cost, net_revenue)},
            "platform_commission": {
                "yuan": round(platform_commission, 2),
                "pct_of_revenue": _pct(platform_commission, net_revenue),
            },
            "labor_cost": {"yuan": round(labor_cost, 2), "pct_of_revenue": _pct(labor_cost, net_revenue)},
            "other_expense": {"yuan": round(other_expense, 2), "pct_of_revenue": _pct(other_expense, net_revenue)},
            "total_cost": {"yuan": round(total_cost, 2), "pct_of_revenue": _pct(total_cost, net_revenue)},
        },
        "profit_summary": {
            "gross_profit_yuan": round(gross_profit, 2),
            "profit_margin_pct": _pct(gross_profit, net_revenue),
        },
    }


async def compute_profit_attribution(
    db: AsyncSession,
    store_id: str,
    period: str,
    force: bool = False,
) -> Dict[str, Any]:
    """
    从 business_events 聚合利润归因，写入/更新 profit_attribution_results。
    幂等：同一 store_id + period + calc_date 覆盖写入。
    """
    today = date.today().isoformat()

    # 如非强制，先检查当日缓存
    if not force:
        cached = (
            await db.execute(
                text("""
            SELECT * FROM profit_attribution_results
            WHERE store_id = :sid AND period = :period AND calc_date = :today
            LIMIT 1
        """),
                {"sid": store_id, "period": period, "today": today},
            )
        ).fetchone()
        if cached:
            return _row_to_dict(cached)

    # ── 从事件流水聚合各维度金额 ──────────────────────────────────────────
    rows = (
        await db.execute(
            text("""
        SELECT event_type, SUM(amount_yuan) AS total_yuan, COUNT(*) AS cnt
        FROM business_events
        WHERE store_id = :sid AND period = :period
        GROUP BY event_type
    """),
            {"sid": store_id, "period": period},
        )
    ).fetchall()

    # 汇总
    by_type: Dict[str, float] = {r.event_type: _safe_float(r.total_yuan) for r in rows}
    event_count = sum(r.cnt for r in rows)

    gross_revenue = by_type.get("sale", 0.0)
    refund = by_type.get("refund", 0.0)
    net_revenue = gross_revenue - refund

    # 食材成本 = 采购 + 收货（如重复则取较大值；通常只选一种来源）
    # 简化规则：purchase 为主，receipt 为补充（若没有 purchase）
    purchase_cost = by_type.get("purchase", 0.0)
    receipt_cost = by_type.get("receipt", 0.0)
    food_cost = purchase_cost if purchase_cost > 0 else receipt_cost

    waste_cost = by_type.get("waste", 0.0)
    platform_commission = by_type.get("settlement", 0.0)
    # expense + payment 都算其他费用
    other_expense = by_type.get("expense", 0.0) + by_type.get("payment", 0.0)
    labor_cost = 0.0  # Phase 5 Month 1 暂从 expense 中不做细分

    total_cost = food_cost + waste_cost + platform_commission + labor_cost + other_expense
    gross_profit = net_revenue - total_cost
    margin_pct = _pct(gross_profit, net_revenue) if net_revenue > 0 else 0.0

    detail = build_attribution_detail(
        gross_revenue,
        refund,
        net_revenue,
        food_cost,
        waste_cost,
        platform_commission,
        labor_cost,
        other_expense,
        total_cost,
        gross_profit,
    )

    # ── 幂等 upsert ──────────────────────────────────────────────────────
    existing = (
        await db.execute(
            text("""
        SELECT id FROM profit_attribution_results
        WHERE store_id = :sid AND period = :period AND calc_date = :today
    """),
            {"sid": store_id, "period": period, "today": today},
        )
    ).fetchone()

    if existing:
        await db.execute(
            text("""
            UPDATE profit_attribution_results SET
                gross_revenue_yuan       = :grev,
                refund_yuan              = :ref,
                net_revenue_yuan         = :nrev,
                food_cost_yuan           = :fc,
                waste_cost_yuan          = :wc,
                platform_commission_yuan = :pc,
                labor_cost_yuan          = :lc,
                other_expense_yuan       = :oe,
                total_cost_yuan          = :tc,
                gross_profit_yuan        = :gp,
                profit_margin_pct        = :pmp,
                attribution_detail       = :detail,
                event_count              = :ecount
            WHERE store_id = :sid AND period = :period AND calc_date = :today
        """),
            {
                "grev": gross_revenue,
                "ref": refund,
                "nrev": net_revenue,
                "fc": food_cost,
                "wc": waste_cost,
                "pc": platform_commission,
                "lc": labor_cost,
                "oe": other_expense,
                "tc": total_cost,
                "gp": gross_profit,
                "pmp": margin_pct,
                "detail": json.dumps(detail),
                "ecount": event_count,
                "sid": store_id,
                "period": period,
                "today": today,
            },
        )
    else:
        rid = str(uuid.uuid4())
        await db.execute(
            text("""
            INSERT INTO profit_attribution_results
              (id, store_id, period, calc_date,
               gross_revenue_yuan, refund_yuan, net_revenue_yuan,
               food_cost_yuan, waste_cost_yuan, platform_commission_yuan,
               labor_cost_yuan, other_expense_yuan, total_cost_yuan,
               gross_profit_yuan, profit_margin_pct,
               attribution_detail, event_count, created_at)
            VALUES
              (:id, :sid, :period, :today,
               :grev, :ref, :nrev,
               :fc, :wc, :pc,
               :lc, :oe, :tc,
               :gp, :pmp,
               :detail, :ecount, NOW())
        """),
            {
                "id": rid,
                "grev": gross_revenue,
                "ref": refund,
                "nrev": net_revenue,
                "fc": food_cost,
                "wc": waste_cost,
                "pc": platform_commission,
                "lc": labor_cost,
                "oe": other_expense,
                "tc": total_cost,
                "gp": gross_profit,
                "pmp": margin_pct,
                "detail": json.dumps(detail),
                "ecount": event_count,
                "sid": store_id,
                "period": period,
                "today": today,
            },
        )

    await db.commit()
    logger.info(
        "profit_attribution_computed", store_id=store_id, period=period, net_revenue=net_revenue, gross_profit=gross_profit
    )

    return {
        "store_id": store_id,
        "period": period,
        "calc_date": today,
        "revenue": {
            "gross_revenue_yuan": round(gross_revenue, 2),
            "refund_yuan": round(refund, 2),
            "net_revenue_yuan": round(net_revenue, 2),
        },
        "costs": {
            "food_cost_yuan": round(food_cost, 2),
            "waste_cost_yuan": round(waste_cost, 2),
            "platform_commission_yuan": round(platform_commission, 2),
            "labor_cost_yuan": round(labor_cost, 2),
            "other_expense_yuan": round(other_expense, 2),
            "total_cost_yuan": round(total_cost, 2),
        },
        "profit": {
            "gross_profit_yuan": round(gross_profit, 2),
            "profit_margin_pct": margin_pct,
        },
        "event_count": event_count,
        "attribution_detail": detail,
    }


def _row_to_dict(row: Any) -> Dict[str, Any]:
    """SQLAlchemy row → dict（供缓存命中时使用）"""
    detail = None
    if row.attribution_detail:
        try:
            detail = json.loads(row.attribution_detail)
        except (json.JSONDecodeError, TypeError):
            detail = None
    return {
        "store_id": row.store_id,
        "period": row.period,
        "calc_date": str(row.calc_date),
        "revenue": {
            "gross_revenue_yuan": _safe_float(row.gross_revenue_yuan),
            "refund_yuan": _safe_float(row.refund_yuan),
            "net_revenue_yuan": _safe_float(row.net_revenue_yuan),
        },
        "costs": {
            "food_cost_yuan": _safe_float(row.food_cost_yuan),
            "waste_cost_yuan": _safe_float(row.waste_cost_yuan),
            "platform_commission_yuan": _safe_float(row.platform_commission_yuan),
            "labor_cost_yuan": _safe_float(row.labor_cost_yuan),
            "other_expense_yuan": _safe_float(row.other_expense_yuan),
            "total_cost_yuan": _safe_float(row.total_cost_yuan),
        },
        "profit": {
            "gross_profit_yuan": _safe_float(row.gross_profit_yuan),
            "profit_margin_pct": _safe_float(row.profit_margin_pct),
        },
        "event_count": row.event_count,
        "attribution_detail": detail,
    }
