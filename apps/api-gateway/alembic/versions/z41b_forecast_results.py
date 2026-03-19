"""z41_forecast_results

补齐 FEAT-002 预测性备料引擎的 forecast_results 持久化表。

Revision ID: z41b
Revises: z41
Create Date: 2026-03-12
"""
from alembic import op
import sqlalchemy as sa


revision = "z41b"
down_revision = "z41"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "forecast_results",
        sa.Column("id", sa.String(length=50), nullable=False),
        sa.Column("store_id", sa.String(length=50), nullable=False),
        sa.Column("brand_id", sa.String(length=50), nullable=True),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("metric", sa.String(length=50), nullable=False, server_default="revenue"),
        sa.Column("predicted_value", sa.Float(), nullable=False),
        sa.Column("confidence", sa.String(length=20), nullable=False),
        sa.Column("basis", sa.String(length=50), nullable=False),
        sa.Column("estimated_revenue", sa.Float(), nullable=True),
        sa.Column("generated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("items", sa.JSON(), nullable=True, server_default=sa.text("'[]'")),
        sa.Column("actual_value", sa.Float(), nullable=True),
        sa.Column("accuracy_pct", sa.Float(), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_forecast_results_store_id", "forecast_results", ["store_id"])
    op.create_index("ix_forecast_results_target_date", "forecast_results", ["target_date"])


def downgrade() -> None:
    op.drop_index("ix_forecast_results_target_date", table_name="forecast_results")
    op.drop_index("ix_forecast_results_store_id", table_name="forecast_results")
    op.drop_table("forecast_results")
