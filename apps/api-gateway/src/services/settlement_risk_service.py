"""
结算风控引擎 — Phase 5 Month 3

职责：
1. 接收平台结算记录，与 business_events 预期收款对比
2. 检测异常：结算偏差 / 异常退款率 / 逾期未结算 / 平台抽佣超标
3. 自动生成 risk_tasks（高风险）和 agent_action_log（L1/L2）
4. 支持人工核销（verified）

风控规则：
  deviation_risk: 净结算 vs 预期偏差 > 5% → medium, > 10% → high, > 20% → critical
  refund_risk:    退款/毛收入 > 8% → medium, > 15% → high
  commission_risk: 抽佣率 > 行业均值(22%) + 5% → high
  overdue_risk:   结算周期结束后 >7天未到账 → medium, >15天 → high
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

# ── 风控阈值 ──────────────────────────────────────────────────────────────────
DEVIATION_THRESHOLDS = {"critical": 0.20, "high": 0.10, "medium": 0.05}
REFUND_RATE_THRESHOLDS = {"high": 0.15, "medium": 0.08}
COMMISSION_RATE_BENCHMARK = 0.22  # 外卖平台行业均值抽佣率
COMMISSION_RATE_WARN = COMMISSION_RATE_BENCHMARK + 0.05  # 超过 27% 告警
OVERDUE_DAYS_HIGH = 15
OVERDUE_DAYS_MEDIUM = 7

PLATFORM_LABELS = {
    "meituan": "美团外卖",
    "eleme": "饿了么",
    "wechat_pay": "微信支付",
    "alipay": "支付宝",
    "unionpay": "银联",
    "cash": "现金",
    "other": "其他",
}

ITEM_TYPE_LABELS = {
    "sale_income": "销售收入",
    "commission": "平台佣金",
    "refund_deduction": "退款扣款",
    "marketing_subsidy": "营销补贴",
    "packaging_fee": "包装费",
    "tech_fee": "技术服务费",
    "adjustment": "调账",
    "other": "其他",
}


def _safe_float(v: Any) -> float:
    if v is None:
        return 0.0
    if isinstance(v, Decimal):
        return float(v)
    return float(v)


def _assess_deviation_risk(deviation_pct: float) -> str:
    abs_pct = abs(deviation_pct)
    if abs_pct >= DEVIATION_THRESHOLDS["critical"]:
        return "critical"
    if abs_pct >= DEVIATION_THRESHOLDS["high"]:
        return "high"
    if abs_pct >= DEVIATION_THRESHOLDS["medium"]:
        return "medium"
    return "low"


def assess_settlement_risk(
    gross_yuan: float,
    commission_yuan: float,
    refund_yuan: float,
    net_yuan: float,
    expected_yuan: Optional[float],
    settle_date: date,
    cycle_end: Optional[date],
) -> Dict[str, Any]:
    """
    综合评估单条结算记录的风险等级。
    返回: {risk_level, deviation_yuan, deviation_pct, findings}
    """
    today = date.today()
    findings: List[str] = []
    risk_levels = ["low"]

    # 1. 偏差风险
    deviation_yuan = 0.0
    deviation_pct = 0.0
    if expected_yuan is not None and expected_yuan > 0:
        deviation_yuan = net_yuan - expected_yuan
        deviation_pct = deviation_yuan / expected_yuan * 100
        dev_risk = _assess_deviation_risk(deviation_pct / 100)
        if dev_risk != "low":
            risk_levels.append(dev_risk)
            findings.append(f"结算偏差 {deviation_pct:.1f}%（预期¥{expected_yuan:.2f} 实到¥{net_yuan:.2f}）")

    # 2. 退款率风险
    if gross_yuan > 0:
        refund_rate = refund_yuan / gross_yuan
        if refund_rate >= REFUND_RATE_THRESHOLDS["high"]:
            risk_levels.append("high")
            findings.append(f"退款率 {refund_rate*100:.1f}% 超过 {REFUND_RATE_THRESHOLDS['high']*100:.0f}% 警戒线")
        elif refund_rate >= REFUND_RATE_THRESHOLDS["medium"]:
            risk_levels.append("medium")
            findings.append(f"退款率 {refund_rate*100:.1f}% 偏高")

    # 3. 抽佣率风险
    if gross_yuan > 0 and commission_yuan > 0:
        commission_rate = commission_yuan / gross_yuan
        if commission_rate >= COMMISSION_RATE_WARN:
            risk_levels.append("high")
            findings.append(
                f"平台抽佣率 {commission_rate*100:.1f}% 超出行业均值" f"（{COMMISSION_RATE_BENCHMARK*100:.0f}%+5%）"
            )

    # 4. 逾期风险（结算周期结束后N天仍未到账）
    if cycle_end and net_yuan <= 0:
        overdue_days = (today - cycle_end).days
        if overdue_days >= OVERDUE_DAYS_HIGH:
            risk_levels.append("high")
            findings.append(f"结算周期结束 {overdue_days} 天，资金仍未到账")
        elif overdue_days >= OVERDUE_DAYS_MEDIUM:
            risk_levels.append("medium")
            findings.append(f"结算周期结束 {overdue_days} 天，尚未确认到账")

    # 取最高风险级别
    priority = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    final_risk = max(risk_levels, key=lambda r: priority.get(r, 0))

    return {
        "risk_level": final_risk,
        "deviation_yuan": round(deviation_yuan, 2),
        "deviation_pct": round(deviation_pct, 2),
        "findings": findings,
    }


async def create_settlement_record(
    db: AsyncSession,
    store_id: str,
    platform: str,
    period: str,
    settle_date: str,
    gross_yuan: float,
    commission_yuan: float,
    refund_yuan: float,
    adjustment_yuan: float = 0.0,
    settlement_no: Optional[str] = None,
    cycle_start: Optional[str] = None,
    cycle_end: Optional[str] = None,
    brand_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    录入平台结算记录，自动计算净额、评估风险、生成 risk_task（高风险时）。
    """
    net_yuan = gross_yuan - commission_yuan - refund_yuan + adjustment_yuan

    # 查预期收款（来自当期 collection/sale 类事件）
    expected_row = (
        await db.execute(
            text("""
        SELECT COALESCE(SUM(amount_yuan), 0) AS expected
        FROM business_events
        WHERE store_id = :sid AND period = :period
          AND event_type IN ('sale', 'collection')
          AND source_system = :platform
    """),
            {"sid": store_id, "period": period, "platform": platform},
        )
    ).fetchone()
    expected_yuan = _safe_float(expected_row.expected) if expected_row else None
    if expected_yuan == 0.0:
        expected_yuan = None  # 无历史数据时不评估偏差

    d_settle = date.fromisoformat(settle_date)
    d_cycle_end = date.fromisoformat(cycle_end) if cycle_end else None

    risk_result = assess_settlement_risk(
        gross_yuan=gross_yuan,
        commission_yuan=commission_yuan,
        refund_yuan=refund_yuan,
        net_yuan=net_yuan,
        expected_yuan=expected_yuan,
        settle_date=d_settle,
        cycle_end=d_cycle_end,
    )

    rid = str(uuid.uuid4())
    await db.execute(
        text("""
        INSERT INTO settlement_records
          (id, store_id, brand_id, platform, period, settlement_no,
           settle_date, cycle_start, cycle_end,
           gross_yuan, commission_yuan, refund_yuan, adjustment_yuan, net_yuan,
           expected_yuan, deviation_yuan, deviation_pct,
           risk_level, status, created_at, updated_at)
        VALUES
          (:id, :sid, :bid, :plat, :period, :sno,
           :sd, :cs, :ce,
           :gross, :comm, :ref, :adj, :net,
           :exp, :dev, :devpct,
           :risk, 'pending', NOW(), NOW())
    """),
        {
            "id": rid,
            "sid": store_id,
            "bid": brand_id,
            "plat": platform,
            "period": period,
            "sno": settlement_no,
            "sd": settle_date,
            "cs": cycle_start,
            "ce": cycle_end,
            "gross": gross_yuan,
            "comm": commission_yuan,
            "ref": refund_yuan,
            "adj": adjustment_yuan,
            "net": net_yuan,
            "exp": expected_yuan,
            "dev": risk_result["deviation_yuan"],
            "devpct": risk_result["deviation_pct"],
            "risk": risk_result["risk_level"],
        },
    )

    # 高风险 → 生成 risk_task
    if risk_result["risk_level"] in ("high", "critical"):
        await _create_risk_task(
            db,
            store_id,
            brand_id,
            rid,
            risk_type="invoice_mismatch" if risk_result["deviation_yuan"] != 0 else "unusual_refund",
            severity=risk_result["risk_level"],
            title=f"{PLATFORM_LABELS.get(platform, platform)} 结算风险 ({period})",
            description=" | ".join(risk_result["findings"]),
            amount_yuan=abs(risk_result["deviation_yuan"]) or net_yuan,
        )
        await _log_agent_action(
            db,
            store_id,
            period,
            level="L2" if risk_result["risk_level"] == "critical" else "L1",
            agent="SettlementAgent",
            trigger="settlement_risk",
            title=f"{PLATFORM_LABELS.get(platform, platform)} 结算异常：{risk_result['findings'][0]}",
            description="; ".join(risk_result["findings"]),
            impact=-abs(risk_result["deviation_yuan"]),
            ref_id=rid,
        )

    await db.commit()
    logger.info("settlement_created", store_id=store_id, platform=platform, risk=risk_result["risk_level"], net=net_yuan)

    return {
        "id": rid,
        "store_id": store_id,
        "platform": platform,
        "period": period,
        "net_yuan": round(net_yuan, 2),
        "risk_level": risk_result["risk_level"],
        "deviation_yuan": risk_result["deviation_yuan"],
        "deviation_pct": risk_result["deviation_pct"],
        "findings": risk_result["findings"],
    }


