"""add_latitude_longitude_to_stores

Revision ID: e48b5dd51f6d
Revises: b2c3d4e5f6g7
Create Date: 2026-02-20 10:41:15.399662

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e48b5dd51f6d'
down_revision: Union[str, None] = 'b2c3d4e5f6g7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add latitude and longitude columns to stores table
    op.add_column('stores', sa.Column('latitude', sa.Float(), nullable=True))
    op.add_column('stores', sa.Column('longitude', sa.Float(), nullable=True))


def downgrade() -> None:
    # Remove latitude and longitude columns from stores table
    op.drop_column('stores', 'longitude')
    op.drop_column('stores', 'latitude')
