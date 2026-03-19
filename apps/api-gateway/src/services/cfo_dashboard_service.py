"""CFO工作台服务 — Phase 5 Month 6 capstone

品牌级财务综合驾驶舱，聚合 Phase 5 前5个月所有数据层：
  - 财务健康评分 (finance_health_scores)
  - 财务预警事件 (financial_alert_events)
  - 预算计划     (budget_plans + profit_attribution_results)
  - 财务洞察     (finance_insights)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# ── 常量 ─────────────────────────────────────────────────────────────────────

GRADE_THRESHOLDS = {"A": 80.0, "B": 60.0, "C": 40.0}

INSIGHT_PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}

ALERT_SEVERITY_WEIGHT = {"critical": 3, "high": 2, "medium": 1, "low": 0}

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


# ── 纯函数层 ─────────────────────────────────────────────────────────────────


def compute_brand_grade_distribution(scores: List[float]) -> Dict[str, int]:
    """从门店评分列表统计 A/B/C/D 分布。"""
    dist = {"A": 0, "B": 0, "C": 0, "D": 0}
    for s in scores:
        if s >= GRADE_THRESHOLDS["A"]:
            dist["A"] += 1
        elif s >= GRADE_THRESHOLDS["B"]:
            dist["B"] += 1
        elif s >= GRADE_THRESHOLDS["C"]:
            dist["C"] += 1
        else:
            dist["D"] += 1
    return dist


def compute_brand_avg_grade(avg_score: float) -> str:
    """品牌综合等级（依据平均分）。"""
    if avg_score >= GRADE_THRESHOLDS["A"]:
        return "A"
    if avg_score >= GRADE_THRESHOLDS["B"]:
        return "B"
    if avg_score >= GRADE_THRESHOLDS["C"]:
        return "C"
    return "D"


def generate_financial_narrative(
    avg_score: float,
    brand_grade: str,
    store_count: int,
    open_alerts: int,
    critical_alerts: int,
    budget_achievement_pct: Optional[float],
    worst_store_id: Optional[str],
    worst_store_score: Optional[float],
    top_insight_type: Optional[str],
) -> str:
    """
    生成 ≤300 字的中文财务叙事简报，整合健康评分、预警、预算三个维度。

    纯函数，无 DB 依赖，便于单元测试。
    """
    # 等级描述
    grade_desc = {"A": "优秀", "B": "良好", "C": "待改善", "D": "高风险"}.get(brand_grade, "未知")

    parts: List[str] = []

    # 综合健康
    parts.append(f"本期{store_count}家门店财务健康均分 {avg_score:.1f}分（{grade_desc}），")

    # 预警态势
    if critical_alerts > 0:
        parts.append(f"存在 {critical_alerts} 条严重告警需立即处理，开放告警共 {open_alerts} 条。")
    elif open_alerts > 0:
        parts.append(f"共有 {open_alerts} 条财务预警待处理，无严重级别告警。")
    else:
        parts.append("当前无开放财务预警，整体运营稳定。")

    # 预算执行
    if budget_achievement_pct is not None:
        if budget_achievement_pct >= 100:
            parts.append(f"预算达成率 {budget_achievement_pct:.1f}%，超额完成目标。")
        elif budget_achievement_pct >= 80:
            parts.append(f"预算达成率 {budget_achievement_pct:.1f}%，整体执行良好。")
        else:
            parts.append(f"预算达成率仅 {budget_achievement_pct:.1f}%，建议排查执行偏差。")

    # 最弱门店
    if worst_store_id and worst_store_score is not None:
        worst_grade = compute_brand_avg_grade(worst_store_score)
        parts.append(f"门店 {worst_store_id} 评分最低（{worst_store_score:.1f}分/{worst_grade}），建议优先关注。")

    # 重点洞察类型
    insight_labels = {
        "profit": "利润率",
        "cash": "现金流",
        "tax": "税务偏差",
        "settlement": "结算风控",
        "budget": "预算偏差",
    }
    if top_insight_type and top_insight_type in insight_labels:
        parts.append(f"当前最突出问题类型：{insight_labels[top_insight_type]}，建议重点干预。")

    narrative = "".join(parts)
    # 截断至 300 字
    return narrative[:300]


def prioritize_brand_actions(
    insights: List[Dict[str, Any]],
    alert_events: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    合并门店洞察 + 告警事件，按优先级排序，返回 Top 15 行动项。

    insights 每项期望字段: {store_id, insight_type, priority, content}
    alert_events 每项期望字段: {store_id, metric, severity, message, event_id}
    """
    items: List[Dict[str, Any]] = []

    for ins in insights:
        p = ins.get("priority", "low")
        items.append(
            {
                "source": "insight",
                "store_id": ins.get("store_id", ""),
                "type": ins.get("insight_type", ""),
                "priority": p,
                "sort_key": INSIGHT_PRIORITY_ORDER.get(p, 99),
                "content": ins.get("content", ""),
                "action_id": f"ins_{ins.get('store_id','')}_{ins.get('insight_type','')}",
            }
        )

    for evt in alert_events:
        sev = evt.get("severity", "low")
        items.append(
            {
                "source": "alert",
                "store_id": evt.get("store_id", ""),
                "type": evt.get("metric", ""),
                "priority": "high" if sev in ("critical", "high") else "medium",
                "sort_key": -ALERT_SEVERITY_WEIGHT.get(sev, 0),  # 严重告警排前
                "content": evt.get("message", ""),
                "action_id": f"alert_{evt.get('event_id', '')}",
            }
        )

    items.sort(key=lambda x: (x["sort_key"], x["store_id"]))
    return items[:15]


