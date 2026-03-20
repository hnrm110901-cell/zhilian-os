"""HrKnowledgeService — Rule retrieval + skill graph traversal for HRAgent v1.

技能图谱查询能力（P1-5 PostgreSQL 替代 Neo4j）：
- get_prerequisite_chain: 递归 CTE 获取完整前置技能链
- get_dependent_skills: 反向查找依赖某技能的所有下游技能
- validate_skill_order: 拓扑排序验证技能学习顺序合法性
"""
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
            # N.B.: the f-string below injects only parameter *names* (:excl_0, :excl_1, ...)
            # into the SQL text, never data values — actual UUIDs go through the params dict.
            # This is the standard SQLAlchemy pattern for parameterized IN clauses.
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

    # ─────────────────────────────────────────────────────────────────────
    # P1-5: PostgreSQL 图查询（替代 Neo4j 技能图谱）
    # ─────────────────────────────────────────────────────────────────────

    async def get_prerequisite_chain(
        self,
        skill_id: uuid.UUID,
        max_depth: int = 10,
    ) -> list[dict]:
        """递归获取技能的完整前置依赖链（PostgreSQL 递归 CTE）。

        返回按依赖深度排序的技能列表（深度0=直接前置，深度1=前置的前置...）。
        自动检测循环依赖，防止无限递归。

        Args:
            skill_id: 目标技能 UUID
            max_depth: 最大递归深度（防止死循环，默认10）

        Returns:
            [{"id": ..., "skill_name": ..., "depth": 0}, ...]
        """
        result = await self._session.execute(
            sa.text("""
                WITH RECURSIVE prereq_chain AS (
                    -- 锚点：目标技能的直接前置
                    SELECT
                        unnest(sn.prerequisite_skill_ids) AS prereq_id,
                        0 AS depth,
                        ARRAY[sn.id] AS visited
                    FROM skill_nodes sn
                    WHERE sn.id = :skill_id
                      AND sn.prerequisite_skill_ids IS NOT NULL

                    UNION ALL

                    -- 递归：前置技能的前置
                    SELECT
                        unnest(sn2.prerequisite_skill_ids) AS prereq_id,
                        pc.depth + 1 AS depth,
                        pc.visited || sn2.id
                    FROM prereq_chain pc
                    JOIN skill_nodes sn2 ON sn2.id = pc.prereq_id
                    WHERE pc.depth < :max_depth
                      AND sn2.prerequisite_skill_ids IS NOT NULL
                      AND NOT (sn2.id = ANY(pc.visited))  -- 防循环
                )
                SELECT DISTINCT ON (sn3.id)
                    sn3.id,
                    sn3.skill_name,
                    sn3.category,
                    sn3.estimated_revenue_lift,
                    pc2.depth
                FROM prereq_chain pc2
                JOIN skill_nodes sn3 ON sn3.id = pc2.prereq_id
                ORDER BY sn3.id, pc2.depth ASC
            """),
            {"skill_id": str(skill_id), "max_depth": max_depth},
        )

        rows = result.fetchall()
        return [
            {
                "id": str(r._mapping["id"]),
                "skill_name": r._mapping["skill_name"],
                "category": r._mapping.get("category"),
                "estimated_revenue_lift": float(r._mapping.get("estimated_revenue_lift") or 0),
                "depth": r._mapping["depth"],
            }
            for r in rows
        ]

    async def get_dependent_skills(
        self,
        skill_id: uuid.UUID,
    ) -> list[dict]:
        """查找所有依赖指定技能的下游技能（反向图查询）。

        即：哪些技能的 prerequisite_skill_ids 包含 skill_id。

        Args:
            skill_id: 被依赖的技能 UUID

        Returns:
            [{"id": ..., "skill_name": ..., "category": ...}, ...]
        """
        result = await self._session.execute(
            sa.text("""
                SELECT id, skill_name, category, estimated_revenue_lift
                FROM skill_nodes
                WHERE :skill_id = ANY(prerequisite_skill_ids)
                ORDER BY skill_name
            """),
            {"skill_id": str(skill_id)},
        )

        rows = result.fetchall()
        return [
            {
                "id": str(r._mapping["id"]),
                "skill_name": r._mapping["skill_name"],
                "category": r._mapping.get("category"),
                "estimated_revenue_lift": float(r._mapping.get("estimated_revenue_lift") or 0),
            }
            for r in rows
        ]

    @staticmethod
    def validate_skill_order(
        skill_graph: dict[str, list[str]],
        achieved_order: list[str],
    ) -> tuple[bool, list[str]]:
        """验证技能学习顺序是否满足前置依赖（纯函数，无DB依赖）。

        使用拓扑排序验证：每个已学技能的所有前置技能必须在它之前出现。

        Args:
            skill_graph: {skill_id: [prerequisite_skill_ids]} 邻接表
            achieved_order: 技能学习顺序 [先学的, ..., 后学的]

        Returns:
            (is_valid, violations) — violations 格式: ["skill_X 缺少前置 skill_Y"]
        """
        achieved_set: set[str] = set()
        violations: list[str] = []

        for skill_id in achieved_order:
            prereqs = skill_graph.get(skill_id, [])
            for prereq in prereqs:
                if prereq not in achieved_set:
                    violations.append(f"{skill_id} 缺少前置 {prereq}")
            achieved_set.add(skill_id)

        return (len(violations) == 0, violations)
