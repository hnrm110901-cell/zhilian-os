"""岗位标准化知识库 + 员工成长模块 — 4张新表

创建以下表：
  job_standards          — 连锁餐饮岗位标准（行业本体）
  job_sops               — 岗位SOP操作步骤
  employee_job_bindings  — 员工岗位绑定关系
  employee_growth_traces — 员工成长溯源时间轴

Revision ID: z51_job_standard_module
Revises: z50_daily_ops_module
Create Date: 2026-03-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "z51_job_standard_module"
down_revision = "z50_daily_ops_module"
branch_labels = None
depends_on = None


def _table_exists(conn, table_name: str) -> bool:
    result = conn.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name=:t)"
        ),
        {"t": table_name},
    )
    return result.scalar()


def upgrade():
    conn = op.get_bind()

    # ─────────────────────────────────────────────────────────────
    # 1. job_standards
    # ─────────────────────────────────────────────────────────────
    if not _table_exists(conn, "job_standards"):
        op.create_table(
            "job_standards",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("job_code", sa.String(64), nullable=False),
            sa.Column("job_name", sa.String(128), nullable=False),
            sa.Column("job_level", sa.String(32), nullable=False),
            sa.Column("job_category", sa.String(64), nullable=False),
            sa.Column("report_to_role", sa.String(256)),
            sa.Column("manages_roles", sa.String(256)),
            sa.Column("job_objective", sa.Text),
            sa.Column("responsibilities", JSONB),
            sa.Column("daily_tasks", JSONB),
            sa.Column("weekly_tasks", JSONB),
            sa.Column("monthly_tasks", JSONB),
            sa.Column("kpi_targets", JSONB),
            sa.Column("experience_years_min", sa.Integer, server_default="0"),
            sa.Column("education_requirement", sa.String(64)),
            sa.Column("skill_requirements", JSONB),
            sa.Column("common_issues", JSONB),
            sa.Column("industry_category", sa.String(64), server_default="通用"),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
            sa.Column("sort_order", sa.Integer, server_default="0"),
            sa.Column("created_by", sa.String(64), server_default="system"),
            sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.text("now()")),
        )
        op.create_index("ix_job_standards_job_code", "job_standards", ["job_code"], unique=True)

    # ─────────────────────────────────────────────────────────────
    # 2. job_sops
    # ─────────────────────────────────────────────────────────────
    if not _table_exists(conn, "job_sops"):
        op.create_table(
            "job_sops",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "job_standard_id",
                UUID(as_uuid=True),
                sa.ForeignKey("job_standards.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("sop_type", sa.String(32), nullable=False),
            sa.Column("sop_name", sa.String(128), nullable=False),
            sa.Column("steps", JSONB, nullable=False),
            sa.Column("duration_minutes", sa.Integer),
            sa.Column("responsible_role", sa.String(64)),
            sa.Column("sort_order", sa.Integer, server_default="0"),
            sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.text("now()")),
        )
        op.create_index("ix_job_sops_job_standard_id", "job_sops", ["job_standard_id"])

    # ─────────────────────────────────────────────────────────────
    # 3. employee_job_bindings
    # ─────────────────────────────────────────────────────────────
    if not _table_exists(conn, "employee_job_bindings"):
        op.create_table(
            "employee_job_bindings",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("employee_id", sa.String(64), nullable=False),
            sa.Column("employee_name", sa.String(128)),
            sa.Column("store_id", sa.String(64), nullable=False),
            sa.Column(
                "job_standard_id",
                UUID(as_uuid=True),
                sa.ForeignKey("job_standards.id"),
                nullable=False,
            ),
            sa.Column("job_code", sa.String(64), nullable=False),
            sa.Column("job_name", sa.String(128)),
            sa.Column("bound_at", sa.DateTime, nullable=False),
            sa.Column("unbound_at", sa.DateTime),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
            sa.Column("bound_by", sa.String(64)),
            sa.Column("notes", sa.Text),
            sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.text("now()")),
        )
        op.create_index("ix_employee_job_bindings_employee_id", "employee_job_bindings", ["employee_id"])
        op.create_index("ix_employee_job_bindings_store_id", "employee_job_bindings", ["store_id"])

    # ─────────────────────────────────────────────────────────────
    # 4. employee_growth_traces
    # ─────────────────────────────────────────────────────────────
    if not _table_exists(conn, "employee_growth_traces"):
        op.create_table(
            "employee_growth_traces",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("employee_id", sa.String(64), nullable=False),
            sa.Column("employee_name", sa.String(128)),
            sa.Column("store_id", sa.String(64)),
            sa.Column("trace_type", sa.String(32), nullable=False),
            sa.Column("trace_date", sa.Date, nullable=False),
            sa.Column("event_title", sa.String(256), nullable=False),
            sa.Column("event_detail", sa.Text),
            sa.Column("from_job_code", sa.String(64)),
            sa.Column("from_job_name", sa.String(128)),
            sa.Column("to_job_code", sa.String(64)),
            sa.Column("to_job_name", sa.String(128)),
            sa.Column("kpi_snapshot", JSONB),
            sa.Column("assessment_score", sa.Integer),
            sa.Column("assessor_id", sa.String(64)),
            sa.Column("attachments", JSONB),
            sa.Column("is_milestone", sa.Boolean, server_default="false"),
            sa.Column("created_by", sa.String(64)),
            sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.text("now()")),
        )
        op.create_index("ix_employee_growth_traces_employee_id", "employee_growth_traces", ["employee_id"])
        op.create_index("ix_employee_growth_traces_store_id", "employee_growth_traces", ["store_id"])
        op.create_index("ix_employee_growth_traces_trace_type", "employee_growth_traces", ["trace_type"])
        op.create_index("ix_employee_growth_traces_trace_date", "employee_growth_traces", ["trace_date"])


def downgrade():
    conn = op.get_bind()
    # 逆序删除（先删依赖表）
    if _table_exists(conn, "employee_growth_traces"):
        op.drop_table("employee_growth_traces")
    if _table_exists(conn, "employee_job_bindings"):
        op.drop_table("employee_job_bindings")
    if _table_exists(conn, "job_sops"):
        op.drop_table("job_sops")
    if _table_exists(conn, "job_standards"):
        op.drop_table("job_standards")
