"""RetentionRiskService — rule-based retention risk scoring + WF-1 store scan.

B级 implementation: simple heuristic scoring, no ML.
Score formula: min(1.0, baseline + new_hire_factor + no_achievement_factor + existing_signal_blend)
"""
import json
import uuid
from datetime import date
from typing import Optional

import structlog
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# Lazy import to avoid circular import at module level
wechat_service = None


def _get_wechat_service():
    global wechat_service
    if wechat_service is None:
        try:
            from src.services.wechat_work_message_service import wechat_work_message_service as _ws
            wechat_service = _ws
        except ImportError:
            logger.warning("hr_retention.wechat_import_failed")
    return wechat_service


_BASELINE_RISK = 0.3
_NEW_HIRE_BONUS = 0.2       # <90 days tenure
_NO_ACHIEVEMENT_BONUS = 0.2  # zero person_achievements
_EXISTING_SIGNAL_WEIGHT = 0.5
_HIGH_RISK_THRESHOLD = 0.70
_ESTIMATED_RECRUITMENT_COST_YUAN = 3000.00


class RetentionRiskService:
    """Compute and manage retention risk signals."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def compute_risk_for_assignment(
        self,
        assignment_id: uuid.UUID,
        session: Optional[AsyncSession] = None,
    ) -> float:
        """Rule-based risk score 0.0-1.0.

        Formula: min(1.0, 0.3 + new_hire*0.2 + no_achievements*0.2 + existing_signal*0.5)
        """
        s = session or self._session

        # Fetch start_date and person_id in one round-trip
        assignment_result = await s.execute(
            sa.text(
                "SELECT start_date, person_id FROM employment_assignments "
                "WHERE id = :aid"
            ),
            {"aid": str(assignment_id)},
        )
        row = assignment_result.fetchone()
        if row is None:
            return 0.0
        start_date = row.start_date
        person_id = row.person_id

        score = _BASELINE_RISK

        # New hire factor
        if start_date and (date.today() - start_date).days < 90:
            score += _NEW_HIRE_BONUS

        # Achievement factor
        if person_id:
            ach_result = await s.execute(
                sa.text(
                    "SELECT COUNT(*) FROM person_achievements "
                    "WHERE person_id = :pid"
                ),
                {"pid": str(person_id)},
            )
            ach_count = ach_result.scalar() or 0
            if ach_count == 0:
                score += _NO_ACHIEVEMENT_BONUS

        # Existing signal blend
        sig_result = await s.execute(
            sa.text(
                "SELECT risk_score FROM retention_signals "
                "WHERE assignment_id = :aid "
                "ORDER BY computed_at DESC LIMIT 1"
            ),
            {"aid": str(assignment_id)},
        )
        existing_score = sig_result.scalar_one_or_none()
        if existing_score is not None:
            score += float(existing_score) * _EXISTING_SIGNAL_WEIGHT

        return min(1.0, score)

    async def scan_store(self, org_node_id: str) -> tuple[list[dict], int]:
        """WF-1: compute risk for all active assignments in store.

        Returns (high_risk_list, total_scanned_count).
        high_risk_list: entries with score > 0.70.
        total_scanned_count: all active assignments processed.
        Writes retention_signals for each assignment.
        """
        # Get active assignments
        assign_result = await self._session.execute(
            sa.text(
                "SELECT ea.id, ea.person_id, ea.start_date "
                "FROM employment_assignments ea "
                "WHERE ea.org_node_id = :org_node_id "
                "  AND ea.status = 'active'"
            ),
            {"org_node_id": org_node_id},
        )
        assignments = assign_result.fetchall()

        high_risk = []
        for row in assignments:
            aid = row.id if hasattr(row, 'id') else row[0]
            person_id = row.person_id if hasattr(row, 'person_id') else row[1]

            risk_score = await self.compute_risk_for_assignment(
                uuid.UUID(str(aid)), session=self._session
            )

            risk_factors = {
                "computed_by": "rule_based_v1",
                "threshold": _HIGH_RISK_THRESHOLD,
            }

            # Insert new retention_signal row (history tracking)
            await self._session.execute(
                sa.text(
                    "INSERT INTO retention_signals "
                    "(id, assignment_id, risk_score, risk_factors, "
                    " intervention_status, computed_at) "
                    "VALUES (:id, :aid, :score, :factors::jsonb, "
                    "        'pending', NOW())"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "aid": str(aid),
                    "score": risk_score,
                    "factors": json.dumps(risk_factors),
                },
            )

            if risk_score >= _HIGH_RISK_THRESHOLD:
                # Look up person name
                name_result = await self._session.execute(
                    sa.text("SELECT name FROM persons WHERE id = :pid"),
                    {"pid": str(person_id)},
                )
                person_name = name_result.scalar_one_or_none() or "未知"

                high_risk.append({
                    "assignment_id": str(aid),
                    "person_id": str(person_id),
                    "person_name": person_name,
                    "risk_score": round(risk_score, 2),
                    "risk_factors": risk_factors,
                })

        await self._session.commit()

        total_scanned = len(assignments)
        logger.info(
            "hr_retention.scan_complete",
            org_node_id=org_node_id,
            total_scanned=total_scanned,
            high_risk_count=len(high_risk),
        )
        return high_risk, total_scanned

    async def run_wf1_for_store(self, org_node_id: str) -> dict:
        """Full WF-1: scan → push WeChat alerts for high-risk.

        Returns {scanned: int, high_risk: int, alerted: int}.
        """
        high_risk, total_scanned = await self.scan_store(org_node_id)

        alerted = 0
        for entry in high_risk:
            try:
                ws = _get_wechat_service()
                if ws is None:
                    logger.warning("hr_retention.wechat_unavailable")
                    continue
                message = (
                    f"【离职风险预警】\n"
                    f"员工: {entry['person_name']}\n"
                    f"风险分: {entry['risk_score']}\n"
                    f"建议: 安排1对1面谈，了解诉求，预期挽留可避免¥{_ESTIMATED_RECRUITMENT_COST_YUAN:.2f}招聘成本"
                )
                await ws.send_text_message(content=message)
                alerted += 1
            except Exception as exc:
                logger.warning(
                    "hr_retention.wechat_alert_failed",
                    person_name=entry["person_name"],
                    error=str(exc),
                )

        return {
            "scanned": total_scanned,
            "high_risk": len(high_risk),
            "alerted": alerted,
        }
