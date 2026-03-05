"""
c01: 会员生命周期状态机表 + private_domain_members 新增 lifecycle_state 列

- 新建 member_lifecycle_histories 表（状态变更审计追踪）
- private_domain_members 新增 lifecycle_state / lifecycle_state_updated_at 列

Revision ID: c01_member_lifecycle
Revises: b03_employee_metric_record
Create Date: 2026-03-05
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'c01_member_lifecycle'
down_revision = 'b03_employee_metric_record'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. 新建 member_lifecycle_histories 表
    op.create_table(
        'member_lifecycle_histories',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('store_id',    sa.String(50),  nullable=False),
        sa.Column('customer_id', sa.String(100), nullable=False),
        sa.Column('from_state',  sa.String(30),  nullable=True),
        sa.Column('to_state',    sa.String(30),  nullable=False),
        sa.Column('trigger',     sa.String(50),  nullable=True),
        sa.Column('changed_by',  sa.String(100), nullable=True),
        sa.Column('changed_at',  sa.DateTime,    nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('reason',      sa.String(500), nullable=True),
    )
    op.create_index('ix_mlh_store_customer',   'member_lifecycle_histories',
                    ['store_id', 'customer_id'])
    op.create_index('ix_mlh_store_changed_at', 'member_lifecycle_histories',
                    ['store_id', 'changed_at'])

    # 2. private_domain_members 新增 lifecycle_state 列
    op.add_column(
        'private_domain_members',
        sa.Column('lifecycle_state', sa.String(30), nullable=True),
    )
    op.add_column(
        'private_domain_members',
        sa.Column('lifecycle_state_updated_at', sa.DateTime, nullable=True),
    )
    op.create_index('ix_pdm_lifecycle_state', 'private_domain_members',
                    ['store_id', 'lifecycle_state'])


def downgrade() -> None:
    op.drop_index('ix_pdm_lifecycle_state', table_name='private_domain_members')
    op.drop_column('private_domain_members', 'lifecycle_state_updated_at')
    op.drop_column('private_domain_members', 'lifecycle_state')

    op.drop_index('ix_mlh_store_changed_at', table_name='member_lifecycle_histories')
    op.drop_index('ix_mlh_store_customer',   table_name='member_lifecycle_histories')
    op.drop_table('member_lifecycle_histories')
