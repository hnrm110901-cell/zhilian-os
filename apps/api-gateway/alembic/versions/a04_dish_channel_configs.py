"""
Task4: dish_channel_configs 表（菜品渠道定价）

Revision ID: a04_dish_channel_configs
Revises: a03_bom_scope
Create Date: 2026-03-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'a04_dish_channel_configs'
down_revision = 'a03_bom_scope'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'dish_channel_configs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('dish_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('dishes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('channel', sa.String(30), nullable=False),
        sa.Column('price_fen', sa.Integer, nullable=False),
        sa.Column('is_available', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.text('NOW()')),
    )
    op.create_unique_constraint(
        'uq_dish_channel_config_dish_channel', 'dish_channel_configs', ['dish_id', 'channel']
    )
    op.create_index('idx_dish_channel_config_dish_id', 'dish_channel_configs', ['dish_id'])
    op.create_index('idx_dish_channel_config_channel', 'dish_channel_configs', ['channel'])


def downgrade() -> None:
    op.drop_index('idx_dish_channel_config_channel', table_name='dish_channel_configs')
    op.drop_index('idx_dish_channel_config_dish_id', table_name='dish_channel_configs')
    op.drop_constraint('uq_dish_channel_config_dish_channel', 'dish_channel_configs', type_='unique')
    op.drop_table('dish_channel_configs')
