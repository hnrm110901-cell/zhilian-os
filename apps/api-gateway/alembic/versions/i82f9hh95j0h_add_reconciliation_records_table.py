"""add_reconciliation_records_table

Revision ID: i82f9hh95j0h
Revises: h71e8gg84i9g
Create Date: 2026-02-21 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'i82f9hh95j0h'
down_revision: Union[str, None] = 'h71e8gg84i9g'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create reconciliation_records table
    op.create_table(
        'reconciliation_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('store_id', sa.String(length=50), nullable=False),
        sa.Column('reconciliation_date', sa.Date(), nullable=False),
        sa.Column('pos_total_amount', sa.Integer(), nullable=True),
        sa.Column('pos_order_count', sa.Integer(), nullable=True),
        sa.Column('pos_transaction_count', sa.Integer(), nullable=True),
        sa.Column('actual_total_amount', sa.Integer(), nullable=True),
        sa.Column('actual_order_count', sa.Integer(), nullable=True),
        sa.Column('actual_transaction_count', sa.Integer(), nullable=True),
        sa.Column('diff_amount', sa.Integer(), nullable=True),
        sa.Column('diff_ratio', sa.Float(), nullable=True),
        sa.Column('diff_order_count', sa.Integer(), nullable=True),
        sa.Column('diff_transaction_count', sa.Integer(), nullable=True),
        sa.Column('status', sa.Enum('pending', 'matched', 'mismatched', 'confirmed', 'investigating', name='reconciliationstatus'), nullable=False),
        sa.Column('discrepancies', sa.JSON(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('confirmed_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('confirmed_at', sa.String(length=50), nullable=True),
        sa.Column('resolution', sa.Text(), nullable=True),
        sa.Column('alert_sent', sa.String(length=10), nullable=True),
        sa.Column('alert_sent_at', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes
    op.create_index(op.f('ix_reconciliation_records_store_id'), 'reconciliation_records', ['store_id'], unique=False)
    op.create_index(op.f('ix_reconciliation_records_reconciliation_date'), 'reconciliation_records', ['reconciliation_date'], unique=False)
    op.create_index(op.f('ix_reconciliation_records_status'), 'reconciliation_records', ['status'], unique=False)

    # Create unique constraint on store_id + reconciliation_date
    op.create_index('ix_reconciliation_records_store_date', 'reconciliation_records', ['store_id', 'reconciliation_date'], unique=True)


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_reconciliation_records_store_date', table_name='reconciliation_records')
    op.drop_index(op.f('ix_reconciliation_records_status'), table_name='reconciliation_records')
    op.drop_index(op.f('ix_reconciliation_records_reconciliation_date'), table_name='reconciliation_records')
    op.drop_index(op.f('ix_reconciliation_records_store_id'), table_name='reconciliation_records')

    # Drop table
    op.drop_table('reconciliation_records')

    # Drop enum
    op.execute('DROP TYPE reconciliationstatus')
