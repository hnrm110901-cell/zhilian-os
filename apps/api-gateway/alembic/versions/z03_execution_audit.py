"""
ARCH-004: execution_audit 表迁移

Revision ID: z03_execution_audit
Revises: rls_002_brand_isolation
Create Date: 2026-03-01

变更说明:
1. 创建 execution_audit 表
2. REVOKE UPDATE/DELETE on app_user（确保审计日志不可篡改）
"""
from alembic import op
import sqlalchemy as sa


revision = 'z03_execution_audit'
down_revision = 'rls_002_brand_isolation'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 创建审计日志表
    op.create_table(
        'execution_audit',
        sa.Column('id', sa.String(50), primary_key=True),
        sa.Column('command_type', sa.String(100), nullable=False),
        sa.Column('payload', sa.JSON, nullable=False, server_default='{}'),
        sa.Column('actor_id', sa.String(100), nullable=False),
        sa.Column('actor_role', sa.String(50), nullable=False),
        sa.Column('store_id', sa.String(50), nullable=False),
        sa.Column('brand_id', sa.String(50)),
        sa.Column('status', sa.String(50), nullable=False),
        sa.Column('level', sa.String(20), nullable=False),
        sa.Column('amount', sa.String(30)),
        sa.Column('result', sa.JSON, server_default='{}'),
        sa.Column('rollback_id', sa.String(50)),
        sa.Column('rolled_back_by', sa.String(100)),
        sa.Column('rolled_back_at', sa.DateTime),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('NOW()')),
    )

    # 创建索引
    op.create_index('ix_execution_audit_command_type', 'execution_audit', ['command_type'])
    op.create_index('ix_execution_audit_actor_id', 'execution_audit', ['actor_id'])
    op.create_index('ix_execution_audit_store_id', 'execution_audit', ['store_id'])
    op.create_index('ix_execution_audit_status', 'execution_audit', ['status'])
    op.create_index('ix_execution_audit_created_at', 'execution_audit', ['created_at'])

    # REVOKE UPDATE/DELETE on app_user — 确保审计日志不可篡改
    # 注意：此处针对 app_user 角色（非 superuser）进行权限撤销
    # superuser 保留完整权限用于运维操作
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user') THEN
                REVOKE UPDATE, DELETE ON execution_audit FROM app_user;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    # 还原权限
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user') THEN
                GRANT UPDATE, DELETE ON execution_audit TO app_user;
            END IF;
        END $$;
    """)

    # 删除索引
    op.drop_index('ix_execution_audit_created_at', table_name='execution_audit')
    op.drop_index('ix_execution_audit_status', table_name='execution_audit')
    op.drop_index('ix_execution_audit_store_id', table_name='execution_audit')
    op.drop_index('ix_execution_audit_actor_id', table_name='execution_audit')
    op.drop_index('ix_execution_audit_command_type', table_name='execution_audit')

    # 删除表
    op.drop_table('execution_audit')
