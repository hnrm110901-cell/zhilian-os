"""hr12 — 考勤系统扩展（班次模板 + 考勤规则 + AttendanceLog新字段）

Revision ID: hr12
Revises: hr11
Create Date: 2026-03-15

支撑 4871 名员工 × 62 家门店的真实连锁考勤场景。
新增 shift_templates、attendance_rules 表；
为 attendance_logs 追加班次关联、GPS、扣款等字段。
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

revision = 'hr12'
down_revision = 'hr11'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. shift_templates 班次模板 ───────────────────────────
    op.create_table(
        'shift_templates',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('brand_id', sa.String(50), nullable=False, index=True),
        sa.Column('store_id', sa.String(50), nullable=True),
        sa.Column('name', sa.String(50), nullable=False),
        sa.Column('code', sa.String(20), nullable=False),
        sa.Column('start_time', sa.Time, nullable=False),
        sa.Column('end_time', sa.Time, nullable=False),
        sa.Column('is_cross_day', sa.Boolean, server_default='false'),
        sa.Column('break_minutes', sa.Integer, server_default='60'),
        sa.Column('min_work_hours', sa.Numeric(4, 1), nullable=True),
        sa.Column('late_threshold_minutes', sa.Integer, server_default='5'),
        sa.Column('early_leave_threshold_minutes', sa.Integer, server_default='5'),
        sa.Column('applicable_positions', JSON, server_default='[]'),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('sort_order', sa.Integer, server_default='0'),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_shift_templates_brand_store', 'shift_templates', ['brand_id', 'store_id'])
    op.create_index('ix_shift_templates_code', 'shift_templates', ['brand_id', 'code'])

    # ── 2. attendance_rules 考勤规则 ──────────────────────────
    op.create_table(
        'attendance_rules',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('brand_id', sa.String(50), nullable=False, index=True),
        sa.Column('store_id', sa.String(50), nullable=True),
        sa.Column('employment_type', sa.String(30), nullable=True),
        # 打卡方式
        sa.Column('clock_methods', JSON, server_default='["wechat"]'),
        # GPS围栏
        sa.Column('gps_fence_enabled', sa.Boolean, server_default='false'),
        sa.Column('gps_latitude', sa.Numeric(10, 7), nullable=True),
        sa.Column('gps_longitude', sa.Numeric(10, 7), nullable=True),
        sa.Column('gps_radius_meters', sa.Integer, server_default='200'),
        # 扣款规则（分）
        sa.Column('late_deduction_fen', sa.Integer, server_default='0'),
        sa.Column('absent_deduction_fen', sa.Integer, server_default='0'),
        sa.Column('early_leave_deduction_fen', sa.Integer, server_default='0'),
        # 加班倍数
        sa.Column('weekday_overtime_rate', sa.Numeric(3, 1), server_default='1.5'),
        sa.Column('weekend_overtime_rate', sa.Numeric(3, 1), server_default='2.0'),
        sa.Column('holiday_overtime_rate', sa.Numeric(3, 1), server_default='3.0'),
        # 综合工时
        sa.Column('work_hour_type', sa.String(30), server_default="'standard'"),
        sa.Column('monthly_standard_hours', sa.Numeric(5, 1), server_default='174'),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        'ix_attendance_rules_brand_store_emp',
        'attendance_rules',
        ['brand_id', 'store_id', 'employment_type'],
    )

    # ── 3. attendance_logs 新增字段 ───────────────────────────
    op.add_column('attendance_logs', sa.Column('shift_template_id', UUID(as_uuid=True), nullable=True))
    op.add_column('attendance_logs', sa.Column('scheduled_start', sa.DateTime(timezone=True), nullable=True))
    op.add_column('attendance_logs', sa.Column('scheduled_end', sa.DateTime(timezone=True), nullable=True))
    op.add_column('attendance_logs', sa.Column('early_leave_minutes', sa.Integer, nullable=True))
    op.add_column('attendance_logs', sa.Column('gps_clock_in', JSON, nullable=True))
    op.add_column('attendance_logs', sa.Column('gps_clock_out', JSON, nullable=True))
    op.add_column('attendance_logs', sa.Column('is_cross_day', sa.Boolean, server_default='false'))
    op.add_column('attendance_logs', sa.Column('deduction_fen', sa.Integer, server_default='0'))
    op.add_column('attendance_logs', sa.Column('deduction_reason', sa.String(200), nullable=True))

    # 查询优化索引
    op.create_index('ix_attendance_logs_shift_template', 'attendance_logs', ['shift_template_id'])
    op.create_index('ix_attendance_logs_deduction', 'attendance_logs', ['store_id', 'deduction_fen'])


def downgrade() -> None:
    # 删除 attendance_logs 新增索引和字段
    op.drop_index('ix_attendance_logs_deduction')
    op.drop_index('ix_attendance_logs_shift_template')
    op.drop_column('attendance_logs', 'deduction_reason')
    op.drop_column('attendance_logs', 'deduction_fen')
    op.drop_column('attendance_logs', 'is_cross_day')
    op.drop_column('attendance_logs', 'gps_clock_out')
    op.drop_column('attendance_logs', 'gps_clock_in')
    op.drop_column('attendance_logs', 'early_leave_minutes')
    op.drop_column('attendance_logs', 'scheduled_end')
    op.drop_column('attendance_logs', 'scheduled_start')
    op.drop_column('attendance_logs', 'shift_template_id')

    # 删除新表
    op.drop_index('ix_attendance_rules_brand_store_emp')
    op.drop_table('attendance_rules')
    op.drop_index('ix_shift_templates_code')
    op.drop_index('ix_shift_templates_brand_store')
    op.drop_table('shift_templates')
