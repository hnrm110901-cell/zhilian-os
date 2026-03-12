"""persist edge hub queue observability

Revision ID: z44_edge_hub_queue_observability
Revises: z43_edge_hub_credentials
Create Date: 2026-03-12
"""
from alembic import op
import sqlalchemy as sa

revision = "z44_edge_hub_queue_observability"
down_revision = "z43_edge_hub_credentials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("edge_hubs", sa.Column("pending_status_queue", sa.Integer(), nullable=True))
    op.add_column("edge_hubs", sa.Column("last_queue_error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("edge_hubs", "last_queue_error")
    op.drop_column("edge_hubs", "pending_status_queue")
