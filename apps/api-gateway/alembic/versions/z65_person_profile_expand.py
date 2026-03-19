"""z65 — Person 档案字段扩展 + EmploymentAssignment 补充就业字段

Sprint 2：补齐 Person 个人档案属性（性别、健康证、银行卡、profile_ext JSONB 等），
以及 EmploymentAssignment 就业属性（日薪标准、工时类型、职级），
使所有 Employee 依赖均可迁移到三层模型。

新增 Person 列（12列）：
  gender, birth_date, health_cert_expiry, health_cert_attachment, id_card_expiry,
  bank_name, bank_account, bank_branch, background_check, accommodation,
  union_member, profile_ext

新增 EmploymentAssignment 列（3列）：
  daily_wage_standard_fen, work_hour_type, grade_level

包含数据回填：从 employees 表通过 legacy_employee_id 复制档案字段到 persons。

Revision ID: z65_person_profile_expand
Revises: z64_person_im_fields
Create Date: 2026-03-19
"""
import sqlalchemy as sa
from alembic import op


revision = "z65_person_profile_expand"
down_revision = "z64_person_im_fields"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    """幂等检查：列是否已存在"""
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :table AND column_name = :column"
        ),
        {"table": table, "column": column},
    )
    return result.scalar() is not None


def upgrade() -> None:
    # ── Person 档案字段 ──────────────────────────────────────

    person_columns = [
        ("gender", sa.String(10)),
        ("birth_date", sa.Date()),
        ("health_cert_expiry", sa.Date()),
        ("health_cert_attachment", sa.String(500)),
        ("id_card_expiry", sa.Date()),
        ("bank_name", sa.String(100)),
        ("bank_account", sa.String(50)),
        ("bank_branch", sa.String(200)),
        ("background_check", sa.String(100)),
        ("accommodation", sa.String(200)),
    ]

    for col_name, col_type in person_columns:
        if not _column_exists("persons", col_name):
            op.add_column("persons", sa.Column(col_name, col_type, nullable=True))

    if not _column_exists("persons", "union_member"):
        op.add_column(
            "persons",
            sa.Column("union_member", sa.Boolean(), nullable=True, server_default="false"),
        )

    if not _column_exists("persons", "profile_ext"):
        op.add_column(
            "persons",
            sa.Column(
                "profile_ext",
                sa.dialects.postgresql.JSONB(),
                nullable=True,
                server_default="'{}'",
            ),
        )

    # health_cert_expiry 需要索引（合规告警按到期日扫描）
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_persons_health_cert_expiry "
            "ON persons (health_cert_expiry) WHERE health_cert_expiry IS NOT NULL"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_persons_id_card_expiry "
            "ON persons (id_card_expiry) WHERE id_card_expiry IS NOT NULL"
        )
    )

    # ── EmploymentAssignment 就业字段 ────────────────────────

    if not _column_exists("employment_assignments", "daily_wage_standard_fen"):
        op.add_column(
            "employment_assignments",
            sa.Column("daily_wage_standard_fen", sa.Integer(), nullable=True,
                      comment="日薪标准（分），用于小时工/灵活用工薪资计算"),
        )

    if not _column_exists("employment_assignments", "work_hour_type"):
        op.add_column(
            "employment_assignments",
            sa.Column("work_hour_type", sa.String(30), nullable=True,
                      comment="工时类型：standard/flexible/shift"),
        )

    if not _column_exists("employment_assignments", "grade_level"):
        op.add_column(
            "employment_assignments",
            sa.Column("grade_level", sa.String(30), nullable=True,
                      comment="职级"),
        )

    # ── 数据回填：从 employees 复制档案字段到 persons ─────────

    # 仅当 employees 表存在时回填（测试环境可能无此表）
    conn = op.get_bind()
    emp_exists = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'employees' AND table_schema = 'public'"
        )
    ).scalar()

    if emp_exists:
        # 回填 Person 档案字段
        op.execute(
            sa.text("""
                UPDATE persons p
                SET
                    gender              = e.gender,
                    birth_date          = e.birth_date,
                    health_cert_expiry  = e.health_cert_expiry,
                    health_cert_attachment = e.health_cert_attachment,
                    id_card_expiry      = e.id_card_expiry,
                    bank_name           = e.bank_name,
                    bank_account        = e.bank_account,
                    bank_branch         = e.bank_branch,
                    background_check    = e.background_check,
                    accommodation       = e.accommodation,
                    union_member        = COALESCE(e.union_member, FALSE),
                    profile_ext         = jsonb_build_object(
                        'education',         COALESCE(e.education, ''),
                        'graduation_school', COALESCE(e.graduation_school, ''),
                        'major',             COALESCE(e.major, ''),
                        'professional_cert', COALESCE(e.professional_cert, ''),
                        'marital_status',    COALESCE(e.marital_status, ''),
                        'ethnicity',         COALESCE(e.ethnicity, ''),
                        'hukou_type',        COALESCE(e.hukou_type, ''),
                        'hukou_location',    COALESCE(e.hukou_location, ''),
                        'political_status',  COALESCE(e.political_status, ''),
                        'height_cm',         COALESCE(e.height_cm, 0),
                        'weight_kg',         COALESCE(e.weight_kg, 0),
                        'regular_date',      COALESCE(CAST(e.regular_date AS TEXT), ''),
                        'emergency_phone',   COALESCE(e.emergency_phone, ''),
                        'emergency_relation', COALESCE(e.emergency_relation, ''),
                        'emergency_contact_name', COALESCE(e.emergency_contact, '')
                    )
                FROM employees e
                WHERE p.legacy_employee_id = e.id
                  AND p.gender IS NULL
            """)
        )

        # 回填 EmploymentAssignment 就业字段
        op.execute(
            sa.text("""
                UPDATE employment_assignments ea
                SET
                    daily_wage_standard_fen = e.daily_wage_standard_fen,
                    work_hour_type          = e.work_hour_type,
                    grade_level             = e.grade_level
                FROM persons p
                JOIN employees e ON p.legacy_employee_id = e.id
                WHERE ea.person_id = p.id
                  AND ea.daily_wage_standard_fen IS NULL
            """)
        )


def downgrade() -> None:
    # EmploymentAssignment 列
    for col in ("grade_level", "work_hour_type", "daily_wage_standard_fen"):
        if _column_exists("employment_assignments", col):
            op.drop_column("employment_assignments", col)

    # Person 索引
    op.execute(sa.text("DROP INDEX IF EXISTS ix_persons_health_cert_expiry"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_persons_id_card_expiry"))

    # Person 列
    person_cols = [
        "profile_ext", "union_member", "accommodation", "background_check",
        "bank_branch", "bank_account", "bank_name", "id_card_expiry",
        "health_cert_attachment", "health_cert_expiry", "birth_date", "gender",
    ]
    for col in person_cols:
        if _column_exists("persons", col):
            op.drop_column("persons", col)
