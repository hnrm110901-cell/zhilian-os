"""z69: 集团层级数据模型升级 — Phase 1

新增四层集团架构支持（集团>品牌>区域>门店）：
1. ALTER groups 表：增加 org_node_id / is_active / subscription_tier / max_brands / max_stores
2. ALTER brands 表：增加 org_node_id / is_active / cross_brand_one_id
3. ALTER regions 表：增加 org_node_id / group_id / is_active
4. ALTER stores 表：增加 region_id / group_id
5. CREATE TABLE group_tenants（集团SaaS计费锚点）
6. CREATE TABLE brand_consumer_profiles（品牌维度会员档案，含 One ID 支持）
7. CREATE FUNCTION is_store_accessible()（RLS 辅助函数）
8. 为 stores 表启用 RLS + 创建访问策略
9. 创建所有新增列的索引

Revision ID: z69_group_hierarchy_upgrade
Revises: z68_mission_journey
Create Date: 2026-03-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "z69_group_hierarchy_upgrade"
down_revision = "z68_mission_journey"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # =========================================================
    # 1. ALTER groups — 增加集团层级字段
    # =========================================================
    _add_column_if_not_exists("groups", "org_node_id", sa.String(64))
    _add_column_if_not_exists("groups", "is_active", sa.Boolean(),
                               server_default="true", nullable=False)
    _add_column_if_not_exists("groups", "subscription_tier", sa.String(20),
                               server_default="standard", nullable=False)
    _add_column_if_not_exists("groups", "max_brands", sa.Integer())
    _add_column_if_not_exists("groups", "max_stores", sa.Integer())

    # =========================================================
    # 2. ALTER brands — 增加品牌层级字段
    # =========================================================
    _add_column_if_not_exists("brands", "org_node_id", sa.String(64))
    _add_column_if_not_exists("brands", "is_active", sa.Boolean(),
                               server_default="true", nullable=False)
    _add_column_if_not_exists("brands", "cross_brand_one_id", sa.Boolean(),
                               server_default="false", nullable=False)

    # =========================================================
    # 3. ALTER regions — 增加区域层级字段
    # =========================================================
    _add_column_if_not_exists("regions", "org_node_id", sa.String(64))
    _add_column_if_not_exists("regions", "group_id", sa.String(50))
    _add_column_if_not_exists("regions", "is_active", sa.Boolean(),
                               server_default="true", nullable=False)

    # =========================================================
    # 4. ALTER stores — 增加区域/集团关联
    # =========================================================
    _add_column_if_not_exists("stores", "region_id", sa.String(50))
    _add_column_if_not_exists("stores", "group_id", sa.String(50))

    # =========================================================
    # 5. CREATE TABLE group_tenants
    # =========================================================
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS group_tenants (
            id                  VARCHAR(50)  PRIMARY KEY,
            group_id            VARCHAR(50)  NOT NULL UNIQUE,
            billing_email       VARCHAR(200) NOT NULL,
            subscription_tier   VARCHAR(20)  NOT NULL DEFAULT 'standard',
            feature_flags       JSONB        NOT NULL DEFAULT '{}',
            status              VARCHAR(20)  NOT NULL DEFAULT 'trial',
            contract_start_date DATE,
            notes               TEXT,
            created_at          TIMESTAMP    NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMP    NOT NULL DEFAULT NOW()
        )
    """))

    # group_tenants RLS
    conn.execute(sa.text("""
        ALTER TABLE group_tenants ENABLE ROW LEVEL SECURITY
    """))
    conn.execute(sa.text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_policies
                WHERE tablename = 'group_tenants'
                AND policyname = 'group_tenants_group_isolation'
            ) THEN
                CREATE POLICY group_tenants_group_isolation
                    ON group_tenants
                    USING (group_id = current_setting('app.current_group_id', TRUE));
            END IF;
        END $$
    """))

    # =========================================================
    # 6. CREATE TABLE brand_consumer_profiles
    # =========================================================
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS brand_consumer_profiles (
            id                      UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            consumer_id             UUID         NOT NULL,
            brand_id                VARCHAR(50)  NOT NULL,
            group_id                VARCHAR(50)  NOT NULL,
            brand_member_no         VARCHAR(100),
            brand_level             VARCHAR(30)  NOT NULL DEFAULT '普通',
            brand_points            INTEGER      NOT NULL DEFAULT 0,
            brand_balance_fen       BIGINT       NOT NULL DEFAULT 0,
            brand_order_count       INTEGER      NOT NULL DEFAULT 0,
            brand_order_amount_fen  BIGINT       NOT NULL DEFAULT 0,
            brand_first_order_at    TIMESTAMP,
            brand_last_order_at     TIMESTAMP,
            lifecycle_state         VARCHAR(30)  NOT NULL DEFAULT 'registered',
            registration_channel    VARCHAR(50)  NOT NULL DEFAULT 'manual',
            brand_wechat_openid     VARCHAR(100),
            brand_wechat_unionid    VARCHAR(100),
            is_active               BOOLEAN      NOT NULL DEFAULT TRUE,
            created_at              TIMESTAMP    NOT NULL DEFAULT NOW(),
            updated_at              TIMESTAMP    NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_brand_consumer_profile_consumer_brand
                UNIQUE (consumer_id, brand_id)
        )
    """))

    # brand_consumer_profiles RLS
    conn.execute(sa.text("""
        ALTER TABLE brand_consumer_profiles ENABLE ROW LEVEL SECURITY
    """))
    conn.execute(sa.text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_policies
                WHERE tablename = 'brand_consumer_profiles'
                AND policyname = 'bcp_brand_isolation'
            ) THEN
                CREATE POLICY bcp_brand_isolation
                    ON brand_consumer_profiles
                    USING (
                        brand_id = current_setting('app.current_brand_id', TRUE)
                        OR group_id = current_setting('app.current_group_id', TRUE)
                    );
            END IF;
        END $$
    """))

    # =========================================================
    # 7. CREATE OR REPLACE FUNCTION is_store_accessible()
    #    辅助函数：判断门店是否在当前 session 的访问范围内
    # =========================================================
    conn.execute(sa.text("""
        CREATE OR REPLACE FUNCTION is_store_accessible(
            p_store_id  VARCHAR,
            p_brand_id  VARCHAR,
            p_region_id VARCHAR,
            p_group_id  VARCHAR
        ) RETURNS BOOLEAN
        LANGUAGE plpgsql STABLE SECURITY DEFINER
        AS $$
        DECLARE
            v_current_tenant  TEXT := current_setting('app.current_tenant',  TRUE);
            v_current_group   TEXT := current_setting('app.current_group_id', TRUE);
            v_current_brand   TEXT := current_setting('app.current_brand_id', TRUE);
            v_current_region  TEXT := current_setting('app.current_region_id', TRUE);
        BEGIN
            -- 门店级：精确匹配 store_id
            IF v_current_tenant IS NOT NULL AND v_current_tenant <> '' THEN
                RETURN p_store_id = v_current_tenant;
            END IF;

            -- 区域级：匹配 region_id
            IF v_current_region IS NOT NULL AND v_current_region <> '' THEN
                RETURN p_region_id = v_current_region;
            END IF;

            -- 品牌级：匹配 brand_id
            IF v_current_brand IS NOT NULL AND v_current_brand <> '' THEN
                RETURN p_brand_id = v_current_brand;
            END IF;

            -- 集团级：匹配 group_id
            IF v_current_group IS NOT NULL AND v_current_group <> '' THEN
                RETURN p_group_id = v_current_group;
            END IF;

            -- 无上下文：拒绝访问（安全兜底）
            RETURN FALSE;
        END;
        $$
    """))

    # =========================================================
    # 8. stores 表启用 RLS + 创建四层访问策略
    # =========================================================
    conn.execute(sa.text("ALTER TABLE stores ENABLE ROW LEVEL SECURITY"))

    conn.execute(sa.text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_policies
                WHERE tablename = 'stores'
                AND policyname = 'stores_hierarchy_access'
            ) THEN
                CREATE POLICY stores_hierarchy_access
                    ON stores
                    USING (
                        is_store_accessible(
                            id::varchar,
                            brand_id,
                            region_id,
                            group_id
                        )
                    );
            END IF;
        END $$
    """))

    # =========================================================
    # 9. 索引：所有新增列
    # =========================================================
    _create_index_if_not_exists("ix_groups_org_node_id",     "groups",  "org_node_id")
    _create_index_if_not_exists("ix_groups_is_active",       "groups",  "is_active")
    _create_index_if_not_exists("ix_brands_org_node_id",     "brands",  "org_node_id")
    _create_index_if_not_exists("ix_brands_is_active",       "brands",  "is_active")
    _create_index_if_not_exists("ix_regions_org_node_id",    "regions", "org_node_id")
    _create_index_if_not_exists("ix_regions_group_id",       "regions", "group_id")
    _create_index_if_not_exists("ix_regions_is_active",      "regions", "is_active")
    _create_index_if_not_exists("ix_stores_region_id",       "stores",  "region_id")
    _create_index_if_not_exists("ix_stores_group_id",        "stores",  "group_id")

    # group_tenants 索引
    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_group_tenants_group_id
            ON group_tenants (group_id)
    """))
    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_group_tenants_status
            ON group_tenants (status)
    """))

    # brand_consumer_profiles 索引
    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_bcp_consumer_id
            ON brand_consumer_profiles (consumer_id)
    """))
    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_bcp_brand_id
            ON brand_consumer_profiles (brand_id)
    """))
    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_bcp_group_id
            ON brand_consumer_profiles (group_id)
    """))
    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_bcp_lifecycle_state
            ON brand_consumer_profiles (lifecycle_state)
    """))
    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_bcp_consumer_group
            ON brand_consumer_profiles (consumer_id, group_id)
    """))
    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_bcp_brand_lifecycle
            ON brand_consumer_profiles (brand_id, lifecycle_state)
    """))


