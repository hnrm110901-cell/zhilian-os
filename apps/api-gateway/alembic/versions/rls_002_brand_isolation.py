"""
ARCH-002: 品牌（Brand）隔离层 RLS 策略

Revision ID: rls_002_brand_isolation
Revises: rls_001_tenant_isolation
Create Date: 2026-03-01

变更说明:
1. 为 stores 和 users 表增加 brand_id 列（可空，向后兼容）
2. 为所有租户表增加 brand_isolation_policy（基于 app.current_brand）
3. super_admin / system_admin 豁免两层隔离
4. 创建 set_current_brand() / clear_current_brand() PG 辅助函数
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'rls_002_brand_isolation'
down_revision = 'rls_001_tenant_isolation'
branch_labels = None
depends_on = None


# 需要应用品牌 RLS 的表（与 rls_001 相同的表集）
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


def _column_exists(table_name: str, column_name: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT EXISTS ("
            "  SELECT 1 FROM information_schema.columns"
            "  WHERE table_schema='public' AND table_name=:t AND column_name=:c"
            ")"
        ),
        {"t": table_name, "c": column_name},
    )
    return result.scalar()


def upgrade() -> None:
    """
    1. 为 stores / users 表增加 brand_id 列
    2. 为所有租户表创建 brand_isolation_policy RLS 策略
    3. 创建 PG 辅助函数
    """

    # --- 1. 为核心表添加 brand_id 列（nullable，向后兼容）---
    for table, col_type in [("stores", "VARCHAR(50)"), ("users", "VARCHAR(50)")]:
        if _table_exists(table) and not _column_exists(table, "brand_id"):
            op.execute(f"ALTER TABLE {table} ADD COLUMN brand_id {col_type};")
            op.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_brand_id ON {table} (brand_id);")

    # --- 2. 为租户表创建品牌隔离 RLS 策略 ---
    # 策略逻辑：
    #   - 如果 app.current_brand 未设置（NULL/空），则允许所有行（向后兼容）
    #   - 如果已设置，则要求行的 brand_id 匹配（或行的 brand_id 为 NULL）
    for table_name in TENANT_TABLES:
        if not _table_exists(table_name):
            continue

        # 先检查该表是否有 brand_id 列（有些表可能没有）
        has_brand_col = _column_exists(table_name, "brand_id")

        if not has_brand_col:
            # 对于没有 brand_id 列的表，只创建允许策略（不限制品牌）
            policy_name = f'{table_name}_brand_isolation_policy'
            op.execute(f"""
                CREATE POLICY {policy_name} ON {table_name}
                AS PERMISSIVE
                FOR ALL
                USING (
                    current_setting('app.current_brand', TRUE) IS NULL
                    OR current_setting('app.current_brand', TRUE) = ''
                );
            """)
        else:
            policy_name = f'{table_name}_brand_isolation_policy'
            op.execute(f"""
                CREATE POLICY {policy_name} ON {table_name}
                AS PERMISSIVE
                FOR ALL
                USING (
                    current_setting('app.current_brand', TRUE) IS NULL
                    OR current_setting('app.current_brand', TRUE) = ''
                    OR brand_id IS NULL
                    OR brand_id = current_setting('app.current_brand', TRUE)::text
                )
                WITH CHECK (
                    current_setting('app.current_brand', TRUE) IS NULL
                    OR current_setting('app.current_brand', TRUE) = ''
                    OR brand_id IS NULL
                    OR brand_id = current_setting('app.current_brand', TRUE)::text
                );
            """)

    # --- 3. 创建 PG 辅助函数 ---
    op.execute("""
        CREATE OR REPLACE FUNCTION set_current_brand(brand_id text)
        RETURNS void AS $$
        BEGIN
            PERFORM set_config('app.current_brand', brand_id, FALSE);
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION clear_current_brand()
        RETURNS void AS $$
        BEGIN
            PERFORM set_config('app.current_brand', '', FALSE);
        END;
        $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    """
    1. 删除品牌 RLS 策略
    2. 删除 PG 辅助函数
    3. 删除 brand_id 列
    """
    # 删除辅助函数
    op.execute('DROP FUNCTION IF EXISTS set_current_brand(text);')
    op.execute('DROP FUNCTION IF EXISTS clear_current_brand();')

    # 删除品牌 RLS 策略
    for table_name in TENANT_TABLES:
        if not _table_exists(table_name):
            continue
        policy_name = f'{table_name}_brand_isolation_policy'
        op.execute(f'DROP POLICY IF EXISTS {policy_name} ON {table_name};')

    # 删除 stores / users 的 brand_id 列
    for table in ["stores", "users"]:
        if _table_exists(table) and _column_exists(table, "brand_id"):
            op.execute(f"DROP INDEX IF EXISTS idx_{table}_brand_id;")
            op.execute(f"ALTER TABLE {table} DROP COLUMN brand_id;")
