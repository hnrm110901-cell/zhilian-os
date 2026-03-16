"""
税务规则引擎 — Phase 5 Month 2

从 business_events 事件流水 + tax_rules 配置 计算应纳税额，
检测税务偏差，生成 L1/L2 级别的 Agent 提醒。

税种覆盖：
  vat_small    — 增值税小规模纳税人（默认税率 3%，计税基础=销售净额）
  vat_general  — 增值税一般纳税人（默认税率 6%，进项可抵扣）
  income_tax   — 企业所得税（默认税率 25%，计税基础=税前利润）
  stamp_duty   — 印花税（默认税率 0.03%，计税基础=合同金额/销售额）
"""

from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# ── 默认税率（税务规则表为空时的兜底） ────────────────────────────────────────
DEFAULT_TAX_RATES: Dict[str, float] = {
    "vat_small": 0.03,  # 增值税小规模
    "vat_general": 0.06,  # 增值税一般纳税人（简化，不含进项抵扣）
    "income_tax": 0.25,  # 企业所得税
    "stamp_duty": 0.0003,  # 印花税（万分之三）
}

DEFAULT_TAX_NAMES: Dict[str, str] = {
    "vat_small": "增值税（小规模）",
    "vat_general": "增值税（一般纳税人）",
    "income_tax": "企业所得税",
    "stamp_duty": "印花税",
}

# 偏差风险阈值
RISK_THRESHOLDS = {
    "critical": 0.20,  # 偏差 > 20% → critical
    "high": 0.10,  # 偏差 > 10% → high
    "medium": 0.05,  # 偏差 > 5%  → medium
    # else → low
}


def _safe_float(v: Any) -> float:
    if v is None:
        return 0.0
    if isinstance(v, Decimal):
        return float(v)
    return float(v)


def _assess_risk(deviation_pct: float) -> str:
    abs_pct = abs(deviation_pct)
    if abs_pct >= RISK_THRESHOLDS["critical"]:
        return "critical"
    if abs_pct >= RISK_THRESHOLDS["high"]:
        return "high"
    if abs_pct >= RISK_THRESHOLDS["medium"]:
        return "medium"
    return "low"


def compute_tax_for_type(
    tax_type: str,
    net_revenue_yuan: float,
    gross_profit_yuan: float,
    total_sales_yuan: float,
    tax_rate: Optional[float] = None,
) -> Dict[str, Any]:
    """
    计算单个税种的应纳税额。
    返回: {tax_type, taxable_base, tax_amount, rate, detail}
    """
    rate = tax_rate if tax_rate is not None else DEFAULT_TAX_RATES.get(tax_type, 0.0)

    if tax_type == "vat_small":
        # 计税基础：销售净额（不含税收入）
        # 不含税收入 = 含税收入 / (1 + 税率)
        taxable_base = net_revenue_yuan / (1 + rate) if (1 + rate) > 0 else 0.0
        tax_amount = taxable_base * rate
        detail = f"不含税收入 ¥{taxable_base:.2f} × {rate*100:.1f}%"

    elif tax_type == "vat_general":
        # 简化：按销售额×税率（实际应扣进项，此处不做）
        taxable_base = net_revenue_yuan / (1 + rate) if (1 + rate) > 0 else 0.0
        tax_amount = taxable_base * rate
        detail = f"销项税 ¥{tax_amount:.2f}（进项抵扣需手动录入）"

    elif tax_type == "income_tax":
        # 计税基础：税前利润（= gross_profit，简化未扣税前可扣项）
        taxable_base = max(0.0, gross_profit_yuan)
        tax_amount = taxable_base * rate
        detail = f"税前利润 ¥{taxable_base:.2f} × {rate*100:.1f}%"

    elif tax_type == "stamp_duty":
        # 计税基础：合同金额（此处近似用总销售额）
        taxable_base = total_sales_yuan
        tax_amount = taxable_base * rate
        detail = f"合同金额 ¥{taxable_base:.2f} × {rate*100:.4f}%"

    else:
        taxable_base = net_revenue_yuan
        tax_amount = taxable_base * rate
        detail = f"通用税种 ¥{taxable_base:.2f} × {rate*100:.4f}%"

    return {
        "tax_type": tax_type,
        "tax_name": DEFAULT_TAX_NAMES.get(tax_type, tax_type),
        "tax_rate": rate,
        "taxable_base": round(taxable_base, 2),
        "tax_amount": round(tax_amount, 2),
        "detail": detail,
    }


