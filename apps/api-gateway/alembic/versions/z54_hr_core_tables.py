"""HR核心人员表 — 替换 Employee 模型的底层数据结构

创建以下表：
  persons                — 全局人员档案（跨门店唯一身份）
  employment_assignments — 在岗关系（人员 × 门店节点 × 岗位）
  employment_contracts   — 用工合同（薪酬方案 + 考勤规则）
  employee_id_map        — 迁移桥接表（旧String PK → 新UUID，临时，M4删除）
  attendance_rules       — 考勤规则配置（employment_contracts依赖）
  kpi_templates          — KPI模板配置（employment_contracts依赖）

Revision ID: z54_hr_core_tables
Revises: z53
Create Date: 2026-03-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "z54_hr_core_tables"
down_revision = "z53"
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


def upgrade() -> None:
    conn = op.get_bind()

    if not _table_exists(conn, "attendance_rules"):
        op.create_table(
            "attendance_rules",
            sa.Column("id", UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text("gen_random_uuid()")),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("rule_config", JSONB, nullable=False, server_default="{}"),
            sa.Column("org_node_id", sa.String(64), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                      server_default=sa.text("NOW()"), nullable=False),
        )

    if not _table_exists(conn, "kpi_templates"):
        op.create_table(
            "kpi_templates",
            sa.Column("id", UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text("gen_random_uuid()")),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("template_config", JSONB, nullable=False, server_default="{}"),
            sa.Column("org_node_id", sa.String(64), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                      server_default=sa.text("NOW()"), nullable=False),
        )

    if not _table_exists(conn, "persons"):
        op.create_table(
            "persons",
            sa.Column("id", UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text("gen_random_uuid()")),
            sa.Column("legacy_employee_id", sa.String(50), nullable=True, index=True,
                      comment="迁移桥接：原employees.id（如EMP001），M4后删除"),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("id_number", sa.String(18), nullable=True,
                      comment="身份证号，应用层加密后存储"),
            sa.Column("phone", sa.String(20), nullable=True),
            sa.Column("email", sa.String(200), nullable=True),
            sa.Column("photo_url", sa.String(500), nullable=True),
            sa.Column("preferences", JSONB, nullable=True, server_default="{}"),
            sa.Column("emergency_contact", JSONB, nullable=True, server_default="{}"),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                      server_default=sa.text("NOW()"), nullable=False),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True),
                      server_default=sa.text("NOW()"), nullable=False),
        )

    if not _table_exists(conn, "employment_assignments"):
        op.create_table(
            "employment_assignments",
            sa.Column("id", UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text("gen_random_uuid()")),
            sa.Column("person_id", UUID(as_uuid=True),
                      sa.ForeignKey("persons.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("org_node_id", sa.String(64),
                      sa.ForeignKey("org_nodes.id", ondelete="RESTRICT"),
                      nullable=False, index=True),
            sa.Column("job_standard_id", UUID(as_uuid=True), nullable=True,
                      comment="引用job_standards.id，无强FK约束（跨模块）"),
            sa.Column("employment_type", sa.String(30), nullable=False,
                      comment="full_time / hourly / outsourced / dispatched / partner"),
            sa.Column("start_date", sa.Date, nullable=False),
            sa.Column("end_date", sa.Date, nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="'active'",
                      comment="active / ended / suspended"),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                      server_default=sa.text("NOW()"), nullable=False),
        )
        op.create_index(
            "idx_employment_assignments_active",
            "employment_assignments",
            ["org_node_id", "status"],
        )

    if not _table_exists(conn, "employment_contracts"):
        op.create_table(
            "employment_contracts",
            sa.Column("id", UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text("gen_random_uuid()")),
            sa.Column("assignment_id", UUID(as_uuid=True),
                      sa.ForeignKey("employment_assignments.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("contract_type", sa.String(30), nullable=False,
                      comment="labor / hourly / outsource / dispatch / partnership"),
            sa.Column("pay_scheme", JSONB, nullable=False, server_default="{}"),
            sa.Column("attendance_rule_id", UUID(as_uuid=True),
                      sa.ForeignKey("attendance_rules.id", ondelete="SET NULL"),
                      nullable=True),
            sa.Column("kpi_template_id", UUID(as_uuid=True),
                      sa.ForeignKey("kpi_templates.id", ondelete="SET NULL"),
                      nullable=True),
            sa.Column("valid_from", sa.Date, nullable=False),
            sa.Column("valid_to", sa.Date, nullable=True),
            sa.Column("signed_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("file_url", sa.String(500), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                      server_default=sa.text("NOW()"), nullable=False),
        )

    if not _table_exists(conn, "employee_id_map"):
        op.create_table(
            "employee_id_map",
            sa.Column("legacy_employee_id", sa.String(50), primary_key=True,
                      comment="原employees.id值，如EMP001"),
            sa.Column("person_id", UUID(as_uuid=True),
                      sa.ForeignKey("persons.id", ondelete="CASCADE"),
                      nullable=False),
            sa.Column("assignment_id", UUID(as_uuid=True),
                      sa.ForeignKey("employment_assignments.id", ondelete="CASCADE"),
                      nullable=False),
        )
        op.create_index("idx_employee_id_map_person", "employee_id_map", ["person_id"])
        op.create_index("idx_employee_id_map_assignment", "employee_id_map", ["assignment_id"])


def downgrade() -> None:
    conn = op.get_bind()
    for table in [
        "employee_id_map", "employment_contracts", "employment_assignments",
        "persons", "kpi_templates", "attendance_rules",
    ]:
        if _table_exists(conn, table):
            op.drop_table(table)
