"""z73: 经营目标树 + OKR KR 表 — 战略目标拆解

新增：
1. business_objectives      — 经营目标树（公司/品牌/区域/门店四级，支持BSC四维度）
2. objective_key_results    — OKR的KR部分（关键结果，带权重）

RLS 策略：
- business_objectives: brand_id / platform_admin 隔离
- objective_key_results: brand_id / platform_admin 隔离

索引设计：
- idx_bo_brand_store_period — 按 brand_id + store_id + fiscal_year + period_type 支持目标查询
- idx_bo_parent             — 按 parent_id（部分索引）支持目标树向上/向下遍历
- idx_okr_objective         — 按 objective_id 支持KR列表查询

Revision ID: z73_business_objectives
Revises: z72_ai_prediction_journey
Create Date: 2026-04-10
"""

from alembic import op
import sqlalchemy as sa

revision = "z73_business_objectives"
down_revision = "z72_ai_prediction_journey"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. 经营目标树 ─────────────────────────────────────────────────────────
    conn.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS business_objectives (
                id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
                brand_id        VARCHAR(50) NOT NULL,
                store_id        VARCHAR(50),
                parent_id       UUID        REFERENCES business_objectives(id),
                level           VARCHAR(20) NOT NULL,
                fiscal_year     INTEGER     NOT NULL,
                period_type     VARCHAR(10) NOT NULL,
                period_value    INTEGER     NOT NULL DEFAULT 0,
                objective_name  VARCHAR(200) NOT NULL,
                metric_code     VARCHAR(50) NOT NULL,
                target_value    BIGINT      NOT NULL,
                floor_value     BIGINT,
                stretch_value   BIGINT,
                actual_value    BIGINT      DEFAULT 0,
                unit            VARCHAR(20) NOT NULL DEFAULT 'fen',
                bsc_dimension   VARCHAR(20) NOT NULL DEFAULT 'financial',
                status          VARCHAR(20) DEFAULT 'active',
                owner_id        UUID,
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                updated_at      TIMESTAMPTZ DEFAULT NOW()
            )
            """
        )
    )

    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_bo_brand_store_period
                ON business_objectives(brand_id, store_id, fiscal_year, period_type)
            """
        )
    )

    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_bo_parent
                ON business_objectives(parent_id)
                WHERE parent_id IS NOT NULL
            """
        )
    )

    conn.execute(
        sa.text(
            """
            ALTER TABLE business_objectives ENABLE ROW LEVEL SECURITY
            """
        )
    )

    conn.execute(
        sa.text(
            """
            CREATE POLICY bo_isolation ON business_objectives
                USING (
                    brand_id = current_setting('app.current_brand_id', TRUE)
                    OR current_setting('app.is_platform_admin', TRUE) = 'true'
                )
            """
        )
    )

    # ── 2. OKR 关键结果表 ─────────────────────────────────────────────────────
    conn.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS objective_key_results (
                id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
                objective_id    UUID        NOT NULL REFERENCES business_objectives(id) ON DELETE CASCADE,
                brand_id        VARCHAR(50) NOT NULL,
                kr_name         VARCHAR(200) NOT NULL,
                metric_code     VARCHAR(50) NOT NULL,
                target_value    BIGINT      NOT NULL,
                actual_value    BIGINT      DEFAULT 0,
                unit            VARCHAR(20) NOT NULL DEFAULT 'fen',
                weight          NUMERIC(3,2) DEFAULT 1.00,
                status          VARCHAR(20) DEFAULT 'active',
                owner_id        UUID,
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                updated_at      TIMESTAMPTZ DEFAULT NOW()
            )
            """
        )
    )

    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_okr_objective
                ON objective_key_results(objective_id)
            """
        )
    )

    conn.execute(
        sa.text(
            """
            ALTER TABLE objective_key_results ENABLE ROW LEVEL SECURITY
            """
        )
    )

    conn.execute(
        sa.text(
            """
            CREATE POLICY okr_isolation ON objective_key_results
                USING (
                    brand_id = current_setting('app.current_brand_id', TRUE)
                    OR current_setting('app.is_platform_admin', TRUE) = 'true'
                )
            """
        )
    )


def downgrade() -> None:
    conn = op.get_bind()

    conn.execute(sa.text("DROP TABLE IF EXISTS objective_key_results CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS business_objectives CASCADE"))
