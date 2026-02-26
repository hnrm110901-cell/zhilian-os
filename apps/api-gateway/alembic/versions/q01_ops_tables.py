"""
添加运维相关表

Revision ID: q01_ops_tables
Revises: p01_private_domain_tables
Create Date: 2026-02-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'q01_ops_tables'
down_revision = 'p01_private_domain_tables'
branch_labels = None
depends_on = None


def upgrade():
    # 1. ops_assets（先建，maintenance_plans 有 FK 依赖）
    op.create_table(
        'ops_assets',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('store_id', sa.String(50), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('asset_type', sa.String(30), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('mac_address', sa.String(17), nullable=True),
        sa.Column('firmware_version', sa.String(50), nullable=True),
        sa.Column('serial_number', sa.String(100), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='online'),
        sa.Column('last_seen', sa.DateTime, nullable=True),
        sa.Column('asset_metadata', sa.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.text('now()')),
    )
    op.create_index('ix_ops_assets_store_id', 'ops_assets', ['store_id'])
    op.create_index('ix_ops_assets_type', 'ops_assets', ['asset_type'])
    op.create_index('ix_ops_assets_status', 'ops_assets', ['status'])

    # 2. ops_events
    op.create_table(
        'ops_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('store_id', sa.String(50), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('severity', sa.String(20), nullable=False, server_default='medium'),
        sa.Column('component', sa.String(100), nullable=True),
        sa.Column('description', sa.Text, nullable=False),
        sa.Column('raw_data', sa.JSON, nullable=True),
        sa.Column('diagnosis', sa.Text, nullable=True),
        sa.Column('resolution', sa.Text, nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='open'),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('now()'), nullable=False),
        sa.Column('resolved_at', sa.DateTime, nullable=True),
    )
    op.create_index('ix_ops_events_store_id', 'ops_events', ['store_id'])
    op.create_index('ix_ops_events_severity', 'ops_events', ['severity'])
    op.create_index('ix_ops_events_status', 'ops_events', ['status'])
    op.create_index('ix_ops_events_created', 'ops_events', ['created_at'])

    # 3. ops_maintenance_plans
    op.create_table(
        'ops_maintenance_plans',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('store_id', sa.String(50), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('asset_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('ops_assets.id'), nullable=True),
        sa.Column('plan_type', sa.String(50), nullable=False),
        sa.Column('description', sa.Text, nullable=False),
        sa.Column('priority', sa.String(20), nullable=False, server_default='medium'),
        sa.Column('scheduled_at', sa.DateTime, nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('now()'), nullable=False),
        sa.Column('completed_at', sa.DateTime, nullable=True),
    )
    op.create_index('ix_ops_mp_store_id', 'ops_maintenance_plans', ['store_id'])
    op.create_index('ix_ops_mp_status', 'ops_maintenance_plans', ['status'])
    op.create_index('ix_ops_mp_scheduled', 'ops_maintenance_plans', ['scheduled_at'])


def downgrade():
    op.drop_table('ops_maintenance_plans')
    op.drop_table('ops_events')
    op.drop_table('ops_assets')
