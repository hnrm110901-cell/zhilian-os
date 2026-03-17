"""
ConfigResolver — 组织配置继承引擎

解析规则（优先级从高到低）：
  1. 当前节点自身配置
  2. 父节点配置（逐层向上直到根）
  3. 默认值

is_override=True 的配置：
  表示该节点"强制覆盖"，不向上继承同 key 的祖先值。
  实际上默认行为就是就近优先，is_override=True 仅作标注，
  提醒运维"这个值是主动覆盖的，不要轻易删除"。
"""
from __future__ import annotations
from typing import Any, Optional
from src.models.org_node import OrgNode
from src.models.org_config import OrgConfig


class ConfigResolver:
    """
    纯内存解析器（不直接依赖数据库，方便单元测试和缓存）

    使用方式（在 Service 层）：
        nodes = await org_hierarchy_service.get_scope_chain(store_id)
        node_map = {n.id: n for n in nodes}
        resolver = ConfigResolver(node_map=node_map)
        value = resolver.resolve(store_id, ConfigKey.PROBATION_DAYS, default=90)
    """

    def __init__(self, node_map: dict[str, OrgNode]):
        """
        node_map: {node_id -> OrgNode}（OrgNode.configs 已预加载）
        """
        self._node_map = node_map

    def _get_scope_chain(self, node_id: str) -> list[OrgNode]:
        """
        返回从当前节点到根节点的路径（当前节点在前，根节点在后）
        基于 path 字段构造，O(depth) 时间复杂度
        """
        node = self._node_map.get(node_id)
        if not node:
            return []

        # 从 path 解析祖先链，如 "grp.brd.sto" → ["grp", "brd", "sto"]
        path_parts = node.path.split(".")
        chain: list[OrgNode] = []
        for part in reversed(path_parts):  # 从当前节点往上
            ancestor = self._node_map.get(part)
            if ancestor:
                chain.append(ancestor)
        return chain  # chain[0] = 当前节点, chain[-1] = 根节点

    def _find_config(self, node: OrgNode, key: str) -> Optional[OrgConfig]:
        """在指定节点的 configs 列表中查找 key"""
        for cfg in (node.configs or []):
            if cfg.config_key == key:
                return cfg
        return None

    def resolve(self, node_id: str, key: str, default: Any = None) -> Any:
        """
        解析指定节点在指定 key 上的最终生效值

        就近原则：当前节点 > 父节点 > 祖父节点 > ... > 默认值
        """
        chain = self._get_scope_chain(node_id)
        for node in chain:
            cfg = self._find_config(node, key)
            if cfg is not None:
                return cfg.typed_value()
        return default

    def resolve_all(self, node_id: str) -> dict[str, Any]:
        """
        返回该节点所有配置 key 的最终生效值字典
        合并所有祖先节点的配置，当前节点优先级最高
        """
        chain = self._get_scope_chain(node_id)
        # 从根节点往下合并（后面的覆盖前面的 = 当前节点优先）
        merged: dict[str, Any] = {}
        for node in reversed(chain):  # 根节点先写，当前节点后写（覆盖）
            for cfg in (node.configs or []):
                merged[cfg.config_key] = cfg.typed_value()
        return merged

    def set_config(
        self,
        node: OrgNode,
        key: str,
        value: Any,
        value_type: str = "str",
        is_override: bool = False,
    ) -> OrgConfig:
        """
        在内存中设置节点配置（调用方负责持久化到数据库）
        如果 key 已存在则更新，否则新建
        """
        existing = self._find_config(node, key)
        if existing:
            existing.config_value = str(value)
            existing.value_type = value_type
            existing.is_override = is_override
            return existing

        cfg = OrgConfig()
        cfg.org_node_id = node.id
        cfg.config_key = key
        cfg.config_value = str(value)
        cfg.value_type = value_type
        cfg.is_override = is_override
        if node.configs is None:
            node.configs = []
        node.configs.append(cfg)
        return cfg
