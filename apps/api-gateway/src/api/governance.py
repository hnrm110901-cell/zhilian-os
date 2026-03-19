"""
AI 治理看板 API
Governance Dashboard — 聚合决策采纳率、Agent 健康度、人工干预率等治理指标
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.dependencies import get_current_active_user, get_db
from ..models.decision_log import DecisionLog, DecisionOutcome, DecisionStatus
from ..models.user import User
from ..services.agent_monitor_service import agent_monitor_service

logger = structlog.get_logger()
router = APIRouter()


@router.get("/governance/dashboard")
async def get_governance_dashboard(
    store_id: Optional[str] = Query(None, description="门店ID，不传则全部门店"),
    days: int = Query(30, ge=7, le=90, description="统计天数"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    AI 治理看板总览

    返回：
    - summary        KPI 卡片（总决策数、采纳率、干预率、平均置信度）
    - status_dist    决策状态分布（饼图）
    - weekly_trend   周度采纳率趋势（折线图）
    - agent_stats    各 Agent 调用统计（柱状图）
    - recent_logs    最近 20 条决策日志（表格）
    """
    try:
        since = datetime.utcnow() - timedelta(days=days)
        conditions = [DecisionLog.created_at >= since]
        if store_id:
            conditions.append(DecisionLog.store_id == store_id)

        result = await db.execute(select(DecisionLog).where(and_(*conditions)).order_by(DecisionLog.created_at.desc()))
        logs: List[DecisionLog] = result.scalars().all()

        # ── KPI summary ───────────────────────────────────────────────────────
        total = len(logs)
        decided = [
            l
            for l in logs
            if l.decision_status
            in (
                DecisionStatus.APPROVED,
                DecisionStatus.REJECTED,
                DecisionStatus.MODIFIED,
                DecisionStatus.EXECUTED,
            )
        ]
        approved_count = sum(
            1
            for l in decided
            if l.decision_status
            in (
                DecisionStatus.APPROVED,
                DecisionStatus.EXECUTED,
            )
        )
        rejected_count = sum(1 for l in decided if l.decision_status == DecisionStatus.REJECTED)
        modified_count = sum(1 for l in decided if l.decision_status == DecisionStatus.MODIFIED)

        adoption_rate = round(approved_count / len(decided) * 100, 1) if decided else 0.0
        override_rate = round((rejected_count + modified_count) / len(decided) * 100, 1) if decided else 0.0

        confidences = [l.ai_confidence for l in logs if l.ai_confidence is not None]
        avg_confidence = round(sum(confidences) / len(confidences) * 100, 1) if confidences else 0.0

        trust_scores = [l.trust_score for l in logs if l.trust_score is not None]
        avg_trust = round(sum(trust_scores) / len(trust_scores) * 100, 1) if trust_scores else 0.0

        # ── 决策状态分布（饼图）─────────────────────────────────────────────
        status_counts: Dict[str, int] = {}
        for l in logs:
            s = l.decision_status.value if l.decision_status else "unknown"
            status_counts[s] = status_counts.get(s, 0) + 1
        status_dist = [{"status": k, "count": v} for k, v in status_counts.items()]

        # ── 周度采纳率趋势（最近 N 周）────────────────────────────────────────
        weekly_trend = []
        for week_offset in range(days // 7):
            week_end = datetime.utcnow() - timedelta(days=week_offset * 7)
            week_start = week_end - timedelta(days=7)
            wl = [l for l in logs if week_start <= l.created_at <= week_end]
            if not wl:
                continue
            w_decided = [
                l
                for l in wl
                if l.decision_status
                in (
                    DecisionStatus.APPROVED,
                    DecisionStatus.REJECTED,
                    DecisionStatus.MODIFIED,
                    DecisionStatus.EXECUTED,
                )
            ]
            w_approved = sum(
                1
                for l in w_decided
                if l.decision_status
                in (
                    DecisionStatus.APPROVED,
                    DecisionStatus.EXECUTED,
                )
            )
            w_rate = round(w_approved / len(w_decided) * 100, 1) if w_decided else 0.0
            weekly_trend.append(
                {
                    "week_start": week_start.strftime("%m-%d"),
                    "week_end": week_end.strftime("%m-%d"),
                    "total": len(wl),
                    "decided": len(w_decided),
                    "adoption_rate": w_rate,
                }
            )
        weekly_trend.reverse()

        # ── 各 Agent 决策统计（柱状图）────────────────────────────────────────
        agent_buckets: Dict[str, Dict] = {}
        for l in logs:
            at = l.agent_type or "unknown"
            if at not in agent_buckets:
                agent_buckets[at] = {"total": 0, "approved": 0, "rejected": 0, "modified": 0, "pending": 0}
            agent_buckets[at]["total"] += 1
            if l.decision_status in (DecisionStatus.APPROVED, DecisionStatus.EXECUTED):
                agent_buckets[at]["approved"] += 1
            elif l.decision_status == DecisionStatus.REJECTED:
                agent_buckets[at]["rejected"] += 1
            elif l.decision_status == DecisionStatus.MODIFIED:
                agent_buckets[at]["modified"] += 1
            else:
                agent_buckets[at]["pending"] += 1
        agent_stats = [
            {
                "agent_type": k,
                **v,
                "adoption_rate": (
                    round(v["approved"] / (v["approved"] + v["rejected"] + v["modified"]) * 100, 1)
                    if (v["approved"] + v["rejected"] + v["modified"]) > 0
                    else 0.0
                ),
            }
            for k, v in agent_buckets.items()
        ]
        agent_stats.sort(key=lambda x: x["total"], reverse=True)

        # ── 最近 20 条决策日志 ─────────────────────────────────────────────────
        recent_logs = []
        for l in logs[:20]:
            recent_logs.append(
                {
                    "id": str(l.id),
                    "created_at": l.created_at.strftime("%Y-%m-%d %H:%M"),
                    "store_id": l.store_id,
                    "agent_type": l.agent_type,
                    "decision_type": l.decision_type.value if l.decision_type else None,
                    "ai_suggestion": (l.ai_suggestion or "")[:80],
                    "decision_status": l.decision_status.value if l.decision_status else None,
                    "outcome": l.outcome.value if l.outcome else None,
                    "ai_confidence": round((l.ai_confidence or 0) * 100, 1),
                    "trust_score": round((l.trust_score or 0) * 100, 1),
                    "cost_impact_yuan": float(l.cost_impact or 0),
                    "revenue_impact_yuan": float(l.revenue_impact or 0),
                }
            )

        # ── 实时 Agent 调用指标（来自内存）────────────────────────────────────
        realtime = await agent_monitor_service.get_realtime_stats()

        return {
            "success": True,
            "period_days": days,
            "store_id": store_id,
            "summary": {
                "total_decisions": total,
                "decided_count": len(decided),
                "adoption_rate": adoption_rate,
                "override_rate": override_rate,
                "avg_confidence": avg_confidence,
                "avg_trust_score": avg_trust,
                "pending_count": sum(1 for l in logs if l.decision_status == DecisionStatus.PENDING),
            },
            "status_dist": status_dist,
            "weekly_trend": weekly_trend,
            "agent_stats": agent_stats,
            "recent_logs": recent_logs,
            "realtime": realtime.get("stats", {}),
        }

    except Exception as e:
        logger.error("governance_dashboard_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
