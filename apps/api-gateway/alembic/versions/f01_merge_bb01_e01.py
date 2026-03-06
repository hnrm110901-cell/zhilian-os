"""Merge bb01_order_waiter_id and e01_ops_monitoring into single head

Revision ID: f01_merge_bb01_e01
Revises: bb01_order_waiter_id, e01_ops_monitoring
Create Date: 2026-03-06
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'f01_merge_bb01_e01'
down_revision: Union[str, Sequence[str], None] = (
    'bb01_order_waiter_id',
    'e01_ops_monitoring',
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
