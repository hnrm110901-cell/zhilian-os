"""z74: BSC 四维度经营快照时序表 — 门店运营数据聚合

新增：
1. operation_snapshots — BSC四维度经营快照（财务/客户/流程/学习），按日/周/月/季聚合

字段设计：
- 财务维度：收入/成本明细/毛利/净利（单位：分）
- 客户维度：客户数/客单价/翻台率/NPS/投诉/线上评分
- 流程维度：订单结构/出餐时间/损耗/采购准确率
- 学习维度：员工数/离职/培训/满意度

RLS 策略：
- operation_snapshots: brand_id / platform_admin 隔离

索引设计：
- UNIQUE(brand_id, store_id, snapshot_date, period_type) — 去重约束
- idx_os_store_period_date  — 按 store_id + period_type + snapshot_date DESC 支持门店时序查询
- idx_os_brand_period_date  — 按 brand_id + period_type + snapshot_date DESC 支持品牌汇总查询

Revision ID: z74_operation_snapshots
Revises: z73_business_objectives
Create Date: 2026-04-10
"""

from alembic import op
import sqlalchemy as sa

revision = "z74_operation_snapshots"
down_revision = "z73_business_objectives"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. BSC 四维度经营快照时序表 ───────────────────────────────────────────
    conn.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS operation_snapshots (
                id                      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
                brand_id                VARCHAR(50) NOT NULL,
                store_id                VARCHAR(50) NOT NULL,

                snapshot_date           DATE        NOT NULL,
                period_type             VARCHAR(10) NOT NULL,

                -- 财务维度（分）
                revenue_fen             BIGINT      DEFAULT 0,
                cost_material_fen       BIGINT      DEFAULT 0,
                cost_labor_fen          BIGINT      DEFAULT 0,
                cost_rent_fen           BIGINT      DEFAULT 0,
                cost_utility_fen        BIGINT      DEFAULT 0,
                cost_platform_fee_fen   BIGINT      DEFAULT 0,
                cost_other_fen          BIGINT      DEFAULT 0,
                gross_profit_fen        BIGINT      DEFAULT 0,
                net_profit_fen          BIGINT      DEFAULT 0,

                -- 客户维度
                customer_count          INTEGER     DEFAULT 0,
                new_customer_count      INTEGER     DEFAULT 0,
                returning_customer_count INTEGER    DEFAULT 0,
                avg_ticket_fen          BIGINT      DEFAULT 0,
                table_turnover_rate     NUMERIC(5,2),
                nps_score               NUMERIC(4,1),
                complaint_count         INTEGER     DEFAULT 0,
                online_rating_avg       NUMERIC(3,1),

                -- 流程维度
                order_count             INTEGER     DEFAULT 0,
                dine_in_order_count     INTEGER     DEFAULT 0,
                takeout_order_count     INTEGER     DEFAULT 0,
                delivery_order_count    INTEGER     DEFAULT 0,
                avg_serve_time_sec      INTEGER,
                waste_value_fen         BIGINT      DEFAULT 0,
                waste_rate_pct          NUMERIC(5,2),
                procurement_accuracy_pct NUMERIC(5,2),

                -- 学习维度
                employee_count          INTEGER     DEFAULT 0,
                turnover_count          INTEGER     DEFAULT 0,
                training_hours          NUMERIC(6,1) DEFAULT 0,
                employee_satisfaction   NUMERIC(4,1),

                -- 聚合元信息
                data_completeness_pct   NUMERIC(5,2) DEFAULT 100.00,
                source_record_count     INTEGER     DEFAULT 0,
                aggregated_at           TIMESTAMPTZ DEFAULT NOW(),

                CONSTRAINT uq_os_brand_store_date_period
                    UNIQUE (brand_id, store_id, snapshot_date, period_type)
            )
            """
        )
    )

    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_os_store_period_date
                ON operation_snapshots(store_id, period_type, snapshot_date DESC)
            """
        )
    )

    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_os_brand_period_date
                ON operation_snapshots(brand_id, period_type, snapshot_date DESC)
            """
        )
    )

    conn.execute(
        sa.text(
            """
            ALTER TABLE operation_snapshots ENABLE ROW LEVEL SECURITY
            """
        )
    )

    conn.execute(
        sa.text(
            """
            CREATE POLICY os_isolation ON operation_snapshots
                USING (
                    brand_id = current_setting('app.current_brand_id', TRUE)
                    OR current_setting('app.is_platform_admin', TRUE) = 'true'
                )
            """
        )
    )


def downgrade() -> None:
    conn = op.get_bind()

    conn.execute(sa.text("DROP TABLE IF EXISTS operation_snapshots CASCADE"))
