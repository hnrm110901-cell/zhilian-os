"""hr11 — 报表视图（预留索引优化）

Revision ID: hr11
Revises: hr10
Create Date: 2026-03-15

Adds indexes for report queries.
"""
from alembic import op
import sqlalchemy as sa

revision = 'hr11'
down_revision = 'hr10'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 报表查询常用索引
    op.create_index('ix_payroll_records_store_month', 'payroll_records', ['store_id', 'pay_month'])
    op.create_index('ix_exit_interviews_resign_date', 'exit_interviews', ['store_id', 'resign_date'])
    op.create_index('ix_training_enrollments_status', 'training_enrollments', ['store_id', 'status'])
    op.create_index('ix_mentorships_status', 'mentorships', ['store_id', 'status'])


def downgrade() -> None:
    op.drop_index('ix_mentorships_status')
    op.drop_index('ix_training_enrollments_status')
    op.drop_index('ix_exit_interviews_resign_date')
    op.drop_index('ix_payroll_records_store_month')
