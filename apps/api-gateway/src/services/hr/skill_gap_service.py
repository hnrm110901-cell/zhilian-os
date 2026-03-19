"""SkillGapService — per-person skill gap analysis + next-skill recommendation (WF-3)."""
import uuid

import structlog
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from .knowledge_service import HrKnowledgeService

logger = structlog.get_logger()


class SkillGapService:
    """Analyze skill gaps and recommend next skill with revenue impact."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._knowledge = HrKnowledgeService(session=session)

    async def analyze_person(self, person_id: uuid.UUID) -> dict:
        """Full skill gap analysis for a single person.

        Returns:
            {
                "person_id": str,
                "achieved_skills": [...],
                "next_recommended": {...} | None,
                "total_potential_yuan": float,
            }
        """
        achieved = await self._knowledge.get_skills_for_person(person_id)

        # Try each standard category
        best_next = None
        total_potential = 0.0
        for category in ("service", "kitchen", "management", "compliance"):
            next_skill = await self._knowledge.get_next_skill_for_person(
                person_id, target_category=category
            )
            if next_skill:
                lift = next_skill.get("estimated_revenue_lift", 0) or 0
                total_potential += float(lift)
                if best_next is None or float(lift) > float(
                    best_next.get("estimated_revenue_lift", 0) or 0
                ):
                    best_next = next_skill

        return {
            "person_id": str(person_id),
            "achieved_skills": achieved,
            "next_recommended": best_next,
            "total_potential_yuan": round(total_potential, 2),
        }

    async def analyze_store(self, org_node_id: str) -> list[dict]:
        """Analyze skill gaps for all active employees in a store.

        Returns list of per-person gap analyses.
        """
        result = await self._session.execute(
            sa.text(
                "SELECT ea.person_id "
                "FROM employment_assignments ea "
                "WHERE ea.org_node_id = :org_node_id "
                "  AND ea.status = 'active'"
            ),
            {"org_node_id": org_node_id},
        )
        person_ids = result.scalars().all()

        analyses = []
        for pid in person_ids:
            try:
                analysis = await self.analyze_person(uuid.UUID(str(pid)))
                analyses.append(analysis)
            except Exception as exc:
                logger.warning(
                    "hr_skill_gap.person_analysis_failed",
                    person_id=str(pid),
                    error=str(exc),
                )

        return analyses
