# apps/api-gateway/alembic/versions/z53_org_scope.py
"""z53 org_scope — User.org_node_id + OrgPermission 表

Revision ID: z53
Revises: z52
Create Date: 2026-03-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'z53'
down_revision = 'z52'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── org_permissions 表 ───────────────────────────────────────────
    op.create_table(
        'org_permissions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('org_node_id', sa.String(64),
                  sa.ForeignKey('org_nodes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('permission_level', sa.String(32), nullable=False,
                  server_default='read_only'),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('granted_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime, nullable=False,
                  server_default=sa.text('NOW()')),
        sa.UniqueConstraint('user_id', 'org_node_id', name='uq_org_perm_user_node'),
    )
    op.create_index('ix_org_perm_user_id', 'org_permissions', ['user_id'])
    op.create_index('ix_org_perm_node_id', 'org_permissions', ['org_node_id'])

    # ── users 表新增字段 ──────────────────────────────────────────────
    op.add_column('users',
        sa.Column('org_node_id', sa.String(64),
                  sa.ForeignKey('org_nodes.id'), nullable=True))
    op.create_index('ix_users_org_node_id', 'users', ['org_node_id'])


def downgrade() -> None:
    op.drop_index('ix_users_org_node_id', 'users')
    op.drop_column('users', 'org_node_id')
    op.drop_index('ix_org_perm_node_id', 'org_permissions')
    op.drop_index('ix_org_perm_user_id', 'org_permissions')
    op.drop_table('org_permissions')
