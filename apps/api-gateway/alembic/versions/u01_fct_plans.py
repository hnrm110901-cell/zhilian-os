"""FCT 年度计划表

Revision ID: u01_fct_plans
Revises: t01_fct_phase3
Create Date: 2026-02-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'u01_fct_plans'
down_revision = 't01_fct_phase3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'fct_plans',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', sa.String(64), nullable=False),
        sa.Column('entity_id', sa.String(64), nullable=False, server_default=''),
        sa.Column('plan_year', sa.Integer(), nullable=False),
        sa.Column('targets', sa.JSON(), nullable=False),
        sa.Column('extra', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_fct_plans_tenant_id'), 'fct_plans', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_fct_plans_entity_id'), 'fct_plans', ['entity_id'], unique=False)
    op.create_index(op.f('ix_fct_plans_plan_year'), 'fct_plans', ['plan_year'], unique=False)
    op.create_index('ix_fct_plans_tenant_entity_year', 'fct_plans', ['tenant_id', 'entity_id', 'plan_year'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_fct_plans_tenant_entity_year', table_name='fct_plans')
    op.drop_index(op.f('ix_fct_plans_plan_year'), table_name='fct_plans')
    op.drop_index(op.f('ix_fct_plans_entity_id'), table_name='fct_plans')
    op.drop_index(op.f('ix_fct_plans_tenant_id'), table_name='fct_plans')
    op.drop_table('fct_plans')
