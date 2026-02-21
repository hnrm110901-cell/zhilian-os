"""add_daily_reports_table

Revision ID: h71e8gg84i9g
Revises: g60d7ff73h8f
Create Date: 2026-02-21 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'h71e8gg84i9g'
down_revision: Union[str, None] = 'g60d7ff73h8f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create daily_reports table
    op.create_table(
        'daily_reports',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('store_id', sa.String(length=50), nullable=False),
        sa.Column('report_date', sa.Date(), nullable=False),
        sa.Column('total_revenue', sa.Integer(), nullable=True),
        sa.Column('order_count', sa.Integer(), nullable=True),
        sa.Column('customer_count', sa.Integer(), nullable=True),
        sa.Column('avg_order_value', sa.Integer(), nullable=True),
        sa.Column('revenue_change_rate', sa.Float(), nullable=True),
        sa.Column('order_change_rate', sa.Float(), nullable=True),
        sa.Column('customer_change_rate', sa.Float(), nullable=True),
        sa.Column('inventory_alert_count', sa.Integer(), nullable=True),
        sa.Column('task_completion_rate', sa.Float(), nullable=True),
        sa.Column('service_issue_count', sa.Integer(), nullable=True),
        sa.Column('top_dishes', sa.JSON(), nullable=True),
        sa.Column('peak_hours', sa.JSON(), nullable=True),
        sa.Column('payment_methods', sa.JSON(), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('highlights', sa.JSON(), nullable=True),
        sa.Column('alerts', sa.JSON(), nullable=True),
        sa.Column('is_sent', sa.String(length=10), nullable=True),
        sa.Column('sent_at', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes
    op.create_index(op.f('ix_daily_reports_store_id'), 'daily_reports', ['store_id'], unique=False)
    op.create_index(op.f('ix_daily_reports_report_date'), 'daily_reports', ['report_date'], unique=False)

    # Create unique constraint on store_id + report_date
    op.create_index('ix_daily_reports_store_date', 'daily_reports', ['store_id', 'report_date'], unique=True)


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_daily_reports_store_date', table_name='daily_reports')
    op.drop_index(op.f('ix_daily_reports_report_date'), table_name='daily_reports')
    op.drop_index(op.f('ix_daily_reports_store_id'), table_name='daily_reports')

    # Drop table
    op.drop_table('daily_reports')
