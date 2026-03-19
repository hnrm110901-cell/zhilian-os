"""
老板多店版每日简报服务
HQ Multi-Store Daily Briefing Service

为老板/总部视角生成横向对比简报：
  ① 各门店健康分排名（红绿灯）
  ② 全局 Top3 决策（跨店优先级最高）
  ③ 最差门店预警（健康分 < 50 的门店）
  ④ 全局经营摘要（总营收/平均成本率）

依赖（零新增表）：
  - private_domain_health_service.calculate_health_score()
  - DecisionPriorityEngine.get_top_decisions()
  - orders / inventory_transactions（营收/成本）
  - wechat_service（企微推送）
"""

from __future__ import annotations

import asyncio
import datetime
import os
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

_BASE_URL = os.getenv("APP_BASE_URL", "https://your-domain.com")
_HEALTH_ALERT_THRESHOLD = 50  # 低于此分数触发预警
_HEALTH_WARNING_THRESHOLD = 70  # 低于此分数显示黄色


async def _all_store_ids(db: AsyncSession) -> List[str]:
    try:
        rows = (await db.execute(text("SELECT id FROM stores WHERE is_active = true ORDER BY id"))).fetchall()
        return [r[0] for r in rows]
    except Exception as exc:
        logger.warning("hq_briefing.stores_failed", error=str(exc))
        return ["store_001"]


async def _store_health(store_id: str, db: AsyncSession) -> Dict[str, Any]:
    from .private_domain_health_service import calculate_health_score

    try:
        return await calculate_health_score(store_id, db)
    except Exception as exc:
        logger.warning("hq_briefing.health_failed", store_id=store_id, error=str(exc))
        return {
            "store_id": store_id,
            "total_score": 0,
            "grade": {"level": "未知", "color": "default"},
            "dimensions": [],
            "top_actions": [],
        }


async def _global_revenue_summary(
    store_ids: List[str],
    db: AsyncSession,
) -> Dict[str, Any]:
    """昨日全店合并营收/成本率。"""
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    today = datetime.date.today().isoformat()
    placeholders = ", ".join(f":s{i}" for i in range(len(store_ids)))
    params = {f"s{i}": sid for i, sid in enumerate(store_ids)}
    params["yesterday"] = yesterday
    params["today"] = today

    rev_row = cost_row = None
    try:
        rev_row = (
            await db.execute(
                text(f"""
                SELECT COALESCE(SUM(total_amount), 0)
                FROM orders
                WHERE store_id IN ({placeholders})
                  AND created_at::date = :yesterday
            """),
                params,
            )
        ).fetchone()
        cost_row = (
            await db.execute(
                text(f"""
                SELECT COALESCE(SUM(total_cost), 0)
                FROM inventory_transactions
                WHERE store_id IN ({placeholders})
                  AND transaction_type = 'usage'
                  AND created_at::date = :yesterday
            """),
                params,
            )
        ).fetchone()
    except Exception as exc:
        logger.warning("hq_briefing.revenue_failed", error=str(exc))

    revenue_fen = int(rev_row[0]) if rev_row else 0
    cost_fen = int(cost_row[0]) if cost_row else 0
    cost_rate = cost_fen / revenue_fen if revenue_fen > 0 else 0.0

    return {
        "total_revenue_yuan": round(revenue_fen / 100, 2),
        "total_cost_yuan": round(cost_fen / 100, 2),
        "avg_cost_rate_pct": round(cost_rate * 100, 1),
    }


async def _global_top3(store_ids: List[str], db: AsyncSession) -> List[Dict[str, Any]]:
    """跨所有门店取置信度最高的 Top3 决策。"""
    all_decisions: List[Dict[str, Any]] = []
    try:
        from .decision_priority_engine import DecisionPriorityEngine

        engine = DecisionPriorityEngine()
        for sid in store_ids[:5]:  # 最多扫描5个门店避免超时
            try:
                r = await engine.get_top_decisions(store_id=sid, db=db, limit=3)
                items = r.get("decisions", []) if isinstance(r, dict) else r[:3]
                for d in items:
                    d["_store_id"] = sid
                all_decisions.extend(items)
            except Exception:
                pass
    except Exception as exc:
        logger.warning("hq_briefing.decisions_failed", error=str(exc))

    # 按 confidence 降序取 Top3
    all_decisions.sort(key=lambda d: d.get("confidence", 0), reverse=True)
    return all_decisions[:3]