async def run_overdue_scan(
    db: AsyncSession,
    store_id: str,
) -> Dict[str, Any]:
    """
    扫描当前门店所有未核销结算记录，
    检测逾期（cycle_end 超过 N 天仍 pending）并更新风险等级。
    """
    today = date.today().isoformat()

    # 逾期高风险（>15天）
    high_rows = (
        await db.execute(
            text("""
        SELECT id, platform, period, cycle_end, net_yuan
        FROM settlement_records
        WHERE store_id = :sid AND status = 'pending'
          AND cycle_end IS NOT NULL
          AND cycle_end < (:today::date - :days * INTERVAL '1 day')
    """),
            {"sid": store_id, "today": today, "days": OVERDUE_DAYS_HIGH},
        )
    ).fetchall()

    # 逾期中风险（>7天，未在高风险列表内）
    medium_rows = (
        await db.execute(
            text("""
        SELECT id, platform, period, cycle_end, net_yuan
        FROM settlement_records
        WHERE store_id = :sid AND status = 'pending'
          AND cycle_end IS NOT NULL
          AND cycle_end < (:today::date - :days * INTERVAL '1 day')
          AND risk_level NOT IN ('high', 'critical')
    """),
            {"sid": store_id, "today": today, "days": OVERDUE_DAYS_MEDIUM},
        )
    ).fetchall()

    updated_high = 0
    updated_medium = 0

    for r in high_rows:
        await db.execute(
            text("""
            UPDATE settlement_records SET risk_level = 'high', updated_at = NOW()
            WHERE id = :id AND risk_level NOT IN ('critical')
        """),
            {"id": r.id},
        )
        updated_high += 1

    for r in medium_rows:
        await db.execute(
            text("""
            UPDATE settlement_records SET risk_level = 'medium', updated_at = NOW()
            WHERE id = :id AND risk_level = 'low'
        """),
            {"id": r.id},
        )
        updated_medium += 1

    if updated_high > 0:
        await _log_agent_action(
            db,
            store_id,
            period=date.today().strftime("%Y-%m"),
            level="L2",
            agent="SettlementAgent",
            trigger="overdue_payment",
            title=f"发现 {updated_high} 笔结算逾期超 {OVERDUE_DAYS_HIGH} 天未到账",
            description=f"涉及平台：{', '.join(set(PLATFORM_LABELS.get(r.platform, r.platform) for r in high_rows))}",
            impact=-sum(_safe_float(r.net_yuan) for r in high_rows),
        )

    await db.commit()
    return {
        "store_id": store_id,
        "scanned_at": today,
        "high_updated": updated_high,
        "medium_updated": updated_medium,
    }


