"""banquet_revenue_targets table

Revision ID: z37_banquet_revenue_target
Revises: z36
Create Date: 2026-03-09
"""
from alembic import op
import sqlalchemy as sa

revision = "z37_banquet_revenue_target"
down_revision = "z36"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "banquet_revenue_targets",
        sa.Column("id",         sa.String(36),  nullable=False),
        sa.Column("store_id",   sa.String(36),  nullable=False),
        sa.Column("year",       sa.Integer(),   nullable=False),
        sa.Column("month",      sa.Integer(),   nullable=False),
        sa.Column("target_fen", sa.Integer(),   nullable=False),
        sa.Column("created_at", sa.DateTime(),  nullable=True),
        sa.Column("updated_at", sa.DateTime(),  nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("store_id", "year", "month",
                            name="uq_revenue_target_store_ym"),
    )
    op.create_index("ix_revenue_target_store", "banquet_revenue_targets",
                    ["store_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_revenue_target_store", table_name="banquet_revenue_targets")
    op.drop_table("banquet_revenue_targets")
