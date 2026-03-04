"""
Task B1: meal_periods 表

Revision ID: b01_meal_period
Revises: a04_dish_channel_configs
Create Date: 2026-03-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'b01_meal_period'
down_revision = 'a04_dish_channel_configs'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'meal_periods',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('store_id', sa.String(50),
                  sa.ForeignKey('stores.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(50), nullable=False),
        sa.Column('start_hour', sa.SmallInteger, nullable=False),
        sa.Column('end_hour', sa.SmallInteger, nullable=False),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.text('NOW()')),
    )
    op.create_unique_constraint(
        'uq_meal_period_store_name', 'meal_periods', ['store_id', 'name']
    )
    op.create_index('idx_meal_period_store_id', 'meal_periods', ['store_id'])
    op.create_index('idx_meal_period_store_active', 'meal_periods', ['store_id', 'is_active'])


def downgrade() -> None:
    op.drop_index('idx_meal_period_store_active', table_name='meal_periods')
    op.drop_index('idx_meal_period_store_id', table_name='meal_periods')
    op.drop_constraint('uq_meal_period_store_name', 'meal_periods', type_='unique')
    op.drop_table('meal_periods')
