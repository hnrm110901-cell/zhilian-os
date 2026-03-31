"""
SQLAlchemy租户过滤器
在Session层自动注入租户隔离条件
支持PostgreSQL Row-Level Security (RLS)

Phase 1 升级：支持四层集团架构的 session 变量注入
  org_node_type = "group"  → 设置 app.current_group_id
  org_node_type = "brand"  → 设置 app.current_group_id + app.current_brand_id
  org_node_type = "region" → 设置以上两个 + app.current_region_id
  org_node_type = "store"  → 设置以上三个 + app.current_tenant（向后兼容）
  无 org_node_type          → 仅设置 app.current_tenant（原有单层逻辑）
"""

import structlog
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select
from src.core.tenant_context import TenantContext

logger = structlog.get_logger()

# 需要进行租户隔离的表列表
TENANT_TABLES = {
    "orders",
    "order_items",
    "reservations",
    "inventory_items",
    "inventory_transactions",
    "schedules",
    "employees",
    "training_records",
    "training_plans",
    "service_feedbacks",
    "complaints",
    "tasks",
    "notifications",
    "pos_transactions",
    "member_transactions",
    "financial_records",
    "supply_orders",
    "reconciliation_records",
}

# 不需要租户隔离的表（系统级表）
SYSTEM_TABLES = {
    "users",
    "stores",
    "roles",
    "permissions",
    "audit_logs",
    "alembic_version",
}


def receive_do_orm_execute(orm_execute_state) -> None:
    """
    拦截ORM查询，自动添加租户过滤条件
    """
    if not orm_execute_state.is_select:
        return

    # 获取当前租户ID
    current_tenant = TenantContext.get_current_tenant()
    if not current_tenant:
        return

    # 检查查询涉及的表
    statement = orm_execute_state.statement

    # 遍历查询中的所有表
    for table in statement.froms:
        table_name = table.name if hasattr(table, "name") else str(table)

        # 如果是需要租户隔离的表，添加过滤条件
        if table_name in TENANT_TABLES:
            # 检查是否已经有store_id过滤条件
            if not _has_store_filter(statement):
                # 添加租户过滤条件
                orm_execute_state.statement = statement.where(table.c.store_id == current_tenant)
                logger.debug("Tenant filter applied", table=table_name, tenant_id=current_tenant)


async def enable_tenant_filter(
    session: AsyncSession,
    use_rls: bool = True,
    org_node_type: str | None = None,
    group_id: str | None = None,
    brand_id: str | None = None,
    region_id: str | None = None,
) -> None:
    """
    为Session启用租户过滤器，支持四层集团架构 session 变量注入。

    Args:
        session: SQLAlchemy AsyncSession实例
        use_rls: 是否使用PostgreSQL Row-Level Security（默认True）
        org_node_type: JWT中的组织节点类型（group/brand/region/store），
                       None 时退化为原有单层逻辑（向后兼容）
        group_id: 集团ID（org_node_type=group/brand/region/store 时传入）
        brand_id: 品牌ID（org_node_type=brand/region/store 时传入）
        region_id: 区域ID（org_node_type=region/store 时传入）

    注入规则（org_node_type 存在时）：
        "group"  → app.current_group_id
        "brand"  → app.current_group_id + app.current_brand_id
        "region" → app.current_group_id + app.current_brand_id + app.current_region_id
        "store"  → 以上三个 + app.current_tenant（兼容现有 RLS）
    """
    tenant_id = TenantContext.get_current_tenant()

    # 如果既无 tenant_id 也无 group_id，说明完全没有上下文，警告并返回
    if not tenant_id and not group_id:
        logger.warning(
            "Tenant filter enabled but no tenant context set. "
            "Queries may return data from all tenants."
        )
        return

    if use_rls:
        try:
            if org_node_type is None:
                # --- 原有单层逻辑（向后兼容）---
                await session.execute(
                    text("SELECT set_config('app.current_tenant', :tenant_id, FALSE)"),
                    {"tenant_id": tenant_id},
                )
                logger.info("PostgreSQL RLS tenant context set", tenant_id=tenant_id)

            else:
                # --- 四层集团架构注入 ---
                await _inject_hierarchy_session_vars(
                    session, org_node_type, group_id, brand_id, region_id, tenant_id
                )

        except Exception as e:
            logger.warning(
                "Failed to set PostgreSQL RLS context, falling back to ORM filter",
                error=str(e),
            )
            use_rls = False

    if not use_rls:
        event.listen(session, "do_orm_execute", receive_do_orm_execute)
        logger.info("ORM-level tenant filter enabled for session", tenant_id=tenant_id)


