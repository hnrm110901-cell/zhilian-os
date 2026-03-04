"""
Task B2: order_items 添加食材实际成本字段

Revision ID: b02_order_item_food_cost
Revises: b01_meal_period
Create Date: 2026-03-02
"""
from alembic import op
import sqlalchemy as sa

revision = 'b02_order_item_food_cost'
down_revision = 'b01_meal_period'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('order_items',
        sa.Column('food_cost_actual', sa.Integer, nullable=True)
    )
    op.add_column('order_items',
        sa.Column('gross_margin', sa.Numeric(6, 4), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('order_items', 'gross_margin')
    op.drop_column('order_items', 'food_cost_actual')
