"""z76: Chief Agent编排系统 — 经营大脑四表

新增：
1. chief_agent_sessions — 经营大脑编排会话记录
2. agent_events — Agent间事件总线（异常广播+联动响应）
3. review_sessions — AI生成复盘报告（日/周/月/季）
4. prediction_log — 预测值vs实际值反馈闭环

RLS: brand_id / platform_admin 隔离

Revision ID: z76_chief_agent_system
Revises: z75_store_pnl
Create Date: 2026-04-10
"""

from alembic import op
import sqlalchemy as sa

revision = "z76_chief_agent_system"
down_revision = "z75_store_pnl"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. chief_agent_sessions — 经营大脑编排会话 ─────────────────────────────
    conn.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS chief_agent_sessions (
                id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
                brand_id            VARCHAR(50) NOT NULL,
                store_id            VARCHAR(50),
                trigger_type        VARCHAR(20) NOT NULL,
                trigger_source      VARCHAR(100),
                orchestration_plan  JSONB       NOT NULL DEFAULT '{}'::jsonb,
                final_output        JSONB,
                confidence          NUMERIC(3,2),
                status              VARCHAR(20) DEFAULT 'running',
                started_at          TIMESTAMPTZ DEFAULT NOW(),
                completed_at        TIMESTAMPTZ,
                user_feedback       VARCHAR(20),
                feedback_notes      TEXT,
                created_at          TIMESTAMPTZ DEFAULT NOW()
            )
            """
        )
    )

    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_cas_brand_status
                ON chief_agent_sessions(brand_id, status, started_at DESC)
            """
        )
    )

    conn.execute(
        sa.text(
            """
            ALTER TABLE chief_agent_sessions ENABLE ROW LEVEL SECURITY
            """
        )
    )

    conn.execute(
        sa.text(
            """
            CREATE POLICY cas_isolation ON chief_agent_sessions
                USING (
                    brand_id = current_setting('app.current_brand_id', TRUE)
                    OR current_setting('app.is_platform_admin', TRUE) = 'true'
                )
            """
        )
    )

    # ── 2. agent_events — Agent间事件总线 ──────────────────────────────────────
    conn.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS agent_events (
                id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
                brand_id        VARCHAR(50) NOT NULL,
                store_id        VARCHAR(50),
                source_agent    VARCHAR(50) NOT NULL,
                event_type      VARCHAR(100) NOT NULL,
                severity        VARCHAR(10) DEFAULT 'info',
                payload         JSONB       NOT NULL DEFAULT '{}'::jsonb,
                target_agents   TEXT[],
                responses       JSONB,
                processed       BOOLEAN     DEFAULT FALSE,
                processed_at    TIMESTAMPTZ,
                created_at      TIMESTAMPTZ DEFAULT NOW()
            )
            """
        )
    )

    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_ae_unprocessed
                ON agent_events(brand_id, processed, created_at DESC)
                WHERE processed = FALSE
            """
        )
    )

    conn.execute(
        sa.text(
            """
            ALTER TABLE agent_events ENABLE ROW LEVEL SECURITY
            """
        )
    )

    conn.execute(
        sa.text(
            """
            CREATE POLICY ae_isolation ON agent_events
                USING (
                    brand_id = current_setting('app.current_brand_id', TRUE)
                    OR current_setting('app.is_platform_admin', TRUE) = 'true'
                )
            """
        )
    )

    # ── 3. review_sessions — AI复盘报告 ───────────────────────────────────────
    conn.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS review_sessions (
                id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
                brand_id        VARCHAR(50) NOT NULL,
                store_id        VARCHAR(50),
                review_type     VARCHAR(20) NOT NULL,
                period_start    DATE        NOT NULL,
                period_end      DATE        NOT NULL,
                ai_summary      JSONB       NOT NULL DEFAULT '{}'::jsonb,
                benchmark_data  JSONB,
                manager_notes   TEXT,
                action_items    JSONB       DEFAULT '[]'::jsonb,
                status          VARCHAR(20) DEFAULT 'draft',
                confirmed_by    UUID,
                confirmed_at    TIMESTAMPTZ,
                created_at      TIMESTAMPTZ DEFAULT NOW()
            )
            """
        )
    )

    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_rs_store_type
                ON review_sessions(store_id, review_type, period_end DESC)
            """
        )
    )

    conn.execute(
        sa.text(
            """
            ALTER TABLE review_sessions ENABLE ROW LEVEL SECURITY
            """
        )
    )

    conn.execute(
        sa.text(
            """
            CREATE POLICY rs_isolation ON review_sessions
                USING (
                    brand_id = current_setting('app.current_brand_id', TRUE)
                    OR current_setting('app.is_platform_admin', TRUE) = 'true'
                )
            """
        )
    )

    # ── 4. prediction_log — 预测反馈闭环 ──────────────────────────────────────
    conn.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS prediction_log (
                id                      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
                brand_id                VARCHAR(50) NOT NULL,
                store_id                VARCHAR(50) NOT NULL,
                prediction_type         VARCHAR(50) NOT NULL,
                prediction_date         DATE        NOT NULL,
                predicted_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                predicted_value         NUMERIC(15,2) NOT NULL,
                actual_value            NUMERIC(15,2),
                error_pct               NUMERIC(5,2),
                model_version           VARCHAR(50),
                features_used           JSONB,
                is_feedback_collected   BOOLEAN     DEFAULT FALSE,
                created_at              TIMESTAMPTZ DEFAULT NOW()
            )
            """
        )
    )

    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_pl_store_type_date
                ON prediction_log(store_id, prediction_type, prediction_date)
            """
        )
    )

    conn.execute(
        sa.text(
            """
            ALTER TABLE prediction_log ENABLE ROW LEVEL SECURITY
            """
        )
    )

    conn.execute(
        sa.text(
            """
            CREATE POLICY pl_isolation ON prediction_log
                USING (
                    brand_id = current_setting('app.current_brand_id', TRUE)
                    OR current_setting('app.is_platform_admin', TRUE) = 'true'
                )
            """
        )
    )


def downgrade() -> None:
    conn = op.get_bind()

    conn.execute(sa.text("DROP TABLE IF EXISTS prediction_log CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS review_sessions CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS agent_events CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS chief_agent_sessions CASCADE"))
