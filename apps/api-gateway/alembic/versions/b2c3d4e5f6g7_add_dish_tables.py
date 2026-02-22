"""
添加菜品主档表

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2026-02-22

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6g7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """创建菜品相关表"""

    # 1. 创建dish_categories表（菜品分类）
    op.create_table(
        'dish_categories',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('store_id', sa.String(50), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('code', sa.String(50)),
        sa.Column('parent_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('dish_categories.id')),
        sa.Column('sort_order', sa.Integer, default=0),
        sa.Column('description', sa.Text),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()')),
    )
    op.create_index('idx_dish_category_store_id', 'dish_categories', ['store_id'])
    op.create_index('idx_dish_category_parent_id', 'dish_categories', ['parent_id'])

    # 2. 创建dishes表（菜品主档）
    op.create_table(
        'dishes',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('store_id', sa.String(50), sa.ForeignKey('stores.id'), nullable=False),
        # 基本信息
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('code', sa.String(50), unique=True, nullable=False),
        sa.Column('category_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('dish_categories.id')),
        sa.Column('description', sa.Text),
        sa.Column('image_url', sa.String(500)),
        # 价格信息
        sa.Column('price', sa.Numeric(10, 2), nullable=False),
        sa.Column('original_price', sa.Numeric(10, 2)),
        sa.Column('cost', sa.Numeric(10, 2)),
        sa.Column('profit_margin', sa.Numeric(5, 2)),
        # 规格信息
        sa.Column('unit', sa.String(20), default='份'),
        sa.Column('serving_size', sa.String(50)),
        sa.Column('spicy_level', sa.Integer, default=0),
        # 营养信息
        sa.Column('calories', sa.Integer),
        sa.Column('protein', sa.Numeric(5, 2)),
        sa.Column('fat', sa.Numeric(5, 2)),
        sa.Column('carbohydrate', sa.Numeric(5, 2)),
        # 标签和属性
        sa.Column('tags', postgresql.ARRAY(sa.String)),
        sa.Column('allergens', postgresql.ARRAY(sa.String)),
        sa.Column('dietary_info', postgresql.ARRAY(sa.String)),
        # 销售信息
        sa.Column('is_available', sa.Boolean, default=True),
        sa.Column('is_recommended', sa.Boolean, default=False),
        sa.Column('is_seasonal', sa.Boolean, default=False),
        sa.Column('season', sa.String(20)),
        sa.Column('sort_order', sa.Integer, default=0),
        # 制作信息
        sa.Column('preparation_time', sa.Integer),
        sa.Column('cooking_method', sa.String(50)),
        sa.Column('kitchen_station', sa.String(50)),
        # 统计信息
        sa.Column('total_sales', sa.Integer, default=0),
        sa.Column('total_revenue', sa.Numeric(12, 2), default=0),
        sa.Column('rating', sa.Numeric(3, 2)),
        sa.Column('review_count', sa.Integer, default=0),
        # 库存关联
        sa.Column('requires_inventory', sa.Boolean, default=True),
        sa.Column('low_stock_threshold', sa.Integer),
        # 额外信息
        sa.Column('notes', sa.Text),
        sa.Column('metadata', postgresql.JSON),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()')),
    )
    op.create_index('idx_dish_store_id', 'dishes', ['store_id'])
    op.create_index('idx_dish_code', 'dishes', ['code'])
    op.create_index('idx_dish_category_id', 'dishes', ['category_id'])
    op.create_index('idx_dish_store_available', 'dishes', ['store_id', 'is_available'])
    op.create_index('idx_dish_store_category', 'dishes', ['store_id', 'category_id'])

    # 3. 创建dish_ingredients表（菜品-食材关联）
    op.create_table(
        'dish_ingredients',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('store_id', sa.String(50), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('dish_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('dishes.id'), nullable=False),
        sa.Column('ingredient_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('inventory_items.id'), nullable=False),
        sa.Column('quantity', sa.Numeric(10, 3), nullable=False),
        sa.Column('unit', sa.String(20), nullable=False),
        sa.Column('cost_per_serving', sa.Numeric(10, 2)),
        sa.Column('is_required', sa.Boolean, default=True),
        sa.Column('is_substitutable', sa.Boolean, default=False),
        sa.Column('substitute_ids', postgresql.ARRAY(postgresql.UUID(as_uuid=True))),
        sa.Column('notes', sa.Text),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()')),
    )
    op.create_index('idx_dish_ingredient_dish_id', 'dish_ingredients', ['dish_id'])
    op.create_index('idx_dish_ingredient_ingredient_id', 'dish_ingredients', ['ingredient_id'])
    op.create_index('idx_dish_ingredient_store_id', 'dish_ingredients', ['store_id'])


def downgrade() -> None:
    """删除菜品相关表"""
    op.drop_table('dish_ingredients')
    op.drop_table('dishes')
    op.drop_table('dish_categories')
