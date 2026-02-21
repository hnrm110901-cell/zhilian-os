"""add_wechat_user_id_to_users

Revision ID: f59c6ee62g7e
Revises: e48b5dd51f6d
Create Date: 2026-02-21 16:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f59c6ee62g7e'
down_revision: Union[str, None] = 'e48b5dd51f6d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add wechat_user_id column to users table
    op.add_column('users', sa.Column('wechat_user_id', sa.String(length=100), nullable=True))
    op.create_index(op.f('ix_users_wechat_user_id'), 'users', ['wechat_user_id'], unique=False)


def downgrade() -> None:
    # Remove wechat_user_id column from users table
    op.drop_index(op.f('ix_users_wechat_user_id'), table_name='users')
    op.drop_column('users', 'wechat_user_id')
