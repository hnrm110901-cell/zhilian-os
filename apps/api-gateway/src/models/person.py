"""
Backward compatibility — 旧 Person 模型已迁移到 src/models/hr/person.py
本文件仅为向后兼容的 re-export，新代码请直接从 src.models.hr.person 导入。
"""
from src.models.hr.person import Person  # noqa: F401

__all__ = ["Person"]