async def _create_risk_task(
    db: AsyncSession,
    store_id: str,
    brand_id: Optional[str],
    settlement_id: str,
    risk_type: str,
    severity: str,
    title: str,
    description: str,
    amount_yuan: float,
) -> None:
    tid = str(uuid.uuid4())
    await db.execute(
        text("""
        INSERT INTO risk_tasks
          (id, store_id, brand_id, risk_type, severity, title, description,
           related_event_ids, amount_yuan, status, created_at, updated_at)
        VALUES
          (:id, :sid, :bid, :rtype, :sev, :title, :desc,
           :refs, :amt, 'open', NOW(), NOW())
    """),
        {
            "id": tid,
            "sid": store_id,
            "bid": brand_id,
            "rtype": risk_type,
            "sev": severity,
            "title": title,
            "desc": description,
            "refs": json.dumps([settlement_id]),
            "amt": round(amount_yuan, 2),
        },
    )


async def _log_agent_action(
    db: AsyncSession,
    store_id: str,
    period: str,
    level: str,
    agent: str,
    trigger: str,
    title: str,
    description: str,
    impact: float = 0.0,
    ref_id: Optional[str] = None,
) -> None:
    aid = str(uuid.uuid4())
    await db.execute(
        text("""
        INSERT INTO agent_action_log
          (id, store_id, action_level, agent_name, trigger_type, title, description,
           expected_impact_yuan, confidence, ref_type, ref_id,
           status, period, created_at)
        VALUES
          (:id, :sid, :level, :agent, :trigger, :title, :desc,
           :impact, 0.82, 'settlement_record', :ref_id,
           'pending', :period, NOW())
    """),
        {
            "id": aid,
            "sid": store_id,
            "level": level,
            "agent": agent,
            "trigger": trigger,
            "title": title,
            "desc": description,
            "impact": round(impact, 2),
            "ref_id": ref_id,
            "period": period,
        },
    )
