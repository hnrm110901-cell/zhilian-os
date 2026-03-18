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
        When skip_if_exists=False (--force), truncates the table first to avoid
        duplicates, since each insert generates a fresh UUID and ON CONFLICT
        only catches PK collisions.
        """
        if skip_if_exists and await self._rule_count() > 0:
            logger.info("hr_knowledge_rules already seeded, skipping.")
            return 0

        if not skip_if_exists:
            await self._session.execute(
                sa.text("TRUNCATE TABLE hr_knowledge_rules")
            )

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
        When skip_if_exists=False (--force), truncates the table first to avoid
        duplicates, since each insert generates a fresh UUID and ON CONFLICT
        only catches PK collisions.
        """
        if skip_if_exists and await self._skill_count() > 0:
            logger.info("skill_nodes already seeded, skipping.")
            return 0

        if not skip_if_exists:
            await self._session.execute(
                sa.text("TRUNCATE TABLE skill_nodes CASCADE")
            )

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

    async def load_xuji_org(self, skip_if_exists: bool = True) -> int:
        """加载徐记海鲜组织架构种子数据"""
        if skip_if_exists:
            result = await self._session.execute(
                sa.text("SELECT COUNT(*) FROM org_nodes WHERE id = :id"),
                {"id": "xj-group"},
            )
            if (result.scalar() or 0) > 0:
                logger.info("xuji org nodes already seeded, skipping.")
                return 0

        nodes = self._load_json("xuji_org_seed.json")
        inserted = 0
        for node in nodes:
            await self._session.execute(
                sa.text(
                    "INSERT INTO org_nodes "
                    "(id, name, node_type, parent_id, path, depth, is_active, sort_order) "
                    "VALUES (:id, :name, :node_type, :parent_id, :path, :depth, true, 0) "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                {
                    "id": node["id"],
                    "name": node["name"],
                    "node_type": node["node_type"],
                    "parent_id": node.get("parent_id"),
                    "path": node["path"],
                    "depth": node["depth"],
                },
            )
            inserted += 1

        await self._session.commit()
        logger.info("Inserted %d xuji org nodes.", inserted)
        return inserted

    async def load_xuji_employees(self, skip_if_exists: bool = True) -> int:
        """加载徐记海鲜员工种子数据"""
        if skip_if_exists:
            result = await self._session.execute(
                sa.text("SELECT COUNT(*) FROM persons WHERE phone LIKE :pattern"),
                {"pattern": "13800138%"},
            )
            if (result.scalar() or 0) > 0:
                logger.info("xuji employees already seeded, skipping.")
                return 0

        employees = self._load_json("xuji_employees_seed.json")
        inserted = 0
        for emp in employees:
            person_id = str(uuid.uuid4())
            await self._session.execute(
                sa.text(
                    "INSERT INTO persons "
                    "(id, name, phone, id_number, preferences) "
                    "VALUES (:id, :name, :phone, :id_number, :preferences::jsonb)"
                ),
                {
                    "id": person_id,
                    "name": emp["name"],
                    "phone": emp["phone"],
                    "id_number": emp.get("id_number"),
                    "preferences": json.dumps({}),
                },
            )

            assignment_id = str(uuid.uuid4())
            await self._session.execute(
                sa.text(
                    "INSERT INTO employment_assignments "
                    "(id, person_id, org_node_id, employment_type, start_date, status) "
                    "VALUES (:id, :person_id, :org_node_id, :employment_type, "
                    "        :start_date, :status)"
                ),
                {
                    "id": assignment_id,
                    "person_id": person_id,
                    "org_node_id": emp["org_node_id"],
                    "employment_type": emp.get("employment_type", "full_time"),
                    "start_date": emp["start_date"],
                    "status": "active",
                },
            )

            contract_id = str(uuid.uuid4())
            await self._session.execute(
                sa.text(
                    "INSERT INTO employment_contracts "
                    "(id, assignment_id, contract_type, pay_scheme, valid_from) "
                    "VALUES (:id, :assignment_id, :contract_type, "
                    "        :pay_scheme::jsonb, :valid_from)"
                ),
                {
                    "id": contract_id,
                    "assignment_id": assignment_id,
                    "contract_type": "labor",
                    "pay_scheme": json.dumps(emp.get("pay_scheme", {})),
                    "valid_from": emp["start_date"],
                },
            )
            inserted += 1

        await self._session.commit()
        logger.info("Inserted %d xuji employees.", inserted)
        return inserted

    async def load_xuji_attendance_rules(self, skip_if_exists: bool = True) -> int:
        """加载徐记海鲜考勤规则种子数据到 attendance_rules 表"""
        if skip_if_exists:
            result = await self._session.execute(
                sa.text(
                    "SELECT COUNT(*) FROM attendance_rules "
                    "WHERE org_node_id = :org"
                ),
                {"org": "xj-brand"},
            )
            if (result.scalar() or 0) > 0:
                logger.info("xuji attendance rules already seeded, skipping.")
                return 0

        rules = self._load_json("xuji_attendance_rules.json")
        inserted = 0
        for rule in rules:
            await self._session.execute(
                sa.text(
                    "INSERT INTO attendance_rules "
                    "(id, name, rule_config, org_node_id) "
                    "VALUES (:id, :name, :rule_config::jsonb, :org_node_id) "
                    "ON CONFLICT DO NOTHING"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "name": rule["name"],
                    "rule_config": json.dumps(rule["rule_config"]),
                    "org_node_id": rule.get("org_node_id"),
                },
            )
            inserted += 1

        await self._session.commit()
        logger.info("Inserted %d xuji attendance rules.", inserted)
        return inserted

    # ── private ───────────────────────────────────────────────────────────

    async def _skill_count(self) -> int:
        result = await self._session.execute(
            sa.text("SELECT COUNT(*) FROM skill_nodes")
        )
        return result.scalar() or 0
