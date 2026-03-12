"""
AgentCollaborationOptimizer API
多Agent协同总线 — 冲突检测·优先级仲裁·全局优化
路由前缀: /api/v1/agent-collab
"""
import uuid
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from src.core.database import get_db
from src.core.dependencies import get_current_active_user
from src.models.user import User
from src.models.agent_collab import AgentConflict, GlobalOptimizationLog, AgentCollabSnapshot
from src.services.agent_collab_optimizer import (
    AgentCollabOptimizer,
    AgentRecommendation,
    agent_collab_optimizer,
)

import structlog
logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/agent-collab", tags=["agent-collab"])


# ──────────────────────────────────────────────
# Request / Response schemas
# ──────────────────────────────────────────────

class RecommendationInput(BaseModel):
    id:                   str   = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_name:           str   = Field(..., description="Agent 名称")
    store_id:             str   = Field(..., description="门店 ID")
    recommendation_type:  str   = Field(..., description="建议类型")
    recommendation_text:  str   = Field(..., description="建议内容")
    expected_impact_yuan: float = Field(0.0, description="预期¥影响")
    confidence_score:     float = Field(0.5, ge=0, le=1)
    priority_override:    Optional[int] = None


class OptimizeRequest(BaseModel):
    recommendations:       list[RecommendationInput]
    suppress_threshold_yuan: float = Field(100.0, description="低于此¥影响且置信度<0.4的建议被抑制")
    store_id:              Optional[str] = None   # 过滤特定门店
    brand_id:              Optional[str] = None


# ──────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────

