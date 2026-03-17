"""z52 org_hierarchy — 组织层级模型 + Store/Employee 字段扩展

Revision ID: z52
Revises: z51_job_standard_module
Create Date: 2026-03-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'z52'
down_revision = 'z51_job_standard_module'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. org_nodes 表 ───────────────────────────────────────────────
    op.create_table(
        'org_nodes',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('name', sa.String(128), nullable=False),
        sa.Column('code', sa.String(32), unique=True, nullable=True),
        sa.Column('node_type', sa.String(32), nullable=False),
        sa.Column('parent_id', sa.String(64), sa.ForeignKey('org_nodes.id'), nullable=True),
        sa.Column('path', sa.String(512), nullable=False),
        sa.Column('depth', sa.Integer, nullable=False, server_default='0'),
        sa.Column('store_type', sa.String(32), nullable=True),
        sa.Column('operation_mode', sa.String(32), nullable=True),
        sa.Column('store_ref_id', sa.String(50), sa.ForeignKey('stores.id'), nullable=True),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('extra', postgresql.JSON(astext_type=sa.Text()), server_default='{}'),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('sort_order', sa.Integer, server_default='0'),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.text('NOW()')),
    )
    op.create_index('ix_org_nodes_node_type', 'org_nodes', ['node_type'])
    op.create_index('ix_org_nodes_parent_id', 'org_nodes', ['parent_id'])
    op.create_index('ix_org_nodes_path', 'org_nodes', ['path'])

    # ── 2. org_configs 表 ────────────────────────────────────────────
    op.create_table(
        'org_configs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('org_node_id', sa.String(64), sa.ForeignKey('org_nodes.id'), nullable=False),
        sa.Column('config_key', sa.String(128), nullable=False),
        sa.Column('config_value', sa.Text, nullable=False),
        sa.Column('value_type', sa.String(16), server_default='str'),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('is_override', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('set_by', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.text('NOW()')),
        sa.UniqueConstraint('org_node_id', 'config_key', name='uq_org_config_node_key'),
    )
    op.create_index('ix_org_configs_node_id', 'org_configs', ['org_node_id'])
    op.create_index('ix_org_configs_key', 'org_configs', ['config_key'])

    # ── 3. stores 表新增字段 ─────────────────────────────────────────
    op.add_column('stores', sa.Column('org_node_id', sa.String(64),
                  sa.ForeignKey('org_nodes.id'), nullable=True))
    op.add_column('stores', sa.Column('store_type', sa.String(32), nullable=True))
    op.add_column('stores', sa.Column('operation_mode', sa.String(32), nullable=True))
    op.create_index('ix_stores_org_node_id', 'stores', ['org_node_id'])

    # ── 4. employees 表新增字段 ──────────────────────────────────────
    op.add_column('employees', sa.Column('dept_node_id', sa.String(64),
                  sa.ForeignKey('org_nodes.id'), nullable=True))
    op.create_index('ix_employees_dept_node_id', 'employees', ['dept_node_id'])


def downgrade() -> None:
    op.drop_index('ix_employees_dept_node_id', 'employees')
    op.drop_column('employees', 'dept_node_id')
    op.drop_index('ix_stores_org_node_id', 'stores')
    op.drop_column('stores', 'operation_mode')
    op.drop_column('stores', 'store_type')
    op.drop_column('stores', 'org_node_id')
    op.drop_index('ix_org_configs_key', 'org_configs')
    op.drop_index('ix_org_configs_node_id', 'org_configs')
    op.drop_table('org_configs')
    op.drop_index('ix_org_nodes_path', 'org_nodes')
    op.drop_index('ix_org_nodes_parent_id', 'org_nodes')
    op.drop_index('ix_org_nodes_node_type', 'org_nodes')
    op.drop_table('org_nodes')
