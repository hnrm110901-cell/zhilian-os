"""业财税资金一体化（FCT）表

Revision ID: s01_fct_tables
Revises: q01_ops_tables
Create Date: 2026-02-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 's01_fct_tables'
down_revision = 'q01_ops_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE fctvoucherstatus AS ENUM ('draft', 'pending', 'approved', 'posted', 'rejected');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    op.create_table(
        'fct_vouchers',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('voucher_no', sa.String(32), nullable=False),
        sa.Column('tenant_id', sa.String(64), nullable=False),
        sa.Column('entity_id', sa.String(64), nullable=False),
        sa.Column('biz_date', sa.Date(), nullable=False),
        sa.Column('event_type', sa.String(64), nullable=True),
        sa.Column('event_id', sa.String(64), nullable=True),
        sa.Column('status', postgresql.ENUM('draft', 'pending', 'approved', 'posted', 'rejected', name='fctvoucherstatus', create_type=False), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('attachments', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_fct_vouchers_entity_id'), 'fct_vouchers', ['entity_id'], unique=False)
    op.create_index(op.f('ix_fct_vouchers_tenant_id'), 'fct_vouchers', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_fct_vouchers_biz_date'), 'fct_vouchers', ['biz_date'], unique=False)
    op.create_index(op.f('ix_fct_vouchers_status'), 'fct_vouchers', ['status'], unique=False)
    op.create_index(op.f('ix_fct_vouchers_voucher_no'), 'fct_vouchers', ['voucher_no'], unique=False)

    op.create_table(
        'fct_voucher_lines',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('voucher_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('line_no', sa.Integer(), nullable=False),
        sa.Column('account_code', sa.String(32), nullable=False),
        sa.Column('account_name', sa.String(128), nullable=True),
        sa.Column('debit', sa.Numeric(18, 2), nullable=True),
        sa.Column('credit', sa.Numeric(18, 2), nullable=True),
        sa.Column('auxiliary', sa.JSON(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['voucher_id'], ['fct_vouchers.id'], ondelete='CASCADE'),
    )
    op.create_index(op.f('ix_fct_voucher_lines_voucher_id'), 'fct_voucher_lines', ['voucher_id'], unique=False)

    op.create_table(
        'fct_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('event_id', sa.String(64), nullable=False),
        sa.Column('event_type', sa.String(64), nullable=False),
        sa.Column('occurred_at', sa.String(32), nullable=False),
        sa.Column('source_system', sa.String(64), nullable=False),
        sa.Column('source_id', sa.String(128), nullable=True),
        sa.Column('tenant_id', sa.String(64), nullable=False),
        sa.Column('entity_id', sa.String(64), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('processed_at', sa.String(32), nullable=True),
        sa.Column('voucher_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['voucher_id'], ['fct_vouchers.id'], ondelete='SET NULL'),
    )
    op.create_index(op.f('ix_fct_events_entity_id'), 'fct_events', ['entity_id'], unique=False)
    op.create_index(op.f('ix_fct_events_event_type'), 'fct_events', ['event_type'], unique=False)
    op.create_index(op.f('ix_fct_events_tenant_id'), 'fct_events', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_fct_events_event_id'), 'fct_events', ['event_id'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_fct_events_event_id'), table_name='fct_events')
    op.drop_index(op.f('ix_fct_events_tenant_id'), table_name='fct_events')
    op.drop_index(op.f('ix_fct_events_event_type'), table_name='fct_events')
    op.drop_index(op.f('ix_fct_events_entity_id'), table_name='fct_events')
    op.drop_table('fct_events')

    op.drop_index(op.f('ix_fct_voucher_lines_voucher_id'), table_name='fct_voucher_lines')
    op.drop_table('fct_voucher_lines')

    op.drop_index(op.f('ix_fct_vouchers_voucher_no'), table_name='fct_vouchers')
    op.drop_index(op.f('ix_fct_vouchers_status'), table_name='fct_vouchers')
    op.drop_index(op.f('ix_fct_vouchers_biz_date'), table_name='fct_vouchers')
    op.drop_index(op.f('ix_fct_vouchers_tenant_id'), table_name='fct_vouchers')
    op.drop_index(op.f('ix_fct_vouchers_entity_id'), table_name='fct_vouchers')
    op.drop_table('fct_vouchers')

    op.execute('DROP TYPE IF EXISTS fctvoucherstatus')
