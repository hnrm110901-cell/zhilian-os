"""hr18 — 工资单增加规则快照字段

为 payroll_records 表增加 rule_snapshot JSON 列，
记录算薪时使用的业务规则（HRRuleEngine三级级联结果），用于审计溯源。

Revision ID: hr18
Revises: hr17
Create Date: 2026-03-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

revision = 'hr18'
down_revision = 'hr17'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'payroll_records',
        sa.Column('rule_snapshot', JSON, nullable=True),
    )


def downgrade() -> None:
    op.drop_column('payroll_records', 'rule_snapshot')
