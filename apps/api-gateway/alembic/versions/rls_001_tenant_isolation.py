"""
添加Row-Level Security (RLS)策略

Revision ID: rls_001_tenant_isolation
Revises:
Create Date: 2026-02-22

"""
from alembic import op, context
import re
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'rls_001_tenant_isolation'
down_revision = 'm01_sync_phase1_models'
branch_labels = None
depends_on = None

# DDL 标识符（表名/策略名）不支持 bind 参数，必须拼入 SQL。
# 白名单正则确保表名只含小写字母、数字、下划线，防止未来维护失误。
_SAFE_IDENT_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _assert_safe_ident(name: str) -> None:
    if not _SAFE_IDENT_RE.match(name):
        raise ValueError(f"Unsafe SQL identifier in migration: {name!r}")


# 需要应用RLS的表列表
TENANT_TABLES = [
    'orders',
    'order_items',
    'reservations',
    'inventory_items',
    'inventory_transactions',
    'schedules',
    'employees',
    'training_records',
    'training_plans',
    'service_feedbacks',
    'complaints',
    'tasks',
    'notifications',
    'pos_transactions',
    'member_transactions',
    'financial_records',
    'supply_orders',
    'reconciliation_records',
]


def _table_exists(table_name: str) -> bool:
    if context.is_offline_mode():
        # Offline SQL export validates migration ordering, not live catalog state.
        return True
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename=:t)"
        ),
        {"t": table_name},
    )
    return result.scalar()


def _column_exists(table_name: str, column_name: str) -> bool:
    if context.is_offline_mode():
        return True
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT EXISTS ("
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=:t AND column_name=:c)"
        ),
        {"t": table_name, "c": column_name},
    )
    return result.scalar()


def upgrade() -> None:
    """
    启用Row-Level Security策略
    """
    # 为每个租户表启用RLS（跳过尚未创建的表）
    for table_name in TENANT_TABLES:
        _assert_safe_ident(table_name)   # DDL 不支持 bind 参数，白名单前置校验
        if not _table_exists(table_name) or not _column_exists(table_name, "store_id"):
            continue
        # 启用RLS
        op.execute(f'ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;')

        # 创建策略：用户只能访问自己租户的数据
        # 注意：这里使用current_setting获取当前会话的tenant_id
        policy_name = f'{table_name}_tenant_isolation_policy'

        # 创建SELECT策略
        op.execute(f"""
            CREATE POLICY {policy_name}_select ON {table_name}
            FOR SELECT
            USING (
                store_id = current_setting('app.current_tenant', TRUE)::text
                OR current_setting('app.current_tenant', TRUE) IS NULL
            );
        """)

        # 创建INSERT策略
        op.execute(f"""
            CREATE POLICY {policy_name}_insert ON {table_name}
            FOR INSERT
            WITH CHECK (
                store_id = current_setting('app.current_tenant', TRUE)::text
                OR current_setting('app.current_tenant', TRUE) IS NULL
            );
        """)

        # 创建UPDATE策略
        op.execute(f"""
            CREATE POLICY {policy_name}_update ON {table_name}
            FOR UPDATE
            USING (
                store_id = current_setting('app.current_tenant', TRUE)::text
                OR current_setting('app.current_tenant', TRUE) IS NULL
            )
            WITH CHECK (
                store_id = current_setting('app.current_tenant', TRUE)::text
                OR current_setting('app.current_tenant', TRUE) IS NULL
            );
        """)

        # 创建DELETE策略
        op.execute(f"""
            CREATE POLICY {policy_name}_delete ON {table_name}
            FOR DELETE
            USING (
                store_id = current_setting('app.current_tenant', TRUE)::text
                OR current_setting('app.current_tenant', TRUE) IS NULL
            );
        """)

    # 创建辅助函数：设置当前租户
    op.execute("""
        CREATE OR REPLACE FUNCTION set_current_tenant(tenant_id text)
        RETURNS void AS $$
        BEGIN
            PERFORM set_config('app.current_tenant', tenant_id, FALSE);
        END;
        $$ LANGUAGE plpgsql;
    """)

    # 创建辅助函数：清除当前租户
    op.execute("""
        CREATE OR REPLACE FUNCTION clear_current_tenant()
        RETURNS void AS $$
        BEGIN
            PERFORM set_config('app.current_tenant', '', FALSE);
        END;
        $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    """
    移除Row-Level Security策略
    """
    # 删除辅助函数
    op.execute('DROP FUNCTION IF EXISTS set_current_tenant(text);')
    op.execute('DROP FUNCTION IF EXISTS clear_current_tenant();')

    # 为每个租户表移除RLS
    for table_name in TENANT_TABLES:
        _assert_safe_ident(table_name)   # DDL 不支持 bind 参数，白名单前置校验
        if not _table_exists(table_name) or not _column_exists(table_name, "store_id"):
            continue
        policy_name = f'{table_name}_tenant_isolation_policy'

        # 删除所有策略
        op.execute(f'DROP POLICY IF EXISTS {policy_name}_select ON {table_name};')
        op.execute(f'DROP POLICY IF EXISTS {policy_name}_insert ON {table_name};')
        op.execute(f'DROP POLICY IF EXISTS {policy_name}_update ON {table_name};')
        op.execute(f'DROP POLICY IF EXISTS {policy_name}_delete ON {table_name};')

        # 禁用RLS
        op.execute(f'ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY;')
