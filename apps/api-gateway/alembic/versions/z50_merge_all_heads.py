"""z50 merge all active heads

Merges hr21, z44_edge_hub_queue_observability, z49_pos_daily_summaries
into a single head for linear migration history.

Revision ID: z50_merge_all_heads
Revises: hr21, z44_edge_hub_queue_observability, z49_pos_daily_summaries
Create Date: 2026-03-16
"""

from alembic import op


revision = "z50_merge_all_heads"
down_revision = ("hr21", "z44_edge_hub_queue_observability", "z49_pos_daily_summaries")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
