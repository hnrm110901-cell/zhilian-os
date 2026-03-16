"""菜品成本预警引擎 — Phase 6 Month 3

监控每道菜的食材成本率/毛利率/BCG象限环比变化，自动触发告警并量化¥损失。
关闭 "发现问题 → 量化影响 → 建议优化" 的完整闭环。

告警类型:
  fcr_spike     — 食材成本率单月上涨 ≥ 3 个百分点
  margin_drop   — 毛利率单月下跌 ≥ 5 个百分点
  bcg_downgrade — BCG 象限排名下降（人气或盈利恶化）
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ── 常量 ──────────────────────────────────────────────────────────────────────
ALERT_TYPES = ["fcr_spike", "margin_drop", "bcg_downgrade"]

ALERT_LABELS: dict[str, str] = {
    "fcr_spike": "成本率飙升",
    "margin_drop": "毛利率下滑",
    "bcg_downgrade": "BCG象限下降",
}

SEVERITIES = ["critical", "warning", "info"]

# FCR spike 阈值（百分点，绝对值）
FCR_SPIKE_INFO = 3.0
FCR_SPIKE_WARNING = 5.0
FCR_SPIKE_CRITICAL = 10.0

# Margin drop 阈值（百分点，绝对值）
MARGIN_DROP_INFO = 5.0
MARGIN_DROP_WARNING = 10.0
MARGIN_DROP_CRITICAL = 15.0

# BCG 象限排名（越高越好）
BCG_RANK: dict[str, int] = {
    "star": 4,
    "cash_cow": 3,
    "question_mark": 2,
    "dog": 1,
}


# ── 纯函数 ────────────────────────────────────────────────────────────────────


def compute_mom_change(current: float, previous: float) -> float:
    """环比变化率 (%)。previous=0 时返回 0.0。"""
    if previous == 0.0:
        return 0.0
    return round((current - previous) / abs(previous) * 100, 2)


def classify_fcr_severity(change_pp: float) -> str:
    """根据食材成本率上涨幅度（百分点）判断严重度。"""
    if change_pp >= FCR_SPIKE_CRITICAL:
        return "critical"
    if change_pp >= FCR_SPIKE_WARNING:
        return "warning"
    return "info"


def classify_margin_severity(change_pp: float) -> str:
    """根据毛利率下跌幅度（百分点）判断严重度。"""
    if change_pp >= MARGIN_DROP_CRITICAL:
        return "critical"
    if change_pp >= MARGIN_DROP_WARNING:
        return "warning"
    return "info"


def classify_bcg_severity(rank_drop: int) -> str:
    """根据 BCG 象限排名下降幅度判断严重度。"""
    if rank_drop >= 3:  # star → dog
        return "critical"
    if rank_drop >= 2:  # star → question_mark / cash_cow → dog
        return "warning"
    return "info"  # 下降 1 级


def detect_bcg_downgrade(current_bcg: str, prev_bcg: str) -> bool:
    """当前 BCG 排名严格低于上期 → 发生下降。"""
    return BCG_RANK.get(current_bcg, 0) < BCG_RANK.get(prev_bcg, 0)


def compute_yuan_impact(revenue_yuan: float, change_pp: float) -> float:
    """百分点变化带来的¥影响估算。

    fcr_spike:     额外食材支出 = change_pp/100 × revenue
    margin_drop:   减少毛利额  = change_pp/100 × revenue
    bcg_downgrade: 同 margin_drop 逻辑（传 gpm drop 的绝对值）
    """
    return round(abs(change_pp) / 100.0 * revenue_yuan, 2)


def generate_alert_message(
    alert_type: str,
    dish_name: str,
    current_value: float,
    prev_value: float,
    change_pp: float,
    yuan_impact: float,
) -> str:
    """生成不超过 150 字的告警描述。"""
    msg_map = {
        "fcr_spike": (
            f"{dish_name}食材成本率从{prev_value:.1f}%上涨至{current_value:.1f}%，"
            f"上升{change_pp:.1f}pp，额外食材支出估算¥{yuan_impact:.0f}"
        ),
        "margin_drop": (
            f"{dish_name}毛利率从{prev_value:.1f}%下滑至{current_value:.1f}%，"
            f"下降{change_pp:.1f}pp，减少毛利估算¥{yuan_impact:.0f}"
        ),
        "bcg_downgrade": (
            f"{dish_name}BCG象限从{prev_value:.0f}级下降至{current_value:.0f}级，"
            f"人气或盈利恶化，影响利润估算¥{yuan_impact:.0f}"
        ),
    }
    return msg_map.get(alert_type, f"{dish_name}成本预警")[:150]


def build_dish_alerts(
    store_id: str,
    period: str,
    current: dict,
    prev: Optional[dict],
) -> list[dict]:
    """比对当期与上期菜品数据，返回触发的告警列表。

    若 prev 为 None（新菜品无历史数据），返回空列表。
    """
    if not prev:
        return []

    dish_id = current["dish_id"]
    dish_name = current["dish_name"]
    category = current.get("category")
    curr_bcg = current.get("bcg_quadrant") or "dog"
    prev_bcg = prev.get("bcg_quadrant") or "dog"
    curr_fcr = float(current.get("food_cost_rate") or 0.0)
    prev_fcr = float(prev.get("food_cost_rate") or 0.0)
    curr_gpm = float(current.get("gross_profit_margin") or 0.0)
    prev_gpm = float(prev.get("gross_profit_margin") or 0.0)
    revenue = float(current.get("revenue_yuan") or 0.0)

    def _make(
        alert_type: str, severity: str, current_val: float, prev_val: float, change_pp: float, yuan_impact: float
    ) -> dict:
        return {
            "store_id": store_id,
            "period": period,
            "dish_id": dish_id,
            "dish_name": dish_name,
            "category": category,
            "bcg_quadrant": curr_bcg,
            "prev_bcg_quadrant": prev_bcg,
            "alert_type": alert_type,
            "severity": severity,
            "current_value": round(current_val, 2),
            "prev_value": round(prev_val, 2),
            "change_pp": round(change_pp, 2),
            "yuan_impact_yuan": yuan_impact,
            "message": generate_alert_message(
                alert_type,
                dish_name,
                current_val,
                prev_val,
                change_pp,
                yuan_impact,
            ),
        }

    alerts: list[dict] = []

    # 1. FCR spike（食材成本率上涨）
    fcr_change = curr_fcr - prev_fcr
    if fcr_change >= FCR_SPIKE_INFO:
        yuan_imp = compute_yuan_impact(revenue, fcr_change)
        alerts.append(
            _make(
                "fcr_spike",
                classify_fcr_severity(fcr_change),
                curr_fcr,
                prev_fcr,
                fcr_change,
                yuan_imp,
            )
        )

    # 2. Margin drop（毛利率下跌）
    gpm_drop = prev_gpm - curr_gpm  # 正值 = 下跌
    if gpm_drop >= MARGIN_DROP_INFO:
        yuan_imp = compute_yuan_impact(revenue, gpm_drop)
        alerts.append(
            _make(
                "margin_drop",
                classify_margin_severity(gpm_drop),
                curr_gpm,
                prev_gpm,
                gpm_drop,
                yuan_imp,
            )
        )

    # 3. BCG downgrade（象限排名下降）
    if detect_bcg_downgrade(curr_bcg, prev_bcg):
        rank_drop = BCG_RANK.get(prev_bcg, 0) - BCG_RANK.get(curr_bcg, 0)
        severity = classify_bcg_severity(rank_drop)
        gpm_delta = max(0.0, prev_gpm - curr_gpm)
        yuan_imp = compute_yuan_impact(revenue, gpm_delta) if gpm_delta > 0 else 0.0
        alerts.append(
            _make(
                "bcg_downgrade",
                severity,
                float(BCG_RANK.get(curr_bcg, 0)),
                float(BCG_RANK.get(prev_bcg, 0)),
                float(rank_drop),
                yuan_imp,
            )
        )

    return alerts


def summarize_alerts(alerts: list[dict]) -> dict:
    """聚合告警列表：按严重度计数 + 总¥影响。"""
    counts = {"critical": 0, "warning": 0, "info": 0}
    type_counts = {t: 0 for t in ALERT_TYPES}
    total_impact = 0.0
    for a in alerts:
        sev = a.get("severity", "info")
        if sev in counts:
            counts[sev] += 1
        at = a.get("alert_type", "")
        if at in type_counts:
            type_counts[at] += 1
        total_impact += float(a.get("yuan_impact_yuan") or 0.0)
    return {
        "total_count": len(alerts),
        "by_severity": counts,
        "by_type": type_counts,
        "total_yuan_impact": round(total_impact, 2),
        "critical_count": counts["critical"],
        "warning_count": counts["warning"],
    }


# ── DB 辅助 ───────────────────────────────────────────────────────────────────


def _to_float(val) -> float:
    if val is None:
        return 0.0
    try:
        return float(Decimal(str(val)))
    except Exception:
        return 0.0


def _prev_period(period: str) -> str:
    """计算上一个自然月的 YYYY-MM 字符串。"""
    year, month = int(period[:4]), int(period[5:7])
    if month == 1:
        return f"{year - 1:04d}-12"
    return f"{year:04d}-{month - 1:02d}"


def _start_period(period: str, n: int) -> str:
    """往前推 n 个月。"""
    year, month = int(period[:4]), int(period[5:7])
    total = year * 12 + (month - 1) - (n - 1)
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


# ── DB 函数 ───────────────────────────────────────────────────────────────────

_DISH_PROFIT_KEYS = [
    "dish_id",
    "dish_name",
    "category",
    "bcg_quadrant",
    "order_count",
    "avg_selling_price",
    "revenue_yuan",
    "food_cost_yuan",
    "food_cost_rate",
    "gross_profit_yuan",
    "gross_profit_margin",
]


async def _fetch_period_records(db: AsyncSession, store_id: str, period: str) -> list[dict]:
    sql = text("""
        SELECT dish_id, dish_name, category, bcg_quadrant,
               order_count, avg_selling_price,
               revenue_yuan, food_cost_yuan, food_cost_rate,
               gross_profit_yuan, gross_profit_margin
        FROM dish_profitability_records
        WHERE store_id = :sid AND period = :period
    """)
    result = await db.execute(sql, {"sid": store_id, "period": period})
    rows = result.fetchall()
    out = []
    for row in rows:
        d = dict(zip(_DISH_PROFIT_KEYS, row))
        for k in ("food_cost_rate", "gross_profit_margin", "revenue_yuan", "gross_profit_yuan", "avg_selling_price"):
            d[k] = _to_float(d.get(k))
        out.append(d)
    return out


async def _upsert_alert(db: AsyncSession, a: dict) -> None:
    sql = text("""
        INSERT INTO dish_cost_alerts (
            store_id, period, dish_id, dish_name, category,
            bcg_quadrant, prev_bcg_quadrant,
            alert_type, severity,
            current_value, prev_value, change_pp, yuan_impact_yuan, message,
            status, computed_at, updated_at
        ) VALUES (
            :sid, :period, :dish_id, :dish_name, :category,
            :bcg, :prev_bcg,
            :alert_type, :severity,
            :current_val, :prev_val, :change_pp, :yuan_impact, :message,
            'open', NOW(), NOW()
        )
        ON CONFLICT (store_id, period, dish_id, alert_type) DO UPDATE SET
            severity          = EXCLUDED.severity,
            current_value     = EXCLUDED.current_value,
            prev_value        = EXCLUDED.prev_value,
            change_pp         = EXCLUDED.change_pp,
            yuan_impact_yuan  = EXCLUDED.yuan_impact_yuan,
            message           = EXCLUDED.message,
            bcg_quadrant      = EXCLUDED.bcg_quadrant,
            prev_bcg_quadrant = EXCLUDED.prev_bcg_quadrant,
            updated_at        = NOW()
        WHERE dish_cost_alerts.status = 'open'
    """)
    await db.execute(
        sql,
        {
            "sid": a["store_id"],
            "period": a["period"],
            "dish_id": a["dish_id"],
            "dish_name": a["dish_name"],
            "category": a.get("category"),
            "bcg": a.get("bcg_quadrant"),
            "prev_bcg": a.get("prev_bcg_quadrant"),
            "alert_type": a["alert_type"],
            "severity": a["severity"],
            "current_val": a["current_value"],
            "prev_val": a["prev_value"],
            "change_pp": a["change_pp"],
            "yuan_impact": a["yuan_impact_yuan"],
            "message": a.get("message"),
        },
    )


async def generate_dish_cost_alerts(db: AsyncSession, store_id: str, period: str) -> dict:
    """比对当期与上期 BCG 数据，生成并持久化成本预警。幂等操作。"""
    prev = _prev_period(period)
    current_records = await _fetch_period_records(db, store_id, period)
    prev_records = await _fetch_period_records(db, store_id, prev)

    if not current_records:
        return {
            "store_id": store_id,
            "period": period,
            "dish_count": 0,
            "alert_count": 0,
        }

    prev_by_dish = {r["dish_id"]: r for r in prev_records}

    total_alerts = 0
    for dish in current_records:
        prev_dish = prev_by_dish.get(dish["dish_id"])
        alerts = build_dish_alerts(store_id, period, dish, prev_dish)
        for a in alerts:
            await _upsert_alert(db, a)
            total_alerts += 1

    await db.commit()
    return {
        "store_id": store_id,
        "period": period,
        "prev_period": prev,
        "dish_count": len(current_records),
        "alert_count": total_alerts,
    }


_ALERT_SELECT = """
    SELECT
        id, store_id, period, dish_id, dish_name, category,
        bcg_quadrant, prev_bcg_quadrant,
        alert_type, severity,
        current_value, prev_value, change_pp, yuan_impact_yuan,
        message, status, computed_at
    FROM dish_cost_alerts
