"""hr06: Add department_store_mapping to brand_im_configs

Revision ID: hr06
Revises: hr05
Create Date: 2026-03-15 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

# revision identifiers
revision = 'hr06'
down_revision = 'hr05'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'brand_im_configs',
        sa.Column('department_store_mapping', JSON, nullable=True),
    )


def downgrade() -> None:
    op.drop_column('brand_im_configs', 'department_store_mapping')