def downgrade() -> None:
    conn = op.get_bind()

    # 删除 stores 策略和函数（逆序）
    conn.execute(sa.text("""
        DO $$ BEGIN
            DROP POLICY IF EXISTS stores_hierarchy_access ON stores;
        EXCEPTION WHEN OTHERS THEN NULL;
        END $$
    """))
    conn.execute(sa.text("ALTER TABLE stores DISABLE ROW LEVEL SECURITY"))
    conn.execute(sa.text("DROP FUNCTION IF EXISTS is_store_accessible(VARCHAR, VARCHAR, VARCHAR, VARCHAR)"))

    # 删除 brand_consumer_profiles
    conn.execute(sa.text("""
        DROP POLICY IF EXISTS bcp_brand_isolation ON brand_consumer_profiles
    """))
    conn.execute(sa.text("DROP TABLE IF EXISTS brand_consumer_profiles"))

    # 删除 group_tenants
    conn.execute(sa.text("""
        DROP POLICY IF EXISTS group_tenants_group_isolation ON group_tenants
    """))
    conn.execute(sa.text("DROP TABLE IF EXISTS group_tenants"))

    # 删除 stores 新增列
    _drop_column_if_exists("stores", "group_id")
    _drop_column_if_exists("stores", "region_id")

    # 删除 regions 新增列
    _drop_column_if_exists("regions", "is_active")
    _drop_column_if_exists("regions", "group_id")
    _drop_column_if_exists("regions", "org_node_id")

    # 删除 brands 新增列
    _drop_column_if_exists("brands", "cross_brand_one_id")
    _drop_column_if_exists("brands", "is_active")
    _drop_column_if_exists("brands", "org_node_id")

    # 删除 groups 新增列
    _drop_column_if_exists("groups", "max_stores")
    _drop_column_if_exists("groups", "max_brands")
    _drop_column_if_exists("groups", "subscription_tier")
    _drop_column_if_exists("groups", "is_active")
    _drop_column_if_exists("groups", "org_node_id")


# ===========================================================
# 辅助函数（幂等操作）
# ===========================================================

def _add_column_if_not_exists(
    table: str,
    column: str,
    col_type,
    server_default=None,
    nullable: bool = True,
) -> None:
    """幂等地向表添加列（列已存在时跳过）"""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = :tbl AND column_name = :col"
    ), {"tbl": table, "col": column})
    if result.fetchone():
        return  # 列已存在，跳过

    opts: dict = {}
    if server_default is not None:
        opts["server_default"] = server_default
    if not nullable:
        opts["nullable"] = False

    op.add_column(table, sa.Column(column, col_type, **opts))


def _drop_column_if_exists(table: str, column: str) -> None:
    """幂等地删除列（列不存在时跳过）"""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = :tbl AND column_name = :col"
    ), {"tbl": table, "col": column})
    if result.fetchone():
        op.drop_column(table, column)


def _create_index_if_not_exists(index_name: str, table: str, column: str) -> None:
    """幂等地创建单列索引"""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM pg_indexes WHERE indexname = :idx"
    ), {"idx": index_name})
    if not result.fetchone():
        op.create_index(index_name, table, [column])