async def compute_tax_calculation(
    db: AsyncSession,
    store_id: str,
    period: str,
    force: bool = False,
) -> List[Dict[str, Any]]:
    """
    从 profit_attribution_results + business_events 计算本期税务。
    幂等：同一 store_id+period+tax_type 覆盖写入。
    返回：所有税种的计算结果列表。
    """
    today = date.today().isoformat()

    if not force:
        # 查是否已有当日计算
        existing = (
            (
                await db.execute(
                    text("""
            SELECT COUNT(*) FROM tax_calculations
            WHERE store_id = :sid AND period = :period AND calc_date = :today
        """),
                    {"sid": store_id, "period": period, "today": today},
                )
            ).scalar()
            or 0
        )
        if existing > 0:
            rows = (
                await db.execute(
                    text("""
                SELECT * FROM tax_calculations
                WHERE store_id = :sid AND period = :period AND calc_date = :today
                ORDER BY tax_type
            """),
                    {"sid": store_id, "period": period, "today": today},
                )
            ).fetchall()
            return [_row_to_tax_dict(r) for r in rows]

    # ── 获取利润归因数据 ──────────────────────────────────────────────────
    attr = (
        await db.execute(
            text("""
        SELECT net_revenue_yuan, gross_revenue_yuan, gross_profit_yuan
        FROM profit_attribution_results
        WHERE store_id = :sid AND period = :period
        ORDER BY calc_date DESC LIMIT 1
    """),
            {"sid": store_id, "period": period},
        )
    ).fetchone()

    net_revenue = _safe_float(attr.net_revenue_yuan) if attr else 0.0
    gross_revenue = _safe_float(attr.gross_revenue_yuan) if attr else 0.0
    gross_profit = _safe_float(attr.gross_profit_yuan) if attr else 0.0

    # ── 获取已申报税额（来自 invoice 类型事件） ──────────────────────────
    declared_row = (
        await db.execute(
            text("""
        SELECT COALESCE(SUM(amount_yuan), 0) AS declared_total
        FROM business_events
        WHERE store_id = :sid AND period = :period
          AND event_type = 'invoice'
          AND event_subtype = 'tax_paid'
    """),
            {"sid": store_id, "period": period},
        )
    ).fetchone()
    declared_total = _safe_float(declared_row.declared_total) if declared_row else 0.0

    # ── 查税务规则（有则用，无则用默认） ────────────────────────────────────
    rule_rows = (
        await db.execute(
            text("""
        SELECT tax_type, tax_rate
        FROM tax_rules
        WHERE (store_id = :sid OR store_id IS NULL)
          AND is_active = true
          AND effective_from <= :today
          AND (effective_to IS NULL OR effective_to >= :today)
        ORDER BY store_id NULLS LAST, tax_type
    """),
            {"sid": store_id, "today": today},
        )
    ).fetchall()

    # store_id 专属规则优先，否则用全局规则
    custom_rates: Dict[str, float] = {}
    for r in rule_rows:
        if r.tax_type not in custom_rates:
            custom_rates[r.tax_type] = _safe_float(r.tax_rate)

    # ── 计算各税种 ─────────────────────────────────────────────────────────
    # 餐饮通用：小规模增值税 + 印花税
    # 有利润时加企业所得税
    tax_types_to_calc = ["vat_small", "stamp_duty"]
    if gross_profit > 0:
        tax_types_to_calc.append("income_tax")

    results = []
    for tax_type in tax_types_to_calc:
        rate = custom_rates.get(tax_type)
        calc = compute_tax_for_type(
            tax_type=tax_type,
            net_revenue_yuan=net_revenue,
            gross_profit_yuan=gross_profit,
            total_sales_yuan=gross_revenue,
            tax_rate=rate,
        )

        # 偏差（只对增值税有意义，其他税未申报也正常）
        declared = declared_total if tax_type == "vat_small" else 0.0
        deviation = calc["tax_amount"] - declared
        deviation_pct = (deviation / calc["tax_amount"] * 100) if calc["tax_amount"] > 0 else 0.0
        risk_level = _assess_risk(deviation_pct)

        # 幂等 upsert
        existing_row = (
            await db.execute(
                text("""
            SELECT id FROM tax_calculations
            WHERE store_id = :sid AND period = :period AND tax_type = :tt
        """),
                {"sid": store_id, "period": period, "tt": tax_type},
            )
        ).fetchone()

        detail_json = json.dumps(
            {
                "formula": calc["detail"],
                "net_revenue_yuan": round(net_revenue, 2),
                "gross_profit_yuan": round(gross_profit, 2),
            }
        )

        if existing_row:
            await db.execute(
                text("""
                UPDATE tax_calculations SET
                    calc_date        = :today,
                    tax_name         = :tn,
                    tax_rate         = :rate,
                    taxable_base_yuan= :base,
                    tax_amount_yuan  = :amt,
                    declared_yuan    = :decl,
                    deviation_yuan   = :dev,
                    deviation_pct    = :devpct,
                    risk_level       = :risk,
                    calc_detail      = :detail
                WHERE store_id = :sid AND period = :period AND tax_type = :tt
            """),
                {
                    "today": today,
                    "tn": calc["tax_name"],
                    "rate": calc["tax_rate"],
                    "base": calc["taxable_base"],
                    "amt": calc["tax_amount"],
                    "decl": declared,
                    "dev": round(deviation, 2),
                    "devpct": round(deviation_pct, 2),
                    "risk": risk_level,
                    "detail": detail_json,
                    "sid": store_id,
                    "period": period,
                    "tt": tax_type,
                },
            )
        else:
            tid = str(uuid.uuid4())
            await db.execute(
                text("""
                INSERT INTO tax_calculations
                  (id, store_id, period, calc_date, tax_type, tax_name, tax_rate,
                   taxable_base_yuan, tax_amount_yuan, declared_yuan, deviation_yuan,
                   deviation_pct, risk_level, calc_detail, created_at)
                VALUES
                  (:id, :sid, :period, :today, :tt, :tn, :rate,
                   :base, :amt, :decl, :dev, :devpct, :risk, :detail, NOW())
            """),
                {
                    "id": tid,
                    "sid": store_id,
                    "period": period,
                    "today": today,
                    "tt": tax_type,
                    "tn": calc["tax_name"],
                    "rate": calc["tax_rate"],
                    "base": calc["taxable_base"],
                    "amt": calc["tax_amount"],
                    "decl": declared,
                    "dev": round(deviation, 2),
                    "devpct": round(deviation_pct, 2),
                    "risk": risk_level,
                    "detail": detail_json,
                },
            )

        results.append(
            {
                "tax_type": tax_type,
                "tax_name": calc["tax_name"],
                "tax_rate": calc["tax_rate"],
                "taxable_base_yuan": calc["taxable_base"],
                "tax_amount_yuan": calc["tax_amount"],
                "declared_yuan": round(declared, 2),
                "deviation_yuan": round(deviation, 2),
                "deviation_pct": round(deviation_pct, 2),
                "risk_level": risk_level,
                "detail": calc["detail"],
            }
        )

    await db.commit()

    # 高风险时生成 Agent 动作
    high_risk = [r for r in results if r["risk_level"] in ("high", "critical")]
    if high_risk:
        for r in high_risk:
            await _log_agent_action(
                db,
                store_id,
                period,
                level="L1" if r["risk_level"] == "high" else "L2",
                trigger="tax_deviation",
                title=f"{r['tax_name']}偏差预警：差额 ¥{abs(r['deviation_yuan']):.2f}",
                description=f"期间 {period} {r['tax_name']} 应纳 ¥{r['tax_amount_yuan']:.2f}，"
                f"已申报 ¥{r['declared_yuan']:.2f}，"
                f"偏差 {r['deviation_pct']:.1f}%（{r['risk_level']}）",
                expected_impact=-abs(r["deviation_yuan"]),
            )
        await db.commit()

    logger.info("tax_calculated", store_id=store_id, period=period, types=len(results))
    return results


