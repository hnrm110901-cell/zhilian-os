"""
Add webhook_secret to external_systems

Revision ID: n01_pos_webhook_secret
Revises: rls_001_tenant_isolation
Create Date: 2026-02-24
"""
from alembic import op
import sqlalchemy as sa

revision = 'n01_pos_webhook_secret'
down_revision = 'rls_001_tenant_isolation'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'external_systems',
        sa.Column('webhook_secret', sa.String(500), nullable=True, comment='Webhook签名密钥(HMAC-SHA256)')
    )


def downgrade():
    op.drop_column('external_systems', 'webhook_secret')
