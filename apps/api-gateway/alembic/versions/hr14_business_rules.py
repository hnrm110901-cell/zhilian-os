"""hr14 — HR业务规则配置表

Revision ID: hr14
Revises: hr13
Create Date: 2026-03-15

替代硬编码的考勤扣款/工龄补贴/加班倍数等规则，支持品牌→门店→岗位三级配置继承。
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

revision = 'hr14'
down_revision = 'hr13'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'hr_business_rules',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('brand_id', sa.String(50), nullable=False, index=True),
        sa.Column('store_id', sa.String(50), nullable=True),
        sa.Column('position', sa.String(50), nullable=True),
        sa.Column('employment_type', sa.String(30), nullable=True),
        sa.Column('category', sa.String(50), nullable=False, index=True),
        sa.Column('rule_name', sa.String(100), nullable=False),
        sa.Column('rules_json', JSON, nullable=False),
        sa.Column('priority', sa.Integer, default=0),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    # 复合索引：品牌+门店+类别（三级继承查询常用）
    op.create_index(
        'ix_hr_business_rules_brand_store_cat',
        'hr_business_rules',
        ['brand_id', 'store_id', 'category'],
    )


def downgrade() -> None:
    op.drop_index('ix_hr_business_rules_brand_store_cat')
    op.drop_table('hr_business_rules')
