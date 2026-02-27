"""FCT 会计期间表 fct_periods

Revision ID: x01_fct_periods
Revises: w01_fct_voucher_voided
Create Date: 2026-02-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'x01_fct_periods'
down_revision = 'w01_fct_voucher_voided'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'fct_periods',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', sa.String(64), nullable=False),
        sa.Column('period_key', sa.String(16), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='open'),
        sa.Column('closed_at', sa.String(32), nullable=True),
        sa.Column('extra', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_fct_periods_tenant_id'), 'fct_periods', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_fct_periods_period_key'), 'fct_periods', ['period_key'], unique=False)
    op.create_index('ix_fct_periods_tenant_period', 'fct_periods', ['tenant_id', 'period_key'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_fct_periods_tenant_period', table_name='fct_periods')
    op.drop_index(op.f('ix_fct_periods_period_key'), table_name='fct_periods')
    op.drop_index(op.f('ix_fct_periods_tenant_id'), table_name='fct_periods')
    op.drop_table('fct_periods')
