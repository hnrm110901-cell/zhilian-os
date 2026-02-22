"""
SQLAlchemy租户过滤器
在Session层自动注入租户隔离条件
支持PostgreSQL Row-Level Security (RLS)
"""
from sqlalchemy import event, text
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select
import structlog

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


def enable_tenant_filter(session: Session, use_rls: bool = True) -> None:
    """
    为Session启用租户过滤器

    Args:
        session: SQLAlchemy Session实例
        use_rls: 是否使用PostgreSQL Row-Level Security（默认True）
    """
    tenant_id = TenantContext.get_current_tenant()

    if not tenant_id:
        logger.warning(
            "Tenant filter enabled but no tenant context set. "
            "Queries may return data from all tenants."
        )
        return

    # 如果使用PostgreSQL RLS，设置session变量
    if use_rls:
        try:
            # 设置PostgreSQL session变量，RLS策略会自动使用
            session.execute(
                text("SELECT set_config('app.current_tenant', :tenant_id, FALSE)"),
                {"tenant_id": tenant_id}
            )
            logger.info("PostgreSQL RLS tenant context set", tenant_id=tenant_id)
        except Exception as e:
            logger.warning(
                "Failed to set PostgreSQL RLS context, falling back to ORM filter",
                error=str(e)
            )
            use_rls = False

    # 如果不使用RLS或RLS设置失败，使用ORM级别的过滤器
    if not use_rls:
        @event.listens_for(session, "do_orm_execute")
        def receive_do_orm_execute(orm_execute_state):
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
                        orm_execute_state.statement = statement.where(
                            table.c.store_id == current_tenant
                        )
                        logger.debug(
                            "Tenant filter applied",
                            table=table_name,
                            tenant_id=current_tenant
                        )

        logger.info("ORM-level tenant filter enabled for session", tenant_id=tenant_id)


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


def disable_tenant_filter(session: Session) -> None:
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

    def __init__(self, session: Session, enable: bool = True):
        self.session = session
        self.enable = enable

    async def __aenter__(self):
        if self.enable:
            enable_tenant_filter(self.session)
        return self.session

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.enable:
            disable_tenant_filter(self.session)
