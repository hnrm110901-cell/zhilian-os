"""z60: HR attendance and leave tables

Revision ID: z60_hr_attendance_leave
Revises: z59_hr_approval_workflow
Create Date: 2026-03-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "z60_hr_attendance_leave"
down_revision = "z59_hr_approval_workflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. clock_records
    op.create_table(
        "clock_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("assignment_id", UUID(as_uuid=True),
                  sa.ForeignKey("employment_assignments.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("clock_type", sa.String(20), nullable=False),
        sa.Column("clock_time", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("location", JSONB, nullable=True),
        sa.Column("is_anomaly", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("ix_clock_records_assignment_id", "clock_records", ["assignment_id"])

    # 2. daily_attendances
    op.create_table(
        "daily_attendances",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("assignment_id", UUID(as_uuid=True),
                  sa.ForeignKey("employment_assignments.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="'normal'"),
        sa.Column("work_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("overtime_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("late_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("early_leave_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("calculated_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.Column("locked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("ix_daily_attendances_assignment_id", "daily_attendances",
                    ["assignment_id"])
    op.create_index("ix_daily_attendances_date", "daily_attendances", ["date"])
    op.create_unique_constraint("uq_daily_attendance_assignment_date",
                                "daily_attendances", ["assignment_id", "date"])

    # 3. leave_requests
    op.create_table(
        "leave_requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("assignment_id", UUID(as_uuid=True),
                  sa.ForeignKey("employment_assignments.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("leave_type", sa.String(30), nullable=False),
        sa.Column("start_datetime", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("end_datetime", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("days", sa.Numeric(4, 1), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="'pending'"),
        sa.Column("approved_by", sa.String(100), nullable=True),
        sa.Column("created_by", sa.String(100), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("ix_leave_requests_assignment_id", "leave_requests",
                    ["assignment_id"])

    # 4. leave_balances
    op.create_table(
        "leave_balances",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("assignment_id", UUID(as_uuid=True),
                  sa.ForeignKey("employment_assignments.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("leave_type", sa.String(30), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("total_days", sa.Numeric(5, 1), nullable=False, server_default="0"),
        sa.Column("used_days", sa.Numeric(5, 1), nullable=False, server_default="0"),
        sa.Column("remaining_days", sa.Numeric(5, 1), nullable=False,
                  server_default="0"),
        sa.Column("accrual_rule", JSONB, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("ix_leave_balances_assignment_id", "leave_balances",
                    ["assignment_id"])
    op.create_unique_constraint("uq_leave_balance_assignment_type_year",
                                "leave_balances",
                                ["assignment_id", "leave_type", "year"])


def downgrade() -> None:
    op.drop_constraint("uq_leave_balance_assignment_type_year", "leave_balances",
                       type_="unique")
    op.drop_index("ix_leave_balances_assignment_id", table_name="leave_balances")
    op.drop_table("leave_balances")

    op.drop_index("ix_leave_requests_assignment_id", table_name="leave_requests")
    op.drop_table("leave_requests")

    op.drop_constraint("uq_daily_attendance_assignment_date", "daily_attendances",
                       type_="unique")
    op.drop_index("ix_daily_attendances_date", table_name="daily_attendances")
    op.drop_index("ix_daily_attendances_assignment_id", table_name="daily_attendances")
    op.drop_table("daily_attendances")

    op.drop_index("ix_clock_records_assignment_id", table_name="clock_records")
    op.drop_table("clock_records")
