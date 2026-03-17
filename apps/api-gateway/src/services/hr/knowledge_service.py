"""HrKnowledgeService — Rule retrieval + skill graph traversal for HRAgent v1."""
import uuid
from typing import Optional

import structlog
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


class HrKnowledgeService:
    """Query HR knowledge rules and skill graph."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def query_rules(
        self,
        category: Optional[str] = None,
        rule_type: Optional[str] = None,
    ) -> list[dict]:
        """Fetch active hr_knowledge_rules, optionally filtered."""
        if category and rule_type:
            result = await self._session.execute(
                sa.text(
                    "SELECT id, rule_type, category, condition, action, "
                    "       expected_impact, confidence, industry_source "
                    "FROM hr_knowledge_rules "
                    "WHERE is_active = true AND category = :category "
                    "  AND rule_type = :rule_type "
                    "ORDER BY confidence DESC"
                ),
                {"category": category, "rule_type": rule_type},
            )
        elif category:
            result = await self._session.execute(
                sa.text(
                    "SELECT id, rule_type, category, condition, action, "
                    "       expected_impact, confidence, industry_source "
                    "FROM hr_knowledge_rules "
                    "WHERE is_active = true AND category = :category "
                    "ORDER BY confidence DESC"
                ),
                {"category": category},
            )
        elif rule_type:
            result = await self._session.execute(
                sa.text(
                    "SELECT id, rule_type, category, condition, action, "
                    "       expected_impact, confidence, industry_source "
                    "FROM hr_knowledge_rules "
                    "WHERE is_active = true AND rule_type = :rule_type "
                    "ORDER BY confidence DESC"
                ),
                {"rule_type": rule_type},
            )
        else:
            result = await self._session.execute(
                sa.text(
                    "SELECT id, rule_type, category, condition, action, "
                    "       expected_impact, confidence, industry_source "
                    "FROM hr_knowledge_rules "
                    "WHERE is_active = true "
                    "ORDER BY confidence DESC"
                ),
            )

        rows = result.fetchall()
        return [
            {
                "id": str(row._mapping["id"]) if hasattr(row, '_mapping') else str(row.id),
                "rule_type": row._mapping.get("rule_type", "") if hasattr(row, '_mapping') else row.rule_type,
                "category": row._mapping.get("category") if hasattr(row, '_mapping') else row.category,
                "condition": row._mapping.get("condition", {}) if hasattr(row, '_mapping') else row.condition,
                "action": row._mapping.get("action", {}) if hasattr(row, '_mapping') else row.action,
                "confidence": row._mapping.get("confidence", 0) if hasattr(row, '_mapping') else row.confidence,
            }
            for row in rows
        ]

    async def get_skills_for_person(self, person_id: uuid.UUID) -> list[str]:
        """Return skill_names the person has achieved."""
        result = await self._session.execute(
            sa.text(
                "SELECT sn.skill_name "
                "FROM person_achievements pa "
                "JOIN skill_nodes sn ON sn.id = pa.skill_node_id "
                "WHERE pa.person_id = :person_id "
                "ORDER BY pa.achieved_at DESC"
            ),
            {"person_id": str(person_id)},
        )
        rows = result.fetchall()
        return [row.skill_name for row in rows]

    async def get_next_skill_for_person(
        self,
        person_id: uuid.UUID,
        target_category: str = "service",
    ) -> Optional[dict]:
        """Return the highest-revenue-lift unachieved skill in category.

        Returns None if person has all skills in category.
        """
        # Get already-achieved skill IDs
        achieved_result = await self._session.execute(
            sa.text(
                "SELECT skill_node_id FROM person_achievements "
                "WHERE person_id = :person_id"
            ),
            {"person_id": str(person_id)},
        )
        achieved_ids = achieved_result.scalars().all()

        # Find unskilled nodes in category, ordered by revenue lift
        if achieved_ids:
            # Build safe parameterized exclusion
            placeholders = ", ".join(f":excl_{i}" for i in range(len(achieved_ids)))
            params = {
                "category": target_category,
                **{f"excl_{i}": str(aid) for i, aid in enumerate(achieved_ids)},
            }
            result = await self._session.execute(
                sa.text(
                    f"SELECT id, skill_name, estimated_revenue_lift, category "
                    f"FROM skill_nodes "
                    f"WHERE category = :category "
                    f"  AND id NOT IN ({placeholders}) "
                    f"ORDER BY COALESCE(estimated_revenue_lift, 0) DESC "
                    f"LIMIT 1"
                ),
                params,
            )
        else:
            result = await self._session.execute(
                sa.text(
                    "SELECT id, skill_name, estimated_revenue_lift, category "
                    "FROM skill_nodes "
                    "WHERE category = :category "
                    "ORDER BY COALESCE(estimated_revenue_lift, 0) DESC "
                    "LIMIT 1"
                ),
                {"category": target_category},
            )

        rows = result.fetchall()
        if not rows:
            return None

        row = rows[0]
        return {
            "id": str(row._mapping["id"]) if hasattr(row, '_mapping') else str(row.id),
            "skill_name": row._mapping.get("skill_name", "") if hasattr(row, '_mapping') else row.skill_name,
            "estimated_revenue_lift": float(
                row._mapping.get("estimated_revenue_lift", 0) if hasattr(row, '_mapping')
                else (row.estimated_revenue_lift or 0)
            ),
            "category": row._mapping.get("category", "") if hasattr(row, '_mapping') else row.category,
        }
