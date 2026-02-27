"""FCT 预算控制配置表 fct_budget_control

Revision ID: y01_fct_budget_control
Revises: x01_fct_periods
Create Date: 2026-02-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'y01_fct_budget_control'
down_revision = 'x01_fct_periods'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'fct_budget_control',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', sa.String(64), nullable=False),
        sa.Column('entity_id', sa.String(64), nullable=False, server_default=''),
        sa.Column('budget_type', sa.String(16), nullable=False),
        sa.Column('category', sa.String(64), nullable=False, server_default=''),
        sa.Column('enforce_check', sa.String(8), nullable=False, server_default='false'),
        sa.Column('auto_occupy', sa.String(8), nullable=False, server_default='false'),
        sa.Column('extra', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_fct_budget_control_tenant_id'), 'fct_budget_control', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_fct_budget_control_entity_id'), 'fct_budget_control', ['entity_id'], unique=False)
    op.create_index(op.f('ix_fct_budget_control_budget_type'), 'fct_budget_control', ['budget_type'], unique=False)
    op.create_index(op.f('ix_fct_budget_control_category'), 'fct_budget_control', ['category'], unique=False)
    op.create_index('ix_fct_budget_control_tenant_entity_type_cat', 'fct_budget_control', ['tenant_id', 'entity_id', 'budget_type', 'category'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_fct_budget_control_tenant_entity_type_cat', table_name='fct_budget_control')
    op.drop_index(op.f('ix_fct_budget_control_category'), table_name='fct_budget_control')
    op.drop_index(op.f('ix_fct_budget_control_budget_type'), table_name='fct_budget_control')
    op.drop_index(op.f('ix_fct_budget_control_entity_id'), table_name='fct_budget_control')
    op.drop_index(op.f('ix_fct_budget_control_tenant_id'), table_name='fct_budget_control')
    op.drop_table('fct_budget_control')