"""

_ALERT_KEYS = [
    "id",
    "store_id",
    "period",
    "dish_id",
    "dish_name",
    "category",
    "bcg_quadrant",
    "prev_bcg_quadrant",
    "alert_type",
    "severity",
    "current_value",
    "prev_value",
    "change_pp",
    "yuan_impact_yuan",
    "message",
    "status",
    "computed_at",
]

_ALERT_FLOAT_KEYS = {"current_value", "prev_value", "change_pp", "yuan_impact_yuan"}


def _parse_alert_rows(rows) -> list[dict]:
    out = []
    for row in rows:
        d = dict(zip(_ALERT_KEYS, row))
        d["alert_label"] = ALERT_LABELS.get(d["alert_type"], d["alert_type"])
        for k in _ALERT_FLOAT_KEYS:
            d[k] = _to_float(d.get(k))
        d["computed_at"] = d["computed_at"].isoformat() if d.get("computed_at") else None
        out.append(d)
    return out


async def get_dish_cost_alerts(
    db: AsyncSession,
    store_id: str,
    period: str,
    severity: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    # L011: 4 branches for 2 optional filters
    if severity is not None and status is not None:
        sql = text(
            _ALERT_SELECT + "WHERE store_id=:sid AND period=:period "
            "AND severity=:sev AND status=:st "
            "ORDER BY severity DESC, yuan_impact_yuan DESC LIMIT :lim"
        )
        params = {"sid": store_id, "period": period, "sev": severity, "st": status, "lim": limit}
    elif severity is not None:
        sql = text(
            _ALERT_SELECT + "WHERE store_id=:sid AND period=:period AND severity=:sev "
            "ORDER BY yuan_impact_yuan DESC LIMIT :lim"
        )
        params = {"sid": store_id, "period": period, "sev": severity, "lim": limit}
    elif status is not None:
        sql = text(
            _ALERT_SELECT + "WHERE store_id=:sid AND period=:period AND status=:st "
            "ORDER BY severity DESC, yuan_impact_yuan DESC LIMIT :lim"
        )
        params = {"sid": store_id, "period": period, "st": status, "lim": limit}
    else:
        sql = text(
            _ALERT_SELECT + "WHERE store_id=:sid AND period=:period "
            "ORDER BY severity DESC, yuan_impact_yuan DESC LIMIT :lim"
        )
        params = {"sid": store_id, "period": period, "lim": limit}

    result = await db.execute(sql, params)
    return _parse_alert_rows(result.fetchall())


async def get_alert_summary(db: AsyncSession, store_id: str, period: str) -> dict:
    sql = text("""
        SELECT alert_type, severity, status,
               COUNT(*) AS cnt,
               COALESCE(SUM(yuan_impact_yuan), 0) AS total_impact
        FROM dish_cost_alerts
        WHERE store_id = :sid AND period = :period
        GROUP BY alert_type, severity, status
    """)
    result = await db.execute(sql, {"sid": store_id, "period": period})
    rows = result.fetchall()

    by_type: dict[str, dict] = {t: {"count": 0, "total_impact": 0.0, "open": 0, "resolved": 0} for t in ALERT_TYPES}
    by_sev = {"critical": 0, "warning": 0, "info": 0}
    total_open_impact = 0.0

    for row in rows:
        at, sev, st, cnt, impact = (row[0], row[1], row[2], int(row[3]), _to_float(row[4]))
        if at in by_type:
            by_type[at]["count"] += cnt
            by_type[at]["total_impact"] += impact
            if st == "open":
                by_type[at]["open"] += cnt
                total_open_impact += impact
            elif st == "resolved":
                by_type[at]["resolved"] += cnt
        if sev in by_sev:
            by_sev[sev] += cnt

    return {
        "by_type": [
            {
                "alert_type": at,
                "label": ALERT_LABELS[at],
                **v,
                "total_impact": round(v["total_impact"], 2),
            }
            for at, v in by_type.items()
        ],
        "by_severity": by_sev,
        "total_open_yuan_impact": round(total_open_impact, 2),
        "open_count": sum(v["open"] for v in by_type.values()),
        "resolved_count": sum(v["resolved"] for v in by_type.values()),
        "critical_count": by_sev["critical"],
    }


async def resolve_alert(db: AsyncSession, alert_id: int) -> dict:
    sql = text("""
        UPDATE dish_cost_alerts
        SET status = 'resolved', resolved_at = NOW(), updated_at = NOW()
        WHERE id = :aid AND status = 'open'
        RETURNING id
    """)
    result = await db.execute(sql, {"aid": alert_id})
    row = result.fetchone()
    if row:
        await db.commit()
        return {"updated": True, "alert_id": alert_id}
    return {"updated": False, "reason": "not_found_or_not_open"}


async def get_store_cost_trend(db: AsyncSession, store_id: str, period: str, periods: int = 6) -> list[dict]:
    """门店级各期平均食材成本率/毛利率趋势（聚合自 dish_profitability_records）。"""
    start = _start_period(period, periods)
    sql = text("""
        SELECT
            period,
            COUNT(*)                              AS dish_count,
            ROUND(AVG(food_cost_rate)::numeric, 2) AS avg_fcr,
            ROUND(AVG(gross_profit_margin)::numeric, 2) AS avg_gpm,
            COALESCE(SUM(revenue_yuan), 0)        AS total_revenue,
            COALESCE(SUM(gross_profit_yuan), 0)   AS total_profit,
            COALESCE(SUM(order_count), 0)         AS total_orders
        FROM dish_profitability_records
        WHERE store_id = :sid
          AND period >= :start AND period <= :end
        GROUP BY period
        ORDER BY period ASC
    """)
    result = await db.execute(sql, {"sid": store_id, "start": start, "end": period})
    rows = result.fetchall()
    keys = ["period", "dish_count", "avg_fcr", "avg_gpm", "total_revenue", "total_profit", "total_orders"]
    out = []
    for row in rows:
        d = dict(zip(keys, row))
        for k in ("avg_fcr", "avg_gpm", "total_revenue", "total_profit"):
            d[k] = _to_float(d.get(k))
        d["dish_count"] = int(d.get("dish_count") or 0)
        d["total_orders"] = int(d.get("total_orders") or 0)
        out.append(d)
    return out


async def get_dish_alert_history(db: AsyncSession, store_id: str, dish_id: str, periods: int = 6) -> list[dict]:
    """某道菜近 N 期的历史预警记录。"""
    sql = text("""
        SELECT period, alert_type, severity,
               current_value, prev_value, change_pp, yuan_impact_yuan,
               message, status
        FROM dish_cost_alerts
        WHERE store_id = :sid AND dish_id = :did
        ORDER BY period DESC, severity DESC
        LIMIT :lim
    """)
    result = await db.execute(sql, {"sid": store_id, "did": dish_id, "lim": periods * 3})
    return [
        {
            "period": row[0],
            "alert_type": row[1],
            "alert_label": ALERT_LABELS.get(row[1], row[1]),
            "severity": row[2],
            "current_value": _to_float(row[3]),
            "prev_value": _to_float(row[4]),
            "change_pp": _to_float(row[5]),
            "yuan_impact_yuan": _to_float(row[6]),
            "message": row[7],
            "status": row[8],
        }
        for row in result.fetchall()
    ]
