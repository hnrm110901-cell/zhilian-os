"""HrSeedService — HR知识库冷启动数据加载器

用法（CLI）：
    python -m src.cli.seed_hr_knowledge
"""
import json
import uuid
import logging
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent.parent.parent / "data"


class HrSeedService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── public ────────────────────────────────────────────────────────────

    async def load_rules(self, skip_if_exists: bool = True) -> int:
        """Load hr_seed_rules.json into hr_knowledge_rules.

        Returns number of rows inserted (0 if skipped).
        Uses ON CONFLICT DO NOTHING to handle re-runs safely.
        """
        if skip_if_exists and await self._rule_count() > 0:
            logger.info("hr_knowledge_rules already seeded, skipping.")
            return 0

        rules = self._load_json("hr_seed_rules.json")
        inserted = 0
        for rule in rules:
            await self._session.execute(
                sa.text(
                    "INSERT INTO hr_knowledge_rules "
                    "(id, rule_type, category, condition, action, "
                    " expected_impact, confidence, industry_source, is_active) "
                    "VALUES (:id, :rule_type, :category, :condition::jsonb, "
                    "        :action::jsonb, :expected_impact::jsonb, "
                    "        :confidence, :industry_source, true) "
                    "ON CONFLICT DO NOTHING"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "rule_type": rule.get("rule_type", "sop"),
                    "category": rule.get("category"),
                    "condition": json.dumps(rule.get("condition", {})),
                    "action": json.dumps(rule.get("action", {})),
                    "expected_impact": json.dumps(rule.get("expected_impact") or {}),
                    "confidence": rule.get("confidence", 0.8),
                    "industry_source": rule.get("industry_source"),
                },
            )
            inserted += 1

        await self._session.commit()
        logger.info("Inserted %d HR knowledge rules.", inserted)
        return inserted

    async def load_skills(self, skip_if_exists: bool = True) -> int:
        """Load hr_seed_skills.json into skill_nodes.

        Returns number of rows inserted (0 if skipped).
        Uses ON CONFLICT DO NOTHING to handle re-runs safely.
        """
        if skip_if_exists and await self._skill_count() > 0:
            logger.info("skill_nodes already seeded, skipping.")
            return 0

        skills = self._load_json("hr_seed_skills.json")
        inserted = 0
        for skill in skills:
            await self._session.execute(
                sa.text(
                    "INSERT INTO skill_nodes "
                    "(id, skill_name, category, description, "
                    " kpi_impact, estimated_revenue_lift) "
                    "VALUES (:id, :skill_name, :category, :description, "
                    "        :kpi_impact::jsonb, :estimated_revenue_lift) "
                    "ON CONFLICT DO NOTHING"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "skill_name": skill["skill_name"],
                    "category": skill.get("category"),
                    "description": skill.get("description"),
                    "kpi_impact": json.dumps(skill.get("kpi_impact") or {}),
                    "estimated_revenue_lift": skill.get("estimated_revenue_lift"),
                },
            )
            inserted += 1

        await self._session.commit()
        logger.info("Inserted %d skill nodes.", inserted)
        return inserted

    # ── private ───────────────────────────────────────────────────────────

    def _load_json(self, filename: str) -> list[dict[str, Any]]:
        path = _DATA_DIR / filename
        with path.open(encoding="utf-8") as f:
            return json.load(f)

    async def _rule_count(self) -> int:
        result = await self._session.execute(
            sa.text("SELECT COUNT(*) FROM hr_knowledge_rules")
        )
        return result.scalar() or 0

    async def _skill_count(self) -> int:
        result = await self._session.execute(
            sa.text("SELECT COUNT(*) FROM skill_nodes")
        )
        return result.scalar() or 0
