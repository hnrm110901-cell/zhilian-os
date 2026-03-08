"""wf02 — staffing_patterns 模板库

Revision ID: wf02
Revises: wf01
"""

revision = "wf02"
down_revision = "wf01"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.create_table(
        "staffing_patterns",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("store_id", sa.String(50), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("pattern_name", sa.String(100), nullable=False),
        sa.Column("day_type", sa.String(20), nullable=False),
        sa.Column("meal_period", sa.String(20), nullable=False, server_default="all_day"),
        sa.Column("shifts_template", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("source_start_date", sa.Date, nullable=True),
        sa.Column("source_end_date", sa.Date, nullable=True),
        sa.Column("sample_days", sa.Integer, nullable=False, server_default="0"),
        sa.Column("avg_labor_cost_rate", sa.Numeric(6, 2), nullable=True),
        sa.Column("performance_score", sa.Numeric(6, 2), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("ix_sp_store_day_type", "staffing_patterns", ["store_id", "day_type"])
    op.create_unique_constraint(
        "uq_sp_store_day_meal",
        "staffing_patterns",
        ["store_id", "day_type", "meal_period"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_sp_store_day_meal", "staffing_patterns", type_="unique")
    op.drop_index("ix_sp_store_day_type", table_name="staffing_patterns")
    op.drop_table("staffing_patterns")
