"""persist edge hub credentials and telemetry

Revision ID: z43_edge_hub_credentials
Revises: z42_merge_all_heads
Create Date: 2026-03-12
"""
from alembic import op
import sqlalchemy as sa

revision = "z43_edge_hub_credentials"
down_revision = "z42_merge_all_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("edge_hubs", sa.Column("mac_address", sa.String(length=64), nullable=True))
    op.add_column("edge_hubs", sa.Column("network_mode", sa.String(length=32), nullable=False, server_default="cloud"))
    op.add_column("edge_hubs", sa.Column("temperature_c", sa.Float(), nullable=True))
    op.add_column("edge_hubs", sa.Column("uptime_seconds", sa.Integer(), nullable=True))
    op.add_column("edge_hubs", sa.Column("device_secret_hash", sa.String(length=128), nullable=True))
    op.add_column("edge_hubs", sa.Column("provisioned_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("edge_hubs", "provisioned_at")
    op.drop_column("edge_hubs", "device_secret_hash")
    op.drop_column("edge_hubs", "uptime_seconds")
    op.drop_column("edge_hubs", "temperature_c")
    op.drop_column("edge_hubs", "network_mode")
    op.drop_column("edge_hubs", "mac_address")
