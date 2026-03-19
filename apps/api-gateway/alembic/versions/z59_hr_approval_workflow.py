"""z59: HR approval workflow tables

Revision ID: z59_hr_approval_workflow
Revises: z58_hr_lifecycle_tables
Create Date: 2026-03-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "z59_hr_approval_workflow"
down_revision = "z58_hr_lifecycle_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. approval_templates
    op.create_table(
        "approval_templates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(30), nullable=False),
        sa.Column("org_node_id", sa.String(64), nullable=True),
        sa.Column("steps", JSONB, nullable=False, server_default="'[]'::jsonb"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("ix_approval_templates_resource_type", "approval_templates", ["resource_type"])
    op.create_index("ix_approval_templates_org_node_id", "approval_templates", ["org_node_id"])

    # 2. approval_instances
    op.create_table(
        "approval_instances",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("template_id", UUID(as_uuid=True), sa.ForeignKey("approval_templates.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("resource_type", sa.String(30), nullable=False),
        sa.Column("resource_id", UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="'pending'"),
        sa.Column("current_step", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(100), nullable=False),
        sa.Column("extra_data", JSONB, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("ix_approval_instances_template_id", "approval_instances", ["template_id"])
    op.create_index("ix_approval_instances_resource_type", "approval_instances", ["resource_type"])
    op.create_index("ix_approval_instances_resource_id", "approval_instances", ["resource_id"])

    # 3. approval_step_records
    op.create_table(
        "approval_step_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("instance_id", UUID(as_uuid=True), sa.ForeignKey("approval_instances.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step", sa.Integer(), nullable=False),
        sa.Column("approver_id", sa.String(100), nullable=False),
        sa.Column("approver_name", sa.String(100), nullable=False),
        sa.Column("action", sa.String(20), nullable=False, server_default="'pending'"),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("acted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("notified_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("ix_approval_step_records_instance_id", "approval_step_records", ["instance_id"])


def downgrade() -> None:
    op.drop_index("ix_approval_step_records_instance_id", table_name="approval_step_records")
    op.drop_table("approval_step_records")

    op.drop_index("ix_approval_instances_resource_id", table_name="approval_instances")
    op.drop_index("ix_approval_instances_resource_type", table_name="approval_instances")
    op.drop_index("ix_approval_instances_template_id", table_name="approval_instances")
    op.drop_table("approval_instances")

    op.drop_index("ix_approval_templates_org_node_id", table_name="approval_templates")
    op.drop_index("ix_approval_templates_resource_type", table_name="approval_templates")
    op.drop_table("approval_templates")