# ── DB 函数层 ─────────────────────────────────────────────────────────────────


async def get_brand_health_overview(
    db: AsyncSession,
    brand_id: str,
    period: str,
) -> Dict[str, Any]:
    """
    从 finance_health_scores 查询所有门店当期健康评分。

    注：当前 finance_health_scores 无 brand_id 列，暂时返回全部门店（多租户隔离在后续版本加）。
    """
    rows = await db.execute(
        text("""
            SELECT store_id, total_score, grade,
                   profit_score, cash_score, tax_score, settlement_score, budget_score
            FROM finance_health_scores
            WHERE period = :period
            ORDER BY total_score DESC
        """),
        {"period": period},
    )
    rows = rows.fetchall()

    if not rows:
        return {
            "store_scores": [],
            "avg_score": 0.0,
            "grade_distribution": {"A": 0, "B": 0, "C": 0, "D": 0},
            "best_store": None,
            "worst_store": None,
            "store_count": 0,
        }

    scores_list = [_to_float(r[1]) for r in rows]
    avg_score = sum(scores_list) / len(scores_list)

    store_scores = [
        {
            "store_id": r[0],
            "total_score": _to_float(r[1]),
            "grade": r[2],
            "profit_score": _to_float(r[3]),
            "cash_score": _to_float(r[4]),
            "tax_score": _to_float(r[5]),
            "settlement_score": _to_float(r[6]),
            "budget_score": _to_float(r[7]),
        }
        for r in rows
    ]

    return {
        "store_scores": store_scores,
        "avg_score": round(avg_score, 2),
        "grade_distribution": compute_brand_grade_distribution(scores_list),
        "best_store": {
            "store_id": store_scores[0]["store_id"],
            "total_score": store_scores[0]["total_score"],
            "grade": store_scores[0]["grade"],
        },
        "worst_store": {
            "store_id": store_scores[-1]["store_id"],
            "total_score": store_scores[-1]["total_score"],
            "grade": store_scores[-1]["grade"],
        },
        "store_count": len(rows),
    }


async def get_brand_alert_summary(
    db: AsyncSession,
    brand_id: str,
) -> Dict[str, Any]:
    """聚合所有门店的开放告警数量和严重度分布。"""
    rows = await db.execute(
        text("""
            SELECT e.store_id, e.severity, e.status, e.metric, e.message, e.id
            FROM financial_alert_events e
            WHERE e.status IN ('open', 'acknowledged')
            ORDER BY e.store_id, e.severity DESC
        """),
    )
    rows = rows.fetchall()

    open_count = sum(1 for r in rows if r[2] == "open")
    critical_count = sum(1 for r in rows if r[1] == "critical")
    acknowledged_count = sum(1 for r in rows if r[2] == "acknowledged")

    # 按门店分组
    by_store: Dict[str, List[Dict]] = {}
    for r in rows:
        sid = r[0]
        if sid not in by_store:
            by_store[sid] = []
        by_store[sid].append(
            {
                "severity": r[1],
                "status": r[2],
                "metric": r[3],
                "message": r[4],
                "event_id": r[5],
                "store_id": sid,
            }
        )

    return {
        "open_count": open_count,
        "critical_count": critical_count,
        "acknowledged_count": acknowledged_count,
        "total_count": len(rows),
        "by_store": [{"store_id": sid, "events": evts} for sid, evts in by_store.items()],
        "all_events": [
            {"severity": r[1], "status": r[2], "metric": r[3], "message": r[4], "event_id": r[5], "store_id": r[0]}
            for r in rows
        ],
    }


