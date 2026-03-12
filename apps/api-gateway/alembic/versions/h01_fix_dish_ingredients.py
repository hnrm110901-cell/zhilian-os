"""
修复 dish_ingredients 表缺失问题

由于旧版 b2c3d4e5f6g7 迁移中 ingredient_id 列类型为 UUID 而
inventory_items.id 为 VARCHAR，导致 FK 约束建立失败，dish_ingredients
表未能创建。本迁移补建该表（ingredient_id 使用 String(50)）。

Revision ID: h01_fix_dish_ingredients
Revises: g01_onboarding_engine
Create Date: 2026-03-06
"""
from alembic import op, context
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'h01_fix_dish_ingredients'
down_revision = 'g01_onboarding_engine'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 仅在表不存在时创建，防止重复执行报错
    if context.is_offline_mode():
        exists = False
    else:
        conn = op.get_bind()
        exists = conn.execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM pg_tables "
                "WHERE schemaname='public' AND tablename='dish_ingredients')"
            )
        ).scalar()

    if not exists:
        op.create_table(
            'dish_ingredients',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('store_id', sa.String(50), sa.ForeignKey('stores.id'), nullable=False),
            sa.Column('dish_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('dishes.id'), nullable=False),
            sa.Column('ingredient_id', sa.String(50), sa.ForeignKey('inventory_items.id'), nullable=False),
            sa.Column('quantity', sa.Numeric(10, 3), nullable=False),
            sa.Column('unit', sa.String(20), nullable=False),
            sa.Column('cost_per_serving', sa.Numeric(10, 2)),
            sa.Column('is_required', sa.Boolean, server_default='true'),
            sa.Column('is_substitutable', sa.Boolean, server_default='false'),
            sa.Column('substitute_ids', postgresql.ARRAY(sa.String(50))),
            sa.Column('notes', sa.Text),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        )
        op.create_index('idx_dish_ingredient_dish_id', 'dish_ingredients', ['dish_id'])
        op.create_index('idx_dish_ingredient_ingredient_id', 'dish_ingredients', ['ingredient_id'])
        op.create_index('idx_dish_ingredient_store_id', 'dish_ingredients', ['store_id'])


def downgrade() -> None:
    op.drop_table('dish_ingredients')
