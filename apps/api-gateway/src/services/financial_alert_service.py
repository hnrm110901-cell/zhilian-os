"""
财务预警服务 — Phase 5 Month 4

职责:
  - 管理预警规则（CRUD，支持启用/禁用）
  - 评估门店当前指标 vs 规则阈值
  - 冷却期防重复告警（cooldown_minutes）
  - 预警事件 FSM（open → acknowledged → resolved）

支持指标:
  profit_margin_pct    — 利润率 (%)
  food_cost_rate       — 食材成本率 (%)
  net_revenue_yuan     — 净收入 (元)
  gross_profit_yuan    — 毛利润 (元)
  cash_gap_days        — 预测期内现金缺口天数
  settlement_high_risk — 高/严重风险待核销结算笔数
  tax_deviation_pct    — 最大税务偏差率 (%)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = structlog.get_logger()

# ── Constants ─────────────────────────────────────────────────────────────────

SUPPORTED_METRICS: List[str] = [
    "profit_margin_pct",
    "food_cost_rate",
    "net_revenue_yuan",
    "gross_profit_yuan",
    "cash_gap_days",
    "settlement_high_risk",
    "tax_deviation_pct",
]

VALID_ALERT_TRANSITIONS: Dict[str, set] = {
    "open":         {"acknowledged", "resolved"},
    "acknowledged": {"resolved"},
    "resolved":     set(),
}

_METRIC_LABELS: Dict[str, str] = {
    "profit_margin_pct":    "利润率",
    "food_cost_rate":       "食材成本率",
    "net_revenue_yuan":     "净收入",
    "gross_profit_yuan":    "毛利润",
    "cash_gap_days":        "现金缺口天数",
    "settlement_high_risk": "高风险结算笔数",
    "tax_deviation_pct":    "税务偏差率",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_float(v: Any) -> float:
    if v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _check_threshold(
    current: float, threshold_type: str, threshold_value: float,
) -> bool:
    """Return True if the alert condition is triggered."""
    if threshold_type == "above":
        return current > threshold_value
    elif threshold_type == "below":
        return current < threshold_value
    elif threshold_type == "abs_above":
        return abs(current) > threshold_value
    return False


def _format_alert_message(
    metric: str, current: float, threshold_type: str, threshold_value: float,
) -> str:
    direction = "超过" if threshold_type in ("above", "abs_above") else "低于"
    label = _METRIC_LABELS.get(metric, metric)

    if metric in ("profit_margin_pct", "food_cost_rate", "tax_deviation_pct"):
        cur_str = f"{current:.1f}%"
        thr_str = f"{threshold_value:.1f}%"
    elif metric in ("net_revenue_yuan", "gross_profit_yuan"):
        cur_str = f"¥{current:.0f}"
        thr_str = f"¥{threshold_value:.0f}"
    else:
        cur_str = f"{current:.0f}"
        thr_str = f"{threshold_value:.0f}"

    return f"{label} {cur_str} {direction}阈值 {thr_str}"


# ── Metric fetchers ───────────────────────────────────────────────────────────

async def _get_metric_value(
    db: AsyncSession,
    store_id: str,
    period: str,
    metric: str,
) -> Optional[float]:
    """Fetch current metric value for a store/period from the appropriate table."""
    today = datetime.now(timezone.utc).date().isoformat()

    if metric in ("profit_margin_pct", "food_cost_rate", "net_revenue_yuan", "gross_profit_yuan"):
        res = await db.execute(text("""
            SELECT net_revenue_yuan, food_cost_yuan, gross_profit_yuan, profit_margin_pct
            FROM profit_attribution_results
            WHERE store_id = :sid AND period = :period
            ORDER BY calc_date DESC LIMIT 1
        """), {"sid": store_id, "period": period})
        row = res.fetchone()
        if not row:
            return None
        net_rev     = _safe_float(row[0])
        food_cost   = _safe_float(row[1])
        gross_profit = _safe_float(row[2])
        margin       = _safe_float(row[3])
        if metric == "profit_margin_pct":
            return margin
        elif metric == "food_cost_rate":
            return round((food_cost / net_rev * 100), 2) if net_rev > 0 else 0.0
        elif metric == "net_revenue_yuan":
            return net_rev
        elif metric == "gross_profit_yuan":
            return gross_profit

    elif metric == "cash_gap_days":
        res = await db.execute(text("""
            SELECT COUNT(*) FROM cashflow_forecasts
            WHERE store_id = :sid AND balance_yuan < 0 AND forecast_date >= :today
        """), {"sid": store_id, "today": today})
        row = res.fetchone()
        return float(row[0]) if row else 0.0

    elif metric == "settlement_high_risk":
        res = await db.execute(text("""
            SELECT COUNT(*) FROM settlement_records
            WHERE store_id = :sid
              AND risk_level IN ('high', 'critical')
              AND status = 'pending'
        """), {"sid": store_id})
        row = res.fetchone()
        return float(row[0]) if row else 0.0

    elif metric == "tax_deviation_pct":
        res = await db.execute(text("""
            SELECT MAX(ABS(deviation_pct)) FROM tax_calculations
            WHERE store_id = :sid AND period = :period
        """), {"sid": store_id, "period": period})
        row = res.fetchone()
        return _safe_float(row[0]) if row else 0.0

    return None


# ── Rule CRUD ─────────────────────────────────────────────────────────────────

async def create_or_update_rule(
    db: AsyncSession,
    store_id: str,
    metric: str,
    threshold_type: str,
    threshold_value: float,
    severity: str,
    cooldown_minutes: int,
    brand_id: Optional[str] = None,
    rule_id: Optional[str] = None,
) -> Dict:
    if metric not in SUPPORTED_METRICS:
        return {"error": f"Unsupported metric: {metric}. Supported: {SUPPORTED_METRICS}"}
    if threshold_type not in ("above", "below", "abs_above"):
        return {"error": f"Invalid threshold_type '{threshold_type}'. Use: above/below/abs_above"}
    if severity not in ("info", "warning", "critical"):
        return {"error": f"Invalid severity '{severity}'. Use: info/warning/critical"}

    now = datetime.now(timezone.utc)

    if rule_id:
        res = await db.execute(text("""
            SELECT id FROM financial_alert_rules WHERE id = :rid AND store_id = :sid
        """), {"rid": rule_id, "sid": store_id})
        if not res.fetchone():
            return {"error": "Rule not found"}
        await db.execute(text("""
            UPDATE financial_alert_rules
            SET metric           = :metric,
                threshold_type   = :ttype,
                threshold_value  = :tval,
                severity         = :severity,
                cooldown_minutes = :cooldown,
                updated_at       = :now
            WHERE id = :rid
        """), {
            "metric": metric, "ttype": threshold_type, "tval": threshold_value,
            "severity": severity, "cooldown": cooldown_minutes,
            "now": now, "rid": rule_id,
        })
        await db.commit()
        return {"rule_id": rule_id, "action": "updated"}
    else:
        rid = str(uuid.uuid4())
        await db.execute(text("""
            INSERT INTO financial_alert_rules
                (id, store_id, brand_id, metric, threshold_type, threshold_value,
                 severity, enabled, cooldown_minutes, created_at, updated_at)
            VALUES
                (:id, :sid, :brand_id, :metric, :ttype, :tval,
                 :severity, TRUE, :cooldown, :now, :now)
        """), {
            "id": rid, "sid": store_id, "brand_id": brand_id,
            "metric": metric, "ttype": threshold_type, "tval": threshold_value,
            "severity": severity, "cooldown": cooldown_minutes, "now": now,
        })
        await db.commit()
        return {"rule_id": rid, "action": "created"}


async def set_rule_enabled(
    db: AsyncSession, rule_id: str, store_id: str, enabled: bool,
) -> Dict:
    now = datetime.now(timezone.utc)
    await db.execute(text("""
        UPDATE financial_alert_rules
        SET enabled = :enabled, updated_at = :now
        WHERE id = :rid AND store_id = :sid
    """), {"enabled": enabled, "now": now, "rid": rule_id, "sid": store_id})
    await db.commit()
    return {"rule_id": rule_id, "enabled": enabled}


async def get_rules(db: AsyncSession, store_id: str) -> List[Dict]:
    res = await db.execute(text("""
        SELECT id, store_id, metric, threshold_type, threshold_value,
               severity, enabled, cooldown_minutes, created_at, updated_at
        FROM financial_alert_rules
        WHERE store_id = :sid
        ORDER BY created_at DESC
    """), {"sid": store_id})
    keys = ["id", "store_id", "metric", "threshold_type", "threshold_value",
            "severity", "enabled", "cooldown_minutes", "created_at", "updated_at"]
    return [dict(zip(keys, r)) for r in res.fetchall()]


# ── Alert evaluation ──────────────────────────────────────────────────────────

async def evaluate_store_alerts(
    db: AsyncSession,
    store_id: str,
    period: str,
) -> Dict:
    """
    Evaluate all enabled rules for a store.
    Respects cooldown_minutes to prevent duplicate alerts.
    """
    rules_res = await db.execute(text("""
        SELECT id, metric, threshold_type, threshold_value, severity, cooldown_minutes
        FROM financial_alert_rules
        WHERE store_id = :sid AND enabled = TRUE
    """), {"sid": store_id})
    rules = rules_res.fetchall()

    now               = datetime.now(timezone.utc)
    triggered_count   = 0
    cooldown_skipped  = 0

    for rule in rules:
        rule_id, metric, ttype, tval, severity, cooldown_min = rule
        tval = _safe_float(tval)

        current_value = await _get_metric_value(db, store_id, period, metric)
        if current_value is None:
            continue

        if not _check_threshold(current_value, ttype, tval):
            continue

        # Cooldown check — skip if a recent open/acknowledged event exists
        cooldown_cutoff = now - timedelta(minutes=int(cooldown_min))
        cooldown_res = await db.execute(text("""
            SELECT id FROM financial_alert_events
            WHERE rule_id = :rid
              AND status IN ('open', 'acknowledged')
              AND triggered_at >= :cutoff
            LIMIT 1
        """), {"rid": rule_id, "cutoff": cooldown_cutoff})
        if cooldown_res.fetchone():
            cooldown_skipped += 1
            continue

        msg = _format_alert_message(metric, current_value, ttype, tval)
        await db.execute(text("""
            INSERT INTO financial_alert_events
                (id, rule_id, store_id, metric, current_value, threshold_value,
                 severity, message, status, period, triggered_at)
            VALUES
                (:id, :rid, :sid, :metric, :cur, :tval,
                 :sev, :msg, 'open', :period, :now)
        """), {
            "id":     str(uuid.uuid4()),
            "rid":    rule_id,
            "sid":    store_id,
            "metric": metric,
            "cur":    current_value,
            "tval":   tval,
            "sev":    severity,
            "msg":    msg,
            "period": period,
            "now":    now,
        })
        triggered_count += 1

    if triggered_count > 0:
        await db.commit()

    return {
        "store_id":         store_id,
        "period":           period,
        "rules_evaluated":  len(rules),
        "alerts_triggered": triggered_count,
        "cooldown_skipped": cooldown_skipped,
    }


# ── Alert event queries & FSM ─────────────────────────────────────────────────

async def get_alert_events(
    db: AsyncSession,
    store_id: str,
    status_filter: Optional[str] = None,
    limit: int = 50,
) -> List[Dict]:
    keys = ["id", "rule_id", "store_id", "metric", "current_value", "threshold_value",
            "severity", "message", "status", "period",
            "triggered_at", "acknowledged_at", "resolved_at"]
    if status_filter:
        res = await db.execute(text("""
            SELECT id, rule_id, store_id, metric, current_value, threshold_value,
                   severity, message, status, period,
                   triggered_at, acknowledged_at, resolved_at
            FROM financial_alert_events
            WHERE store_id = :sid AND status = :status
            ORDER BY triggered_at DESC LIMIT :lim
        """), {"sid": store_id, "status": status_filter, "lim": limit})
    else:
        res = await db.execute(text("""
            SELECT id, rule_id, store_id, metric, current_value, threshold_value,
                   severity, message, status, period,
                   triggered_at, acknowledged_at, resolved_at
            FROM financial_alert_events
            WHERE store_id = :sid
            ORDER BY triggered_at DESC LIMIT :lim
        """), {"sid": store_id, "lim": limit})

    return [dict(zip(keys, r)) for r in res.fetchall()]


async def transition_alert_status(
    db: AsyncSession, alert_id: str, new_status: str,
) -> Dict:
    res = await db.execute(text("""
        SELECT id, status FROM financial_alert_events WHERE id = :aid
    """), {"aid": alert_id})
    row = res.fetchone()
    if not row:
        return {"error": "Alert not found"}

    current = row[1]
    if new_status not in VALID_ALERT_TRANSITIONS.get(current, set()):
        return {"error": f"Cannot transition from '{current}' to '{new_status}'"}

    now = datetime.now(timezone.utc)
    if new_status == "acknowledged":
        await db.execute(text("""
            UPDATE financial_alert_events
            SET status = :new_status, acknowledged_at = :now
            WHERE id = :aid
        """), {"new_status": new_status, "now": now, "aid": alert_id})
    elif new_status == "resolved":
        await db.execute(text("""
            UPDATE financial_alert_events
            SET status = :new_status, resolved_at = :now
            WHERE id = :aid
        """), {"new_status": new_status, "now": now, "aid": alert_id})
    else:
        await db.execute(text("""
            UPDATE financial_alert_events SET status = :new_status WHERE id = :aid
        """), {"new_status": new_status, "aid": alert_id})

    await db.commit()
    return {"alert_id": alert_id, "old_status": current, "new_status": new_status}
