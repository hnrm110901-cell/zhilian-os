"""z42_agent_okr_tables

Agent OKR — P1 统一量化日志
agent_response_logs + agent_okr_snapshots

Revision ID: z42
Revises: z41b
Create Date: 2026-03-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'z42'
down_revision = 'z41b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE agent_okr_agent_name_enum AS ENUM "
        "('business_intel','ops_flow','people','marketing',"
        "'banquet','dish_rd','supplier','compliance','ops','fct')"
    )
    op.execute(
        "CREATE TYPE agent_response_status_enum AS ENUM "
        "('pending','adopted','rejected','auto','expired')"
    )

    op.create_table(
        "agent_response_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("brand_id", sa.String(36), nullable=False),
        sa.Column("store_id", sa.String(36), nullable=False),
        sa.Column("agent_name", postgresql.ENUM(name="agent_okr_agent_name_enum", create_type=False), nullable=False),
        sa.Column("action_type", sa.String(100), nullable=False),
        sa.Column("recommendation_summary", sa.Text, nullable=True),
        sa.Column("recommendation_yuan", sa.Numeric(14, 2), nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("priority", sa.String(10), nullable=True),
        sa.Column("status", postgresql.ENUM(name="agent_response_status_enum", create_type=False), nullable=False, server_default="pending"),
        sa.Column("responded_at", sa.DateTime, nullable=True),
        sa.Column("response_latency_seconds", sa.Integer, nullable=True),
        sa.Column("actual_outcome_yuan", sa.Numeric(14, 2), nullable=True),
        sa.Column("prediction_error_pct", sa.Float, nullable=True),
        sa.Column("outcome_verified", sa.Boolean, server_default="false"),
        sa.Column("outcome_verified_at", sa.DateTime, nullable=True),
        sa.Column("source_record_id", sa.String(36), nullable=True),
        sa.Column("extra_data", postgresql.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_agent_resp_agent_store", "agent_response_logs", ["agent_name", "store_id"])
    op.create_index("idx_agent_resp_status", "agent_response_logs", ["status", "created_at"])
    op.create_index("idx_agent_resp_created", "agent_response_logs", ["created_at"])

    op.create_table(
        "agent_okr_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("brand_id", sa.String(36), nullable=False),
        sa.Column("store_id", sa.String(36), nullable=True),
        sa.Column("agent_name", postgresql.ENUM(name="agent_okr_agent_name_enum", create_type=False), nullable=False),
        sa.Column("period", sa.String(10), nullable=False),
        sa.Column("period_type", sa.String(5), nullable=False, server_default="day"),
        sa.Column("total_recommendations", sa.Integer, nullable=False, server_default="0"),
        sa.Column("adopted_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rejected_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("adoption_rate", sa.Float, nullable=True),
        sa.Column("avg_confidence", sa.Float, nullable=True),
        sa.Column("total_impact_yuan", sa.Numeric(14, 2), nullable=True),
        sa.Column("actual_impact_yuan", sa.Numeric(14, 2), nullable=True),
        sa.Column("avg_prediction_error_pct", sa.Float, nullable=True),
        sa.Column("avg_response_latency_seconds", sa.Integer, nullable=True),
        sa.Column("okr_adoption_met", sa.Boolean, nullable=True),
        sa.Column("okr_accuracy_met", sa.Boolean, nullable=True),
        sa.Column("okr_latency_met", sa.Boolean, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_okr_snap_agent_period", "agent_okr_snapshots", ["agent_name", "period"])
    op.create_index("idx_okr_snap_brand_period", "agent_okr_snapshots", ["brand_id", "period"])


def downgrade() -> None:
    op.drop_table("agent_okr_snapshots")
    op.drop_table("agent_response_logs")
    op.execute("DROP TYPE IF EXISTS agent_response_status_enum")
    op.execute("DROP TYPE IF EXISTS agent_okr_agent_name_enum")
