"""
Dynamic Trust Phase Service - 动态信任阶段服务

Replaces static time-based TrustPhase with accuracy-driven phase calculation.
Phase is determined by DecisionLog history (adoption rate, success rate, confidence)
combined with a minimum observation window.
"""
from datetime import datetime, timedelta, date
from typing import Dict, Any, Optional
from sqlalchemy import select, func, and_
import os
import structlog

from src.core.database import get_db_session
from src.models.decision_log import DecisionLog, DecisionStatus, DecisionOutcome

logger = structlog.get_logger()

# Thresholds (overridable via env)
MIN_OBSERVATION_DAYS = int(os.getenv("HITL_MIN_OBSERVATION_DAYS", "30"))
AUTONOMOUS_MIN_DAYS = int(os.getenv("HITL_AUTONOMOUS_MIN_DAYS", "90"))
AUTONOMOUS_ADOPTION_THRESHOLD = float(os.getenv("HITL_AUTONOMOUS_ADOPTION", "0.75"))
AUTONOMOUS_SUCCESS_THRESHOLD = float(os.getenv("HITL_AUTONOMOUS_SUCCESS", "0.70"))
ASSISTANCE_ADOPTION_THRESHOLD = float(os.getenv("HITL_ASSISTANCE_ADOPTION", "0.50"))
METRICS_WINDOW_DAYS = int(os.getenv("HITL_METRICS_WINDOW_DAYS", "30"))


async def compute_trust_metrics(store_id: str, days: int = METRICS_WINDOW_DAYS) -> Dict[str, Any]:
    """
    Compute trust metrics from DecisionLog for the given store.

    Returns:
        adoption_rate: fraction of decisions approved/executed (not rejected)
        success_rate: fraction of completed decisions with SUCCESS outcome
        avg_confidence: mean ai_confidence across decisions
        total_decisions: total decisions in window
        escalation_rate: fraction escalated to human review
    """
    cutoff = datetime.utcnow() - timedelta(days=days)

    async with get_db_session() as session:
        result = await session.execute(
            select(
                DecisionLog.decision_status,
                DecisionLog.outcome,
                func.avg(DecisionLog.ai_confidence).label("avg_confidence"),
                func.count(DecisionLog.id).label("count"),
            ).where(
                and_(
                    DecisionLog.store_id == store_id,
                    DecisionLog.created_at >= cutoff,
                )
            ).group_by(DecisionLog.decision_status, DecisionLog.outcome)
        )
        rows = result.all()

    if not rows:
        return {
            "adoption_rate": 0.0,
            "success_rate": 0.0,
            "avg_confidence": 0.0,
            "total_decisions": 0,
            "escalation_rate": 0.0,
            "window_days": days,
        }

    total = sum(r.count for r in rows)
    adopted = sum(
        r.count for r in rows
        if r.decision_status in (DecisionStatus.APPROVED, DecisionStatus.EXECUTED)
    )
    successful = sum(
        r.count for r in rows
        if r.outcome == DecisionOutcome.SUCCESS
    )
    completed = sum(
        r.count for r in rows
        if r.outcome in (DecisionOutcome.SUCCESS, DecisionOutcome.FAILURE, DecisionOutcome.PARTIAL)
    )
    escalated = sum(
        r.count for r in rows
        if r.decision_status == DecisionStatus.PENDING
    )
    confidences = [r.avg_confidence * r.count for r in rows if r.avg_confidence is not None]
    avg_conf = sum(confidences) / total if confidences else 0.0

    return {
        "adoption_rate": round(adopted / total, 4),
        "success_rate": round(successful / completed, 4) if completed else 0.0,
        "avg_confidence": round(avg_conf, 4),
        "total_decisions": total,
        "escalation_rate": round(escalated / total, 4),
        "window_days": days,
    }


async def compute_dynamic_phase(store_id: str) -> Dict[str, Any]:
    """
    Determine TrustPhase dynamically based on:
      1. Days since store onboarding (minimum observation window)
      2. Accuracy metrics from DecisionLog

    Phase rules:
      OBSERVATION  - fewer than MIN_OBSERVATION_DAYS elapsed, OR not enough data,
                     OR adoption_rate < ASSISTANCE_ADOPTION_THRESHOLD
      AUTONOMOUS   - days >= AUTONOMOUS_MIN_DAYS AND adoption_rate >= AUTONOMOUS_ADOPTION_THRESHOLD
                     AND success_rate >= AUTONOMOUS_SUCCESS_THRESHOLD
      ASSISTANCE   - everything in between

    Returns phase name + the metrics that drove the decision.
    """
    from src.models.store import Store

    # --- days since onboarding ---
    async with get_db_session() as session:
        result = await session.execute(
            select(Store.created_at).where(Store.id == store_id)
        )
        created_at = result.scalar_one_or_none()

    days_since_onboarding = (date.today() - created_at.date()).days if created_at else 0

    # --- accuracy metrics ---
    metrics = await compute_trust_metrics(store_id)

    adoption_rate = metrics["adoption_rate"]
    success_rate = metrics["success_rate"]
    total_decisions = metrics["total_decisions"]

    # --- phase logic ---
    if (
        days_since_onboarding < MIN_OBSERVATION_DAYS
        or total_decisions < 10
        or adoption_rate < ASSISTANCE_ADOPTION_THRESHOLD
    ):
        phase = "OBSERVATION"
        reason = (
            f"days={days_since_onboarding} < {MIN_OBSERVATION_DAYS}"
            if days_since_onboarding < MIN_OBSERVATION_DAYS
            else f"adoption_rate={adoption_rate:.0%} < {ASSISTANCE_ADOPTION_THRESHOLD:.0%}"
            if adoption_rate < ASSISTANCE_ADOPTION_THRESHOLD
            else f"insufficient data (n={total_decisions})"
        )
    elif (
        days_since_onboarding >= AUTONOMOUS_MIN_DAYS
        and adoption_rate >= AUTONOMOUS_ADOPTION_THRESHOLD
        and success_rate >= AUTONOMOUS_SUCCESS_THRESHOLD
    ):
        phase = "AUTONOMOUS"
        reason = (
            f"days={days_since_onboarding}, "
            f"adoption={adoption_rate:.0%}, "
            f"success={success_rate:.0%}"
        )
    else:
        phase = "ASSISTANCE"
        reason = (
            f"days={days_since_onboarding}, "
            f"adoption={adoption_rate:.0%}, "
            f"success={success_rate:.0%}"
        )

    logger.info(
        "dynamic_trust_phase_computed",
        store_id=store_id,
        phase=phase,
        reason=reason,
        **metrics,
    )

    return {
        "phase": phase,
        "reason": reason,
        "days_since_onboarding": days_since_onboarding,
        "metrics": metrics,
    }
