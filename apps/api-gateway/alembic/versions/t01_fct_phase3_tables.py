"""FCT Phase 3: 主数据、资金流水、税务占位表

Revision ID: t01_fct_phase3
Revises: s01_fct_tables
Create Date: 2026-02-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 't01_fct_phase3'
down_revision = 's01_fct_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE fctmastertype AS ENUM ('store', 'supplier', 'account', 'bank_account');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    op.create_table(
        'fct_master',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', sa.String(64), nullable=False),
        sa.Column('type', postgresql.ENUM('store', 'supplier', 'account', 'bank_account', name='fctmastertype', create_type=False), nullable=False),
        sa.Column('code', sa.String(64), nullable=False),
        sa.Column('name', sa.String(128), nullable=False),
        sa.Column('extra', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_fct_master_tenant_id'), 'fct_master', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_fct_master_type'), 'fct_master', ['type'], unique=False)
    op.create_index(op.f('ix_fct_master_code'), 'fct_master', ['code'], unique=False)
    op.create_index('ix_fct_master_tenant_type_code', 'fct_master', ['tenant_id', 'type', 'code'], unique=True)

    op.create_table(
        'fct_cash_transactions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', sa.String(64), nullable=False),
        sa.Column('entity_id', sa.String(64), nullable=False),
        sa.Column('tx_date', sa.Date(), nullable=False),
        sa.Column('amount', sa.Numeric(18, 2), nullable=False),
        sa.Column('direction', sa.String(8), nullable=False),
        sa.Column('ref_type', sa.String(32), nullable=True),
        sa.Column('ref_id', sa.String(64), nullable=True),
        sa.Column('status', sa.String(20), nullable=True),
        sa.Column('match_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_fct_cash_transactions_entity_id'), 'fct_cash_transactions', ['entity_id'], unique=False)
    op.create_index(op.f('ix_fct_cash_transactions_tenant_id'), 'fct_cash_transactions', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_fct_cash_transactions_tx_date'), 'fct_cash_transactions', ['tx_date'], unique=False)

    op.create_table(
        'fct_tax_invoices',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', sa.String(64), nullable=False),
        sa.Column('entity_id', sa.String(64), nullable=False),
        sa.Column('invoice_type', sa.String(16), nullable=False),
        sa.Column('invoice_no', sa.String(64), nullable=True),
        sa.Column('amount', sa.Numeric(18, 2), nullable=True),
        sa.Column('tax_amount', sa.Numeric(18, 2), nullable=True),
        sa.Column('invoice_date', sa.Date(), nullable=True),
        sa.Column('status', sa.String(20), nullable=True),
        sa.Column('voucher_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('extra', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['voucher_id'], ['fct_vouchers.id'], ondelete='SET NULL'),
    )
    op.create_index(op.f('ix_fct_tax_invoices_entity_id'), 'fct_tax_invoices', ['entity_id'], unique=False)
    op.create_index(op.f('ix_fct_tax_invoices_invoice_no'), 'fct_tax_invoices', ['invoice_no'], unique=False)
    op.create_index(op.f('ix_fct_tax_invoices_tenant_id'), 'fct_tax_invoices', ['tenant_id'], unique=False)

    op.create_table(
        'fct_tax_declarations',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', sa.String(64), nullable=False),
        sa.Column('entity_id', sa.String(64), nullable=False),
        sa.Column('tax_type', sa.String(32), nullable=False),
        sa.Column('period', sa.String(16), nullable=False),
        sa.Column('declared_at', sa.String(32), nullable=True),
        sa.Column('status', sa.String(20), nullable=True),
        sa.Column('extra', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_fct_tax_declarations_entity_id'), 'fct_tax_declarations', ['entity_id'], unique=False)
    op.create_index(op.f('ix_fct_tax_declarations_tenant_id'), 'fct_tax_declarations', ['tenant_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_fct_tax_declarations_tenant_id'), table_name='fct_tax_declarations')
    op.drop_index(op.f('ix_fct_tax_declarations_entity_id'), table_name='fct_tax_declarations')
    op.drop_table('fct_tax_declarations')

    op.drop_index(op.f('ix_fct_tax_invoices_tenant_id'), table_name='fct_tax_invoices')
    op.drop_index(op.f('ix_fct_tax_invoices_invoice_no'), table_name='fct_tax_invoices')
    op.drop_index(op.f('ix_fct_tax_invoices_entity_id'), table_name='fct_tax_invoices')
    op.drop_table('fct_tax_invoices')

    op.drop_index(op.f('ix_fct_cash_transactions_tx_date'), table_name='fct_cash_transactions')
    op.drop_index(op.f('ix_fct_cash_transactions_tenant_id'), table_name='fct_cash_transactions')
    op.drop_index(op.f('ix_fct_cash_transactions_entity_id'), table_name='fct_cash_transactions')
    op.drop_table('fct_cash_transactions')

    op.drop_index('ix_fct_master_tenant_type_code', table_name='fct_master')
    op.drop_index(op.f('ix_fct_master_code'), table_name='fct_master')
    op.drop_index(op.f('ix_fct_master_type'), table_name='fct_master')
    op.drop_index(op.f('ix_fct_master_tenant_id'), table_name='fct_master')
    op.drop_table('fct_master')

    op.execute('DROP TYPE IF EXISTS fctmastertype')
