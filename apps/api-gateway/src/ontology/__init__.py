"""
Ontology 包公共导出
"""

import os
from functools import lru_cache
from typing import TYPE_CHECKING

from .schema import ExtensionNodeLabel, NodeLabel, RelType

if TYPE_CHECKING:
    from .repository import OntologyRepository

__all__ = [
    "NodeLabel",
    "RelType",
    "ExtensionNodeLabel",
    "get_ontology_repository",
]


@lru_cache(maxsize=1)
def get_ontology_repository() -> "OntologyRepository":
    """返回全局单例 OntologyRepository（从环境变量读取连接信息）。
    Neo4j 不可用时返回未连接实例，调用方按需处理连接异常。
    """
    from .repository import OntologyRepository  # 懒加载，避免 neo4j 未安装时影响整体启动

    try:
        from src.core.config import settings
        uri = settings.NEO4J_URI
        user = settings.NEO4J_USER
        password = settings.NEO4J_PASSWORD
    except Exception:
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "changeme")
    return OntologyRepository(uri=uri, user=user, password=password)
