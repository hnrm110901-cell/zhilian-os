"""
Phase 1 — BOM 版本化配方管理表

Revision ID: r01_bom_tables
Revises: rls_001_tenant_isolation
Create Date: 2026-02-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'r01_bom_tables'
down_revision = 'rls_001_tenant_isolation'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── bom_templates ──────────────────────────────────────────────────────────
    op.create_table(
        'bom_templates',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('store_id', sa.String(50), sa.ForeignKey('stores.id', ondelete='CASCADE'), nullable=False),
        sa.Column('dish_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('dishes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('version', sa.String(20), nullable=False),
        sa.Column('effective_date', sa.DateTime(), nullable=False),
        sa.Column('expiry_date', sa.DateTime(), nullable=True),
        sa.Column('yield_rate', sa.Numeric(5, 4), nullable=False, server_default='1.0'),
        sa.Column('standard_portion', sa.Numeric(8, 3), nullable=True),
        sa.Column('prep_time_minutes', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_approved', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('approved_by', sa.String(100), nullable=True),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_by', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()'), onupdate=sa.text('NOW()')),
        sa.UniqueConstraint('dish_id', 'version', name='uq_bom_dish_version'),
    )
    op.create_index('idx_bom_store_id', 'bom_templates', ['store_id'])
    op.create_index('idx_bom_dish_id', 'bom_templates', ['dish_id'])
    op.create_index('idx_bom_active', 'bom_templates', ['dish_id', 'is_active'])
    op.create_index('idx_bom_effective_date', 'bom_templates', ['effective_date'])

    # ── bom_items ──────────────────────────────────────────────────────────────
    op.create_table(
        'bom_items',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('bom_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('bom_templates.id', ondelete='CASCADE'), nullable=False),
        sa.Column('store_id', sa.String(50), sa.ForeignKey('stores.id', ondelete='CASCADE'), nullable=False),
        sa.Column('ingredient_id', sa.String(50), sa.ForeignKey('inventory_items.id'), nullable=False),
        sa.Column('standard_qty', sa.Numeric(10, 4), nullable=False),
        sa.Column('raw_qty', sa.Numeric(10, 4), nullable=True),
        sa.Column('unit', sa.String(20), nullable=False),
        sa.Column('unit_cost', sa.Integer(), nullable=True),
        sa.Column('is_key_ingredient', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_optional', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('waste_factor', sa.Numeric(5, 4), nullable=True, server_default='0.0'),
        sa.Column('prep_notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.UniqueConstraint('bom_id', 'ingredient_id', name='uq_bom_item_ingredient'),
    )
    op.create_index('idx_bom_item_bom_id', 'bom_items', ['bom_id'])
    op.create_index('idx_bom_item_ingredient_id', 'bom_items', ['ingredient_id'])
    op.create_index('idx_bom_item_store_id', 'bom_items', ['store_id'])

    # ── RLS for bom_templates ──────────────────────────────────────────────────
    conn = op.get_bind()
    for tbl in ('bom_templates', 'bom_items'):
        conn.execute(sa.text(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY"))
        conn.execute(sa.text(
            f"CREATE POLICY tenant_isolation ON {tbl} "
            f"USING (store_id = current_setting('app.current_store_id', TRUE))"
        ))


def downgrade() -> None:
    op.drop_table('bom_items')
    op.drop_table('bom_templates')
