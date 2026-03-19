"""hr18 — 门店岗位编制需求配置表

新建 store_staffing_demands 表，用于智能排班算法的需求侧输入。
按日期类型+班次类型配置各岗位最低/最高人数。

Revision ID: hr19
Revises: hr18
Create Date: 2026-03-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 'hr19'
down_revision = 'hr18'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'store_staffing_demands',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('store_id', sa.String(50), nullable=False, index=True),
        sa.Column('brand_id', sa.String(50), nullable=False),
        sa.Column('position', sa.String(50), nullable=False),
        sa.Column('day_type', sa.String(20), nullable=False),
        sa.Column('shift_type', sa.String(20), nullable=False),
        sa.Column('min_count', sa.Integer, nullable=False, server_default='1'),
        sa.Column('max_count', sa.Integer, nullable=False, server_default='3'),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    # 联合索引：按门店+日期类型+班次快速查询
    op.create_index(
        'ix_store_staffing_demands_lookup',
        'store_staffing_demands',
        ['store_id', 'day_type', 'shift_type'],
    )


def downgrade() -> None:
    op.drop_index('ix_store_staffing_demands_lookup', table_name='store_staffing_demands')
    op.drop_table('store_staffing_demands')
