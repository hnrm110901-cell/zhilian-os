"""hr01 — HR业人一体化第1批：薪酬+审批+假勤+生命周期（11张表）

Tables:
  salary_structures           — 员工薪资结构方案
  payroll_records             — 月度工资单
  tax_declarations            — 个税累计预扣记录
  approval_flow_templates     — 审批流程模板
  approval_instances          — 审批实例
  approval_node_records       — 审批节点执行记录
  leave_type_configs          — 假期类型配置
  leave_balances              — 员工假期余额
  leave_requests              — 请假申请单
  overtime_requests           — 加班申请单
  employee_changes            — 员工变动记录

Enum types (PostgreSQL native):
  salary_type, payroll_status, tax_declaration_status,
  approval_type_enum, approval_status_enum, approval_node_type_enum,
  leave_category_enum, leave_request_status_enum,
  overtime_type_enum, overtime_request_status_enum,
  employee_change_type_enum
"""

revision = 'hr01'
down_revision = 'z48_cdp_pdm_link'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


def _create_enum_safe(name: str, values: list[str]) -> None:
    """创建 enum，已存在则跳过"""
    op.execute(f"""
        DO $$
        BEGIN
            CREATE TYPE {name} AS ENUM ({', '.join(f"'{v}'" for v in values)});
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
    """)