async def _log_agent_action(
    db: AsyncSession,
    store_id: str,
    period: str,
    level: str,
    trigger: str,
    title: str,
    description: str,
    expected_impact: float = 0.0,
    agent_name: str = "TaxAgent",
) -> None:
    aid = str(uuid.uuid4())
    await db.execute(
        text("""
        INSERT INTO agent_action_log
          (id, store_id, action_level, agent_name, trigger_type, title, description,
           expected_impact_yuan, confidence, status, period, created_at)
        VALUES
          (:id, :sid, :level, :agent, :trigger, :title, :desc,
           :impact, 0.85, 'pending', :period, NOW())
    """),
        {
            "id": aid,
            "sid": store_id,
            "level": level,
            "agent": agent_name,
            "trigger": trigger,
            "title": title,
            "desc": description,
            "impact": round(expected_impact, 2),
            "period": period,
        },
    )


def _row_to_tax_dict(row: Any) -> Dict[str, Any]:
    detail_str = None
    if row.calc_detail:
        try:
            d = json.loads(row.calc_detail)
            detail_str = d.get("formula", row.calc_detail)
        except (json.JSONDecodeError, TypeError):
            detail_str = row.calc_detail
    return {
        "tax_type": row.tax_type,
        "tax_name": row.tax_name,
        "tax_rate": _safe_float(row.tax_rate),
        "taxable_base_yuan": _safe_float(row.taxable_base_yuan),
        "tax_amount_yuan": _safe_float(row.tax_amount_yuan),
        "declared_yuan": _safe_float(row.declared_yuan),
        "deviation_yuan": _safe_float(row.deviation_yuan),
        "deviation_pct": _safe_float(row.deviation_pct),
        "risk_level": row.risk_level,
        "detail": detail_str,
    }
