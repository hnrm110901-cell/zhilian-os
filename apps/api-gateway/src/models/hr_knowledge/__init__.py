"""HR Knowledge OS models — 三位一体知识操作系统。"""
from .hr_knowledge_rule import HrKnowledgeRule
from .skill_node import SkillNode
from .behavior_pattern import BehaviorPattern
from .person_achievement import PersonAchievement
from .retention_signal import RetentionSignal
from .knowledge_capture import KnowledgeCapture

__all__ = [
    "HrKnowledgeRule",
    "SkillNode",
    "BehaviorPattern",
    "PersonAchievement",
    "RetentionSignal",
    "KnowledgeCapture",
]
