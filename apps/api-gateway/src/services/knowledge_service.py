"""知识OS层核心服务

提供技能图谱、知识采集、技能认证、行为模式、离职风险信号的 CRUD 与查询。
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.achievement import Achievement
from src.models.behavior_pattern import BehaviorPattern
from src.models.knowledge_capture import KnowledgeCapture
from src.models.retention_signal import RetentionSignal
from src.models.skill_node import SkillNode


class KnowledgeService:
    """知识OS层核心服务"""

    # ── 技能节点 ──────────────────────────────────────────────

    @staticmethod
    async def create_skill_node(db: AsyncSession, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建技能节点"""
        node = SkillNode(
            id=uuid4(),
            skill_id=data["skill_id"],
            name=data["name"],
            category=data.get("category"),
            max_level=data.get("max_level", 5),
            kpi_impact=data.get("kpi_impact", {}),
            estimated_revenue_lift=data.get("estimated_revenue_lift", 0.0),
            prerequisites=data.get("prerequisites", []),
            related_trainings=data.get("related_trainings", []),
            description=data.get("description"),
            is_active=True,
        )
        db.add(node)
        await db.commit()
        await db.refresh(node)
        return {
            "id": str(node.id),
            "skill_id": node.skill_id,
            "name": node.name,
            "category": node.category,
            "max_level": node.max_level,
            "kpi_impact": node.kpi_impact,
            "estimated_revenue_lift": node.estimated_revenue_lift,
            "is_active": node.is_active,
        }

    @staticmethod
    async def list_skill_nodes(
        db: AsyncSession, category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """列出技能节点（可按 category 过滤）"""
        stmt = select(SkillNode).where(SkillNode.is_active.is_(True))
        if category:
            stmt = stmt.where(SkillNode.category == category)
        result = await db.execute(stmt)
        nodes = result.scalars().all()
        return [
            {
                "id": str(n.id),
                "skill_id": n.skill_id,
                "name": n.name,
                "category": n.category,
                "max_level": n.max_level,
                "kpi_impact": n.kpi_impact,
                "estimated_revenue_lift": n.estimated_revenue_lift,
            }
            for n in nodes
        ]

    # ── 知识采集 ──────────────────────────────────────────────

    @staticmethod
    async def capture_knowledge(db: AsyncSession, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建知识采集记录（status=draft）"""
        capture = KnowledgeCapture(
            id=uuid4(),
            person_id=data["person_id"],
            trigger_type=data["trigger_type"],
            trigger_context=data.get("trigger_context", {}),
            context=data.get("context"),
            action=data.get("action"),
            result=data.get("result"),
            status="draft",
            capture_method=data.get("capture_method", "dialogue"),
        )
        db.add(capture)
        await db.commit()
        await db.refresh(capture)
        return {
            "id": str(capture.id),
            "person_id": str(capture.person_id),
            "trigger_type": capture.trigger_type,
            "status": capture.status,
        }

    @staticmethod
    async def review_knowledge(
        db: AsyncSession,
        capture_id: str,
        quality_score: str,
        reviewer: str,
    ) -> Dict[str, Any]:
        """审核知识（更新 status=reviewed）"""
        stmt = select(KnowledgeCapture).where(KnowledgeCapture.id == capture_id)
        result = await db.execute(stmt)
        capture = result.scalar_one_or_none()
        if not capture:
            raise ValueError(f"KnowledgeCapture {capture_id} not found")
        capture.status = "reviewed"
        capture.quality_score = quality_score
        capture.reviewed_by = reviewer
        capture.reviewed_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(capture)
        return {
            "id": str(capture.id),
            "status": capture.status,
            "quality_score": capture.quality_score,
            "reviewed_by": str(capture.reviewed_by),
        }

    # ── 技能认证 ──────────────────────────────────────────────

    @staticmethod
    async def record_achievement(db: AsyncSession, data: Dict[str, Any]) -> Dict[str, Any]:
        """记录技能认证"""
        achievement = Achievement(
            id=uuid4(),
            person_id=data["person_id"],
            skill_node_id=data["skill_node_id"],
            level=data.get("level", 1),
            achieved_at=data.get("achieved_at", datetime.now(timezone.utc)),
            evidence=data.get("evidence", {}),
            verification_method=data.get("verification_method"),
            is_valid="valid",
        )
        db.add(achievement)
        await db.commit()
        await db.refresh(achievement)
        return {
            "id": str(achievement.id),
            "person_id": str(achievement.person_id),
            "skill_node_id": str(achievement.skill_node_id),
            "level": achievement.level,
            "is_valid": achievement.is_valid,
        }

    @staticmethod
    async def get_person_skill_passport(
        db: AsyncSession, person_id: str
    ) -> Dict[str, Any]:
        """获取员工技能护照（所有有效认证）"""
        stmt = (
            select(Achievement)
            .where(Achievement.person_id == person_id)
            .where(Achievement.is_valid == "valid")
        )
        result = await db.execute(stmt)
        achievements = result.scalars().all()
        return {
            "person_id": str(person_id),
            "total_achievements": len(achievements),
            "achievements": [
                {
                    "id": str(a.id),
                    "skill_node_id": str(a.skill_node_id),
                    "level": a.level,
                    "achieved_at": a.achieved_at.isoformat() if a.achieved_at else None,
                    "evidence": a.evidence,
                    "is_valid": a.is_valid,
                }
                for a in achievements
            ],
        }

    # ── 行为模式 ──────────────────────────────────────────────

    @staticmethod
    async def detect_behavior_pattern(db: AsyncSession, data: Dict[str, Any]) -> Dict[str, Any]:
        """记录行为模式"""
        pattern = BehaviorPattern(
            id=uuid4(),
            pattern_type=data["pattern_type"],
            name=data.get("name"),
            description=data.get("description"),
            feature_vector=data.get("feature_vector", {}),
            outcome=data.get("outcome"),
            confidence=data.get("confidence", 0.0),
            sample_size=data.get("sample_size", 0),
            is_active=True,
            version=data.get("version", 1),
        )
        db.add(pattern)
        await db.commit()
        await db.refresh(pattern)
        return {
            "id": str(pattern.id),
            "pattern_type": pattern.pattern_type,
            "confidence": pattern.confidence,
            "is_active": pattern.is_active,
        }

    # ── 离职风险信号 ──────────────────────────────────────────

    @staticmethod
    async def create_retention_signal(db: AsyncSession, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建离职风险信号"""
        signal = RetentionSignal(
            id=uuid4(),
            assignment_id=data["assignment_id"],
            risk_score=data["risk_score"],
            risk_level=data.get("risk_level", "medium"),
            risk_factors=data.get("risk_factors", {}),
            intervention_status="none",
            model_version=data.get("model_version"),
            computed_at=data.get("computed_at", datetime.now(timezone.utc)),
        )
        db.add(signal)
        await db.commit()
        await db.refresh(signal)
        return {
            "id": str(signal.id),
            "assignment_id": str(signal.assignment_id),
            "risk_score": signal.risk_score,
            "risk_level": signal.risk_level,
            "intervention_status": signal.intervention_status,
        }
