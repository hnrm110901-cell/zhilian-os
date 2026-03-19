"""hr09 — 离职回访表

Revision ID: hr09
Revises: hr08
Create Date: 2026-03-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 'hr09'
down_revision = 'hr08'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'exit_interviews',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('store_id', sa.String(50), nullable=False, index=True),
        sa.Column('brand_id', sa.String(50), nullable=False, index=True),
        sa.Column('employee_id', sa.String(50), nullable=False, index=True),
        sa.Column('employee_name', sa.String(100), nullable=True),
        sa.Column('resign_date', sa.Date, nullable=False),
        sa.Column('resign_reason', sa.String(50), nullable=False),
        sa.Column('resign_detail', sa.Text, nullable=True),
        sa.Column('interview_date', sa.Date, nullable=True),
        sa.Column('current_status', sa.Text, nullable=True),
        sa.Column('willing_to_return', sa.String(20), nullable=True),
        sa.Column('return_conditions', sa.Text, nullable=True),
        sa.Column('interviewer', sa.String(50), nullable=True),
        sa.Column('remark', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('exit_interviews')