async def get_brand_budget_summary(
    db: AsyncSession,
    brand_id: str,
    period: str,
) -> Dict[str, Any]:
    """
    统计品牌下各门店当期预算达成情况。
    从 profit_attribution_results 获取实际收入，与 budget_plans 中 revenue 条目对比。
    """
    # 拿所有 active/closed 预算计划
    plan_rows = await db.execute(
        text("""
            SELECT bp.id, bp.store_id, bp.status
            FROM budget_plans bp
            WHERE bp.period = :period
              AND bp.status IN ('active', 'closed')
        """),
        {"period": period},
    )
    plan_rows = plan_rows.fetchall()

    if not plan_rows:
        return {
            "store_count_with_budget": 0,
            "avg_achievement_pct": None,
            "over_budget_count": 0,
            "under_budget_count": 0,
            "store_budgets": [],
        }

    plan_ids = [r[0] for r in plan_rows]
    store_map = {r[0]: r[1] for r in plan_rows}  # plan_id → store_id

    # 拿各计划的 revenue 预算行
    budget_rows = await db.execute(
        text("""
            SELECT plan_id, budget_yuan
            FROM budget_line_items
            WHERE plan_id = ANY(:pids) AND category = 'revenue'
        """),
        {"pids": plan_ids},
    )
    budget_map = {r[0]: _to_float(r[1]) for r in budget_rows.fetchall()}

    # 拿各门店当期实际收入
    actual_rows = await db.execute(
        text("""
            SELECT store_id, net_revenue_yuan
            FROM profit_attribution_results
            WHERE period = :period
        """),
        {"period": period},
    )
    actual_map = {r[0]: _to_float(r[1]) for r in actual_rows.fetchall()}

    store_budgets = []
    achievements = []
    over_count = 0
    under_count = 0

    for pid, sid, _ in plan_rows:
        budget_rev = budget_map.get(pid, 0.0)
        actual_rev = actual_map.get(sid, 0.0)
        if budget_rev > 0:
            ach = actual_rev / budget_rev * 100
        else:
            ach = None

        if ach is not None:
            achievements.append(ach)
            if ach >= 100:
                over_count += 1
            else:
                under_count += 1

        store_budgets.append(
            {
                "store_id": sid,
                "budget_revenue": budget_rev,
                "actual_revenue": actual_rev,
                "achievement_pct": round(ach, 2) if ach is not None else None,
            }
        )

    avg_ach = round(sum(achievements) / len(achievements), 2) if achievements else None

    return {
        "store_count_with_budget": len(plan_rows),
        "avg_achievement_pct": avg_ach,
        "over_budget_count": over_count,
        "under_budget_count": under_count,
        "store_budgets": store_budgets,
    }


async def get_brand_actions(
    db: AsyncSession,
    brand_id: str,
    period: str,
) -> List[Dict[str, Any]]:
    """聚合所有门店当期 finance_insights，按优先级降序，返回 Top 20。"""
    rows = await db.execute(
        text("""
            SELECT store_id, insight_type, priority, content
            FROM finance_insights
            WHERE period = :period
            ORDER BY
                CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
                store_id
            LIMIT 20
        """),
        {"period": period},
    )
    return [
        {
            "store_id": r[0],
            "insight_type": r[1],
            "priority": r[2],
            "content": r[3],
        }
        for r in rows.fetchall()
    ]


