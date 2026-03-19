"""
OrgQueryFilter — 通用组织范围查询过滤器

用法：
    from src.core.org_query_filter import OrgQueryFilter

    # 在任何 API handler 中
    q = select(DailySettlement)
    q = OrgQueryFilter.apply(q, DailySettlement, org_scope)
    result = await db.execute(q)

支持的过滤策略：
  store_id  → model.store_id IN scope.accessible_store_ids  （默认，99% 的模型）
  brand_id  → 不过滤（品牌级数据在子树内对所有门店通用）
  node_id   → model.org_node_id IN scope.accessible_node_ids（新模型用）
"""
from __future__ import annotations
from typing import Type
from sqlalchemy import false, true
from sqlalchemy.sql import Select
from src.core.org_scope import OrgScope


class OrgQueryFilter:

    @staticmethod
    def apply(
        query: Select,
        model: Type,
        scope: OrgScope,
        scope_field: str = "store_id",
    ) -> Select:
        """
        给 SQLAlchemy Select 查询追加组织范围过滤

        scope_field: 模型上用于过滤的字段名，默认 "store_id"
        """
        # 全局 Admin 不加任何过滤
        if scope.is_global_admin:
            return query

        # 获取过滤字段
        col = getattr(model, scope_field, None)
        if col is None:
            # 模型没有该字段，跳过过滤（向后兼容）
            return query

        # 根据 scope_field 决定使用哪个 ID 列表
        if scope_field == "store_id":
            allowed_ids = scope.accessible_store_ids
        elif scope_field == "org_node_id":
            allowed_ids = scope.accessible_node_ids
        elif scope_field == "brand_id":
            # 品牌级数据：不做行级过滤（调用方已经在节点层面隔离）
            return query
        else:
            allowed_ids = scope.accessible_store_ids

        # 空权限 → 返回零结果（安全默认值）
        if not allowed_ids:
            return query.where(false())

        return query.where(col.in_(allowed_ids))

    @staticmethod
    def apply_to_aggregation(
        scope: OrgScope,
        store_id_column,
    ):
        """
        返回适用于 GROUP BY 聚合的 WHERE 条件
        用法：
            q = select(func.sum(Order.amount)).where(
                OrgQueryFilter.apply_to_aggregation(scope, Order.store_id)
            )
        """
        if scope.is_global_admin:
            return true()
        if not scope.accessible_store_ids:
            return false()
        return store_id_column.in_(scope.accessible_store_ids)
