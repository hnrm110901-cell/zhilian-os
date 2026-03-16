"""
现金流预测引擎 — Phase 5 Month 2

基于过去90天经营事件的收付模式，预测未来30天每日现金流。
预测方法：移动平均 + 简单季节性修正（周内规律）

入账来源（inflow）：  sale / collection / refund（负）
出账来源（outflow）： purchase / payment / expense / settlement / tax
"""

from __future__ import annotations

import json
import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# 预测天数
FORECAST_DAYS = 30
# 历史回溯天数（用于计算移动平均）
LOOKBACK_DAYS = 90
# 周内季节性系数（0=周一，6=周日）
WEEKDAY_FACTORS = {
    0: 0.85,  # 周一：较低
    1: 0.88,
    2: 0.90,
    3: 0.95,
    4: 1.05,  # 周四：开始回升
    5: 1.25,  # 周五：高峰
    6: 1.30,  # 周日：最高（餐饮）
}

# 事件类型 → 收支分类
INFLOW_TYPES = {"sale", "collection"}
OUTFLOW_TYPES = {"purchase", "payment", "expense", "settlement"}
REFUND_TYPES = {"refund"}  # 负收入（减少入账）


def _safe_float(v: Any) -> float:
    if v is None:
        return 0.0
    if isinstance(v, Decimal):
        return float(v)
    return float(v)


def _weekday_factor(d: date) -> float:
    return WEEKDAY_FACTORS.get(d.weekday(), 1.0)


def compute_daily_avg(
    event_totals: Dict[str, float],
    lookback_days: int,
) -> Dict[str, float]:
    """
    从历史事件汇总 → 每日平均入账/出账。
    event_totals: {event_type: total_yuan_over_lookback_period}
    """
    daily_inflow = sum(event_totals.get(t, 0.0) for t in INFLOW_TYPES) / lookback_days
    daily_refund = sum(event_totals.get(t, 0.0) for t in REFUND_TYPES) / lookback_days
    daily_outflow = sum(event_totals.get(t, 0.0) for t in OUTFLOW_TYPES) / lookback_days
    return {
        "daily_inflow": round(daily_inflow - daily_refund, 2),  # 净入账
        "daily_outflow": round(daily_outflow, 2),
    }


def project_cash_flow(
    daily_avg: Dict[str, float],
    opening_balance: float,
    start_date: date,
    days: int = FORECAST_DAYS,
) -> List[Dict[str, Any]]:
    """
    从日均值 + 季节性系数生成每日预测。
    开期余额 = 上月期末余额（默认0）。
    """
    forecasts = []
    balance = opening_balance
    for i in range(days):
        d = start_date + timedelta(days=i)
        factor = _weekday_factor(d)
        inflow = round(daily_avg["daily_inflow"] * factor, 2)
        outflow = round(daily_avg["daily_outflow"] * factor, 2)
        net = round(inflow - outflow, 2)
        balance = round(balance + net, 2)

        # 置信度：越远的预测置信度越低
        confidence = max(0.5, round(0.95 - i * 0.015, 3))

        forecasts.append(
            {
                "forecast_date": d.isoformat(),
                "inflow_yuan": inflow,
                "outflow_yuan": outflow,
                "net_yuan": net,
                "balance_yuan": balance,
                "confidence": confidence,
            }
        )
    return forecasts


