"""
Task3A: BOMTemplate scope/channel/parent_bom_id/is_delta 字段扩展
        BOMItem item_action/ingredient_master_id 字段扩展

Revision ID: a03_bom_scope
Revises: a02_sales_channel
Create Date: 2026-03-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'a03_bom_scope'
down_revision = 'a02_sales_channel'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. ALTER TABLE bom_templates: 新增 scope/scope_id/channel/parent_bom_id/is_delta
    op.add_column('bom_templates', sa.Column('scope', sa.String(20), nullable=False, server_default='store'))
    op.add_column('bom_templates', sa.Column('scope_id', sa.String(100), nullable=True))
    op.add_column('bom_templates', sa.Column('channel', sa.String(30), nullable=True))
    op.add_column(
        'bom_templates',
        sa.Column('parent_bom_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        'fk_bom_parent_bom_id', 'bom_templates', 'bom_templates',
        ['parent_bom_id'], ['id'], ondelete='SET NULL'
    )
    op.add_column('bom_templates', sa.Column('is_delta', sa.Boolean, nullable=False, server_default='false'))

    # 索引
    op.create_index('idx_bom_scope', 'bom_templates', ['scope'])
    op.create_index('idx_bom_scope_id', 'bom_templates', ['scope_id'])
    op.create_index('idx_bom_channel', 'bom_templates', ['channel'])
    op.create_index('idx_bom_parent_bom_id', 'bom_templates', ['parent_bom_id'])
    op.create_index('idx_bom_is_delta', 'bom_templates', ['is_delta'])

    # 2. ALTER TABLE bom_items: 新增 item_action/ingredient_master_id
    op.add_column('bom_items', sa.Column('item_action', sa.String(20), nullable=False, server_default='ADD'))
    op.add_column('bom_items', sa.Column('ingredient_master_id', sa.String(50), nullable=True))

    # 索引
    op.create_index('idx_bom_item_action', 'bom_items', ['item_action'])
    op.create_index('idx_bom_item_ingredient_master_id', 'bom_items', ['ingredient_master_id'])


def downgrade() -> None:
    op.drop_index('idx_bom_item_ingredient_master_id', table_name='bom_items')
    op.drop_index('idx_bom_item_action', table_name='bom_items')
    op.drop_column('bom_items', 'ingredient_master_id')
    op.drop_column('bom_items', 'item_action')

    op.drop_index('idx_bom_is_delta', table_name='bom_templates')
    op.drop_index('idx_bom_parent_bom_id', table_name='bom_templates')
    op.drop_index('idx_bom_channel', table_name='bom_templates')
    op.drop_index('idx_bom_scope_id', table_name='bom_templates')
    op.drop_index('idx_bom_scope', table_name='bom_templates')
    op.drop_constraint('fk_bom_parent_bom_id', 'bom_templates', type_='foreignkey')
    op.drop_column('bom_templates', 'is_delta')
    op.drop_column('bom_templates', 'parent_bom_id')
    op.drop_column('bom_templates', 'channel')
    op.drop_column('bom_templates', 'scope_id')
    op.drop_column('bom_templates', 'scope')
