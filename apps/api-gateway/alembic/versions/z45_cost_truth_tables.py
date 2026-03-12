"""Cost Truth Engine tables

Revision ID: z45
Revises: z44
Create Date: 2026-03-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "z45"
down_revision = "z44"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Enums ──
    variance_severity = sa.Enum("ok", "watch", "warning", "critical", name="varianceseverity")
    variance_severity.create(op.get_bind(), checkfirst=True)

    attribution_factor = sa.Enum(
        "price_change", "usage_overrun", "waste_loss", "yield_variance", "mix_shift",
        name="attributionfactor",
    )
    attribution_factor.create(op.get_bind(), checkfirst=True)

    # ── cost_truth_daily ──
    op.create_table(
        "cost_truth_daily",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("store_id", sa.String(50), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("truth_date", sa.Date, nullable=False),

        sa.Column("revenue_fen", sa.Integer, server_default="0"),
        sa.Column("theoretical_cost_fen", sa.Integer, server_default="0"),
        sa.Column("actual_cost_fen", sa.Integer, server_default="0"),
        sa.Column("variance_fen", sa.Integer, server_default="0"),

        sa.Column("theoretical_pct", sa.Float, server_default="0"),
        sa.Column("actual_pct", sa.Float, server_default="0"),
        sa.Column("variance_pct", sa.Float, server_default="0"),

        sa.Column("severity", variance_severity, server_default="ok"),

        sa.Column("mtd_actual_pct", sa.Float, nullable=True),
        sa.Column("predicted_eom_pct", sa.Float, nullable=True),
        sa.Column("target_pct", sa.Float, server_default="32"),

        sa.Column("dish_count", sa.Integer, server_default="0"),
        sa.Column("order_count", sa.Integer, server_default="0"),
        sa.Column("top_variance_dish", sa.String(100), nullable=True),
        sa.Column("top_variance_yuan", sa.Float, server_default="0"),

        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),

        sa.UniqueConstraint("store_id", "truth_date", name="uq_cost_truth_daily"),
    )
    op.create_index("ix_cost_truth_store", "cost_truth_daily", ["store_id"])
    op.create_index("ix_cost_truth_date", "cost_truth_daily", ["truth_date"])
    op.create_index("ix_cost_truth_date_sev", "cost_truth_daily", ["truth_date", "severity"])

    # ── cost_truth_dish_detail ──
    op.create_table(
        "cost_truth_dish_detail",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("truth_daily_id", UUID(as_uuid=True), sa.ForeignKey("cost_truth_daily.id"), nullable=False),
        sa.Column("store_id", sa.String(50), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("truth_date", sa.Date, nullable=False),

        sa.Column("dish_id", sa.String(50), nullable=False),
        sa.Column("dish_name", sa.String(100)),
        sa.Column("sold_qty", sa.Integer, server_default="0"),

        sa.Column("theoretical_cost_fen", sa.Integer, server_default="0"),
        sa.Column("actual_cost_fen", sa.Integer, server_default="0"),
        sa.Column("variance_fen", sa.Integer, server_default="0"),
        sa.Column("variance_pct", sa.Float, server_default="0"),

        sa.Column("top_ingredients", sa.JSON, server_default="[]"),

        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),

        sa.UniqueConstraint("truth_daily_id", "dish_id", name="uq_cost_truth_dish"),
    )
    op.create_index("ix_ctd_truth_daily", "cost_truth_dish_detail", ["truth_daily_id"])
    op.create_index("ix_ctd_store", "cost_truth_dish_detail", ["store_id"])
    op.create_index("ix_ctd_dish", "cost_truth_dish_detail", ["dish_id"])

    # ── cost_variance_attribution ──
    op.create_table(
        "cost_variance_attribution",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("truth_daily_id", UUID(as_uuid=True), sa.ForeignKey("cost_truth_daily.id"), nullable=False),
        sa.Column("store_id", sa.String(50), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("truth_date", sa.Date, nullable=False),

        sa.Column("factor", attribution_factor, nullable=False),
        sa.Column("contribution_fen", sa.Integer, server_default="0"),
        sa.Column("contribution_pct", sa.Float, server_default="0"),
        sa.Column("description", sa.Text),
        sa.Column("action", sa.Text),
        sa.Column("detail", sa.JSON, server_default="{}"),

        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),

        sa.UniqueConstraint("truth_daily_id", "factor", name="uq_cost_attribution_factor"),
    )
    op.create_index("ix_cva_truth_daily", "cost_variance_attribution", ["truth_daily_id"])


def downgrade() -> None:
    op.drop_table("cost_variance_attribution")
    op.drop_table("cost_truth_dish_detail")
    op.drop_table("cost_truth_daily")
    sa.Enum(name="attributionfactor").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="varianceseverity").drop(op.get_bind(), checkfirst=True)
