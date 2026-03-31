"""z72: AI 预测快照 + 客户旅程模板/实例表 — Phase 4

新增：
1. consumer_prediction_snapshots — 流失/升级/CLV 预测结果快照
2. journey_templates             — 可配置旅程模板（JSONB steps）
3. journey_instances             — 旅程运行实例（含步骤历史）

RLS 策略：
- consumer_prediction_snapshots: brand_id / group_id / platform_admin 三级隔离
- journey_templates / journey_instances: brand_id / group_id 隔离

索引设计：
- idx_cps_brand_churn    — 按 brand_id + churn_score DESC 支持高风险列表查询
- idx_cps_brand_upgrade  — 按 brand_id + upgrade_probability DESC 支持升级列表查询
- idx_jt_brand           — 按 brand_id + is_active 支持模板列表查询
- idx_ji_consumer        — 按 consumer_id 支持消费者旅程历史查询
- idx_ji_next_action     — 按 next_action_at WHERE status='running' 支持 Celery 扫描

Revision ID: z72_ai_prediction_journey
Revises: z70_omnichannel_orders
Create Date: 2026-03-30
"""

from alembic import op
import sqlalchemy as sa

revision = "z72_ai_prediction_journey"
down_revision = "z70_omnichannel_orders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. 预测快照表 ─────────────────────────────────────────────────────────
    conn.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS consumer_prediction_snapshots (
                id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
                consumer_id          UUID        NOT NULL,
                brand_id             VARCHAR(50) NOT NULL,
                group_id             VARCHAR(50) NOT NULL,

                -- 流失预测
                churn_score          NUMERIC(4,3),
                churn_risk_level     VARCHAR(10),
                churn_predicted_at   TIMESTAMP,

                -- 升级预测
                upgrade_probability  NUMERIC(4,3),
                upgrade_next_level   VARCHAR(20),
                upgrade_days_estimated INTEGER,
                upgrade_predicted_at TIMESTAMP,

                -- CLV 估算
                clv_fen              BIGINT,
                clv_segment          VARCHAR(10),
                clv_calculated_at    TIMESTAMP,

                last_batch_run_at    TIMESTAMP   NOT NULL DEFAULT NOW(),

                CONSTRAINT uq_cps_consumer_brand UNIQUE (consumer_id, brand_id)
            )
            """
        )
    )

    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_cps_brand_churn
                ON consumer_prediction_snapshots(brand_id, churn_score DESC)
            """
        )
    )

    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_cps_brand_upgrade
                ON consumer_prediction_snapshots(brand_id, upgrade_probability DESC)
            """
        )
    )

    conn.execute(
        sa.text(
            """
            ALTER TABLE consumer_prediction_snapshots ENABLE ROW LEVEL SECURITY
            """
        )
    )

    conn.execute(
        sa.text(
            """
            CREATE POLICY cps_isolation ON consumer_prediction_snapshots
                USING (
                    brand_id = current_setting('app.current_brand_id', TRUE)
                    OR group_id = current_setting('app.current_group_id', TRUE)
                    OR current_setting('app.is_platform_admin', TRUE) = 'true'
                )
            """
        )
    )

    # ── 2. 旅程模板表 ─────────────────────────────────────────────────────────
    conn.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS journey_templates (
                id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
                brand_id        VARCHAR(50) NOT NULL,
                group_id        VARCHAR(50) NOT NULL,
                template_name   VARCHAR(100) NOT NULL,
                trigger_event   VARCHAR(50) NOT NULL,
                steps           JSONB       NOT NULL DEFAULT '[]',
                is_active       BOOLEAN     NOT NULL DEFAULT TRUE,
                is_default      BOOLEAN     NOT NULL DEFAULT FALSE,
                created_at      TIMESTAMP   NOT NULL DEFAULT NOW(),
                updated_at      TIMESTAMP   NOT NULL DEFAULT NOW()
            )
            """
        )
    )

    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_jt_brand
                ON journey_templates(brand_id, is_active)
            """
        )
    )

    conn.execute(
        sa.text(
            """
            ALTER TABLE journey_templates ENABLE ROW LEVEL SECURITY
            """
        )
    )

    conn.execute(
        sa.text(
            """
            CREATE POLICY jt_isolation ON journey_templates
                USING (
                    brand_id = current_setting('app.current_brand_id', TRUE)
                    OR group_id = current_setting('app.current_group_id', TRUE)
                )
            """
        )
    )

    # ── 3. 旅程实例表 ─────────────────────────────────────────────────────────
    conn.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS journey_instances (
                id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
                template_id     UUID        NOT NULL REFERENCES journey_templates(id),
                consumer_id     UUID        NOT NULL,
                brand_id        VARCHAR(50) NOT NULL,
                current_step_id VARCHAR(50),
                status          VARCHAR(20) NOT NULL DEFAULT 'running',
                trigger_data    JSONB,
                step_history    JSONB       NOT NULL DEFAULT '[]',
                started_at      TIMESTAMP   NOT NULL DEFAULT NOW(),
                next_action_at  TIMESTAMP,
                completed_at    TIMESTAMP
            )
            """
        )
    )

    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_ji_consumer
                ON journey_instances(consumer_id)
            """
        )
    )

    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_ji_next_action
                ON journey_instances(next_action_at)
                WHERE status = 'running'
            """
        )
    )

    conn.execute(
        sa.text(
            """
            ALTER TABLE journey_instances ENABLE ROW LEVEL SECURITY
            """
        )
    )

    conn.execute(
        sa.text(
            """
            CREATE POLICY ji_isolation ON journey_instances
                USING (
                    brand_id = current_setting('app.current_brand_id', TRUE)
                    OR current_setting('app.current_group_id', TRUE) IS NOT NULL
                )
            """
        )
    )


def downgrade() -> None:
    conn = op.get_bind()

    conn.execute(sa.text("DROP TABLE IF EXISTS journey_instances CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS journey_templates CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS consumer_prediction_snapshots CASCADE"))
