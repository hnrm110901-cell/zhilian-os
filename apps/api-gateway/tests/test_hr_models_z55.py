"""Unit tests for z55 HR knowledge OS models — no DB required."""
import pytest
from src.models.hr_knowledge.hr_knowledge_rule import HrKnowledgeRule
from src.models.hr_knowledge.skill_node import SkillNode
from src.models.hr_knowledge.behavior_pattern import BehaviorPattern
from src.models.hr_knowledge.person_achievement import PersonAchievement
from src.models.hr_knowledge.retention_signal import RetentionSignal
from src.models.hr_knowledge.knowledge_capture import KnowledgeCapture


def test_hr_knowledge_rule_tablename():
    assert HrKnowledgeRule.__tablename__ == "hr_knowledge_rules"


def test_skill_node_has_array_columns():
    from sqlalchemy.dialects.postgresql import ARRAY
    col = SkillNode.__table__.columns["prerequisite_skill_ids"]
    assert isinstance(col.type, ARRAY)


def test_retention_signal_has_risk_score():
    cols = {c.name for c in RetentionSignal.__table__.columns}
    assert "risk_score" in cols
    assert "intervention_status" in cols


def test_person_achievement_unique_constraint():
    uqs = [c for c in PersonAchievement.__table__.constraints
           if hasattr(c, 'columns')]
    col_sets = [frozenset(c.name for c in uq.columns) for uq in uqs
                if len(list(uq.columns)) == 2]
    assert frozenset(["person_id", "skill_node_id"]) in col_sets


def test_knowledge_capture_trigger_types():
    col = KnowledgeCapture.__table__.columns["trigger_type"]
    from sqlalchemy import String
    assert isinstance(col.type, String)


def test_behavior_pattern_has_qdrant_vector_id():
    cols = {c.name for c in BehaviorPattern.__table__.columns}
    assert "qdrant_vector_id" in cols


def test_all_knowledge_models_importable():
    from src.models.hr_knowledge import (
        HrKnowledgeRule, SkillNode, BehaviorPattern,
        PersonAchievement, RetentionSignal, KnowledgeCapture,
    )
    assert all([HrKnowledgeRule, SkillNode, BehaviorPattern,
                PersonAchievement, RetentionSignal, KnowledgeCapture])
