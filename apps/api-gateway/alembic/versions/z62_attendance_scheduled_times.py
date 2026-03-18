"""z62: Add scheduled times to daily_attendances

Revision ID: z62_attendance_scheduled_times
Revises: z61_hr_payroll
"""
from alembic import op
import sqlalchemy as sa

revision = "z62_attendance_scheduled_times"
down_revision = "z61_hr_payroll"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("daily_attendances", sa.Column("scheduled_start_time", sa.Time(), nullable=True))
    op.add_column("daily_attendances", sa.Column("scheduled_end_time", sa.Time(), nullable=True))


def downgrade() -> None:
    op.drop_column("daily_attendances", "scheduled_end_time")
    op.drop_column("daily_attendances", "scheduled_start_time")
