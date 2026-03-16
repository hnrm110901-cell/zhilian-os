"""z43 — AgentCollaborationOptimizer tables

Revision ID: z43
Revises: z42
Create Date: 2026-03-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'z43'
down_revision = 'z42'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""DO $$ BEGIN
        CREATE TYPE conflict_type_enum AS ENUM (
            'resource_contention','financial_constraint','timing_conflict',
            'priority_clash','contradictory_action'
        );
        EXCEPTION WHEN duplicate_object THEN NULL; END $$"""))
    op.execute(sa.text("""DO $$ BEGIN
        CREATE TYPE conflict_severity_enum AS ENUM ('low','medium','high');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$"""))
    op.execute(sa.text("""DO $$ BEGIN
        CREATE TYPE arbitration_status_enum AS ENUM ('pending','resolved','escalated');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$"""))
    op.execute(sa.text("""DO $$ BEGIN
        CREATE TYPE arbitration_method_enum AS ENUM (
            'priority_wins','financial_first','revenue_first','risk_first',
            'manual_override','merge_recommendations'
        );
        EXCEPTION WHEN duplicate_object THEN NULL; END $$"""))

    op.create_table(
        "agent_conflicts",
        sa.Column("id",                  sa.String(36), primary_key=True),
        sa.Column("store_id",            sa.String(64), nullable=False),
        sa.Column("brand_id",            sa.String(64), nullable=True),
        sa.Column("agent_a",             sa.String(64), nullable=False),
        sa.Column("agent_b",             sa.String(64), nullable=False),
        sa.Column("recommendation_a_id", sa.String(36), nullable=True),
        sa.Column("recommendation_b_id", sa.String(36), nullable=True),
        sa.Column("conflict_type",       sa.Enum("resource_contention","financial_constraint","timing_conflict","priority_clash","contradictory_action", name="conflict_type_enum", create_type=False), nullable=False),
        sa.Column("severity",            sa.Enum("low","medium","high", name="conflict_severity_enum", create_type=False), nullable=False),
        sa.Column("description",         sa.Text, nullable=False),
        sa.Column("conflict_data",       JSONB, nullable=True),
        sa.Column("arbitration_status",  sa.Enum("pending","resolved","escalated", name="arbitration_status_enum", create_type=False), nullable=False, server_default="pending"),
        sa.Column("arbitration_method",  sa.Enum("priority_wins","financial_first","revenue_first","risk_first","manual_override","merge_recommendations", name="arbitration_method_enum", create_type=False), nullable=True),
        sa.Column("winning_agent",       sa.String(64), nullable=True),
        sa.Column("arbitration_note",    sa.Text, nullable=True),
        sa.Column("impact_yuan_saved",   sa.Numeric(14, 2), nullable=True),
        sa.Column("created_at",          sa.DateTime, server_default=sa.func.now()),
        sa.Column("resolved_at",         sa.DateTime, nullable=True),
    )
    op.create_index("idx_conflict_store_created", "agent_conflicts", ["store_id", "created_at"])
    op.create_index("idx_conflict_agents", "agent_conflicts", ["agent_a", "agent_b"])

    op.create_table(
        "global_optimization_logs",
        sa.Column("id",                       sa.String(36), primary_key=True),
        sa.Column("store_id",                 sa.String(64), nullable=False),
        sa.Column("brand_id",                 sa.String(64), nullable=True),
        sa.Column("input_count",              sa.Integer, nullable=False),
        sa.Column("output_count",             sa.Integer, nullable=False),
        sa.Column("conflicts_detected",       sa.Integer, server_default="0"),
        sa.Column("dedup_count",              sa.Integer, server_default="0"),
        sa.Column("suppressed_count",         sa.Integer, server_default="0"),
        sa.Column("bundled_count",            sa.Integer, server_default="0"),
        sa.Column("total_impact_yuan_before", sa.Numeric(14, 2), nullable=True),
        sa.Column("total_impact_yuan_after",  sa.Numeric(14, 2), nullable=True),
        sa.Column("optimization_details",     JSONB, nullable=True),
        sa.Column("ai_insight",               sa.Text, nullable=True),
        sa.Column("created_at",               sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_global_opt_store", "global_optimization_logs", ["store_id", "created_at"])

    op.create_table(
        "agent_collab_snapshots",
        sa.Column("id",                          sa.String(36), primary_key=True),
        sa.Column("brand_id",                    sa.String(64), nullable=False),
        sa.Column("snapshot_date",               sa.String(10), nullable=False),
        sa.Column("total_conflicts",             sa.Integer, server_default="0"),
        sa.Column("resolved_conflicts",          sa.Integer, server_default="0"),
        sa.Column("escalated_conflicts",         sa.Integer, server_default="0"),
        sa.Column("avg_resolution_minutes",      sa.Float, nullable=True),
        sa.Column("total_recommendations_before",sa.Integer, server_default="0"),
        sa.Column("total_recommendations_after", sa.Integer, server_default="0"),
        sa.Column("dedup_rate_pct",              sa.Float, nullable=True),
        sa.Column("conflict_rate_pct",           sa.Float, nullable=True),
        sa.Column("total_impact_gain_yuan",      sa.Numeric(14, 2), nullable=True),
        sa.Column("top_conflict_pair",           sa.String(128), nullable=True),
        sa.Column("created_at",                  sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_collab_snap_brand_date", "agent_collab_snapshots", ["brand_id", "snapshot_date"])


def downgrade() -> None:
    op.drop_table("agent_collab_snapshots")
    op.drop_table("global_optimization_logs")
    op.drop_table("agent_conflicts")
    op.execute("DROP TYPE IF EXISTS arbitration_method_enum")
    op.execute("DROP TYPE IF EXISTS arbitration_status_enum")
    op.execute("DROP TYPE IF EXISTS conflict_severity_enum")
    op.execute("DROP TYPE IF EXISTS conflict_type_enum")
