"""hr16 — 离职结算单

Revision ID: hr16
Revises: hr15_approval
Create Date: 2026-03-15

Creates settlement_records table for employee separation settlements.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

revision = 'hr16'
down_revision = 'hr15_approval'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'settlement_records',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('store_id', sa.String(50), nullable=False, index=True),
        sa.Column('brand_id', sa.String(50), nullable=False),
        sa.Column('employee_id', sa.String(50), nullable=False, index=True),
        sa.Column('employee_name', sa.String(100), nullable=True),

        # 离职信息
        sa.Column('separation_type', sa.String(30), nullable=False),
        sa.Column('last_work_date', sa.Date, nullable=False),
        sa.Column('separation_date', sa.Date, nullable=False),

        # 最后月工资
        sa.Column('work_days_last_month', sa.Integer, server_default='0'),
        sa.Column('last_month_salary_fen', sa.Integer, server_default='0'),

        # 未休年假补偿
        sa.Column('unused_annual_days', sa.Integer, server_default='0'),
        sa.Column('annual_leave_compensation_fen', sa.Integer, server_default='0'),
        sa.Column('annual_leave_calc_method', sa.String(20), server_default='legal'),

        # 经济补偿金
        sa.Column('service_years', sa.Integer, server_default='0'),
        sa.Column('compensation_months', sa.Integer, server_default='0'),
        sa.Column('compensation_base_fen', sa.Integer, server_default='0'),
        sa.Column('economic_compensation_fen', sa.Integer, server_default='0'),
        sa.Column('compensation_type', sa.String(20), server_default='none'),

        # 其他
        sa.Column('overtime_pay_fen', sa.Integer, server_default='0'),
        sa.Column('bonus_fen', sa.Integer, server_default='0'),
        sa.Column('deduction_fen', sa.Integer, server_default='0'),
        sa.Column('deduction_detail', sa.Text, nullable=True),

        # 汇总
        sa.Column('total_payable_fen', sa.Integer, server_default='0'),

        # 交接
        sa.Column('handover_items', JSON, nullable=True),
        sa.Column('handover_completed', sa.Boolean, server_default='false'),

        # 状态
        sa.Column('status', sa.String(20), server_default='draft'),
        sa.Column('approval_instance_id', UUID(as_uuid=True), nullable=True),

        # 打款
        sa.Column('paid_at', sa.DateTime, nullable=True),
        sa.Column('paid_by', sa.String(100), nullable=True),

        # 计算快照
        sa.Column('calculation_snapshot', JSON, nullable=True),

        sa.Column('remark', sa.Text, nullable=True),

        # TimestampMixin
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # 复合索引：按门店+状态查询
    op.create_index(
        'ix_settlement_store_status',
        'settlement_records',
        ['store_id', 'status'],
    )


def downgrade() -> None:
    op.drop_index('ix_settlement_store_status', table_name='settlement_records')
    op.drop_table('settlement_records')
