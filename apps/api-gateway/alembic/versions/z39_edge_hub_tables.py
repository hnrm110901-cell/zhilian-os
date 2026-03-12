"""edge_hub tables

Revision ID: z39_edge_hub_tables
Revises: z38
Create Date: 2026-03-11
"""
from alembic import op
import sqlalchemy as sa

revision = "z39_edge_hub_tables"
down_revision = "z38"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "edge_hubs",
        sa.Column("id",              sa.String(36),  nullable=False),
        sa.Column("store_id",        sa.String(36),  nullable=False),
        sa.Column("hub_code",        sa.String(64),  nullable=False),
        sa.Column("name",            sa.String(128), nullable=True),
        sa.Column("status",          sa.String(32),  nullable=False, server_default="offline"),
        sa.Column("runtime_version", sa.String(32),  nullable=True),
        sa.Column("ip_address",      sa.String(64),  nullable=True),
        sa.Column("last_heartbeat",  sa.DateTime(),  nullable=True),
        sa.Column("cpu_pct",         sa.Float(),     nullable=True),
        sa.Column("mem_pct",         sa.Float(),     nullable=True),
        sa.Column("disk_pct",        sa.Float(),     nullable=True),
        sa.Column("is_active",       sa.Boolean(),   nullable=False, server_default="true"),
        sa.Column("created_at",      sa.DateTime(),  nullable=False),
        sa.Column("updated_at",      sa.DateTime(),  nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("hub_code", name="uq_edge_hub_code"),
    )
    op.create_index("ix_edge_hubs_store_id", "edge_hubs", ["store_id"])

    op.create_table(
        "edge_devices",
        sa.Column("id",           sa.String(36),  nullable=False),
        sa.Column("hub_id",       sa.String(36),  nullable=False),
        sa.Column("store_id",     sa.String(36),  nullable=False),
        sa.Column("device_code",  sa.String(64),  nullable=False),
        sa.Column("device_type",  sa.String(32),  nullable=False),
        sa.Column("name",         sa.String(128), nullable=True),
        sa.Column("status",       sa.String(32),  nullable=False, server_default="offline"),
        sa.Column("last_seen",    sa.DateTime(),  nullable=True),
        sa.Column("firmware_ver", sa.String(32),  nullable=True),
        sa.Column("extra",        sa.JSON(),      nullable=True),
        sa.Column("created_at",   sa.DateTime(),  nullable=False),
        sa.Column("updated_at",   sa.DateTime(),  nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["hub_id"], ["edge_hubs.id"]),
    )
    op.create_index("ix_edge_devices_hub_id",   "edge_devices", ["hub_id"])
    op.create_index("ix_edge_devices_store_id", "edge_devices", ["store_id"])

    op.create_table(
        "headset_bindings",
        sa.Column("id",          sa.String(36), nullable=False),
        sa.Column("store_id",    sa.String(36), nullable=False),
        sa.Column("device_id",   sa.String(36), nullable=False),
        sa.Column("position",    sa.String(64), nullable=False),
        sa.Column("employee_id", sa.String(36), nullable=True),
        sa.Column("channel",     sa.Integer(),  nullable=True),
        sa.Column("status",      sa.String(32), nullable=False, server_default="active"),
        sa.Column("bound_at",    sa.DateTime(), nullable=True),
        sa.Column("unbound_at",  sa.DateTime(), nullable=True),
        sa.Column("created_at",  sa.DateTime(), nullable=False),
        sa.Column("updated_at",  sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["device_id"], ["edge_devices.id"]),
    )
    op.create_index("ix_headset_bindings_store_id", "headset_bindings", ["store_id"])

    op.create_table(
        "edge_alerts",
        sa.Column("id",          sa.String(36),  nullable=False),
        sa.Column("store_id",    sa.String(36),  nullable=False),
        sa.Column("hub_id",      sa.String(36),  nullable=True),
        sa.Column("device_id",   sa.String(36),  nullable=True),
        sa.Column("level",       sa.String(8),   nullable=False, server_default="p3"),
        sa.Column("alert_type",  sa.String(64),  nullable=False),
        sa.Column("message",     sa.Text(),      nullable=True),
        sa.Column("status",      sa.String(32),  nullable=False, server_default="open"),
        sa.Column("resolved_at", sa.DateTime(),  nullable=True),
        sa.Column("resolved_by", sa.String(64),  nullable=True),
        sa.Column("created_at",  sa.DateTime(),  nullable=False),
        sa.Column("updated_at",  sa.DateTime(),  nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["hub_id"], ["edge_hubs.id"]),
    )
    op.create_index("ix_edge_alerts_store_id", "edge_alerts", ["store_id"])
    op.create_index("ix_edge_alerts_hub_id",   "edge_alerts", ["hub_id"])
    op.create_index("ix_edge_alerts_status",   "edge_alerts", ["status"])


def downgrade() -> None:
    op.drop_index("ix_edge_alerts_status",      table_name="edge_alerts")
    op.drop_index("ix_edge_alerts_hub_id",      table_name="edge_alerts")
    op.drop_index("ix_edge_alerts_store_id",    table_name="edge_alerts")
    op.drop_table("edge_alerts")

    op.drop_index("ix_headset_bindings_store_id", table_name="headset_bindings")
    op.drop_table("headset_bindings")

    op.drop_index("ix_edge_devices_store_id", table_name="edge_devices")
    op.drop_index("ix_edge_devices_hub_id",   table_name="edge_devices")
    op.drop_table("edge_devices")

    op.drop_index("ix_edge_hubs_store_id", table_name="edge_hubs")
    op.drop_table("edge_hubs")
