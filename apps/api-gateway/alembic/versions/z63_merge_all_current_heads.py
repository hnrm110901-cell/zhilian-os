"""merge all current heads into single canonical head

Unifies the 3 parallel migration heads after PR #82 merge:
  - z62_attendance_scheduled_times  (main HR chain: z53→z54→…→z62)
  - z51_customer_dish_interactions  (signal/data-lineage branch)
  - z50_merge_all_heads             (hr21 + edge + pos-daily branch)

No schema changes — purely a topology merge to enable `alembic upgrade head`.

Revision ID: z63_merge_all_current_heads
Revises: z62_attendance_scheduled_times,
         z51_customer_dish_interactions,
         z50_merge_all_heads
Create Date: 2026-03-19
"""
from alembic import op

revision = "z63_merge_all_current_heads"
down_revision = (
    "z62_attendance_scheduled_times",
    "z51_customer_dish_interactions",
    "z50_merge_all_heads",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
