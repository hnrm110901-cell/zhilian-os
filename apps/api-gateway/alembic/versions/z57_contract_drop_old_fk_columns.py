"""z57 — Contract phase: add NOT NULL, drop old employee_id cols, drop employee_id_map.

Expand → Migrate → Contract — this is the Contract step.

Pre-requisite: z56 has already added assignment_id UUID NULL and backfilled via
employee_id_map. This migration:
  1. Validates zero NULL assignment_id rows remain in all 4 tables.
  2. Adds NOT NULL constraint to assignment_id in all 4 tables.
  3. Drops the legacy employee_id / holder_employee_id / owner_employee_id columns.
  4. Drops the employee_id_map bridge table (no longer needed).
"""
import sqlalchemy as sa
from alembic import op

revision = "z57_contract_drop_old_fk_columns"
down_revision = "z56_fk_migration_to_assignment_id"
branch_labels = None
depends_on = None

# Table names are hardcoded internal constants — not user input.
# f-string interpolation here is safe (DDL table/column names cannot be parameterized).
_TABLES = [
    ("compliance_licenses",     "holder_employee_id"),
    ("customer_ownerships",     "owner_employee_id"),
    ("shifts",                  "employee_id"),
    ("employee_metric_records", "employee_id"),
]


def upgrade() -> None:
    conn = op.get_bind()

    # Step 1: Validate — abort if any NULL assignment_id rows remain
    for table, _ in _TABLES:
        null_count = conn.execute(
            sa.text(f"SELECT COUNT(*) FROM {table} WHERE assignment_id IS NULL")
        ).scalar()
        if null_count:
            raise RuntimeError(
                f"NULL assignment_id found in {table} ({null_count} rows). "
                "Run z56 backfill manually before re-running this migration."
            )

    # Step 2: Set NOT NULL constraint on assignment_id
    for table, _ in _TABLES:
        conn.execute(
            sa.text(
                f"ALTER TABLE {table} "
                f"ALTER COLUMN assignment_id SET NOT NULL"
            )
        )

    # Step 3: Drop old legacy employee_id columns
    for table, legacy_col in _TABLES:
        conn.execute(
            sa.text(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {legacy_col}")
        )

    # Step 4: Drop employee_id_map bridge table (no longer needed post-Contract)
    conn.execute(
        sa.text("DROP TABLE IF EXISTS employee_id_map CASCADE")
    )


def downgrade() -> None:
    conn = op.get_bind()

    # Recreate employee_id_map bridge table
    conn.execute(
        sa.text(
            "CREATE TABLE IF NOT EXISTS employee_id_map ("
            "  legacy_employee_id VARCHAR(50) PRIMARY KEY, "
            "  person_id          UUID NOT NULL, "
            "  assignment_id      UUID NOT NULL"
            ")"
        )
    )

    # Restore old columns (nullable — data is gone, DBA must re-backfill)
    restore_map = [
        ("compliance_licenses",     "holder_employee_id", "VARCHAR(50)"),
        ("customer_ownerships",     "owner_employee_id",  "VARCHAR(50)"),
        ("shifts",                  "employee_id",        "VARCHAR(50)"),
        ("employee_metric_records", "employee_id",        "VARCHAR(50)"),
    ]
    for table, col, col_type in restore_map:
        conn.execute(
            sa.text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {col_type} NULL")
        )

    # Remove NOT NULL from assignment_id
    for table, _ in _TABLES:
        conn.execute(
            sa.text(
                f"ALTER TABLE {table} "
                f"ALTER COLUMN assignment_id DROP NOT NULL"
            )
        )
