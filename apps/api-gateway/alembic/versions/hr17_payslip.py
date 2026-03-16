"""hr17 — 工资条推送记录表

新建 payslip_records 表，记录工资条推送状态、员工确认情况、PDF存储路径。

Revision ID: hr17
Revises: hr14
Create Date: 2026-03-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 'hr17'
down_revision = 'hr16'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'payslip_records',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('store_id', sa.String(50), nullable=False, index=True),
        sa.Column('employee_id', sa.String(50), nullable=False, index=True),
        sa.Column('pay_month', sa.String(7), nullable=False, index=True),
        sa.Column('pushed_at', sa.DateTime, nullable=True),
        sa.Column('push_channel', sa.String(20), nullable=True),
        sa.Column('push_status', sa.String(20), server_default='pending'),
        sa.Column('push_error', sa.String(500), nullable=True),
        sa.Column('confirmed_at', sa.DateTime, nullable=True),
        sa.Column('confirmed', sa.Boolean, server_default='false'),
        sa.Column('pdf_path', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('store_id', 'employee_id', 'pay_month', name='uq_payslip_month'),
    )


def downgrade() -> None:
    op.drop_table('payslip_records')
