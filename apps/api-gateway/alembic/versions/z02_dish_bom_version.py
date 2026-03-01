"""Dish 表增加 bom_version / effective_date（与本体 BOM 版本对齐）

Revision ID: z02_dish_bom_version
Revises: z01_ontology_actions
Create Date: 2026-02-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision = 'z02_dish_bom_version'
down_revision = 'z01_ontology_actions'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('dishes', sa.Column('bom_version', sa.String(50), nullable=True))
    op.add_column('dishes', sa.Column('effective_date', sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column('dishes', 'effective_date')
    op.drop_column('dishes', 'bom_version')
