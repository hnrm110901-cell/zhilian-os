"""z58 — HR lifecycle tables: onboarding, offboarding, transfer + patches to
persons and employment_assignments.

Creates:
  1. onboarding_processes
  2. onboarding_checklist_items
  3. offboarding_processes
  4. transfer_processes

Adds columns:
  persons.career_stage (VARCHAR 20, nullable)
  employment_assignments.onboarding_process_id (UUID, nullable, no FK)
  employment_assignments.offboarding_process_id (UUID, nullable, no FK)
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "z58_hr_lifecycle_tables"
down_revision = "z57_contract_drop_old_fk_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. onboarding_processes
    op.create_table(
        "onboarding_processes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("person_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("persons.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("org_node_id", sa.String(64),
                  sa.ForeignKey("org_nodes.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="'draft'"),
        sa.Column("offer_date", sa.Date, nullable=True),
        sa.Column("planned_start_date", sa.Date, nullable=False),
        sa.Column("actual_start_date", sa.Date, nullable=True),
        sa.Column("created_by", sa.String(100), nullable=False),
        sa.Column("extra_data", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("ix_onboarding_processes_person_id",
                    "onboarding_processes", ["person_id"])
    op.create_index("ix_onboarding_processes_org_node_id",
                    "onboarding_processes", ["org_node_id"])

    # 2. onboarding_checklist_items
    op.create_table(
        "onboarding_checklist_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("process_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("onboarding_processes.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("item_type", sa.String(30), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("required", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_by", sa.String(100), nullable=True),
        sa.Column("file_url", sa.String(500), nullable=True),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("ix_onboarding_checklist_items_process_id",
                    "onboarding_checklist_items", ["process_id"])

    # 3. offboarding_processes
    op.create_table(
        "offboarding_processes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("employment_assignments.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("reason", sa.String(30), nullable=False),
        sa.Column("apply_date", sa.Date, nullable=False),
        sa.Column("planned_last_day", sa.Date, nullable=False),
        sa.Column("actual_last_day", sa.Date, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="'pending'"),
        sa.Column("knowledge_capture_triggered", sa.Boolean, nullable=False,
                  server_default="false"),
        sa.Column("settlement_amount_fen", sa.Integer, nullable=False,
                  server_default="0"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_by", sa.String(100), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("ix_offboarding_processes_assignment_id",
                    "offboarding_processes", ["assignment_id"])

    # 4. transfer_processes
    op.create_table(
        "transfer_processes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("person_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("persons.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("from_assignment_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("employment_assignments.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("to_org_node_id", sa.String(64),
                  sa.ForeignKey("org_nodes.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("to_employment_type", sa.String(30), nullable=False),
        sa.Column("new_pay_scheme", postgresql.JSONB, nullable=True),
        sa.Column("transfer_type", sa.String(30), nullable=False),
        sa.Column("effective_date", sa.Date, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="'pending'"),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("revenue_impact_yuan", sa.Numeric(12, 2), nullable=True),
        sa.Column("created_by", sa.String(100), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("ix_transfer_processes_person_id",
                    "transfer_processes", ["person_id"])
    op.create_index("ix_transfer_processes_from_assignment_id",
                    "transfer_processes", ["from_assignment_id"])
    op.create_index("ix_transfer_processes_to_org_node_id",
                    "transfer_processes", ["to_org_node_id"])

    # 5. Patch persons: add career_stage
    op.add_column(
        "persons",
        sa.Column("career_stage", sa.String(20), nullable=True,
                  comment="probation/regular/senior/lead/manager"),
    )

    # 6. Patch employment_assignments: soft refs (no FK — lifecycle process creates
    #    the assignment, not the reverse; avoids circular FK dependency)
    op.add_column(
        "employment_assignments",
        sa.Column("onboarding_process_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "employment_assignments",
        sa.Column("offboarding_process_id", postgresql.UUID(as_uuid=True), nullable=True),
    )


def downgrade() -> None:
    # Remove columns from employment_assignments
    op.drop_column("employment_assignments", "offboarding_process_id")
    op.drop_column("employment_assignments", "onboarding_process_id")

    # Remove column from persons
    op.drop_column("persons", "career_stage")

    # Drop tables in reverse dependency order
    op.drop_index("ix_transfer_processes_to_org_node_id", table_name="transfer_processes")
    op.drop_index("ix_transfer_processes_from_assignment_id", table_name="transfer_processes")
    op.drop_index("ix_transfer_processes_person_id", table_name="transfer_processes")
    op.drop_table("transfer_processes")

    op.drop_index("ix_offboarding_processes_assignment_id", table_name="offboarding_processes")
    op.drop_table("offboarding_processes")

    op.drop_index("ix_onboarding_checklist_items_process_id",
                  table_name="onboarding_checklist_items")
    op.drop_table("onboarding_checklist_items")

    op.drop_index("ix_onboarding_processes_org_node_id", table_name="onboarding_processes")
    op.drop_index("ix_onboarding_processes_person_id", table_name="onboarding_processes")
    op.drop_table("onboarding_processes")
