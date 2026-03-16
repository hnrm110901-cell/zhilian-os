"""
AI三支柱API — Skill Registry + Effect Loop + BusinessContext

将 P1/P2/P3 基础设施暴露给前端和企微：
  GET  /api/v1/ai/skills                 — 技能发现（跨Agent）
  GET  /api/v1/ai/skills/{skill_id}      — 技能详情
  GET  /api/v1/ai/effects/{store_id}     — 效果评估摘要
  GET  /api/v1/ai/trust/{store_id}       — 信任分趋势
  POST /api/v1/ai/effects/evaluate       — 手动触发评估（管理员）
  GET  /api/v1/ai/context/{trace_id}     — 查询业务上下文链路
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.dependencies import get_current_active_user, get_db
from ..models.user import User

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/ai", tags=["ai-pillars"])


# ── Skill Registry（P1）────────────────────────────────────────────────────────


@router.get("/skills", summary="技能发现（跨Agent）")
async def discover_skills(
    agent_type: Optional[str] = Query(None, description="按Agent类型筛选"),
    intent: Optional[str] = Query(None, description="按业务意图搜索"),
    _: User = Depends(get_current_active_user),
):
    """查询可用技能列表，支持按Agent类型或业务意图过滤。"""
    from src.core.skill_registry import SkillRegistry

    registry = SkillRegistry.get()
    skills = registry.query(agent_type=agent_type, intent=intent)
    return {
        "total": len(skills),
        "skills": [s.to_dict() for s in skills],
    }


@router.get("/skills/{skill_id}", summary="技能详情")
async def get_skill_detail(
    skill_id: str,
    _: User = Depends(get_current_active_user),
):
    """获取指定技能的完整信息（含组合链）。"""
    from src.core.skill_registry import SkillRegistry

    registry = SkillRegistry.get()
    skill = registry.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found")

    chain = registry.get_composition_chain(skill_id)
    return {
        "skill": skill.to_dict(),
        "composition_chain": [s.to_dict() for s in chain],
    }


# ── Effect Loop（P2）──────────────────────────────────────────────────────────


@router.get("/effects/{store_id}", summary="效果评估摘要")
async def get_effect_summary(
    store_id: str,
    days: int = Query(default=30, le=90, description="查询天数"),
    _: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取门店决策效果评估摘要：
    - 已评估/待评估决策数
    - 成功/失败/部分成功分布
    - 平均信任分变化趋势
    - 累计¥节省金额
    """
    since = (date.today() - timedelta(days=days)).isoformat()
    try:
        # 总体统计
        stats_row = (
            await db.execute(
                text("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(outcome) AS evaluated,
                    COUNT(*) - COUNT(outcome) AS pending,
                    SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) AS success,
                    SUM(CASE WHEN outcome = 'failure' THEN 1 ELSE 0 END) AS failure,
                    SUM(CASE WHEN outcome = 'partial' THEN 1 ELSE 0 END) AS partial,
                    ROUND(AVG(trust_score)::numeric, 1) AS avg_trust,
                    ROUND(AVG(CASE WHEN outcome IS NOT NULL THEN trust_score END)::numeric, 1) AS avg_trust_evaluated,
                    COALESCE(SUM(CASE WHEN outcome = 'success' THEN cost_impact ELSE 0 END), 0) AS total_cost_saved_yuan,
                    COALESCE(SUM(CASE WHEN outcome = 'success' THEN revenue_impact ELSE 0 END), 0) AS total_revenue_gain_yuan
                FROM decision_logs
                WHERE store_id = :sid
                  AND created_at >= :since
            """),
                {"sid": store_id, "since": since},
            )
        ).fetchone()

        # 按类型分布
        type_rows = (
            await db.execute(
                text("""
                SELECT decision_type, outcome, COUNT(*) AS cnt
                FROM decision_logs
                WHERE store_id = :sid AND created_at >= :since AND outcome IS NOT NULL
                GROUP BY decision_type, outcome
                ORDER BY decision_type
            """),
                {"sid": store_id, "since": since},
            )
        ).fetchall()

        by_type: Dict[str, Dict[str, int]] = {}
        for r in type_rows:
            dt = r[0]
            if dt not in by_type:
                by_type[dt] = {"success": 0, "failure": 0, "partial": 0}
            by_type[dt][r[1]] = int(r[2])

        # 信任分趋势（按周）
        trend_rows = (
            await db.execute(
                text("""
                SELECT DATE_TRUNC('week', created_at)::date AS week,
                       ROUND(AVG(trust_score)::numeric, 1) AS avg_trust,
                       COUNT(*) AS decisions
                FROM decision_logs
                WHERE store_id = :sid AND created_at >= :since AND trust_score IS NOT NULL
                GROUP BY week
                ORDER BY week
            """),
                {"sid": store_id, "since": since},
            )
        ).fetchall()

        return {
            "store_id": store_id,
            "days": days,
            "total_decisions": int(stats_row[0]) if stats_row else 0,
            "evaluated": int(stats_row[1]) if stats_row else 0,
            "pending_evaluation": int(stats_row[2]) if stats_row else 0,
            "outcome_distribution": {
                "success": int(stats_row[3]) if stats_row else 0,
                "failure": int(stats_row[4]) if stats_row else 0,
                "partial": int(stats_row[5]) if stats_row else 0,
            },
            "avg_trust_score": float(stats_row[6]) if stats_row and stats_row[6] else 0.0,
            "avg_trust_evaluated": float(stats_row[7]) if stats_row and stats_row[7] else 0.0,
            "total_cost_saved_yuan": round(float(stats_row[8]), 2) if stats_row else 0.0,
            "total_revenue_gain_yuan": round(float(stats_row[9]), 2) if stats_row else 0.0,
            "by_type": by_type,
            "trust_trend": [{"week": str(r[0]), "avg_trust": float(r[1]), "decisions": int(r[2])} for r in trend_rows],
        }
    except Exception as exc:
        logger.warning("ai_pillars.effects_failed", store_id=store_id, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/trust/{store_id}", summary="信任分趋势")
async def get_trust_trend(
    store_id: str,
    days: int = Query(default=30, le=90),
    _: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """获取门店AI信任分日趋势。"""
    since = (date.today() - timedelta(days=days)).isoformat()
    try:
        rows = (
            await db.execute(
                text("""
                SELECT DATE(created_at) AS day,
                       ROUND(AVG(trust_score)::numeric, 1) AS avg_trust,
                       COUNT(*) AS decisions,
                       SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) AS success_count
                FROM decision_logs
                WHERE store_id = :sid AND created_at >= :since AND trust_score IS NOT NULL
                GROUP BY day
                ORDER BY day
            """),
                {"sid": store_id, "since": since},
            )
        ).fetchall()

        return {
            "store_id": store_id,
            "days": days,
            "trend": [
                {
                    "date": str(r[0]),
                    "avg_trust": float(r[1]),
                    "decisions": int(r[2]),
                    "success_count": int(r[3]),
                }
                for r in rows
            ],
        }
    except Exception as exc:
        logger.warning("ai_pillars.trust_failed", store_id=store_id, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/effects/evaluate", summary="手动触发效果评估")
async def trigger_evaluation(
    _: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """手动触发一次效果评估扫描（默认每日03:30自动执行）。"""
    from src.services.effect_evaluator import EffectEvaluator

    evaluator = EffectEvaluator(db)
    result = await evaluator.run_evaluation_sweep()
    return result


# ── BusinessContext（P3）──────────────────────────────────────────────────────


@router.get("/context/{trace_id}", summary="查询业务上下文链路")
async def get_context_trace(
    trace_id: str,
    _: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    根据 trace_id 查询业务上下文链路。

    优先从 Redis 读取实时上下文，回退到 DecisionLog.context_data。
    """
    # 尝试 Redis
    try:
        from src.core.business_context import get_business_context_store

        store = await get_business_context_store()
        if store:
            ctx = await store.load(trace_id)
            if ctx:
                return {"source": "redis", "context": ctx.to_dict()}
    except Exception:
        pass

    # 回退到 DecisionLog
    try:
        rows = (
            await db.execute(
                text("""
                SELECT id, decision_type, store_id, context_data, created_at, outcome, trust_score
                FROM decision_logs
                WHERE context_data::text LIKE :pattern
                ORDER BY created_at DESC
                LIMIT 10
            """),
                {"pattern": f"%{trace_id}%"},
            )
        ).fetchall()

        decisions = [
            {
                "decision_id": str(r[0]),
                "decision_type": r[1],
                "store_id": r[2],
                "context_data": r[3],
                "created_at": r[4].isoformat() if r[4] else None,
                "outcome": r[5],
                "trust_score": float(r[6]) if r[6] else None,
            }
            for r in rows
        ]

        return {
            "source": "decision_logs",
            "trace_id": trace_id,
            "related_decisions": decisions,
        }
    except Exception as exc:
        logger.warning("ai_pillars.context_failed", trace_id=trace_id, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))
