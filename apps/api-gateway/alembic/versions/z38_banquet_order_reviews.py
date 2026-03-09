"""banquet_order_reviews table

Revision ID: z38
Revises: z37
Create Date: 2026-03-09
"""
from alembic import op
import sqlalchemy as sa

revision = "z38"
down_revision = "z37"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "banquet_order_reviews",
        sa.Column("id",                 sa.String(36),  nullable=False),
        sa.Column("banquet_order_id",   sa.String(36),  nullable=False),
        sa.Column("customer_rating",    sa.Integer(),   nullable=True),
        sa.Column("ai_score",           sa.Float(),     nullable=True),
        sa.Column("ai_summary",         sa.Text(),      nullable=True),
        sa.Column("improvement_tags",   sa.JSON(),      nullable=True),
        sa.Column("revenue_yuan",       sa.Float(),     nullable=True),
        sa.Column("gross_profit_yuan",  sa.Float(),     nullable=True),
        sa.Column("gross_margin_pct",   sa.Float(),     nullable=True),
        sa.Column("overdue_task_count", sa.Integer(),   nullable=False, server_default="0"),
        sa.Column("exception_count",    sa.Integer(),   nullable=False, server_default="0"),
        sa.Column("created_at",         sa.DateTime(),  nullable=True),
        sa.Column("updated_at",         sa.DateTime(),  nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["banquet_order_id"], ["banquet_orders.id"]),
        sa.UniqueConstraint("banquet_order_id", name="uq_review_order"),
    )
    op.create_index("ix_banquet_order_reviews_order_id",
                    "banquet_order_reviews", ["banquet_order_id"])


def downgrade() -> None:
    op.drop_index("ix_banquet_order_reviews_order_id",
                  table_name="banquet_order_reviews")
    op.drop_table("banquet_order_reviews")
