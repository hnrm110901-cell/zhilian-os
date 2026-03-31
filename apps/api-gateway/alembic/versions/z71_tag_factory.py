"""z71: 可配置标签工厂 — Phase 3

新增两张表：
1. tag_rules：标签规则定义（条件 JSON + 优先级 + AND/OR 逻辑）
2. consumer_tag_snapshots：会员标签评估结果快照

RLS 策略：
- tag_rules：按 brand_id / group_id / platform_admin 隔离
- consumer_tag_snapshots：复用 is_store_accessible_by_brand() 或按 brand_id 隔离

Revision ID: z71_tag_factory
Revises: z69_group_hierarchy_upgrade
Create Date: 2026-03-30
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TEXT, UUID

revision = "z71_tag_factory"
down_revision = "z69_group_hierarchy_upgrade"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # =================================================================
    # 1. CREATE TABLE tag_rules
    # =================================================================
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS tag_rules (
            id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            brand_id    VARCHAR(50) NOT NULL,
            group_id    VARCHAR(50) NOT NULL,
            tag_name    VARCHAR(100) NOT NULL,
            tag_code    VARCHAR(50)  NOT NULL,
            conditions  JSONB        NOT NULL DEFAULT '[]',
            logic       VARCHAR(5)   NOT NULL DEFAULT 'AND',
            priority    INTEGER      NOT NULL DEFAULT 100,
            is_active   BOOLEAN      NOT NULL DEFAULT TRUE,
            created_by  VARCHAR(100),
            created_at  TIMESTAMP    NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMP    NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_tag_rules_brand_code UNIQUE (brand_id, tag_code)
        )
    """))

    # 索引
    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_tag_rules_brand
            ON tag_rules(brand_id, is_active)
    """))
    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_tag_rules_group
            ON tag_rules(group_id)
    """))
    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_tag_rules_priority
            ON tag_rules(priority DESC)
    """))

    # RLS
    conn.execute(sa.text("ALTER TABLE tag_rules ENABLE ROW LEVEL SECURITY"))
    conn.execute(sa.text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_policies
                WHERE tablename = 'tag_rules'
                AND policyname = 'tag_rules_isolation'
            ) THEN
                CREATE POLICY tag_rules_isolation ON tag_rules
                    USING (
                        brand_id = current_setting('app.current_brand_id', TRUE)
                        OR brand_id = '*'
                        OR group_id = current_setting('app.current_group_id', TRUE)
                        OR current_setting('app.is_platform_admin', TRUE) = 'true'
                    );
            END IF;
        END $$
    """))

    # =================================================================
    # 2. CREATE TABLE consumer_tag_snapshots
    # =================================================================
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS consumer_tag_snapshots (
            id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            consumer_id         UUID        NOT NULL,
            brand_id            VARCHAR(50) NOT NULL,
            group_id            VARCHAR(50) NOT NULL,
            tag_codes           TEXT[]      NOT NULL DEFAULT '{}',
            last_evaluated_at   TIMESTAMP   NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_consumer_tag_snapshot UNIQUE (consumer_id, brand_id)
        )
    """))

    # GIN 索引：支持 tag_codes @> ARRAY['xxx'] 的高效查询
    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_cts_brand_tag
            ON consumer_tag_snapshots USING GIN(tag_codes)
    """))
    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_cts_consumer
            ON consumer_tag_snapshots(consumer_id)
    """))
    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_cts_brand_id
            ON consumer_tag_snapshots(brand_id)
    """))
    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_cts_group_id
            ON consumer_tag_snapshots(group_id)
    """))

    # RLS
    conn.execute(sa.text("ALTER TABLE consumer_tag_snapshots ENABLE ROW LEVEL SECURITY"))
    conn.execute(sa.text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_policies
                WHERE tablename = 'consumer_tag_snapshots'
                AND policyname = 'cts_brand_isolation'
            ) THEN
                CREATE POLICY cts_brand_isolation ON consumer_tag_snapshots
                    USING (
                        brand_id = current_setting('app.current_brand_id', TRUE)
                        OR group_id = current_setting('app.current_group_id', TRUE)
                        OR current_setting('app.is_platform_admin', TRUE) = 'true'
                    );
            END IF;
        END $$
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP TABLE IF EXISTS consumer_tag_snapshots"))
    conn.execute(sa.text("DROP TABLE IF EXISTS tag_rules"))