@router.post("/optimize", summary="多Agent建议协同优化（冲突检测+仲裁+全局排序）")
async def optimize_recommendations(
    request: OptimizeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    协同优化入口：
    1. 接收多个 Agent 的建议列表
    2. 检测跨Agent冲突并仲裁
    3. 去重/抑制/重排序
    4. 返回优化后的建议列表 + 冲突报告 + 优化日志
    """
    recs = [
        AgentRecommendation(
            id                   = r.id,
            agent_name           = r.agent_name,
            store_id             = r.store_id,
            recommendation_type  = r.recommendation_type,
            recommendation_text  = r.recommendation_text,
            expected_impact_yuan = r.expected_impact_yuan,
            confidence_score     = r.confidence_score,
            priority_override    = r.priority_override,
        )
        for r in request.recommendations
    ]

    result = agent_collab_optimizer.optimize(recs, request.suppress_threshold_yuan)

    # 持久化冲突记录
    for cf in result.conflicts:
        try:
            db.add(AgentConflict(
                id                 = cf.conflict_id,
                store_id           = request.recommendations[0].store_id if request.recommendations else "unknown",
                brand_id           = request.brand_id,
                agent_a            = cf.agent_a,
                agent_b            = cf.agent_b,
                recommendation_a_id = cf.rec_a_id,
                recommendation_b_id = cf.rec_b_id,
                conflict_type      = cf.conflict_type,
                severity           = cf.severity,
                description        = cf.description,
                conflict_data      = {"rec_a": cf.rec_a_id, "rec_b": cf.rec_b_id},
                arbitration_status = "resolved",
                arbitration_method = cf.arbitration_method,
                winning_agent      = cf.winning_agent,
                arbitration_note   = f"自动仲裁：{cf.arbitration_method}",
                impact_yuan_saved  = cf.impact_yuan_saved,
                resolved_at        = datetime.utcnow(),
            ))
        except Exception as e:
            logger.warning("保存冲突记录失败", error=str(e))

    # 持久化优化日志
    try:
        store_ids = list({r.store_id for r in recs})
        store_id_str = store_ids[0] if store_ids else "unknown"
        db.add(GlobalOptimizationLog(
            id                       = str(uuid.uuid4()),
            store_id                 = store_id_str,
            brand_id                 = request.brand_id,
            input_count              = result.input_count,
            output_count             = result.output_count,
            conflicts_detected       = result.conflicts_detected,
            dedup_count              = result.dedup_count,
            suppressed_count         = result.suppressed_count,
            bundled_count            = result.bundled_count,
            total_impact_yuan_before = result.total_impact_yuan_before,
            total_impact_yuan_after  = result.total_impact_yuan_after,
            ai_insight               = result.ai_insight,
        ))
    except Exception as e:
        logger.warning("保存优化日志失败", error=str(e))

    try:
        await db.commit()
    except Exception:
        await db.rollback()

    return {
        "success":   True,
        "ai_insight": result.ai_insight,
        "stats": {
            "input_count":              result.input_count,
            "output_count":             result.output_count,
            "conflicts_detected":       result.conflicts_detected,
            "dedup_count":              result.dedup_count,
            "suppressed_count":         result.suppressed_count,
            "total_impact_yuan_before": float(result.total_impact_yuan_before),
            "total_impact_yuan_after":  float(result.total_impact_yuan_after),
        },
        "conflicts": [
            {
                "conflict_id":        cf.conflict_id,
                "agent_a":            cf.agent_a,
                "agent_b":            cf.agent_b,
                "conflict_type":      cf.conflict_type,
                "severity":           cf.severity,
                "description":        cf.description,
                "winning_agent":      cf.winning_agent,
                "arbitration_method": cf.arbitration_method,
                "impact_yuan_saved":  cf.impact_yuan_saved,
            }
            for cf in result.conflicts
        ],
        "optimized_recommendations": [
            {
                "id":                   r.id,
                "agent_name":           r.agent_name,
                "store_id":             r.store_id,
                "recommendation_type":  r.recommendation_type,
                "recommendation_text":  r.recommendation_text,
                "expected_impact_yuan": r.expected_impact_yuan,
                "confidence_score":     r.confidence_score,
            }
            for r in result.optimized_recommendations
        ],
    }


@router.get("/conflicts", summary="查询历史冲突记录")
async def list_conflicts(
    store_id:      Optional[str] = Query(None),
    brand_id:      Optional[str] = Query(None),
    severity:      Optional[str] = Query(None),
    status:        Optional[str] = Query(None),
    days:          int = Query(7, ge=1, le=90),
    limit:         int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """查询历史 Agent 冲突记录"""
    since = datetime.utcnow() - timedelta(days=days)
    q = select(AgentConflict).where(AgentConflict.created_at >= since).order_by(
        desc(AgentConflict.created_at)
    )
    if store_id:
        q = q.where(AgentConflict.store_id == store_id)
    if brand_id:
        q = q.where(AgentConflict.brand_id == brand_id)
    if severity:
        q = q.where(AgentConflict.severity == severity)
    if status:
        q = q.where(AgentConflict.arbitration_status == status)
    q = q.limit(limit)

    r = await db.execute(q)
    rows = r.scalars().all()
    return {
        "success": True,
        "data": [
            {
                "id":                  c.id,
                "store_id":            c.store_id,
                "agent_a":             c.agent_a,
                "agent_b":             c.agent_b,
                "conflict_type":       c.conflict_type,
                "severity":            c.severity,
                "description":         c.description,
                "arbitration_status":  c.arbitration_status,
                "arbitration_method":  c.arbitration_method,
                "winning_agent":       c.winning_agent,
                "impact_yuan_saved":   float(c.impact_yuan_saved or 0),
                "created_at":          c.created_at.isoformat() if c.created_at else None,
            }
            for c in rows
        ],
        "count": len(rows),
    }


@router.post("/conflicts/{conflict_id}/escalate", summary="人工升级冲突")
async def escalate_conflict(
    conflict_id:  str,
    note:         str = Query("", description="升级原因"),
    db:           AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """将冲突标记为需要人工处理"""
    r = await db.execute(select(AgentConflict).where(AgentConflict.id == conflict_id))
    conflict = r.scalar_one_or_none()
    if not conflict:
        raise HTTPException(status_code=404, detail=f"冲突记录 {conflict_id} 不存在")
    conflict.arbitration_status = "escalated"
    conflict.arbitration_note   = note or "人工升级"
    conflict.arbitration_method = "manual_override"
    await db.commit()
    return {"success": True, "message": "冲突已升级为人工处理"}


@router.get("/dashboard", summary="协同总线驾驶舱 BFF")
async def collab_dashboard(
    brand_id:    str   = Query(..., description="品牌 ID"),
    days:        int   = Query(7, ge=1, le=90),
    db: AsyncSession   = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    协同总线驾驶舱数据
    包含：冲突统计 / 优化效果 / Top冲突Agent对 / 近期冲突列表
    """
    since = datetime.utcnow() - timedelta(days=days)

    # 冲突统计
    conflict_rows_r = await db.execute(
        select(AgentConflict)
        .where(AgentConflict.brand_id == brand_id, AgentConflict.created_at >= since)
    )
    conflict_rows = conflict_rows_r.scalars().all()

    total_conflicts  = len(conflict_rows)
    resolved_count   = sum(1 for c in conflict_rows if c.arbitration_status == "resolved")
    escalated_count  = sum(1 for c in conflict_rows if c.arbitration_status == "escalated")
    high_severity    = sum(1 for c in conflict_rows if c.severity == "high")
    total_yuan_saved = sum(float(c.impact_yuan_saved or 0) for c in conflict_rows)

    # Top 冲突 Agent 对
    pair_counts: dict[str, int] = {}
    for c in conflict_rows:
        pair = f"{c.agent_a} vs {c.agent_b}"
        pair_counts[pair] = pair_counts.get(pair, 0) + 1
    top_pair = max(pair_counts, key=lambda k: pair_counts[k]) if pair_counts else None

    # 优化效果汇总
    opt_rows_r = await db.execute(
        select(GlobalOptimizationLog)
        .where(GlobalOptimizationLog.brand_id == brand_id, GlobalOptimizationLog.created_at >= since)
    )
    opt_rows = opt_rows_r.scalars().all()
    total_input  = sum(o.input_count  for o in opt_rows)
    total_output = sum(o.output_count for o in opt_rows)
    dedup_rate   = (1 - total_output / total_input) * 100 if total_input > 0 else 0

    # 近期冲突（最多10条）
    recent_conflicts = sorted(conflict_rows, key=lambda c: c.created_at or datetime.min, reverse=True)[:10]

    return {
        "brand_id":   brand_id,
        "period_days": days,
        "conflicts": {
            "total":          total_conflicts,
            "resolved":       resolved_count,
            "escalated":      escalated_count,
            "high_severity":  high_severity,
            "total_yuan_saved": total_yuan_saved,
            "top_conflict_pair": top_pair,
        },
        "optimization": {
            "total_runs":         len(opt_rows),
            "total_input_recs":   total_input,
            "total_output_recs":  total_output,
            "dedup_rate_pct":     round(dedup_rate, 1),
        },
        "recent_conflicts": [
            {
                "id":            c.id,
                "agent_a":       c.agent_a,
                "agent_b":       c.agent_b,
                "severity":      c.severity,
                "description":   c.description,
                "winning_agent": c.winning_agent,
                "yuan_saved":    float(c.impact_yuan_saved or 0),
                "created_at":    c.created_at.isoformat() if c.created_at else None,
            }
            for c in recent_conflicts
        ],
    }