async def compute_cashflow_forecast(
    db: AsyncSession,
    store_id: str,
    opening_balance: float = 0.0,
    force: bool = False,
) -> Dict[str, Any]:
    """
    计算并持久化未来30天现金流预测。
    幂等：同一 store_id + generated_on，只生成一次（force=True覆盖）。
    """
    today = date.today()
    today_str = today.isoformat()

    if not force:
        # 检查当日是否已生成
        existing_count = (
            (
                await db.execute(
                    text("""
            SELECT COUNT(*) FROM cashflow_forecasts
            WHERE store_id = :sid AND generated_on = :today
        """),
                    {"sid": store_id, "today": today_str},
                )
            ).scalar()
            or 0
        )
        if existing_count > 0:
            return await _load_forecast(db, store_id, today_str)

    # ── 历史事件聚合（过去90天） ───────────────────────────────────────────
    lookback_start = (today - timedelta(days=LOOKBACK_DAYS)).isoformat()
    rows = (
        await db.execute(
            text("""
        SELECT event_type, COALESCE(SUM(amount_yuan), 0) AS total_yuan
        FROM business_events
        WHERE store_id = :sid
          AND event_date BETWEEN :start AND :today
          AND event_type IN ('sale','collection','refund','purchase','payment','expense','settlement')
        GROUP BY event_type
    """),
            {"sid": store_id, "start": lookback_start, "today": today_str},
        )
    ).fetchall()

    event_totals = {r.event_type: _safe_float(r.total_yuan) for r in rows}

    # 如果没有历史数据，用零预测
    daily_avg = compute_daily_avg(event_totals, LOOKBACK_DAYS)

    # ── 预测 ──────────────────────────────────────────────────────────────
    start_date = today + timedelta(days=1)
    forecasts = project_cash_flow(daily_avg, opening_balance, start_date)

    # ── 删除旧预测，写入新预测（force模式） ───────────────────────────────
    if force:
        await db.execute(
            text("""
            DELETE FROM cashflow_forecasts
            WHERE store_id = :sid AND generated_on = :today
        """),
            {"sid": store_id, "today": today_str},
        )

    for fc in forecasts:
        # 构建入账/出账明细
        inflow_detail = json.dumps(
            {
                "sale_est": round(
                    event_totals.get("sale", 0.0) / LOOKBACK_DAYS * _weekday_factor(date.fromisoformat(fc["forecast_date"])), 2
                ),
                "collection_est": round(
                    event_totals.get("collection", 0.0)
                    / LOOKBACK_DAYS
                    * _weekday_factor(date.fromisoformat(fc["forecast_date"])),
                    2,
                ),
            }
        )
        outflow_detail = json.dumps(
            {
                "purchase_est": round(
                    event_totals.get("purchase", 0.0)
                    / LOOKBACK_DAYS
                    * _weekday_factor(date.fromisoformat(fc["forecast_date"])),
                    2,
                ),
                "expense_est": round(
                    event_totals.get("expense", 0.0)
                    / LOOKBACK_DAYS
                    * _weekday_factor(date.fromisoformat(fc["forecast_date"])),
                    2,
                ),
                "payment_est": round(
                    event_totals.get("payment", 0.0)
                    / LOOKBACK_DAYS
                    * _weekday_factor(date.fromisoformat(fc["forecast_date"])),
                    2,
                ),
            }
        )
        fid = str(uuid.uuid4())
        await db.execute(
            text("""
            INSERT INTO cashflow_forecasts
              (id, store_id, forecast_date, generated_on, inflow_yuan, outflow_yuan,
               net_yuan, balance_yuan, confidence, method, inflow_detail, outflow_detail,
               created_at)
            VALUES
              (:id, :sid, :fd, :gen, :inf, :out, :net, :bal, :conf, 'moving_avg',
               :ind, :outd, NOW())
            ON CONFLICT (store_id, forecast_date, generated_on) DO UPDATE SET
                inflow_yuan   = EXCLUDED.inflow_yuan,
                outflow_yuan  = EXCLUDED.outflow_yuan,
                net_yuan      = EXCLUDED.net_yuan,
                balance_yuan  = EXCLUDED.balance_yuan,
                confidence    = EXCLUDED.confidence,
                inflow_detail = EXCLUDED.inflow_detail,
                outflow_detail= EXCLUDED.outflow_detail
        """),
            {
                "id": fid,
                "sid": store_id,
                "fd": fc["forecast_date"],
                "gen": today_str,
                "inf": fc["inflow_yuan"],
                "out": fc["outflow_yuan"],
                "net": fc["net_yuan"],
                "bal": fc["balance_yuan"],
                "conf": fc["confidence"],
                "ind": inflow_detail,
                "outd": outflow_detail,
            },
        )

    await db.commit()

    # 检查现金缺口：任意一天 balance < 0 → L2 Agent 提醒
    gap_days = [fc for fc in forecasts if fc["balance_yuan"] < 0]
    if gap_days:
        min_balance = min(fc["balance_yuan"] for fc in gap_days)
        await _log_cash_agent_action(
            db,
            store_id,
            level="L2",
            trigger="cash_gap",
            title=f"现金流预警：未来{FORECAST_DAYS}天内预计出现资金缺口",
            description=f"预测最低余额 ¥{min_balance:.2f}，涉及 {len(gap_days)} 天，" f"建议提前安排融资或调整付款节奏",
            expected_impact=min_balance,
        )
        await db.commit()

    logger.info("cashflow_forecasted", store_id=store_id, days=len(forecasts), gap_days=len(gap_days))

    return {
        "store_id": store_id,
        "generated_on": today_str,
        "forecast_days": len(forecasts),
        "opening_balance": opening_balance,
        "daily_avg": daily_avg,
        "forecasts": forecasts,
        "cash_gap_days": len(gap_days),
        "min_balance_yuan": min(fc["balance_yuan"] for fc in forecasts) if forecasts else 0.0,
        "max_balance_yuan": max(fc["balance_yuan"] for fc in forecasts) if forecasts else 0.0,
    }


