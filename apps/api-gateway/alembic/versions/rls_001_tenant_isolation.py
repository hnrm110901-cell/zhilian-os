"""
添加Row-Level Security (RLS)策略

Revision ID: rls_001_tenant_isolation
Revises:
Create Date: 2026-02-22

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'rls_001_tenant_isolation'
down_revision = 'm01_sync_phase1_models'
branch_labels = None
depends_on = None


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
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename=:t)"
        ),
        {"t": table_name},
    )
    return result.scalar()


def upgrade() -> None:
    """
    启用Row-Level Security策略
    """
    # 为每个租户表启用RLS（跳过尚未创建的表）
    for table_name in TENANT_TABLES:
        if not _table_exists(table_name):
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
        if not _table_exists(table_name):
            continue
        policy_name = f'{table_name}_tenant_isolation_policy'

        # 删除所有策略
        op.execute(f'DROP POLICY IF EXISTS {policy_name}_select ON {table_name};')
        op.execute(f'DROP POLICY IF EXISTS {policy_name}_insert ON {table_name};')
        op.execute(f'DROP POLICY IF EXISTS {policy_name}_update ON {table_name};')
        op.execute(f'DROP POLICY IF EXISTS {policy_name}_delete ON {table_name};')

        # 禁用RLS
        op.execute(f'ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY;')
