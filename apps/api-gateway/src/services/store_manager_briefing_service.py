"""
店长版每日简报服务
Store Manager Daily Briefing Service

组装已有服务，生成店长每日 08:00 简报并推送企微。

简报结构（5节）：
  ① 私域健康分   — 今日综合得分 + 等级
  ② Top3 决策    — 当日最高优先级决策（含¥预期影响）
  ③ 昨日经营快照  — 营收/成本率/损耗（来自 CaseStoryGenerator）
  ④ 流失预警      — 高风险会员数 + 紧急行动建议
  ⑤ 今日行动提示  — 当前最薄弱维度对应的1条改善动作

依赖的现有服务（零新增表）：
  - private_domain_health_service.calculate_health_score()
  - DecisionPriorityEngine.get_top_decisions()
  - CaseStoryGenerator.generate_daily_story()
  - private_domain_metrics（journey_health.churn_risk_count）
  - wechat_service（企微推送）

Rule 6：所有¥金额输出 _yuan 字段
Rule 7：每条推送必须含「建议动作 + ¥影响 + 置信度 + 操作入口」
"""

from __future__ import annotations

import datetime
import os
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# 操作跳转基础 URL
_BASE_URL = os.getenv("APP_BASE_URL", "https://your-domain.com")


# ── 内部聚合 ──────────────────────────────────────────────────────────────────


async def _get_health(store_id: str, db: AsyncSession) -> Dict[str, Any]:
    try:
        from .private_domain_health_service import calculate_health_score

        return await calculate_health_score(store_id, db)
    except Exception as exc:
        logger.warning("briefing.health_failed", store_id=store_id, error=str(exc))
        return {
            "total_score": 0,
            "grade": {"level": "未知", "color": "default", "desc": "-"},
            "top_actions": [],
            "dimensions": [],
        }


async def _get_top3_decisions(store_id: str, db: AsyncSession) -> List[Dict[str, Any]]:
    try:
        from .decision_priority_engine import DecisionPriorityEngine

        engine = DecisionPriorityEngine()
        result = await engine.get_top_decisions(store_id=store_id, db=db, limit=3)
        return result.get("decisions", []) if isinstance(result, dict) else result[:3]
    except Exception as exc:
        logger.warning("briefing.decisions_failed", store_id=store_id, error=str(exc))
        return []


async def _get_yesterday_story(store_id: str, db: AsyncSession) -> Dict[str, Any]:
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    try:
        from .case_story_generator import CaseStoryGenerator

        return await CaseStoryGenerator.generate_daily_story(store_id, yesterday, db)
    except Exception as exc:
        logger.warning("briefing.story_failed", store_id=store_id, error=str(exc))
        return {"cost_metrics": {}, "decision_summary": {}, "narrative": "-", "date": str(yesterday)}


async def _get_ai_trust_summary(store_id: str, db: AsyncSession) -> Dict[str, Any]:
    try:
        row = (
            await db.execute(
                text("""
                SELECT
                    ROUND(AVG(trust_score)::numeric, 1) AS avg_trust,
                    COUNT(CASE WHEN outcome = 'success' THEN 1 END) AS success,
                    COUNT(CASE WHEN outcome IS NOT NULL THEN 1 END) AS evaluated,
                    COALESCE(SUM(CASE WHEN outcome = 'success' THEN cost_impact ELSE 0 END), 0) AS saved
                FROM decision_logs
                WHERE store_id = :s AND created_at >= NOW() - INTERVAL '30 days'
            """),
                {"s": store_id},
            )
        ).fetchone()
        if not row or row[0] is None:
            return {"avg_trust": 0, "success_count": 0, "evaluated_count": 0, "saved_yuan": 0}
        return {
            "avg_trust": float(row[0]),
            "success_count": int(row[1]),
            "evaluated_count": int(row[2]),
            "saved_yuan": round(float(row[3]), 2),
        }
    except Exception as exc:
        logger.warning("briefing.trust_failed", error=str(exc))
        return {"avg_trust": 0, "success_count": 0, "evaluated_count": 0, "saved_yuan": 0}


async def _get_churn_risk_count(store_id: str, db: AsyncSession) -> int:
    try:
        row = (
            await db.execute(
                text("SELECT COUNT(*) FROM private_domain_members " "WHERE store_id = :s AND risk_score >= 0.6"),
                {"s": store_id},
            )
        ).fetchone()
        return int(row[0]) if row else 0
    except Exception as exc:
        logger.warning("briefing.churn_failed", error=str(exc))
        return 0


# ── 简报组装 ──────────────────────────────────────────────────────────────────


