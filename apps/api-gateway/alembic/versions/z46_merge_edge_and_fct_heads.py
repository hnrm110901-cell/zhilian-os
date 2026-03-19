"""merge edge hub observability head with FCT/data-dictionary head

This merge point unifies two parallel z44/z46 chains:
  - z46_data_dictionary (main FCT chain: z44_fct → z45 → z46_data_dictionary)
  - z44_edge_hub_queue_observability (edge chain: z43_edge_hub_credentials → z44_edge_hub)

Revision ID: z46_merge_edge_and_fct_heads
Revises: z46_data_dictionary, z44_edge_hub_queue_observability
Create Date: 2026-03-19
"""
from alembic import op

revision = "z46_merge_edge_and_fct_heads"
down_revision = ("z46_data_dictionary", "z44_edge_hub_queue_observability")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
