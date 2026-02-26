"""
添加私域运营相关表

Revision ID: p01_private_domain_tables
Revises: o01_neural_event_log
Create Date: 2026-02-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'p01_private_domain_tables'
down_revision = 'o01_neural_event_log'
branch_labels = None
depends_on = None


def upgrade():
    # 1. private_domain_members
    op.create_table(
        'private_domain_members',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('store_id', sa.String(50), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('customer_id', sa.String(100), nullable=False),
        sa.Column('rfm_level', sa.String(5), nullable=False, server_default='S3'),
        sa.Column('store_quadrant', sa.String(20), server_default='potential'),
        sa.Column('dynamic_tags', sa.JSON, server_default='[]'),
        sa.Column('recency_days', sa.Integer, server_default='0'),
        sa.Column('frequency', sa.Integer, server_default='0'),
        sa.Column('monetary', sa.Integer, server_default='0'),
        sa.Column('last_visit', sa.DateTime, nullable=True),
        sa.Column('risk_score', sa.Float, server_default='0.0'),
        sa.Column('channel_source', sa.String(50), nullable=True),
        sa.Column('wechat_openid', sa.String(100), nullable=True),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('rfm_updated_at', sa.DateTime, server_default=sa.text('now()')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_pdm_store_rfm', 'private_domain_members', ['store_id', 'rfm_level'])
    op.create_index('ix_pdm_store_customer', 'private_domain_members',
                    ['store_id', 'customer_id'], unique=True)

    # 2. private_domain_signals
    op.create_table(
        'private_domain_signals',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('signal_id', sa.String(100), unique=True, nullable=False),
        sa.Column('store_id', sa.String(50), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('customer_id', sa.String(100), nullable=True),
        sa.Column('signal_type', sa.String(30), nullable=False),
        sa.Column('description', sa.Text, nullable=False),
        sa.Column('severity', sa.String(20), server_default='medium'),
        sa.Column('action_taken', sa.Text, nullable=True),
        sa.Column('triggered_at', sa.DateTime, server_default=sa.text('now()'), nullable=False),
        sa.Column('resolved_at', sa.DateTime, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_pds_store_type', 'private_domain_signals', ['store_id', 'signal_type'])
    op.create_index('ix_pds_triggered', 'private_domain_signals', ['triggered_at'])
    op.create_index('ix_pds_customer', 'private_domain_signals', ['customer_id'])

    # 3. private_domain_journeys
    op.create_table(
        'private_domain_journeys',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('journey_id', sa.String(100), unique=True, nullable=False),
        sa.Column('store_id', sa.String(50), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('customer_id', sa.String(100), nullable=False),
        sa.Column('journey_type', sa.String(30), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('current_step', sa.Integer, server_default='1'),
        sa.Column('total_steps', sa.Integer, nullable=False),
        sa.Column('step_history', sa.JSON, server_default='[]'),
        sa.Column('started_at', sa.DateTime, server_default=sa.text('now()')),
        sa.Column('next_action_at', sa.DateTime, nullable=True),
        sa.Column('completed_at', sa.DateTime, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_pdj_store_status', 'private_domain_journeys', ['store_id', 'status'])
    op.create_index('ix_pdj_customer', 'private_domain_journeys', ['customer_id'])

    # 4. store_quadrant_records
    op.create_table(
        'store_quadrant_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('store_id', sa.String(50), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('quadrant', sa.String(20), nullable=False),
        sa.Column('competition_density', sa.Float, server_default='0.0'),
        sa.Column('member_penetration', sa.Float, server_default='0.0'),
        sa.Column('untapped_potential', sa.Integer, server_default='0'),
        sa.Column('strategy', sa.Text, nullable=True),
        sa.Column('recorded_at', sa.DateTime, server_default=sa.text('now()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_sqr_store_date', 'store_quadrant_records', ['store_id', 'recorded_at'])


def downgrade():
    op.drop_table('store_quadrant_records')
    op.drop_table('private_domain_journeys')
    op.drop_table('private_domain_signals')
    op.drop_table('private_domain_members')
