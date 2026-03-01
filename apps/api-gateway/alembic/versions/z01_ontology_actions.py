"""L4 行动层 ontology_actions 表

Revision ID: z01_ontology_actions
Revises: y01_fct_budget_control
Create Date: 2026-02-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'z01_ontology_actions'
down_revision = 'y01_fct_budget_control'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'ontology_actions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', sa.String(50), nullable=False),
        sa.Column('store_id', sa.String(50), nullable=False),
        sa.Column('action_type', sa.String(80), nullable=False),
        sa.Column('assignee_staff_id', sa.String(50), nullable=False),
        sa.Column('assignee_wechat_id', sa.String(100), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='created'),
        sa.Column('priority', sa.String(10), nullable=False, server_default='P1'),
        sa.Column('deadline_at', sa.DateTime(), nullable=True),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.Column('acked_at', sa.DateTime(), nullable=True),
        sa.Column('done_at', sa.DateTime(), nullable=True),
        sa.Column('traced_reasoning_id', sa.String(100), nullable=True),
        sa.Column('traced_report', postgresql.JSON(), nullable=True),
        sa.Column('escalation_at', sa.DateTime(), nullable=True),
        sa.Column('escalated_to', sa.String(200), nullable=True),
        sa.Column('title', sa.String(200), nullable=True),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('extra', postgresql.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_ontology_actions_tenant_id', 'ontology_actions', ['tenant_id'], unique=False)
    op.create_index('ix_ontology_actions_store_id', 'ontology_actions', ['store_id'], unique=False)
    op.create_index('ix_ontology_actions_assignee_staff_id', 'ontology_actions', ['assignee_staff_id'], unique=False)
    op.create_index('ix_ontology_actions_status', 'ontology_actions', ['status'], unique=False)
    op.create_index('idx_ontology_action_tenant_status', 'ontology_actions', ['tenant_id', 'status'], unique=False)
    op.create_index('idx_ontology_action_deadline', 'ontology_actions', ['deadline_at'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_ontology_action_deadline', table_name='ontology_actions')
    op.drop_index('idx_ontology_action_tenant_status', table_name='ontology_actions')
    op.drop_index('ix_ontology_actions_status', table_name='ontology_actions')
    op.drop_index('ix_ontology_actions_assignee_staff_id', table_name='ontology_actions')
    op.drop_index('ix_ontology_actions_store_id', table_name='ontology_actions')
    op.drop_index('ix_ontology_actions_tenant_id', table_name='ontology_actions')
    op.drop_table('ontology_actions')
