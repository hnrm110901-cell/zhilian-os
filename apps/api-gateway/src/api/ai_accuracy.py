"""
AI建议准确率回溯 API
AI Recommendation Accuracy Retrospective
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List, Dict, Any
from datetime import date, datetime, timedelta
import structlog

from ..core.dependencies import get_current_active_user, get_db
from ..models.user import User
from ..models.decision_log import DecisionLog, DecisionType, DecisionOutcome
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, case

logger = structlog.get_logger()
router = APIRouter()


@router.get("/ai-evolution/accuracy-retrospective")
async def get_accuracy_retrospective(
    store_id: Optional[str] = Query(None, description="门店ID，不传则全部门店"),
    days: int = Query(30, ge=7, le=180, description="回溯天数"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    AI建议准确率回溯：
    - 按决策类型分组的准确率
    - 按时间段的准确率趋势（每7天一个数据点）
    - AI置信度分段 vs 实际成功率
    - 总体统计
    """
    try:
        since = datetime.utcnow() - timedelta(days=days)

        conditions = [
            DecisionLog.created_at >= since,
            DecisionLog.outcome.isnot(None),
        ]
        if store_id:
            conditions.append(DecisionLog.store_id == store_id)

        result = await db.execute(
            select(DecisionLog).where(and_(*conditions))
        )
        logs = result.scalars().all()

        if not logs:
            return {
                "period_days": days,
                "store_id": store_id,
                "total_decisions": 0,
                "overall_accuracy": 0.0,
                "by_type": [],
                "weekly_trend": [],
                "confidence_buckets": [],
            }

        # 总体准确率
        success_count = sum(1 for l in logs if l.outcome == DecisionOutcome.SUCCESS)
        partial_count = sum(1 for l in logs if l.outcome == DecisionOutcome.PARTIAL)
        overall_accuracy = round((success_count + partial_count * 0.5) / len(logs) * 100, 1)

        # 按决策类型分组
        type_stats: Dict[str, Dict] = {}
        for log in logs:
            t = log.decision_type.value if log.decision_type else "unknown"
            if t not in type_stats:
                type_stats[t] = {"total": 0, "success": 0, "partial": 0, "failure": 0, "avg_confidence": 0.0, "confidences": []}
            type_stats[t]["total"] += 1
            if log.outcome == DecisionOutcome.SUCCESS:
                type_stats[t]["success"] += 1
            elif log.outcome == DecisionOutcome.PARTIAL:
                type_stats[t]["partial"] += 1
            elif log.outcome == DecisionOutcome.FAILURE:
                type_stats[t]["failure"] += 1
            if log.ai_confidence is not None:
                type_stats[t]["confidences"].append(log.ai_confidence)

        by_type = []
        for t, s in type_stats.items():
            acc = round((s["success"] + s["partial"] * 0.5) / s["total"] * 100, 1) if s["total"] > 0 else 0
            avg_conf = round(sum(s["confidences"]) / len(s["confidences"]) * 100, 1) if s["confidences"] else 0
            by_type.append({
                "decision_type": t,
                "total": s["total"],
                "success": s["success"],
                "partial": s["partial"],
                "failure": s["failure"],
                "accuracy": acc,
                "avg_confidence": avg_conf,
            })
        by_type.sort(key=lambda x: x["total"], reverse=True)

        # 每7天一个趋势点
        weekly_trend = []
        for week_offset in range(days // 7):
            week_end = datetime.utcnow() - timedelta(days=week_offset * 7)
            week_start = week_end - timedelta(days=7)
            week_logs = [l for l in logs if week_start <= l.created_at <= week_end]
            if not week_logs:
                continue
            w_success = sum(1 for l in week_logs if l.outcome == DecisionOutcome.SUCCESS)
            w_partial = sum(1 for l in week_logs if l.outcome == DecisionOutcome.PARTIAL)
            w_acc = round((w_success + w_partial * 0.5) / len(week_logs) * 100, 1)
            weekly_trend.append({
                "week_start": week_start.strftime("%Y-%m-%d"),
                "week_end": week_end.strftime("%Y-%m-%d"),
                "total": len(week_logs),
                "accuracy": w_acc,
            })
        weekly_trend.reverse()

        # 置信度分桶（0-20%, 20-40%, 40-60%, 60-80%, 80-100%）
        buckets = [
            {"label": "0-20%", "min": 0.0, "max": 0.2},
            {"label": "20-40%", "min": 0.2, "max": 0.4},
            {"label": "40-60%", "min": 0.4, "max": 0.6},
            {"label": "60-80%", "min": 0.6, "max": 0.8},
            {"label": "80-100%", "min": 0.8, "max": 1.01},
        ]
        confidence_buckets = []
        for b in buckets:
            bucket_logs = [l for l in logs if l.ai_confidence is not None and b["min"] <= l.ai_confidence < b["max"]]
            if not bucket_logs:
                continue
            b_success = sum(1 for l in bucket_logs if l.outcome == DecisionOutcome.SUCCESS)
            b_partial = sum(1 for l in bucket_logs if l.outcome == DecisionOutcome.PARTIAL)
            b_acc = round((b_success + b_partial * 0.5) / len(bucket_logs) * 100, 1)
            confidence_buckets.append({
                "confidence_range": b["label"],
                "total": len(bucket_logs),
                "accuracy": b_acc,
            })

        return {
            "period_days": days,
            "store_id": store_id,
            "total_decisions": len(logs),
            "overall_accuracy": overall_accuracy,
            "by_type": by_type,
            "weekly_trend": weekly_trend,
            "confidence_buckets": confidence_buckets,
        }

    except Exception as e:
        logger.error("accuracy_retrospective_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
