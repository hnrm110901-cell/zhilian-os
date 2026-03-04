"""
Task2: SalesChannelConfig 表 + orders.sales_channel 字段

Revision ID: a02_sales_channel
Revises: a01_dish_master
Create Date: 2026-03-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'a02_sales_channel'
down_revision = 'a01_dish_master'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. CREATE TABLE sales_channel_configs
    op.create_table(
        'sales_channel_configs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('brand_id', sa.String(50), nullable=True),
        sa.Column('channel', sa.String(30), nullable=False),
        sa.Column('platform_commission_pct', sa.Numeric(6, 4), nullable=False, server_default='0'),
        sa.Column('delivery_cost_fen', sa.Integer, nullable=False, server_default='0'),
        sa.Column('packaging_cost_fen', sa.Integer, nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.text('NOW()')),
    )
    op.create_unique_constraint(
        'uq_channel_config_brand_channel', 'sales_channel_configs', ['brand_id', 'channel']
    )
    op.create_index('idx_channel_config_brand_id', 'sales_channel_configs', ['brand_id'])
    op.create_index('idx_channel_config_channel', 'sales_channel_configs', ['channel'])

    # 2. ALTER TABLE orders ADD COLUMN sales_channel
    op.add_column(
        'orders',
        sa.Column('sales_channel', sa.String(30), nullable=True),
    )
    op.create_index('idx_order_sales_channel', 'orders', ['sales_channel'])


def downgrade() -> None:
    op.drop_index('idx_order_sales_channel', table_name='orders')
    op.drop_column('orders', 'sales_channel')

    op.drop_index('idx_channel_config_channel', table_name='sales_channel_configs')
    op.drop_index('idx_channel_config_brand_id', table_name='sales_channel_configs')
    op.drop_constraint('uq_channel_config_brand_channel', 'sales_channel_configs', type_='unique')
    op.drop_table('sales_channel_configs')
