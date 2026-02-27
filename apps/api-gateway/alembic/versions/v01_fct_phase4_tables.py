"""FCT Phase 4：费控/备用金、预算占位、发票闭环、审批流占位

Revision ID: v01_fct_phase4
Revises: u01_fct_plans
Create Date: 2026-02-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'v01_fct_phase4'
down_revision = 'u01_fct_plans'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'fct_petty_cash',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', sa.String(64), nullable=False),
        sa.Column('entity_id', sa.String(64), nullable=False),
        sa.Column('cash_type', sa.String(16), nullable=False),
        sa.Column('amount_limit', sa.Numeric(18, 2), nullable=False, server_default='0'),
        sa.Column('current_balance', sa.Numeric(18, 2), nullable=False, server_default='0'),
        sa.Column('status', sa.String(20), nullable=False, server_default='active'),
        sa.Column('extra', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_fct_petty_cash_tenant_id'), 'fct_petty_cash', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_fct_petty_cash_entity_id'), 'fct_petty_cash', ['entity_id'], unique=False)
    op.create_index(op.f('ix_fct_petty_cash_cash_type'), 'fct_petty_cash', ['cash_type'], unique=False)

    op.create_table(
        'fct_petty_cash_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('petty_cash_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('record_type', sa.String(16), nullable=False),
        sa.Column('amount', sa.Numeric(18, 2), nullable=False),
        sa.Column('biz_date', sa.Date(), nullable=False),
        sa.Column('ref_type', sa.String(32), nullable=True),
        sa.Column('ref_id', sa.String(64), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('extra', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['petty_cash_id'], ['fct_petty_cash.id'], ondelete='CASCADE'),
    )
    op.create_index(op.f('ix_fct_petty_cash_records_petty_cash_id'), 'fct_petty_cash_records', ['petty_cash_id'], unique=False)
    op.create_index(op.f('ix_fct_petty_cash_records_record_type'), 'fct_petty_cash_records', ['record_type'], unique=False)
    op.create_index(op.f('ix_fct_petty_cash_records_biz_date'), 'fct_petty_cash_records', ['biz_date'], unique=False)

    op.create_table(
        'fct_budgets',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', sa.String(64), nullable=False),
        sa.Column('entity_id', sa.String(64), nullable=False, server_default=''),
        sa.Column('budget_type', sa.String(16), nullable=False),
        sa.Column('period', sa.String(32), nullable=False),
        sa.Column('category', sa.String(64), nullable=False),
        sa.Column('amount', sa.Numeric(18, 2), nullable=False, server_default='0'),
        sa.Column('used', sa.Numeric(18, 2), nullable=False, server_default='0'),
        sa.Column('status', sa.String(20), nullable=False, server_default='active'),
        sa.Column('extra', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_fct_budgets_tenant_id'), 'fct_budgets', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_fct_budgets_entity_id'), 'fct_budgets', ['entity_id'], unique=False)
    op.create_index(op.f('ix_fct_budgets_budget_type'), 'fct_budgets', ['budget_type'], unique=False)
    op.create_index(op.f('ix_fct_budgets_period'), 'fct_budgets', ['period'], unique=False)
    op.create_index(op.f('ix_fct_budgets_category'), 'fct_budgets', ['category'], unique=False)

    op.add_column('fct_tax_invoices', sa.Column('verify_status', sa.String(20), nullable=True, server_default='pending'))
    op.add_column('fct_tax_invoices', sa.Column('verified_at', sa.String(32), nullable=True))

    op.create_table(
        'fct_approval_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', sa.String(64), nullable=False),
        sa.Column('ref_type', sa.String(32), nullable=False),
        sa.Column('ref_id', sa.String(64), nullable=False),
        sa.Column('step', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('approved_at', sa.String(32), nullable=True),
        sa.Column('approved_by', sa.String(64), nullable=True),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('extra', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_fct_approval_records_tenant_id'), 'fct_approval_records', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_fct_approval_records_ref_type'), 'fct_approval_records', ['ref_type'], unique=False)
    op.create_index(op.f('ix_fct_approval_records_ref_id'), 'fct_approval_records', ['ref_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_fct_approval_records_ref_id'), table_name='fct_approval_records')
    op.drop_index(op.f('ix_fct_approval_records_ref_type'), table_name='fct_approval_records')
    op.drop_index(op.f('ix_fct_approval_records_tenant_id'), table_name='fct_approval_records')
    op.drop_table('fct_approval_records')

    op.drop_column('fct_tax_invoices', 'verified_at')
    op.drop_column('fct_tax_invoices', 'verify_status')

    op.drop_index(op.f('ix_fct_budgets_category'), table_name='fct_budgets')
    op.drop_index(op.f('ix_fct_budgets_period'), table_name='fct_budgets')
    op.drop_index(op.f('ix_fct_budgets_budget_type'), table_name='fct_budgets')
    op.drop_index(op.f('ix_fct_budgets_entity_id'), table_name='fct_budgets')
    op.drop_index(op.f('ix_fct_budgets_tenant_id'), table_name='fct_budgets')
    op.drop_table('fct_budgets')

    op.drop_index(op.f('ix_fct_petty_cash_records_biz_date'), table_name='fct_petty_cash_records')
    op.drop_index(op.f('ix_fct_petty_cash_records_record_type'), table_name='fct_petty_cash_records')
    op.drop_index(op.f('ix_fct_petty_cash_records_petty_cash_id'), table_name='fct_petty_cash_records')
    op.drop_table('fct_petty_cash_records')

    op.drop_index(op.f('ix_fct_petty_cash_cash_type'), table_name='fct_petty_cash')
    op.drop_index(op.f('ix_fct_petty_cash_entity_id'), table_name='fct_petty_cash')
    op.drop_index(op.f('ix_fct_petty_cash_tenant_id'), table_name='fct_petty_cash')
    op.drop_table('fct_petty_cash')
