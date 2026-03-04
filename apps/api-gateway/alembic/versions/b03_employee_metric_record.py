"""
P2: 新增 employee_metric_records 表

Revision ID: b03_employee_metric_record
Revises: b02_order_item_food_cost
Create Date: 2026-03-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'b03_employee_metric_record'
down_revision = 'b02_order_item_food_cost'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'employee_metric_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('employee_id', sa.String(50), sa.ForeignKey('employees.id'), nullable=False),
        sa.Column('store_id',    sa.String(50), sa.ForeignKey('stores.id'),    nullable=False),
        sa.Column('metric_id',   sa.String(50), nullable=False),
        sa.Column('period_start', sa.Date, nullable=False),
        sa.Column('period_end',   sa.Date, nullable=False),
        sa.Column('value',            sa.Numeric(12, 4), nullable=True),
        sa.Column('target',           sa.Numeric(12, 4), nullable=True),
        sa.Column('achievement_rate', sa.Numeric(6,  4), nullable=True),
        sa.Column('data_source',      sa.String(100),    nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime, nullable=False,
                  server_default=sa.text('now()')),
        sa.UniqueConstraint('employee_id', 'metric_id', 'period_start',
                            name='uq_emp_metric_period'),
    )
    op.create_index('idx_emp_metric_employee', 'employee_metric_records', ['employee_id'])
    op.create_index('idx_emp_metric_store_period', 'employee_metric_records',
                    ['store_id', 'period_start'])


def downgrade() -> None:
    op.drop_index('idx_emp_metric_store_period', table_name='employee_metric_records')
    op.drop_index('idx_emp_metric_employee',     table_name='employee_metric_records')
    op.drop_table('employee_metric_records')