async def save_report_snapshot(
    db: AsyncSession,
    brand_id: str,
    period: str,
    data: Dict[str, Any],
) -> None:
    """Upsert CFO报告快照。"""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.execute(
        text("""
            INSERT INTO financial_report_snapshots
                (brand_id, period, report_type, narrative, store_count,
                 avg_health_score, brand_grade, open_alerts_count,
                 critical_alerts_count, budget_achievement_pct, content_json,
                 generated_at, updated_at)
            VALUES
                (:brand_id, :period, 'cfo_monthly', :narrative, :store_count,
                 :avg_score, :brand_grade, :open_alerts, :critical_alerts,
                 :budget_ach, :content_json, :now, :now)
            ON CONFLICT (brand_id, period, report_type) DO UPDATE SET
                narrative             = EXCLUDED.narrative,
                store_count           = EXCLUDED.store_count,
                avg_health_score      = EXCLUDED.avg_health_score,
                brand_grade           = EXCLUDED.brand_grade,
                open_alerts_count     = EXCLUDED.open_alerts_count,
                critical_alerts_count = EXCLUDED.critical_alerts_count,
                budget_achievement_pct= EXCLUDED.budget_achievement_pct,
                content_json          = EXCLUDED.content_json,
                updated_at            = EXCLUDED.updated_at
        """),
        {
            "brand_id": brand_id,
            "period": period,
            "narrative": data.get("narrative"),
            "store_count": data.get("store_count"),
            "avg_score": data.get("avg_health_score"),
            "brand_grade": data.get("brand_grade"),
            "open_alerts": data.get("open_alerts_count"),
            "critical_alerts": data.get("critical_alerts_count"),
            "budget_ach": data.get("budget_achievement_pct"),
            "content_json": json.dumps(data, ensure_ascii=False, default=str),
            "now": now,
        },
    )
    await db.commit()


async def get_cfo_dashboard(
    db: AsyncSession,
    brand_id: str,
    period: str,
) -> Dict[str, Any]:
    """
    BFF 聚合：健康总览 + 预警摘要 + 预算汇总 + 行动清单 + 叙事简报。
    每个子查询独立 try/except 降级，部分失败不影响整体返回。
    """
    health_overview: Optional[Dict] = None
    alert_summary: Optional[Dict] = None
    budget_summary: Optional[Dict] = None
    actions: List[Dict] = []

    try:
        health_overview = await get_brand_health_overview(db, brand_id, period)
    except Exception as exc:
        logger.warning("cfo_dashboard.health_overview_failed", brand_id=brand_id, period=period, error=str(exc))

    try:
        alert_summary = await get_brand_alert_summary(db, brand_id)
    except Exception as exc:
        logger.warning("cfo_dashboard.alert_summary_failed", brand_id=brand_id, error=str(exc))

    try:
        budget_summary = await get_brand_budget_summary(db, brand_id, period)
    except Exception as exc:
        logger.warning("cfo_dashboard.budget_summary_failed", brand_id=brand_id, period=period, error=str(exc))

    try:
        actions = await get_brand_actions(db, brand_id, period)
    except Exception as exc:
        logger.warning("cfo_dashboard.actions_failed", brand_id=brand_id, period=period, error=str(exc))

    # 告警事件列表（供 prioritize_brand_actions 使用）
    alert_events = []
    if alert_summary:
        alert_events = alert_summary.get("all_events", [])

    # 行动优先级排序
    prioritized_actions = prioritize_brand_actions(actions, alert_events)

    # 叙事简报
    narrative = ""
    try:
        avg_score = health_overview["avg_score"] if health_overview else 0.0
        brand_grade = compute_brand_avg_grade(avg_score)
        store_count = health_overview["store_count"] if health_overview else 0
        open_alerts = alert_summary["open_count"] if alert_summary else 0
        critical_alerts = alert_summary["critical_count"] if alert_summary else 0
        budget_ach = budget_summary["avg_achievement_pct"] if budget_summary else None
        worst = health_overview["worst_store"] if health_overview else None
        top_insight = actions[0]["insight_type"] if actions else None
        narrative = generate_financial_narrative(
            avg_score=avg_score,
            brand_grade=brand_grade,
            store_count=store_count,
            open_alerts=open_alerts,
            critical_alerts=critical_alerts,
            budget_achievement_pct=budget_ach,
            worst_store_id=worst["store_id"] if worst else None,
            worst_store_score=worst["total_score"] if worst else None,
            top_insight_type=top_insight,
        )
        brand_grade_final = brand_grade
    except Exception:
        brand_grade_final = "—"

    return {
        "brand_id": brand_id,
        "period": period,
        "brand_grade": brand_grade_final,
        "narrative": narrative,
        "health_overview": health_overview,
        "alert_summary": alert_summary,
        "budget_summary": budget_summary,
        "actions": prioritized_actions,
    }
