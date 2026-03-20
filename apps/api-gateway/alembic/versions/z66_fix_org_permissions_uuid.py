"""z66 — 修复 org_permissions.user_id/granted_by 类型为 UUID

z53 迁移中 org_permissions.user_id 定义为 VARCHAR(64)，
但 users.id 是 UUID 类型，导致外键约束创建失败。
此迁移修正列类型并重建外键约束。

Revision ID: z66_fix_org_permissions_uuid
Revises: z65_person_profile_expand
Create Date: 2026-03-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "z66_fix_org_permissions_uuid"
down_revision = "z65_person_profile_expand"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 检查 org_permissions 表是否存在，不存在则跳过
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
        "WHERE table_name = 'org_permissions')"
    ))
    table_exists = result.scalar()

    if not table_exists:
        # 表不存在，用正确的类型重新创建
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
        return

    # 表已存在 — 修复列类型
    # 1. 先删除外键约束
    op.drop_constraint('org_permissions_user_id_fkey', 'org_permissions', type_='foreignkey')

    # 2. 修改列类型 VARCHAR(64) → UUID
    op.alter_column(
        'org_permissions', 'user_id',
        existing_type=sa.String(64),
        type_=postgresql.UUID(as_uuid=True),
        postgresql_using='user_id::uuid',
    )
    op.alter_column(
        'org_permissions', 'granted_by',
        existing_type=sa.String(64),
        type_=postgresql.UUID(as_uuid=True),
        existing_nullable=True,
        postgresql_using='granted_by::uuid',
    )

    # 3. 重建外键约束
    op.create_foreign_key(
        'org_permissions_user_id_fkey',
        'org_permissions', 'users',
        ['user_id'], ['id'],
        ondelete='CASCADE',
    )


def downgrade() -> None:
    op.drop_constraint('org_permissions_user_id_fkey', 'org_permissions', type_='foreignkey')
    op.alter_column(
        'org_permissions', 'user_id',
        existing_type=postgresql.UUID(as_uuid=True),
        type_=sa.String(64),
        postgresql_using='user_id::text',
    )
    op.alter_column(
        'org_permissions', 'granted_by',
        existing_type=postgresql.UUID(as_uuid=True),
        type_=sa.String(64),
        existing_nullable=True,
        postgresql_using='granted_by::text',
    )
    op.create_foreign_key(
        'org_permissions_user_id_fkey',
        'org_permissions', 'users',
        ['user_id'], ['id'],
        ondelete='CASCADE',
    )
