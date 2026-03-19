"""merge z50 and z55 heads

Revision ID: bcf086b8b19c
Revises: z50_merge_all_heads, z55
Create Date: 2026-03-18 17:47:15.155966

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bcf086b8b19c'
down_revision: Union[str, None] = ('z50_merge_all_heads', 'z55')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
