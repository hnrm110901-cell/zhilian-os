"""
HR03: 提成、奖惩、社保配置表 + 员工扩展字段

新建表:
  - commission_rules          提成规则
  - commission_records        提成记录
  - reward_penalty_records    奖惩记录
  - social_insurance_configs  区域社保费率配置
  - employee_social_insurances 员工参保方案

变更表:
  - employees: +employment_status, +wechat_userid, +probation_end_date
  - payroll_records: +commission_fen, +reward_fen, +penalty_fen
  - employee_changes: change_type enum 添加 'trial'

Revision ID: hr03
Revises: hr02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

revision = 'hr03'
down_revision = 'hr02'
branch_labels = None
depends_on = None


def _create_enum_safe(name, values):
    """安全创建 PostgreSQL ENUM（已存在则跳过）"""
    from sqlalchemy import text
    conn = op.get_bind()
    result = conn.execute(
        text("SELECT 1 FROM pg_type WHERE typname = :name"),
        {"name": name},
    )
    if result.fetchone() is None:
        enum_type = sa.Enum(*values, name=name)
        enum_type.create(conn)


def upgrade():
    # ── ENUM 类型 ──
    _create_enum_safe("commission_type_enum", [
        "sales_amount", "dish_count", "service_fee", "membership", "custom",
    ])
    _create_enum_safe("commission_calc_method_enum", [
        "fixed_per_unit", "percentage", "tiered",
    ])
    _create_enum_safe("reward_penalty_type_enum", [
        "reward", "penalty",
    ])
    _create_enum_safe("reward_penalty_category_enum", [
        "service_excellence", "sales_champion", "zero_waste", "innovation",
        "attendance_perfect", "team_contribution", "customer_praise",
        "food_safety", "hygiene", "discipline", "customer_complaint",
        "equipment_damage", "waste_excess", "other",
    ])
    _create_enum_safe("reward_penalty_status_enum", [
        "pending", "approved", "rejected", "cancelled",
    ])

    # ── 1. commission_rules ──
    op.create_table(
        "commission_rules",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("store_id", sa.String(50), nullable=False, index=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("commission_type", sa.Enum(
            "sales_amount", "dish_count", "service_fee", "membership", "custom",
            name="commission_type_enum", create_type=False,
        ), nullable=False),
        sa.Column("calc_method", sa.Enum(
            "fixed_per_unit", "percentage", "tiered",
            name="commission_calc_method_enum", create_type=False,
        ), nullable=False),
        sa.Column("applicable_positions", JSON, nullable=True),
        sa.Column("applicable_employee_ids", JSON, nullable=True),
        sa.Column("fixed_amount_fen", sa.Integer, default=0),
        sa.Column("rate_pct", sa.Numeric(6, 3), default=0),
        sa.Column("tiered_rules", JSON, nullable=True),
        sa.Column("target_dish_ids", JSON, nullable=True),
        sa.Column("target_categories", JSON, nullable=True),
        sa.Column("is_active", sa.Boolean, default=True, nullable=False),
        sa.Column("effective_date", sa.Date, nullable=False),
        sa.Column("expire_date", sa.Date, nullable=True),
        sa.Column("remark", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    # ── 2. commission_records ──
    op.create_table(
        "commission_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("store_id", sa.String(50), nullable=False, index=True),
        sa.Column("employee_id", sa.String(50), sa.ForeignKey("employees.id"), nullable=False, index=True),
        sa.Column("pay_month", sa.String(7), nullable=False, index=True),
        sa.Column("rule_id", UUID(as_uuid=True), sa.ForeignKey("commission_rules.id"), nullable=False),
        sa.Column("base_amount_fen", sa.Integer, default=0),
        sa.Column("base_quantity", sa.Integer, default=0),
        sa.Column("commission_fen", sa.Integer, nullable=False, default=0),
        sa.Column("calculation_detail", JSON, nullable=True),
        sa.Column("remark", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("employee_id", "pay_month", "rule_id", name="uq_commission_month_rule"),
    )

    # ── 3. reward_penalty_records ──
    op.create_table(
        "reward_penalty_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("store_id", sa.String(50), nullable=False, index=True),
        sa.Column("employee_id", sa.String(50), sa.ForeignKey("employees.id"), nullable=False, index=True),
        sa.Column("rp_type", sa.Enum(
            "reward", "penalty",
            name="reward_penalty_type_enum", create_type=False,
        ), nullable=False),
        sa.Column("category", sa.Enum(
            "service_excellence", "sales_champion", "zero_waste", "innovation",
            "attendance_perfect", "team_contribution", "customer_praise",
            "food_safety", "hygiene", "discipline", "customer_complaint",
            "equipment_damage", "waste_excess", "other",
            name="reward_penalty_category_enum", create_type=False,
        ), nullable=False),
        sa.Column("status", sa.Enum(
            "pending", "approved", "rejected", "cancelled",
            name="reward_penalty_status_enum", create_type=False,
        ), nullable=False, server_default="pending"),
        sa.Column("amount_fen", sa.Integer, nullable=False, default=0),
        sa.Column("pay_month", sa.String(7), nullable=True, index=True),
        sa.Column("incident_date", sa.Date, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("evidence", JSON, nullable=True),
        sa.Column("submitted_by", sa.String(100), nullable=True),
        sa.Column("approved_by", sa.String(100), nullable=True),
        sa.Column("approved_at", sa.Date, nullable=True),
        sa.Column("reject_reason", sa.Text, nullable=True),
        sa.Column("remark", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    # ── 4. social_insurance_configs ──
    op.create_table(
        "social_insurance_configs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("region_code", sa.String(20), nullable=False, index=True),
        sa.Column("region_name", sa.String(50), nullable=False),
        sa.Column("effective_year", sa.Integer, nullable=False),
        sa.Column("base_floor_fen", sa.Integer, nullable=False, default=0),
        sa.Column("base_ceiling_fen", sa.Integer, nullable=False, default=0),
        # 五险费率
        sa.Column("pension_employer_pct", sa.Numeric(5, 2), default=16.0),
        sa.Column("pension_employee_pct", sa.Numeric(5, 2), default=8.0),
        sa.Column("medical_employer_pct", sa.Numeric(5, 2), default=8.0),
        sa.Column("medical_employee_pct", sa.Numeric(5, 2), default=2.0),
        sa.Column("unemployment_employer_pct", sa.Numeric(5, 2), default=0.7),
        sa.Column("unemployment_employee_pct", sa.Numeric(5, 2), default=0.3),
        sa.Column("injury_employer_pct", sa.Numeric(5, 2), default=0.4),
        sa.Column("maternity_employer_pct", sa.Numeric(5, 2), default=0.0),
        # 公积金
        sa.Column("housing_fund_employer_pct", sa.Numeric(5, 2), default=8.0),
        sa.Column("housing_fund_employee_pct", sa.Numeric(5, 2), default=8.0),
        sa.Column("is_active", sa.Boolean, default=True, nullable=False),
        sa.Column("remark", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("region_code", "effective_year", name="uq_si_region_year"),
    )

    # ── 5. employee_social_insurances ──
    op.create_table(
        "employee_social_insurances",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("store_id", sa.String(50), nullable=False, index=True),
        sa.Column("employee_id", sa.String(50), sa.ForeignKey("employees.id"), nullable=False, index=True),
        sa.Column("config_id", UUID(as_uuid=True), sa.ForeignKey("social_insurance_configs.id"), nullable=False),
        sa.Column("effective_year", sa.Integer, nullable=False),
        sa.Column("personal_base_fen", sa.Integer, nullable=False, default=0),
        sa.Column("has_pension", sa.Boolean, default=True),
        sa.Column("has_medical", sa.Boolean, default=True),
        sa.Column("has_unemployment", sa.Boolean, default=True),
        sa.Column("has_injury", sa.Boolean, default=True),
        sa.Column("has_maternity", sa.Boolean, default=True),
        sa.Column("has_housing_fund", sa.Boolean, default=True),
        sa.Column("housing_fund_pct_override", sa.Numeric(5, 2), nullable=True),
        sa.Column("is_active", sa.Boolean, default=True, nullable=False),
        sa.Column("remark", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("employee_id", "effective_year", name="uq_emp_si_year"),
    )

    # ── 6. employees 表扩展字段 ──
    op.add_column("employees", sa.Column("employment_status", sa.String(20), server_default="regular"))
    op.add_column("employees", sa.Column("wechat_userid", sa.String(100), nullable=True))
    op.add_column("employees", sa.Column("probation_end_date", sa.Date, nullable=True))
    op.create_index("ix_employees_wechat_userid", "employees", ["wechat_userid"])

    # ── 7. payroll_records 表扩展字段 ──
    op.add_column("payroll_records", sa.Column("commission_fen", sa.Integer, server_default="0", nullable=False))
    op.add_column("payroll_records", sa.Column("reward_fen", sa.Integer, server_default="0", nullable=False))
    op.add_column("payroll_records", sa.Column("penalty_fen", sa.Integer, server_default="0", nullable=False))

    # ── 8. employee_changes change_type enum 添加 'trial' ──
    op.execute("ALTER TYPE employee_change_type_enum ADD VALUE IF NOT EXISTS 'trial'")


def downgrade():
    # payroll_records 字段
    op.drop_column("payroll_records", "penalty_fen")
    op.drop_column("payroll_records", "reward_fen")
    op.drop_column("payroll_records", "commission_fen")

    # employees 字段
    op.drop_index("ix_employees_wechat_userid", "employees")
    op.drop_column("employees", "probation_end_date")
    op.drop_column("employees", "wechat_userid")
    op.drop_column("employees", "employment_status")

    # 新建表
    op.drop_table("employee_social_insurances")
    op.drop_table("social_insurance_configs")
    op.drop_table("reward_penalty_records")
    op.drop_table("commission_records")
    op.drop_table("commission_rules")