# ── 主函数 ────────────────────────────────────────────────────────────────────


async def generate_hq_briefing(db: AsyncSession) -> Dict[str, Any]:
    """
    生成老板多店版每日简报（结构化 JSON）。

    Returns:
        {
            "briefing_date":   str,
            "generated_at":    str,
            "store_rankings":  [...],   # 各店健康分排名
            "alerts":          [...],   # 健康分 < 50 的预警门店
            "global_top3":     [...],   # 跨店 Top3 决策
            "revenue_summary": {...},   # 昨日全店合并营收
            "push_text":       str,     # 企微推送正文
        }
    """
    today = datetime.date.today()
    store_ids = await _all_store_ids(db)

    # 各门店健康分（顺序执行，session 不支持真并发）
    rankings: List[Dict[str, Any]] = []
    for sid in store_ids:
        h = await _store_health(sid, db)
        score = h.get("total_score", 0)
        grade = h.get("grade", {})
        rankings.append(
            {
                "store_id": sid,
                "score": score,
                "level": grade.get("level", "未知"),
                "color": grade.get("color", "default"),
                "top_action": (h.get("top_actions") or [{}])[0].get("action", "-"),
            }
        )

    rankings.sort(key=lambda x: x["score"], reverse=True)

    # 预警门店（< 阈值）
    alerts = [r for r in rankings if r["score"] < _HEALTH_ALERT_THRESHOLD]

    # 全局 Top3 + 营收汇总
    global_top3, revenue_summary = (
        await _global_top3(store_ids, db),
        await _global_revenue_summary(store_ids, db),
    )

    # 构建企微推送文本
    push_lines: List[str] = [
        f"【{today.strftime('%-m月%-d日')} 多店早报·老板版】",
        f"共 {len(store_ids)} 家门店｜昨日营收 ¥{revenue_summary['total_revenue_yuan']:,.2f}"
        f"｜均成本率 {revenue_summary['avg_cost_rate_pct']:.1f}%",
        "━━ 私域健康排名 ━━",
    ]

    for i, r in enumerate(rankings[:5], 1):
        icon = "🟢" if r["score"] >= 85 else "🟡" if r["score"] >= 70 else "🔴"
        push_lines.append(f"{i}. {icon} {r['store_id']} {r['score']}分 [{r['level']}]")

    if alerts:
        push_lines.append(f"━━ ⚠️ 预警门店 ({len(alerts)}家) ━━")
        for a in alerts[:3]:
            push_lines.append(f"• {a['store_id']} {a['score']}分 → {a['top_action'][:20]}")

    if global_top3:
        push_lines.append("━━ 全局 Top3 决策 ━━")
        for i, d in enumerate(global_top3, 1):
            title = d.get("title") or d.get("description") or d.get("action", "-")
            impact = d.get("expected_impact_yuan") or d.get("financial_impact_yuan", 0)
            store = d.get("_store_id", "")
            push_lines.append(f"{i}. [{store}] {title[:18]} ¥{impact:,.0f}")

    push_lines.append(f"查看详情：{_BASE_URL}/hq/decisions")
    push_text = "\n".join(push_lines)

    return {
        "briefing_date": str(today),
        "generated_at": datetime.datetime.utcnow().isoformat(),
        "store_count": len(store_ids),
        "store_rankings": rankings,
        "alerts": alerts,
        "global_top3": global_top3,
        "revenue_summary": revenue_summary,
        "push_text": push_text,
    }


async def push_hq_briefing(
    db: AsyncSession,
    dry_run: bool = False,
) -> Dict[str, Any]:
    briefing = await generate_hq_briefing(db)
    pushed = False
    push_result = None

    if not dry_run:
        try:
            from .wechat_service import wechat_service

            if wechat_service:
                push_result = await wechat_service.send_text(briefing["push_text"])
                pushed = True
                logger.info("hq_briefing.pushed", stores=briefing["store_count"], alerts=len(briefing["alerts"]))
        except Exception as exc:
            logger.error("hq_briefing.push_failed", error=str(exc))
            push_result = {"error": str(exc)}

    return {"briefing": briefing, "pushed": pushed, "push_result": push_result}