async def generate_briefing(
    store_id: str,
    db: AsyncSession,
) -> Dict[str, Any]:
    """
    生成店长版每日简报（结构化 JSON）。

    Returns:
        {
            "store_id":       str,
            "briefing_date":  str,           # YYYY-MM-DD
            "generated_at":   str,           # ISO datetime
            "health":         {...},          # 私域健康分
            "top3_decisions": [...],          # Top3 决策
            "yesterday":      {...},          # 昨日经营快照
            "churn_risk":     int,            # 高风险会员数
            "top_action":     str,            # 今日1条核心行动建议
            "push_text":      str,            # 企微推送正文（纯文本）
        }
    """
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)

    health, decisions, story, churn, trust = (
        await _get_health(store_id, db),
        await _get_top3_decisions(store_id, db),
        await _get_yesterday_story(store_id, db),
        await _get_churn_risk_count(store_id, db),
        await _get_ai_trust_summary(store_id, db),
    )

    # 今日核心行动（取健康分最薄弱维度的第1条建议）
    top_action = (
        health.get("top_actions", [{}])[0].get("action", "保持现有私域运营节奏")
        if health.get("top_actions")
        else "保持现有私域运营节奏"
    )

    # 昨日经营摘要
    cost_m = story.get("cost_metrics", {})
    revenue_y = cost_m.get("revenue_yuan", 0)
    cost_rate = cost_m.get("actual_cost_rate_pct", 0)
    waste_y = cost_m.get("waste_cost_yuan", 0)

    # 构建企微推送文本（决策型：含¥影响+置信度）
    push_lines: List[str] = [
        f"【{today.strftime('%-m月%-d日')} 店长早报】",
        f"━━━━━━━━━━━━━━",
        f"🏥 私域健康分：{health['total_score']}分 [{health['grade']['level']}]",
        f"━━ 昨日经营 ━━",
        f"营收 ¥{revenue_y:,.2f} | 成本率 {cost_rate:.1f}% | 损耗 ¥{waste_y:,.2f}",
    ]

    if decisions:
        push_lines.append("━━ 今日Top3决策 ━━")
        for i, d in enumerate(decisions, 1):
            title = d.get("title") or d.get("description") or d.get("action", "-")
            impact = d.get("expected_impact_yuan") or d.get("financial_impact_yuan", 0)
            confidence = d.get("confidence", 0)
            push_lines.append(f"{i}. {title[:20]}" f" | ¥{impact:,.0f} | 置信度{confidence:.0%}")

    if trust.get("avg_trust", 0) > 0:
        push_lines.append("━━ AI信任分 ━━")
        push_lines.append(
            f"信任分 {trust['avg_trust']:.0f} | "
            f"已评估 {trust['evaluated_count']}条 | "
            f"成功 {trust['success_count']}条 | "
            f"累计节省 ¥{trust['saved_yuan']:,.2f}"
        )

    if churn > 0:
        push_lines.append(f"━━ 流失预警 ━━")
        push_lines.append(f"⚠️ 高风险会员 {churn} 人，建议立即启动唤醒旅程")

    push_lines.append(f"━━ 今日行动 ━━")
    push_lines.append(f"👉 {top_action}")
    push_lines.append(f"查看详情：{_BASE_URL}/sm/private-domain-health")

    push_text = "\n".join(push_lines)

    return {
        "store_id": store_id,
        "briefing_date": str(today),
        "generated_at": datetime.datetime.utcnow().isoformat(),
        "health": {
            "total_score": health.get("total_score", 0),
            "grade": health.get("grade", {}),
            "top_actions": health.get("top_actions", []),
        },
        "top3_decisions": decisions,
        "yesterday": {
            "date": str(yesterday),
            "revenue_yuan": revenue_y,
            "cost_rate_pct": cost_rate,
            "waste_yuan": waste_y,
            "narrative": story.get("narrative", "-"),
        },
        "churn_risk": churn,
        "ai_trust_summary": trust,
        "top_action": top_action,
        "push_text": push_text,
    }


# ── 企微推送 ──────────────────────────────────────────────────────────────────


async def push_briefing(
    store_id: str,
    db: AsyncSession,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    生成简报并推送至企微。

    Args:
        store_id: 门店 ID
        db:       数据库会话
        dry_run:  True 则只生成不推送（用于测试）

    Returns:
        {"briefing": {...}, "pushed": bool, "push_result": Any}
    """
    briefing = await generate_briefing(store_id, db)
    pushed = False
    push_result: Any = None

    if not dry_run:
        try:
            from .wechat_service import wechat_service

            if wechat_service:
                push_result = await wechat_service.send_text(briefing["push_text"])
                pushed = True
                logger.info("briefing.pushed", store_id=store_id, score=briefing["health"]["total_score"])
            else:
                logger.warning("briefing.wechat_not_configured", store_id=store_id)
        except Exception as exc:
            logger.error("briefing.push_failed", store_id=store_id, error=str(exc))
            push_result = {"error": str(exc)}

    return {
        "briefing": briefing,
        "pushed": pushed,
        "push_result": push_result,
    }
