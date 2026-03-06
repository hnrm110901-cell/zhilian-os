"""Onboarding Engine: onboarding_tasks / onboarding_imports / onboarding_raw_data

Revision ID: g01_onboarding_engine
Revises: f01_merge_bb01_e01
Create Date: 2026-03-06
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = 'g01_onboarding_engine'
down_revision: Union[str, Sequence[str], None] = 'f01_merge_bb01_e01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── onboarding_tasks: tracks per-step progress ───────────────────────────
    op.create_table(
        'onboarding_tasks',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('store_id', sa.String(50), nullable=False),
        sa.Column('step', sa.String(30), nullable=False),   # connect/import/build/diagnose/complete
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('total_records', sa.Integer, nullable=False, server_default='0'),
        sa.Column('imported_records', sa.Integer, nullable=False, server_default='0'),
        sa.Column('failed_records', sa.Integer, nullable=False, server_default='0'),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('extra', JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_onboarding_tasks_store_id', 'onboarding_tasks', ['store_id'])
    op.create_index('ix_onboarding_tasks_store_step', 'onboarding_tasks', ['store_id', 'step'])

    # ── onboarding_imports: one row per data-type per store ───────────────────
    op.create_table(
        'onboarding_imports',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('store_id', sa.String(50), nullable=False),
        sa.Column('data_type', sa.String(10), nullable=False),  # D01-D10
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('row_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('error_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('column_mapping', JSONB, nullable=True),
        sa.Column('imported_at', sa.DateTime, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_onboarding_imports_store_id', 'onboarding_imports', ['store_id'])
    op.create_unique_constraint(
        'uq_onboarding_imports_store_dtype',
        'onboarding_imports',
        ['store_id', 'data_type'],
    )

    # ── onboarding_raw_data: raw imported rows (processed by pipeline) ────────
    op.create_table(
        'onboarding_raw_data',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('store_id', sa.String(50), nullable=False),
        sa.Column('data_type', sa.String(10), nullable=False),  # D01-D10
        sa.Column('row_index', sa.Integer, nullable=False),
        sa.Column('row_data', JSONB, nullable=False),
        sa.Column('is_valid', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('error_msg', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_onboarding_raw_store_dtype', 'onboarding_raw_data', ['store_id', 'data_type'])


def downgrade() -> None:
    op.drop_table('onboarding_raw_data')
    op.drop_index('uq_onboarding_imports_store_dtype', table_name='onboarding_imports')
    op.drop_table('onboarding_imports')
    op.drop_table('onboarding_tasks')
