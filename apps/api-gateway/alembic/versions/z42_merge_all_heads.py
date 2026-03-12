"""z42 merge all active heads

Revision ID: z42_merge_all_heads
Revises: h03_orders_missing_columns, wf02, z41
Create Date: 2026-03-12
"""

from alembic import op


revision = "z42_merge_all_heads"
down_revision = ("h03_orders_missing_columns", "wf02", "z41")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
