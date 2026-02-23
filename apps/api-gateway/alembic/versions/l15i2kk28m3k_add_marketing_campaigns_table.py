"""add marketing campaigns table

Revision ID: l15i2kk28m3k
Revises: k04h1jj17l2j
Create Date: 2026-02-22 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'l15i2kk28m3k'
down_revision = 'k04h1jj17l2j'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'marketing_campaigns',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('store_id', sa.String(50), nullable=False, index=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('campaign_type', sa.String(50)),
        sa.Column('status', sa.String(20), server_default='draft'),
        sa.Column('start_date', sa.Date()),
        sa.Column('end_date', sa.Date()),
        sa.Column('budget', sa.Float(), server_default='0'),
        sa.Column('actual_cost', sa.Float(), server_default='0'),
        sa.Column('reach_count', sa.Integer(), server_default='0'),
        sa.Column('conversion_count', sa.Integer(), server_default='0'),
        sa.Column('revenue_generated', sa.Float(), server_default='0'),
        sa.Column('target_audience', sa.JSON()),
        sa.Column('description', sa.Text()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('NOW()')),
    )
    op.create_index('idx_mc_store_id', 'marketing_campaigns', ['store_id'])
    op.create_index('idx_mc_status', 'marketing_campaigns', ['status'])


def downgrade() -> None:
    op.drop_table('marketing_campaigns')
