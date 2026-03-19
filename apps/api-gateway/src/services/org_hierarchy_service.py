"""
OrgHierarchyService — 组织层级 CRUD + 查询
"""
from __future__ import annotations
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from src.models.org_node import OrgNode
from src.models.org_config import OrgConfig
from src.services.config_resolver import ConfigResolver
import structlog

logger = structlog.get_logger()


class OrgHierarchyService:

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── 节点 CRUD ──────────────────────────────────────────────────────

    async def create_node(
        self,
        id_: str,
        name: str,
        node_type: str,
        parent_id: Optional[str] = None,
        **kwargs,
    ) -> OrgNode:
        """创建组织节点，自动计算 path 和 depth"""
        if parent_id:
            parent = await self.get_node(parent_id)
            if not parent:
                raise ValueError(f"父节点不存在: {parent_id}")
            path = f"{parent.path}.{id_}"
            depth = parent.depth + 1
        else:
            path = id_
            depth = 0

        node = OrgNode(
            id=id_,
            name=name,
            node_type=node_type,
            parent_id=parent_id,
            path=path,
            depth=depth,
            **kwargs,
        )
        self.db.add(node)
        await self.db.flush()
        logger.info("org_node_created", node_id=id_, node_type=node_type, path=path)
        return node

    async def get_node(self, node_id: str) -> Optional[OrgNode]:
        result = await self.db.execute(
            select(OrgNode).where(OrgNode.id == node_id)
        )
        return result.scalar_one_or_none()

    async def get_subtree(self, node_id: str) -> list[OrgNode]:
        """返回以 node_id 为根的整棵子树（含自身）"""
        node = await self.get_node(node_id)
        if not node:
            return []
        result = await self.db.execute(
            select(OrgNode).where(
                or_(
                    OrgNode.id == node_id,                      # 自身
                    OrgNode.path.like(f"{node.path}.%")         # 所有后代（子树）
                )
            ).order_by(OrgNode.depth, OrgNode.sort_order)
        )
        return list(result.scalars().all())

    async def get_scope_chain(self, node_id: str) -> list[OrgNode]:
        """
        返回从当前节点到根节点的路径链（含配置预加载）
        用于 ConfigResolver 初始化
        """
        node = await self.get_node(node_id)
        if not node:
            return []
        ancestor_ids = node.path.split(".")
        result = await self.db.execute(
            select(OrgNode).where(OrgNode.id.in_(ancestor_ids))
        )
        nodes = {n.id: n for n in result.scalars().all()}

        # 预加载各节点的 configs
        cfg_result = await self.db.execute(
            select(OrgConfig).where(OrgConfig.org_node_id.in_(ancestor_ids))
        )
        configs_by_node: dict[str, list[OrgConfig]] = {}
        for cfg in cfg_result.scalars().all():
            configs_by_node.setdefault(cfg.org_node_id, []).append(cfg)
        for nid, node_obj in nodes.items():
            node_obj.configs = configs_by_node.get(nid, [])

        # 按路径深度排序：当前节点（最深）在前，根节点在后
        target_node = nodes.get(node_id)
        if target_node:
            path_parts = target_node.path.split(".")
            ordered = [nodes[p] for p in reversed(path_parts) if p in nodes]
            return ordered
        return list(nodes.values())

    # ── 配置 CRUD ──────────────────────────────────────────────────────

    async def set_config(
        self,
        node_id: str,
        key: str,
        value: str,
        value_type: str = "str",
        is_override: bool = False,
        set_by: Optional[str] = None,
    ) -> OrgConfig:
        """设置节点配置（upsert）"""
        result = await self.db.execute(
            select(OrgConfig).where(
                OrgConfig.org_node_id == node_id,
                OrgConfig.config_key == key,
            )
        )
        cfg = result.scalar_one_or_none()
        if cfg:
            cfg.config_value = value
            cfg.value_type = value_type
            cfg.is_override = is_override
            if set_by:
                cfg.set_by = set_by
        else:
            cfg = OrgConfig(
                org_node_id=node_id,
                config_key=key,
                config_value=value,
                value_type=value_type,
                is_override=is_override,
                set_by=set_by,
            )
            self.db.add(cfg)
        await self.db.flush()
        return cfg

    async def get_resolver(self, node_id: str) -> ConfigResolver:
        """获取针对指定节点的 ConfigResolver（已预加载继承链）"""
        chain = await self.get_scope_chain(node_id)
        node_map = {n.id: n for n in chain}
        return ConfigResolver(node_map=node_map)

    async def resolve(self, node_id: str, key: str, default=None):
        """便捷方法：直接解析一个配置值"""
        resolver = await self.get_resolver(node_id)
        return resolver.resolve(node_id, key, default=default)
