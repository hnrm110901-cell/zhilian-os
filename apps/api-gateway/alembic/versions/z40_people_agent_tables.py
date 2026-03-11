"""z40_people_agent_tables

PeopleAgent — Phase 12B 人员智能体
排班优化 / 绩效评分 / 人力成本 / 考勤预警 / 人员配置

Revision ID: z40
Revises: z39
Create Date: 2026-03-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'z40'
down_revision = 'z39'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 枚举类型 ──────────────────────────────────────────────────────────────
    op.execute("CREATE TYPE people_agent_type_enum AS ENUM ('shift_optimizer','performance_score','labor_cost','attendance_warn','staffing_plan')")
    op.execute("CREATE TYPE people_shift_status_enum AS ENUM ('draft','published','active','completed','cancelled')")
    op.execute("CREATE TYPE people_performance_rating_enum AS ENUM ('outstanding','exceeds','meets','below','unsatisfactory')")
    op.execute("CREATE TYPE people_attendance_alert_type_enum AS ENUM ('late','absent','early_leave','overtime','understaffed')")
    op.execute("CREATE TYPE people_staffing_decision_status_enum AS ENUM ('pending','accepted','rejected')")

    # ── L1: people_shift_records ──────────────────────────────────────────────
    op.create_table(
        "people_shift_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("brand_id", sa.String(36), nullable=False),
        sa.Column("store_id", sa.String(36), nullable=False),
        sa.Column("shift_date", sa.Date, nullable=False),
        sa.Column("required_headcount", sa.Integer, nullable=False, server_default="0"),
        sa.Column("scheduled_headcount", sa.Integer, nullable=False, server_default="0"),
        sa.Column("coverage_rate", sa.Float, nullable=True),
        sa.Column("estimated_labor_cost_yuan", sa.Numeric(14, 2), nullable=True),
        sa.Column("labor_cost_per_revenue_pct", sa.Float, nullable=True),
        sa.Column("shift_assignments", postgresql.JSON, nullable=True),
        sa.Column("optimization_suggestions", postgresql.JSON, nullable=True),
        sa.Column("peak_hours", postgresql.JSON, nullable=True),
        sa.Column("status", postgresql.ENUM(name="people_shift_status_enum", create_type=False), nullable=False, server_default="draft"),
        sa.Column("ai_insight", sa.Text, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True, server_default="0.80"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_people_shift_brand_store_date", "people_shift_records", ["brand_id", "store_id", "shift_date"])

    # ── L2: people_performance_scores ────────────────────────────────────────
    op.create_table(
        "people_performance_scores",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("brand_id", sa.String(36), nullable=False),
        sa.Column("store_id", sa.String(36), nullable=False),
        sa.Column("employee_id", sa.String(36), nullable=False),
        sa.Column("employee_name", sa.String(100), nullable=True),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("kpi_scores", postgresql.JSON, nullable=True),
        sa.Column("overall_score", sa.Float, nullable=False),
        sa.Column("rating", postgresql.ENUM(name="people_performance_rating_enum", create_type=False), nullable=False),
        sa.Column("base_commission_yuan", sa.Numeric(12, 2), nullable=True),
        sa.Column("bonus_commission_yuan", sa.Numeric(12, 2), nullable=True, server_default="0"),
        sa.Column("total_commission_yuan", sa.Numeric(12, 2), nullable=True),
        sa.Column("improvement_areas", postgresql.JSON, nullable=True),
        sa.Column("ai_insight", sa.Text, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True, server_default="0.85"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_people_perf_brand_store_emp_period", "people_performance_scores", ["brand_id", "store_id", "employee_id", "period"])

    # ── L3: people_labor_cost_records ─────────────────────────────────────────
    op.create_table(
        "people_labor_cost_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("brand_id", sa.String(36), nullable=False),
        sa.Column("store_id", sa.String(36), nullable=False),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("total_labor_cost_yuan", sa.Numeric(14, 2), nullable=False),
        sa.Column("revenue_yuan", sa.Numeric(14, 2), nullable=True),
        sa.Column("labor_cost_ratio", sa.Float, nullable=True),
        sa.Column("target_labor_cost_ratio", sa.Float, nullable=True, server_default="0.28"),
        sa.Column("revenue_per_employee_yuan", sa.Numeric(12, 2), nullable=True),
        sa.Column("avg_headcount", sa.Float, nullable=True),
        sa.Column("overtime_hours", sa.Float, nullable=True, server_default="0"),
        sa.Column("overtime_cost_yuan", sa.Numeric(12, 2), nullable=True, server_default="0"),
        sa.Column("cost_breakdown", postgresql.JSON, nullable=True),
        sa.Column("optimization_potential_yuan", sa.Numeric(12, 2), nullable=True),
        sa.Column("ai_insight", sa.Text, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True, server_default="0.80"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_people_labor_brand_store_period", "people_labor_cost_records", ["brand_id", "store_id", "period"])

    # ── L4: people_attendance_alerts ─────────────────────────────────────────
    op.create_table(
        "people_attendance_alerts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("brand_id", sa.String(36), nullable=False),
        sa.Column("store_id", sa.String(36), nullable=False),
        sa.Column("employee_id", sa.String(36), nullable=True),
        sa.Column("employee_name", sa.String(100), nullable=True),
        sa.Column("alert_date", sa.Date, nullable=False),
        sa.Column("alert_type", postgresql.ENUM(name="people_attendance_alert_type_enum", create_type=False), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False, server_default="warning"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("estimated_impact_yuan", sa.Numeric(12, 2), nullable=True),
        sa.Column("recommended_action", sa.Text, nullable=True),
        sa.Column("is_resolved", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("resolved_at", sa.DateTime, nullable=True),
        sa.Column("ai_insight", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_people_alert_brand_store_date", "people_attendance_alerts", ["brand_id", "store_id", "alert_date"])

    # ── L5: people_staffing_decisions ────────────────────────────────────────
    op.create_table(
        "people_staffing_decisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("brand_id", sa.String(36), nullable=False),
        sa.Column("store_id", sa.String(36), nullable=False),
        sa.Column("decision_date", sa.Date, nullable=False),
        sa.Column("recommendations", postgresql.JSON, nullable=False),
        sa.Column("total_impact_yuan", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("priority", sa.String(10), nullable=False, server_default="p1"),
        sa.Column("status", postgresql.ENUM(name="people_staffing_decision_status_enum", create_type=False), nullable=False, server_default="pending"),
        sa.Column("accepted_at", sa.DateTime, nullable=True),
        sa.Column("current_headcount", sa.Integer, nullable=True),
        sa.Column("optimal_headcount", sa.Integer, nullable=True),
        sa.Column("headcount_gap", sa.Integer, nullable=True),
        sa.Column("ai_insight", sa.Text, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True, server_default="0.80"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_people_staffing_brand_store_date", "people_staffing_decisions", ["brand_id", "store_id", "decision_date"])

    # ── people_agent_logs ─────────────────────────────────────────────────────
    op.create_table(
        "people_agent_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("brand_id", sa.String(36), nullable=False),
        sa.Column("agent_type", postgresql.ENUM(name="people_agent_type_enum", create_type=False), nullable=False),
        sa.Column("input_params", postgresql.JSON, nullable=True),
        sa.Column("output_summary", postgresql.JSON, nullable=True),
        sa.Column("impact_yuan", sa.Numeric(14, 2), nullable=True, server_default="0"),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("success", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_people_log_brand_created", "people_agent_logs", ["brand_id", "created_at"])


def downgrade() -> None:
    op.drop_table("people_agent_logs")
    op.drop_table("people_staffing_decisions")
    op.drop_table("people_attendance_alerts")
    op.drop_table("people_labor_cost_records")
    op.drop_table("people_performance_scores")
    op.drop_table("people_shift_records")

    op.execute("DROP TYPE IF EXISTS people_staffing_decision_status_enum")
    op.execute("DROP TYPE IF EXISTS people_attendance_alert_type_enum")
    op.execute("DROP TYPE IF EXISTS people_performance_rating_enum")
    op.execute("DROP TYPE IF EXISTS people_shift_status_enum")
    op.execute("DROP TYPE IF EXISTS people_agent_type_enum")
