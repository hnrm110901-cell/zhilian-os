"""W2-1: 通用审批流引擎 — approval_templates / hr_approval_instances / hr_approval_records / hr_approval_delegations

Revision ID: hr15_approval
Revises: hr14
Create Date: 2026-03-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

revision: str = 'hr15_approval'
down_revision: Union[str, Sequence[str], None] = 'hr14'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. approval_templates: 审批模板 ──────────────────────────
    op.create_table(
        'approval_templates',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('brand_id', sa.String(50), nullable=False),
        sa.Column('template_code', sa.String(50), nullable=False),
        sa.Column('template_name', sa.String(100), nullable=False),
        sa.Column('approval_chain', JSON, nullable=False),
        sa.Column('amount_thresholds', JSON, nullable=True),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default=sa.text('true')),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_approval_templates_brand_id', 'approval_templates', ['brand_id'])
    op.create_unique_constraint('uq_approval_templates_code', 'approval_templates', ['template_code'])

    # ── 2. hr_approval_instances: 审批实例 ───────────────────────
    op.create_table(
        'hr_approval_instances',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('brand_id', sa.String(50), nullable=False),
        sa.Column('store_id', sa.String(50), nullable=False),
        sa.Column('template_code', sa.String(50), nullable=False),
        sa.Column('business_type', sa.String(50), nullable=False),
        sa.Column('business_id', sa.String(100), nullable=False),
        sa.Column('applicant_id', sa.String(50), nullable=False),
        sa.Column('applicant_name', sa.String(100), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('current_level', sa.Integer, nullable=False, server_default='1'),
        sa.Column('amount_fen', sa.Integer, nullable=True),
        sa.Column('summary', sa.Text, nullable=True),
        sa.Column('final_result', sa.String(20), nullable=True),
        sa.Column('completed_at', sa.DateTime, nullable=True),
        sa.Column('deadline', sa.DateTime, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_hr_approval_instances_brand_id', 'hr_approval_instances', ['brand_id'])
    op.create_index('ix_hr_approval_instances_store_id', 'hr_approval_instances', ['store_id'])
    op.create_index('ix_hr_approval_instances_template_code', 'hr_approval_instances', ['template_code'])
    op.create_index('ix_hr_approval_instances_business_id', 'hr_approval_instances', ['business_id'])
    op.create_index('ix_hr_approval_instances_applicant_id', 'hr_approval_instances', ['applicant_id'])
    op.create_index('ix_hr_approval_instances_status', 'hr_approval_instances', ['status'])

    # ── 3. hr_approval_records: 审批记录 ─────────────────────────
    op.create_table(
        'hr_approval_records',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('instance_id', UUID(as_uuid=True),
                  sa.ForeignKey('hr_approval_instances.id'), nullable=False),
        sa.Column('level', sa.Integer, nullable=False),
        sa.Column('approver_id', sa.String(50), nullable=False),
        sa.Column('approver_name', sa.String(100), nullable=True),
        sa.Column('approver_role', sa.String(50), nullable=True),
        sa.Column('action', sa.String(20), nullable=False),
        sa.Column('comment', sa.Text, nullable=True),
        sa.Column('acted_at', sa.DateTime, nullable=True),
        sa.Column('delegated_to_id', sa.String(50), nullable=True),
        sa.Column('delegated_to_name', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_hr_approval_records_instance_id', 'hr_approval_records', ['instance_id'])

    # ── 4. hr_approval_delegations: 审批委托 ─────────────────────
    op.create_table(
        'hr_approval_delegations',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('brand_id', sa.String(50), nullable=False),
        sa.Column('delegator_id', sa.String(50), nullable=False),
        sa.Column('delegator_name', sa.String(100), nullable=True),
        sa.Column('delegate_id', sa.String(50), nullable=False),
        sa.Column('delegate_name', sa.String(100), nullable=True),
        sa.Column('start_date', sa.Date, nullable=False),
        sa.Column('end_date', sa.Date, nullable=False),
        sa.Column('template_codes', JSON, nullable=True),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_hr_approval_delegations_delegator_id', 'hr_approval_delegations', ['delegator_id'])


def downgrade() -> None:
    op.drop_table('hr_approval_delegations')
    op.drop_table('hr_approval_records')
    op.drop_table('hr_approval_instances')
    op.drop_table('approval_templates')
