"""z56 FK迁移 — 4张表新增 assignment_id 列 + 回填

将 compliance_licenses / customer_ownerships / shifts / employee_metric_records
各自新增 assignment_id UUID NULL，通过 employee_id_map 桥接表回填。
M3 不删除旧 employee_id 列，M4 才做最终切割。

Revision ID: z56_fk_migration_to_assignment_id
Revises: z55_hr_knowledge_tables
Create Date: 2026-03-18
"""
import sqlalchemy as sa
from alembic import op

revision = "z56_fk_migration_to_assignment_id"
down_revision = "z55_hr_knowledge_tables"
branch_labels = None
depends_on = None

# (table_name, legacy_col_name)
_TABLES = [
    ("compliance_licenses", "holder_employee_id"),
    ("customer_ownerships", "owner_employee_id"),
    ("shifts", "employee_id"),
    ("employee_metric_records", "employee_id"),
]


def _column_exists(conn, table: str, column: str) -> bool:
    result = conn.execute(
        sa.text(
            "SELECT EXISTS ("
            "  SELECT 1 FROM information_schema.columns"
            "  WHERE table_schema='public'"
            "    AND table_name=:t AND column_name=:c"
            ")"
        ),
        {"t": table, "c": column},
    )
    return result.scalar()


def upgrade() -> None:
    conn = op.get_bind()

    for table, legacy_col in _TABLES:
        if _column_exists(conn, table, "assignment_id"):
            continue

        conn.execute(sa.text(
            f"ALTER TABLE {table} ADD COLUMN assignment_id UUID NULL"
        ))

        conn.execute(sa.text(f"""
            UPDATE {table} t
            SET assignment_id = (
                SELECT ea.id
                FROM employee_id_map m
                JOIN employment_assignments ea ON ea.person_id = m.person_id
                WHERE m.legacy_employee_id = t.{legacy_col}
                  AND ea.status = 'active'
                ORDER BY ea.created_at DESC
                LIMIT 1
            )
            WHERE t.assignment_id IS NULL
        """))

        conn.execute(sa.text(
            f"CREATE INDEX IF NOT EXISTS ix_{table}_assignment_id"
            f" ON {table}(assignment_id)"
        ))


def downgrade() -> None:
    conn = op.get_bind()

    for table, _ in _TABLES:
        if not _column_exists(conn, table, "assignment_id"):
            continue
        conn.execute(sa.text(
            f"DROP INDEX IF EXISTS ix_{table}_assignment_id"
        ))
        conn.execute(sa.text(
            f"ALTER TABLE {table} DROP COLUMN assignment_id"
        ))