def upgrade() -> None:
    # ── Enum 类型 ─────────────────────────────────────────
    _create_enum_safe('salary_type', ['monthly', 'hourly', 'daily'])
    _create_enum_safe('payroll_status', ['draft', 'confirmed', 'paid', 'cancelled'])
    _create_enum_safe('tax_declaration_status', ['pending', 'declared', 'paid'])

    _create_enum_safe('approval_type_enum', [
        'leave', 'overtime', 'payroll', 'offer', 'contract',
        'transfer', 'resignation', 'general',
    ])
    _create_enum_safe('approval_status_enum', [
        'pending', 'approved', 'rejected', 'withdrawn', 'expired',
    ])
    _create_enum_safe('approval_node_type_enum', ['single', 'and_sign', 'or_sign'])

    _create_enum_safe('leave_category_enum', [
        'annual', 'sick', 'personal', 'maternity', 'paternity',
        'marriage', 'bereavement', 'compensatory', 'other',
    ])
    _create_enum_safe('leave_request_status_enum', [
        'draft', 'pending', 'approved', 'rejected', 'cancelled',
    ])
    _create_enum_safe('overtime_type_enum', ['weekday', 'weekend', 'holiday'])
    _create_enum_safe('overtime_request_status_enum', [
        'draft', 'pending', 'approved', 'rejected', 'cancelled',
    ])
    _create_enum_safe('employee_change_type_enum', [
        'onboard', 'probation', 'transfer', 'promotion', 'demotion',
        'salary_adj', 'resign', 'dismiss', 'retire',
    ])

    # ── 1. salary_structures ──────────────────────────────
    op.create_table(
        'salary_structures',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('store_id', sa.String(50), nullable=False),
        sa.Column('employee_id', sa.String(50), sa.ForeignKey('employees.id'), nullable=False),
        sa.Column('salary_type', postgresql.ENUM('monthly', 'hourly', 'daily',
                                                  name='salary_type', create_type=False),
                  nullable=False, server_default='monthly'),
        sa.Column('base_salary_fen', sa.Integer, nullable=False, server_default='0'),
        sa.Column('position_allowance_fen', sa.Integer, nullable=False, server_default='0'),
        sa.Column('meal_allowance_fen', sa.Integer, nullable=False, server_default='0'),
        sa.Column('transport_allowance_fen', sa.Integer, nullable=False, server_default='0'),
        sa.Column('hourly_rate_fen', sa.Integer, nullable=True),
        sa.Column('performance_coefficient', sa.Numeric(4, 2), nullable=False, server_default='1.00'),
        sa.Column('social_insurance_fen', sa.Integer, nullable=False, server_default='0'),
        sa.Column('housing_fund_fen', sa.Integer, nullable=False, server_default='0'),
        sa.Column('special_deduction_fen', sa.Integer, nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('effective_date', sa.Date, nullable=False),
        sa.Column('expire_date', sa.Date, nullable=True),
        sa.Column('approved_by', sa.String(100), nullable=True),
        sa.Column('remark', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('ix_ss_store_id', 'salary_structures', ['store_id'])
    op.create_index('ix_ss_employee_id', 'salary_structures', ['employee_id'])
    op.create_unique_constraint('uq_salary_active', 'salary_structures', ['employee_id', 'is_active'])

    # ── 2. payroll_records ────────────────────────────────
    op.create_table(
        'payroll_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('store_id', sa.String(50), nullable=False),
        sa.Column('employee_id', sa.String(50), sa.ForeignKey('employees.id'), nullable=False),
        sa.Column('pay_month', sa.String(7), nullable=False),
        sa.Column('status', postgresql.ENUM('draft', 'confirmed', 'paid', 'cancelled',
                                             name='payroll_status', create_type=False),
                  nullable=False, server_default='draft'),
        # 应发
        sa.Column('base_salary_fen', sa.Integer, nullable=False, server_default='0'),
        sa.Column('position_allowance_fen', sa.Integer, nullable=False, server_default='0'),
        sa.Column('meal_allowance_fen', sa.Integer, nullable=False, server_default='0'),
        sa.Column('transport_allowance_fen', sa.Integer, nullable=False, server_default='0'),
        sa.Column('performance_bonus_fen', sa.Integer, nullable=False, server_default='0'),
        sa.Column('overtime_pay_fen', sa.Integer, nullable=False, server_default='0'),
        sa.Column('other_bonus_fen', sa.Integer, nullable=False, server_default='0'),
        sa.Column('gross_salary_fen', sa.Integer, nullable=False, server_default='0'),
        # 扣款
        sa.Column('absence_deduction_fen', sa.Integer, nullable=False, server_default='0'),
        sa.Column('late_deduction_fen', sa.Integer, nullable=False, server_default='0'),
        sa.Column('social_insurance_fen', sa.Integer, nullable=False, server_default='0'),
        sa.Column('housing_fund_fen', sa.Integer, nullable=False, server_default='0'),
        sa.Column('tax_fen', sa.Integer, nullable=False, server_default='0'),
        sa.Column('other_deduction_fen', sa.Integer, nullable=False, server_default='0'),
        sa.Column('total_deduction_fen', sa.Integer, nullable=False, server_default='0'),
        # 实发
        sa.Column('net_salary_fen', sa.Integer, nullable=False, server_default='0'),
        # 考勤统计
        sa.Column('attendance_days', sa.Numeric(5, 1), nullable=True),
        sa.Column('absence_days', sa.Numeric(5, 1), nullable=True),
        sa.Column('late_count', sa.Integer, nullable=True),
        sa.Column('overtime_hours', sa.Numeric(6, 1), nullable=True),
        sa.Column('leave_days', sa.Numeric(5, 1), nullable=True),
        # 明细
        sa.Column('calculation_detail', sa.JSON, nullable=True),
        sa.Column('paid_at', sa.DateTime, nullable=True),
        sa.Column('confirmed_by', sa.String(100), nullable=True),
        sa.Column('remark', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('ix_pr_store_id', 'payroll_records', ['store_id'])
    op.create_index('ix_pr_employee_id', 'payroll_records', ['employee_id'])
    op.create_index('ix_pr_pay_month', 'payroll_records', ['pay_month'])
    op.create_unique_constraint('uq_payroll_month', 'payroll_records',
                                ['store_id', 'employee_id', 'pay_month'])

    # ── 3. tax_declarations ───────────────────────────────
    op.create_table(
        'tax_declarations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('store_id', sa.String(50), nullable=False),
        sa.Column('employee_id', sa.String(50), sa.ForeignKey('employees.id'), nullable=False),
        sa.Column('tax_month', sa.String(7), nullable=False),
        sa.Column('status', postgresql.ENUM('pending', 'declared', 'paid',
                                             name='tax_declaration_status', create_type=False),
                  nullable=False, server_default='pending'),
        sa.Column('monthly_income_fen', sa.Integer, nullable=False, server_default='0'),
        sa.Column('monthly_social_deduction_fen', sa.Integer, nullable=False, server_default='0'),
        sa.Column('monthly_special_deduction_fen', sa.Integer, nullable=False, server_default='0'),
        sa.Column('cumulative_income_fen', sa.Integer, nullable=False, server_default='0'),
        sa.Column('cumulative_deduction_fen', sa.Integer, nullable=False, server_default='0'),
        sa.Column('cumulative_taxable_income_fen', sa.Integer, nullable=False, server_default='0'),
        sa.Column('cumulative_tax_fen', sa.Integer, nullable=False, server_default='0'),
        sa.Column('cumulative_prepaid_tax_fen', sa.Integer, nullable=False, server_default='0'),
        sa.Column('current_month_tax_fen', sa.Integer, nullable=False, server_default='0'),
        sa.Column('tax_rate_pct', sa.Numeric(5, 2), nullable=True),
        sa.Column('quick_deduction_fen', sa.Integer, nullable=True),
        sa.Column('declared_at', sa.DateTime, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('ix_td_store_id', 'tax_declarations', ['store_id'])
    op.create_index('ix_td_employee_id', 'tax_declarations', ['employee_id'])
    op.create_index('ix_td_tax_month', 'tax_declarations', ['tax_month'])
    op.create_unique_constraint('uq_tax_month', 'tax_declarations', ['employee_id', 'tax_month'])

    # ── 4. approval_flow_templates ────────────────────────
    op.create_table(
        'approval_flow_templates',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('store_id', sa.String(50), nullable=True),
        sa.Column('brand_id', sa.String(50), nullable=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('approval_type', postgresql.ENUM(
            'leave', 'overtime', 'payroll', 'offer', 'contract',
            'transfer', 'resignation', 'general',
            name='approval_type_enum', create_type=False), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('nodes', sa.JSON, nullable=False, server_default='[]'),
        sa.Column('trigger_conditions', sa.JSON, nullable=True),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('priority', sa.Integer, server_default='0'),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('ix_aft_store_id', 'approval_flow_templates', ['store_id'])
    op.create_index('ix_aft_brand_id', 'approval_flow_templates', ['brand_id'])
    op.create_index('ix_aft_type', 'approval_flow_templates', ['approval_type'])

    # ── 5. approval_instances ─────────────────────────────
    op.create_table(
        'approval_instances',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('store_id', sa.String(50), nullable=False),
        sa.Column('template_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('approval_flow_templates.id'), nullable=True),
        sa.Column('approval_type', postgresql.ENUM(
            'leave', 'overtime', 'payroll', 'offer', 'contract',
            'transfer', 'resignation', 'general',
            name='approval_type_enum', create_type=False), nullable=False),
        sa.Column('status', postgresql.ENUM(
            'pending', 'approved', 'rejected', 'withdrawn', 'expired',
            name='approval_status_enum', create_type=False),
            nullable=False, server_default='pending'),
        sa.Column('applicant_id', sa.String(50), nullable=False),
        sa.Column('applicant_name', sa.String(100), nullable=True),
        sa.Column('business_type', sa.String(50), nullable=False),
        sa.Column('business_id', sa.String(50), nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('summary', sa.Text, nullable=True),
        sa.Column('business_data', sa.JSON, nullable=True),
        sa.Column('current_step', sa.Integer, server_default='1'),
        sa.Column('total_steps', sa.Integer, server_default='1'),
        sa.Column('final_approver_id', sa.String(50), nullable=True),
        sa.Column('final_approver_name', sa.String(100), nullable=True),
        sa.Column('rejection_reason', sa.Text, nullable=True),
        sa.Column('approved_at', sa.DateTime, nullable=True),
        sa.Column('rejected_at', sa.DateTime, nullable=True),
        sa.Column('expired_at', sa.DateTime, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('ix_ai_store_id', 'approval_instances', ['store_id'])
    op.create_index('ix_ai_type', 'approval_instances', ['approval_type'])
    op.create_index('ix_ai_status', 'approval_instances', ['status'])
    op.create_index('ix_ai_applicant', 'approval_instances', ['applicant_id'])

    # ── 6. approval_node_records ──────────────────────────
    op.create_table(
        'approval_node_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('instance_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('approval_instances.id'), nullable=False),
        sa.Column('step', sa.Integer, nullable=False),
        sa.Column('node_type', postgresql.ENUM('single', 'and_sign', 'or_sign',
                                                name='approval_node_type_enum', create_type=False),
                  nullable=False, server_default='single'),
        sa.Column('approver_id', sa.String(50), nullable=False),
        sa.Column('approver_name', sa.String(100), nullable=True),
        sa.Column('approver_role', sa.String(50), nullable=True),
        sa.Column('action', sa.String(20), nullable=True),
        sa.Column('comment', sa.Text, nullable=True),
        sa.Column('acted_at', sa.DateTime, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('ix_anr_instance', 'approval_node_records', ['instance_id'])

    # ── 7. leave_type_configs ─────────────────────────────
    op.create_table(
        'leave_type_configs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('store_id', sa.String(50), nullable=True),
        sa.Column('brand_id', sa.String(50), nullable=True),
        sa.Column('category', postgresql.ENUM(
            'annual', 'sick', 'personal', 'maternity', 'paternity',
            'marriage', 'bereavement', 'compensatory', 'other',
            name='leave_category_enum', create_type=False), nullable=False),
        sa.Column('name', sa.String(50), nullable=False),
        sa.Column('is_paid', sa.Boolean, server_default='true'),
        sa.Column('max_days_per_year', sa.Numeric(5, 1), nullable=True),
        sa.Column('min_unit_hours', sa.Numeric(4, 1), server_default='4'),
        sa.Column('need_approval', sa.Boolean, server_default='true'),
        sa.Column('need_certificate', sa.Boolean, server_default='false'),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('ix_ltc_store_id', 'leave_type_configs', ['store_id'])
    op.create_index('ix_ltc_brand_id', 'leave_type_configs', ['brand_id'])

    # ── 8. leave_balances ─────────────────────────────────
    op.create_table(
        'leave_balances',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('store_id', sa.String(50), nullable=False),
        sa.Column('employee_id', sa.String(50), sa.ForeignKey('employees.id'), nullable=False),
        sa.Column('year', sa.Integer, nullable=False),
        sa.Column('leave_category', postgresql.ENUM(
            'annual', 'sick', 'personal', 'maternity', 'paternity',
            'marriage', 'bereavement', 'compensatory', 'other',
            name='leave_category_enum', create_type=False), nullable=False),
        sa.Column('total_days', sa.Numeric(5, 1), nullable=False, server_default='0'),
        sa.Column('used_days', sa.Numeric(5, 1), nullable=False, server_default='0'),
        sa.Column('pending_days', sa.Numeric(5, 1), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('ix_lb_store_id', 'leave_balances', ['store_id'])
    op.create_index('ix_lb_employee_id', 'leave_balances', ['employee_id'])
    op.create_unique_constraint('uq_leave_balance', 'leave_balances',
                                ['employee_id', 'year', 'leave_category'])

    # ── 9. leave_requests ─────────────────────────────────
    op.create_table(
        'leave_requests',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('store_id', sa.String(50), nullable=False),
        sa.Column('employee_id', sa.String(50), sa.ForeignKey('employees.id'), nullable=False),
        sa.Column('leave_category', postgresql.ENUM(
            'annual', 'sick', 'personal', 'maternity', 'paternity',
            'marriage', 'bereavement', 'compensatory', 'other',
            name='leave_category_enum', create_type=False), nullable=False),
        sa.Column('status', postgresql.ENUM(
            'draft', 'pending', 'approved', 'rejected', 'cancelled',
            name='leave_request_status_enum', create_type=False),
            nullable=False, server_default='draft'),
        sa.Column('start_date', sa.Date, nullable=False),
        sa.Column('end_date', sa.Date, nullable=False),
        sa.Column('start_half', sa.String(10), server_default='am'),
        sa.Column('end_half', sa.String(10), server_default='pm'),
        sa.Column('leave_days', sa.Numeric(5, 1), nullable=False),
        sa.Column('leave_hours', sa.Numeric(6, 1), nullable=True),
        sa.Column('reason', sa.Text, nullable=False),
        sa.Column('attachment_urls', sa.JSON, nullable=True),
        sa.Column('approval_instance_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('substitute_employee_id', sa.String(50), nullable=True),
        sa.Column('approved_by', sa.String(100), nullable=True),
        sa.Column('approved_at', sa.DateTime, nullable=True),
        sa.Column('rejection_reason', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('ix_lr_store_id', 'leave_requests', ['store_id'])
    op.create_index('ix_lr_employee_id', 'leave_requests', ['employee_id'])
    op.create_index('ix_lr_status', 'leave_requests', ['status'])

    # ── 10. overtime_requests ─────────────────────────────
    op.create_table(
        'overtime_requests',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('store_id', sa.String(50), nullable=False),
        sa.Column('employee_id', sa.String(50), sa.ForeignKey('employees.id'), nullable=False),
        sa.Column('overtime_type', postgresql.ENUM('weekday', 'weekend', 'holiday',
                                                    name='overtime_type_enum', create_type=False),
                  nullable=False),
        sa.Column('status', postgresql.ENUM(
            'draft', 'pending', 'approved', 'rejected', 'cancelled',
            name='overtime_request_status_enum', create_type=False),
            nullable=False, server_default='draft'),
        sa.Column('work_date', sa.Date, nullable=False),
        sa.Column('start_time', sa.DateTime, nullable=False),
        sa.Column('end_time', sa.DateTime, nullable=False),
        sa.Column('hours', sa.Numeric(5, 1), nullable=False),
        sa.Column('pay_rate', sa.Numeric(3, 1), nullable=False, server_default='1.5'),
        sa.Column('reason', sa.Text, nullable=False),
        sa.Column('compensatory', sa.Boolean, server_default='false'),
        sa.Column('approval_instance_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('approved_by', sa.String(100), nullable=True),
        sa.Column('approved_at', sa.DateTime, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('ix_or_store_id', 'overtime_requests', ['store_id'])
    op.create_index('ix_or_employee_id', 'overtime_requests', ['employee_id'])
    op.create_index('ix_or_status', 'overtime_requests', ['status'])

    # ── 11. employee_changes ──────────────────────────────
    op.create_table(
        'employee_changes',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('store_id', sa.String(50), nullable=False),
        sa.Column('employee_id', sa.String(50), sa.ForeignKey('employees.id'), nullable=False),
        sa.Column('change_type', postgresql.ENUM(
            'onboard', 'probation', 'transfer', 'promotion', 'demotion',
            'salary_adj', 'resign', 'dismiss', 'retire',
            name='employee_change_type_enum', create_type=False), nullable=False),
        sa.Column('effective_date', sa.Date, nullable=False),
        sa.Column('from_position', sa.String(50), nullable=True),
        sa.Column('to_position', sa.String(50), nullable=True),
        sa.Column('from_store_id', sa.String(50), nullable=True),
        sa.Column('to_store_id', sa.String(50), nullable=True),
        sa.Column('from_salary_fen', sa.Integer, nullable=True),
        sa.Column('to_salary_fen', sa.Integer, nullable=True),
        sa.Column('resign_reason', sa.Text, nullable=True),
        sa.Column('last_work_date', sa.Date, nullable=True),
        sa.Column('handover_to', sa.String(50), nullable=True),
        sa.Column('handover_completed', sa.String(10), server_default='no'),
        sa.Column('approval_instance_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('approved_by', sa.String(100), nullable=True),
        sa.Column('remark', sa.Text, nullable=True),
        sa.Column('attachments', sa.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('ix_ec_store_id', 'employee_changes', ['store_id'])
    op.create_index('ix_ec_employee_id', 'employee_changes', ['employee_id'])
    op.create_index('ix_ec_change_type', 'employee_changes', ['change_type'])


def downgrade() -> None:
    # 按依赖倒序删除表
    op.drop_index('ix_ec_change_type', table_name='employee_changes')
    op.drop_index('ix_ec_employee_id', table_name='employee_changes')
    op.drop_index('ix_ec_store_id', table_name='employee_changes')
    op.drop_table('employee_changes')

    op.drop_index('ix_or_status', table_name='overtime_requests')
    op.drop_index('ix_or_employee_id', table_name='overtime_requests')
    op.drop_index('ix_or_store_id', table_name='overtime_requests')
    op.drop_table('overtime_requests')

    op.drop_index('ix_lr_status', table_name='leave_requests')
    op.drop_index('ix_lr_employee_id', table_name='leave_requests')
    op.drop_index('ix_lr_store_id', table_name='leave_requests')
    op.drop_table('leave_requests')

    op.drop_constraint('uq_leave_balance', 'leave_balances', type_='unique')
    op.drop_index('ix_lb_employee_id', table_name='leave_balances')
    op.drop_index('ix_lb_store_id', table_name='leave_balances')
    op.drop_table('leave_balances')

    op.drop_index('ix_ltc_brand_id', table_name='leave_type_configs')
    op.drop_index('ix_ltc_store_id', table_name='leave_type_configs')
    op.drop_table('leave_type_configs')

    op.drop_index('ix_anr_instance', table_name='approval_node_records')
    op.drop_table('approval_node_records')

    op.drop_index('ix_ai_applicant', table_name='approval_instances')
    op.drop_index('ix_ai_status', table_name='approval_instances')
    op.drop_index('ix_ai_type', table_name='approval_instances')
    op.drop_index('ix_ai_store_id', table_name='approval_instances')
    op.drop_table('approval_instances')

    op.drop_index('ix_aft_type', table_name='approval_flow_templates')
    op.drop_index('ix_aft_brand_id', table_name='approval_flow_templates')
    op.drop_index('ix_aft_store_id', table_name='approval_flow_templates')
    op.drop_table('approval_flow_templates')

    op.drop_constraint('uq_tax_month', 'tax_declarations', type_='unique')
    op.drop_index('ix_td_tax_month', table_name='tax_declarations')
    op.drop_index('ix_td_employee_id', table_name='tax_declarations')
    op.drop_index('ix_td_store_id', table_name='tax_declarations')
    op.drop_table('tax_declarations')

    op.drop_constraint('uq_payroll_month', 'payroll_records', type_='unique')
    op.drop_index('ix_pr_pay_month', table_name='payroll_records')
    op.drop_index('ix_pr_employee_id', table_name='payroll_records')
    op.drop_index('ix_pr_store_id', table_name='payroll_records')
    op.drop_table('payroll_records')

    op.drop_constraint('uq_salary_active', 'salary_structures', type_='unique')
    op.drop_index('ix_ss_employee_id', table_name='salary_structures')
    op.drop_index('ix_ss_store_id', table_name='salary_structures')
    op.drop_table('salary_structures')

    # Enum 类型
    op.execute("DROP TYPE IF EXISTS employee_change_type_enum")
    op.execute("DROP TYPE IF EXISTS overtime_request_status_enum")
    op.execute("DROP TYPE IF EXISTS overtime_type_enum")
    op.execute("DROP TYPE IF EXISTS leave_request_status_enum")
    op.execute("DROP TYPE IF EXISTS leave_category_enum")
    op.execute("DROP TYPE IF EXISTS approval_node_type_enum")
    op.execute("DROP TYPE IF EXISTS approval_status_enum")
    op.execute("DROP TYPE IF EXISTS approval_type_enum")
    op.execute("DROP TYPE IF EXISTS tax_declaration_status")
    op.execute("DROP TYPE IF EXISTS payroll_status")
    op.execute("DROP TYPE IF EXISTS salary_type")
