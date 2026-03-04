"""
Task1: dish_master 集团菜品主档 + BrandMenu + StoreMenu + dishes.dish_master_id

Revision ID: a01_dish_master
Revises: z03_execution_audit
Create Date: 2026-03-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'a01_dish_master'
down_revision = 'z03_execution_audit'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. CREATE TABLE dish_master
    op.create_table(
        'dish_master',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('sku_code', sa.String(50), nullable=False),
        sa.Column('canonical_name', sa.String(200), nullable=False),
        sa.Column('category_name', sa.String(100), nullable=False),
        sa.Column('floor_price', sa.Integer, nullable=False, server_default='0'),
        sa.Column('allergens', postgresql.ARRAY(sa.String), nullable=False, server_default='{}'),
        sa.Column('brand_id', sa.String(50), nullable=True),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.text('NOW()')),
    )
    op.create_unique_constraint('uq_dish_master_sku_code', 'dish_master', ['sku_code'])
    op.create_index('idx_dish_master_sku_code', 'dish_master', ['sku_code'])
    op.create_index('idx_dish_master_brand_id', 'dish_master', ['brand_id'])
    op.create_index('idx_dish_master_is_active', 'dish_master', ['is_active'])

    # 2. CREATE TABLE brand_menus
    op.create_table(
        'brand_menus',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('brand_id', sa.String(50), nullable=False),
        sa.Column('dish_master_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('dish_master.id', ondelete='CASCADE'), nullable=False),
        sa.Column('price_fen', sa.Integer, nullable=True),
        sa.Column('is_available', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.text('NOW()')),
    )
    op.create_unique_constraint(
        'uq_brand_menu_brand_dish', 'brand_menus', ['brand_id', 'dish_master_id']
    )
    op.create_index('idx_brand_menu_brand_id', 'brand_menus', ['brand_id'])
    op.create_index('idx_brand_menu_dish_master_id', 'brand_menus', ['dish_master_id'])

    # 3. CREATE TABLE store_menus
    op.create_table(
        'store_menus',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('store_id', sa.String(50),
                  sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('dish_master_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('dish_master.id', ondelete='CASCADE'), nullable=False),
        sa.Column('price_fen', sa.Integer, nullable=True),
        sa.Column('is_available', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.text('NOW()')),
    )
    op.create_unique_constraint(
        'uq_store_menu_store_dish', 'store_menus', ['store_id', 'dish_master_id']
    )
    op.create_index('idx_store_menu_store_id', 'store_menus', ['store_id'])
    op.create_index('idx_store_menu_dish_master_id', 'store_menus', ['dish_master_id'])

    # 4. ALTER TABLE dishes ADD COLUMN dish_master_id
    op.add_column(
        'dishes',
        sa.Column('dish_master_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        'fk_dish_dish_master_id', 'dishes', 'dish_master',
        ['dish_master_id'], ['id'], ondelete='SET NULL'
    )
    op.create_index('idx_dish_dish_master_id', 'dishes', ['dish_master_id'])


def downgrade() -> None:
    op.drop_index('idx_dish_dish_master_id', table_name='dishes')
    op.drop_constraint('fk_dish_dish_master_id', 'dishes', type_='foreignkey')
    op.drop_column('dishes', 'dish_master_id')

    op.drop_index('idx_store_menu_dish_master_id', table_name='store_menus')
    op.drop_index('idx_store_menu_store_id', table_name='store_menus')
    op.drop_constraint('uq_store_menu_store_dish', 'store_menus', type_='unique')
    op.drop_table('store_menus')

    op.drop_index('idx_brand_menu_dish_master_id', table_name='brand_menus')
    op.drop_index('idx_brand_menu_brand_id', table_name='brand_menus')
    op.drop_constraint('uq_brand_menu_brand_dish', 'brand_menus', type_='unique')
    op.drop_table('brand_menus')

    op.drop_index('idx_dish_master_is_active', table_name='dish_master')
    op.drop_index('idx_dish_master_brand_id', table_name='dish_master')
    op.drop_index('idx_dish_master_sku_code', table_name='dish_master')
    op.drop_constraint('uq_dish_master_sku_code', 'dish_master', type_='unique')
    op.drop_table('dish_master')