async def _inject_hierarchy_session_vars(
    session: AsyncSession,
    org_node_type: str,
    group_id: str | None,
    brand_id: str | None,
    region_id: str | None,
    tenant_id: str | None,
) -> None:
    """
    根据 org_node_type 注入对应层级的 PostgreSQL session 变量。
    每个层级只注入该层及以上的变量，遵循最小权限原则。

    注：所有变量均使用 set_config(..., FALSE) 即事务级生效。
    """
    node_type = org_node_type.lower()

    if node_type == "group":
        if not group_id:
            logger.warning("org_node_type=group but group_id is missing")
            return
        await session.execute(
            text("SELECT set_config('app.current_group_id', :gid, FALSE)"),
            {"gid": group_id},
        )
        logger.info("RLS hierarchy vars set", org_node_type="group", group_id=group_id)

    elif node_type == "brand":
        if not group_id or not brand_id:
            logger.warning(
                "org_node_type=brand but group_id or brand_id is missing",
                group_id=group_id,
                brand_id=brand_id,
            )
            return
        await session.execute(
            text(
                "SELECT set_config('app.current_group_id', :gid, FALSE), "
                "       set_config('app.current_brand_id', :bid, FALSE)"
            ),
            {"gid": group_id, "bid": brand_id},
        )
        logger.info(
            "RLS hierarchy vars set",
            org_node_type="brand",
            group_id=group_id,
            brand_id=brand_id,
        )

    elif node_type == "region":
        if not group_id or not brand_id or not region_id:
            logger.warning(
                "org_node_type=region but one of group_id/brand_id/region_id is missing",
                group_id=group_id,
                brand_id=brand_id,
                region_id=region_id,
            )
            return
        await session.execute(
            text(
                "SELECT set_config('app.current_group_id', :gid, FALSE), "
                "       set_config('app.current_brand_id', :bid, FALSE), "
                "       set_config('app.current_region_id', :rid, FALSE)"
            ),
            {"gid": group_id, "bid": brand_id, "rid": region_id},
        )
        logger.info(
            "RLS hierarchy vars set",
            org_node_type="region",
            group_id=group_id,
            brand_id=brand_id,
            region_id=region_id,
        )

    elif node_type == "store":
        # store 层级：注入全部四层变量（含 app.current_tenant 以兼容现有 RLS 策略）
        params: dict = {"gid": group_id or "", "bid": brand_id or ""}
        sql_parts = [
            "SELECT set_config('app.current_group_id', :gid, FALSE)",
            "set_config('app.current_brand_id', :bid, FALSE)",
        ]
        if region_id:
            sql_parts.append("set_config('app.current_region_id', :rid, FALSE)")
            params["rid"] = region_id
        if tenant_id:
            sql_parts.append("set_config('app.current_tenant', :tenant_id, FALSE)")
            params["tenant_id"] = tenant_id

        await session.execute(text(", ".join(sql_parts)), params)
        logger.info(
            "RLS hierarchy vars set",
            org_node_type="store",
            group_id=group_id,
            brand_id=brand_id,
            region_id=region_id,
            tenant_id=tenant_id,
        )

    else:
        logger.warning("Unknown org_node_type, skipping hierarchy var injection", org_node_type=org_node_type)


def _has_store_filter(statement: Select) -> bool:
    """
    检查查询语句是否已经包含store_id过滤条件

    Args:
        statement: SQL查询语句

    Returns:
        bool: 是否已包含store_id过滤
    """
    if not hasattr(statement, "whereclause") or statement.whereclause is None:
        return False

    # 将where子句转换为字符串检查
    where_str = str(statement.whereclause)
    return "store_id" in where_str.lower()


def disable_tenant_filter(session: AsyncSession) -> None:
    """
    为Session禁用租户过滤器
    用于需要跨租户查询的场景（如超级管理员）

    Args:
        session: SQLAlchemy Session实例
    """
    # 移除所有do_orm_execute监听器
    event.remove(session, "do_orm_execute", receive_do_orm_execute)
    logger.info("Tenant filter disabled for session")


class TenantFilterContext:
    """
    租户过滤器上下文管理器

    用法:
        async with TenantFilterContext(session):
            # 在此上下文中，所有查询自动添加租户过滤
            result = await session.execute(select(Order))
    """

    def __init__(self, session: AsyncSession, enable: bool = True):
        self.session = session
        self.enable = enable

    async def __aenter__(self):
        if self.enable:
            await enable_tenant_filter(self.session)
        return self.session

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.enable:
            disable_tenant_filter(self.session)
