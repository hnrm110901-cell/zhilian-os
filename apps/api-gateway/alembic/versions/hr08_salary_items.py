"""hr08 — 薪酬项定义 + 薪酬项明细 + 城市最低工资

Revision ID: hr08
Revises: hr07
Create Date: 2026-03-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

revision = 'hr08'
down_revision = 'hr07'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 薪酬项定义表 ──
    op.create_table(
        'salary_item_definitions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('brand_id', sa.String(50), nullable=False, index=True),
        sa.Column('store_id', sa.String(50), nullable=True, index=True),
        sa.Column('item_name', sa.String(100), nullable=False),
        sa.Column('item_code', sa.String(50), nullable=True),
        sa.Column('item_category', sa.String(30), nullable=False),
        sa.Column('calc_order', sa.Integer, nullable=False, server_default='50'),
        sa.Column('formula', sa.Text, nullable=True),
        sa.Column('formula_type', sa.String(20), server_default='expression'),
        sa.Column('decimal_places', sa.Integer, server_default='2'),
        sa.Column('is_active', sa.Boolean, server_default='true', nullable=False),
        sa.Column('effective_month', sa.String(7), nullable=True),
        sa.Column('expire_month', sa.String(7), nullable=True),
        sa.Column('remark', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # ── 薪酬项月度明细 ──
    op.create_table(
        'salary_item_records',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('store_id', sa.String(50), nullable=False, index=True),
        sa.Column('employee_id', sa.String(50), nullable=False, index=True),
        sa.Column('pay_month', sa.String(7), nullable=False, index=True),
        sa.Column('item_id', UUID(as_uuid=True), nullable=False, index=True),
        sa.Column('item_name', sa.String(100), nullable=False),
        sa.Column('item_category', sa.String(30), nullable=False),
        sa.Column('amount_fen', sa.Integer, nullable=False, server_default='0'),
        sa.Column('formula_snapshot', sa.Text, nullable=True),
        sa.Column('calc_inputs', JSON, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('employee_id', 'pay_month', 'item_id', name='uq_salary_item_month'),
    )

    # ── 城市最低工资 ──
    op.create_table(
        'city_wage_configs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('city', sa.String(50), nullable=False, index=True),
        sa.Column('province', sa.String(50), nullable=True),
        sa.Column('year', sa.Integer, nullable=False, index=True),
        sa.Column('min_monthly_wage_fen', sa.Integer, nullable=False, server_default='0'),
        sa.Column('min_hourly_wage_fen', sa.Integer, nullable=False, server_default='0'),
        sa.Column('social_insurance_base_floor_fen', sa.Integer, nullable=False, server_default='0'),
        sa.Column('social_insurance_base_ceil_fen', sa.Integer, nullable=False, server_default='0'),
        sa.Column('housing_fund_base_floor_fen', sa.Integer, nullable=False, server_default='0'),
        sa.Column('housing_fund_base_ceil_fen', sa.Integer, nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('city', 'year', name='uq_city_wage_year'),
    )


def downgrade() -> None:
    op.drop_table('city_wage_configs')
    op.drop_table('salary_item_records')
    op.drop_table('salary_item_definitions')