async def _load_forecast(
    db: AsyncSession,
    store_id: str,
    generated_on: str,
) -> Dict[str, Any]:
    """从数据库加载已有预测"""
    rows = (
        await db.execute(
            text("""
        SELECT forecast_date, inflow_yuan, outflow_yuan, net_yuan, balance_yuan, confidence
        FROM cashflow_forecasts
        WHERE store_id = :sid AND generated_on = :gen
        ORDER BY forecast_date
    """),
            {"sid": store_id, "gen": generated_on},
        )
    ).fetchall()

    forecasts = [
        {
            "forecast_date": str(r.forecast_date),
            "inflow_yuan": _safe_float(r.inflow_yuan),
            "outflow_yuan": _safe_float(r.outflow_yuan),
            "net_yuan": _safe_float(r.net_yuan),
            "balance_yuan": _safe_float(r.balance_yuan),
            "confidence": _safe_float(r.confidence),
        }
        for r in rows
    ]

    gap_days = [f for f in forecasts if f["balance_yuan"] < 0]
    return {
        "store_id": store_id,
        "generated_on": generated_on,
        "forecast_days": len(forecasts),
        "forecasts": forecasts,
        "cash_gap_days": len(gap_days),
        "min_balance_yuan": min(f["balance_yuan"] for f in forecasts) if forecasts else 0.0,
        "max_balance_yuan": max(f["balance_yuan"] for f in forecasts) if forecasts else 0.0,
    }


async def _log_cash_agent_action(
    db: AsyncSession,
    store_id: str,
    level: str,
    trigger: str,
    title: str,
    description: str,
    expected_impact: float = 0.0,
) -> None:
    aid = str(uuid.uuid4())
    await db.execute(
        text("""
        INSERT INTO agent_action_log
          (id, store_id, action_level, agent_name, trigger_type, title, description,
           expected_impact_yuan, confidence, status, created_at)
        VALUES
          (:id, :sid, :level, 'CashAgent', :trigger, :title, :desc,
           :impact, 0.80, 'pending', NOW())
    """),
        {
            "id": aid,
            "sid": store_id,
            "level": level,
            "trigger": trigger,
            "title": title,
            "desc": description,
            "impact": round(expected_impact, 2),
        },
    )
