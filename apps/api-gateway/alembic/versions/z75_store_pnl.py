"""z75: 门店损益表 + 盈亏平衡线追踪 — 财务分析核心表

新增：
1. store_pnl           — 门店日/月损益表（收入明细/成本明细/利润/比率/效率/月累计）
2. breakeven_tracker   — 月度盈亏平衡线追踪（固定成本/变动成本率/保本营收/达标日）

RLS 策略：
- store_pnl: brand_id / platform_admin 隔离
- breakeven_tracker: brand_id / platform_admin 隔离

索引设计：
- UNIQUE(brand_id, store_id, period_type, period_date) — store_pnl 去重约束
- idx_pnl_store_period   — 按 store_id + period_type + period_date DESC 支持门店损益时序查询
- UNIQUE(brand_id, store_id, calc_month) — breakeven_tracker 去重约束
- idx_be_store_month     — 按 store_id + calc_month DESC 支持盈亏平衡历史查询

Revision ID: z75_store_pnl
Revises: z74_operation_snapshots
Create Date: 2026-04-10
"""

from alembic import op
import sqlalchemy as sa

revision = "z75_store_pnl"
down_revision = "z74_operation_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. 门店日/月损益表 ────────────────────────────────────────────────────
    conn.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS store_pnl (
                id                      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
                brand_id                VARCHAR(50) NOT NULL,
                store_id                VARCHAR(50) NOT NULL,
                period_type             VARCHAR(10) NOT NULL,
                period_date             DATE        NOT NULL,

                -- 收入明细（分）
                dine_in_revenue_fen     BIGINT      DEFAULT 0,
                takeout_revenue_fen     BIGINT      DEFAULT 0,
                delivery_revenue_fen    BIGINT      DEFAULT 0,
                banquet_revenue_fen     BIGINT      DEFAULT 0,
                other_revenue_fen       BIGINT      DEFAULT 0,
                total_revenue_fen       BIGINT      DEFAULT 0,

                -- 成本明细（分）
                material_cost_fen       BIGINT      DEFAULT 0,
                labor_cost_fen          BIGINT      DEFAULT 0,
                rent_cost_fen           BIGINT      DEFAULT 0,
                utility_cost_fen        BIGINT      DEFAULT 0,
                platform_fee_fen        BIGINT      DEFAULT 0,
                marketing_cost_fen      BIGINT      DEFAULT 0,
                depreciation_fen        BIGINT      DEFAULT 0,
                other_cost_fen          BIGINT      DEFAULT 0,
                total_cost_fen          BIGINT      DEFAULT 0,

                -- 利润（分）
                gross_profit_fen        BIGINT      DEFAULT 0,
                operating_profit_fen    BIGINT      DEFAULT 0,

                -- 关键比率
                material_cost_ratio     NUMERIC(5,2),
                labor_cost_ratio        NUMERIC(5,2),
                gross_margin            NUMERIC(5,2),
                operating_margin        NUMERIC(5,2),

                -- 效率指标
                revenue_per_seat_fen    BIGINT,
                revenue_per_employee_fen BIGINT,

                -- 月累计（日报专用）
                mtd_revenue_fen         BIGINT      DEFAULT 0,
                mtd_profit_fen          BIGINT      DEFAULT 0,
                mtd_target_pct          NUMERIC(5,2),

                is_auto_generated       BOOLEAN     DEFAULT TRUE,
                adjustments             JSONB       DEFAULT '[]'::jsonb,
                created_at              TIMESTAMPTZ DEFAULT NOW(),

                CONSTRAINT uq_pnl_brand_store_period_date
                    UNIQUE (brand_id, store_id, period_type, period_date)
            )
            """
        )
    )

    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_pnl_store_period
                ON store_pnl(store_id, period_type, period_date DESC)
            """
        )
    )

    conn.execute(
        sa.text(
            """
            ALTER TABLE store_pnl ENABLE ROW LEVEL SECURITY
            """
        )
    )

    conn.execute(
        sa.text(
            """
            CREATE POLICY pnl_isolation ON store_pnl
                USING (
                    brand_id = current_setting('app.current_brand_id', TRUE)
                    OR current_setting('app.is_platform_admin', TRUE) = 'true'
                )
            """
        )
    )

    # ── 2. 月度盈亏平衡线追踪 ────────────────────────────────────────────────
    conn.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS breakeven_tracker (
                id                      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
                brand_id                VARCHAR(50) NOT NULL,
                store_id                VARCHAR(50) NOT NULL,
                calc_month              DATE        NOT NULL,
                fixed_cost_fen          BIGINT      NOT NULL,
                variable_cost_ratio     NUMERIC(5,2) NOT NULL,
                breakeven_revenue_fen   BIGINT      NOT NULL,
                breakeven_customers     INTEGER,
                breakeven_day           INTEGER,
                actual_revenue_fen      BIGINT      DEFAULT 0,
                breakeven_reached       BOOLEAN     DEFAULT FALSE,
                reached_date            DATE,
                store_model_score       NUMERIC(4,1),
                score_details           JSONB       DEFAULT '{}'::jsonb,
                created_at              TIMESTAMPTZ DEFAULT NOW(),
                updated_at              TIMESTAMPTZ DEFAULT NOW(),

                CONSTRAINT uq_be_brand_store_month
                    UNIQUE (brand_id, store_id, calc_month)
            )
            """
        )
    )

    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_be_store_month
                ON breakeven_tracker(store_id, calc_month DESC)
            """
        )
    )

    conn.execute(
        sa.text(
            """
            ALTER TABLE breakeven_tracker ENABLE ROW LEVEL SECURITY
            """
        )
    )

    conn.execute(
        sa.text(
            """
            CREATE POLICY be_isolation ON breakeven_tracker
                USING (
                    brand_id = current_setting('app.current_brand_id', TRUE)
                    OR current_setting('app.is_platform_admin', TRUE) = 'true'
                )
            """
        )
    )


def downgrade() -> None:
    conn = op.get_bind()

    conn.execute(sa.text("DROP TABLE IF EXISTS breakeven_tracker CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS store_pnl CASCADE"))
