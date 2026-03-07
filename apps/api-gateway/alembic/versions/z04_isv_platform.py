"""add ISV platform tables

Revision ID: z04_isv_platform
Revises: z03_execution_audit
Create Date: 2026-03-07 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'z04_isv_platform'
down_revision = 'z03_execution_audit'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ISV 开发者主表
    op.create_table(
        'isv_developers',
        sa.Column('id', sa.String(50), primary_key=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('email', sa.String(200), nullable=False),
        sa.Column('company', sa.String(200)),
        sa.Column('tier', sa.String(20), nullable=False, server_default='free'),
        sa.Column('is_verified', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
    )
    op.create_index('ix_isv_developers_email', 'isv_developers', ['email'], unique=True)

    # ISV API Key 表（每个开发者可多个 Key）
    op.create_table(
        'isv_api_keys',
        sa.Column('id', sa.String(50), primary_key=True),
        sa.Column('developer_id', sa.String(50), sa.ForeignKey('isv_developers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('key_name', sa.String(100), nullable=False, server_default='default'),
        sa.Column('api_key', sa.String(100), nullable=False),
        sa.Column('api_secret_hash', sa.String(200), nullable=False),
        sa.Column('rate_limit_rpm', sa.Integer(), nullable=False, server_default='60'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('last_used_at', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
    )
    op.create_index('ix_isv_api_keys_api_key', 'isv_api_keys', ['api_key'], unique=True)
    op.create_index('ix_isv_api_keys_developer_id', 'isv_api_keys', ['developer_id'])


def downgrade() -> None:
    op.drop_table('isv_api_keys')
    op.drop_table('isv_developers')
