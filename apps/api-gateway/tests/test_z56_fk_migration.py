"""Tests for z56 FK migration to assignment_id.

Since CI has no PostgreSQL, we mock schema inspection and verify
the migration SQL logic using string inspection and mock patterns.
"""
import os
import pytest
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/test")
os.environ.setdefault("APP_ENV", "test")


TARGET_TABLES = [
    "compliance_licenses",
    "customer_ownerships",
    "shifts",
    "employee_metric_records",
]


def test_revision_metadata():
    """Migration file has correct revision and down_revision."""
    from alembic.versions.z56_fk_migration_to_assignment_id import (
        revision,
        down_revision,
    )
    assert revision == "z56_fk_migration_to_assignment_id"
    assert down_revision == "z55_hr_knowledge_tables"


def test_upgrade_adds_column_for_all_tables():
    """upgrade() executes SQL touching each of the 4 target tables."""
    with patch("alembic.op.execute") as mock_exec, \
         patch("alembic.op.get_bind") as mock_bind:
        conn = MagicMock()
        conn.execute.return_value.scalar.return_value = False
        mock_bind.return_value = conn

        from alembic.versions.z56_fk_migration_to_assignment_id import upgrade
        upgrade()

    executed_sqls = [str(c.args[0]) for c in conn.execute.call_args_list]
    for table in TARGET_TABLES:
        found = any(table in sql for sql in executed_sqls)
        assert found, f"No SQL executed for table {table}"


def test_upgrade_skips_existing_column():
    """upgrade() skips ADD COLUMN when assignment_id already exists (idempotent)."""
    with patch("alembic.op.execute") as mock_exec, \
         patch("alembic.op.get_bind") as mock_bind:
        conn = MagicMock()
        conn.execute.return_value.scalar.return_value = True  # column already exists
        mock_bind.return_value = conn

        from alembic.versions.z56_fk_migration_to_assignment_id import upgrade
        upgrade()

    mock_exec.assert_not_called()


def test_upgrade_runs_backfill_update():
    """upgrade() runs UPDATE referencing employee_id_map for each table."""
    with patch("alembic.op.execute") as mock_exec, \
         patch("alembic.op.get_bind") as mock_bind:
        conn = MagicMock()
        conn.execute.return_value.scalar.return_value = False
        mock_bind.return_value = conn

        from alembic.versions.z56_fk_migration_to_assignment_id import upgrade
        upgrade()

    all_sqls = " ".join(str(c.args[0]) for c in conn.execute.call_args_list)
    assert "employee_id_map" in all_sqls
    assert "assignment_id" in all_sqls


def test_downgrade_drops_column_for_all_tables():
    """downgrade() drops assignment_id from all 4 tables."""
    with patch("alembic.op.execute") as mock_exec, \
         patch("alembic.op.get_bind") as mock_bind:
        conn = MagicMock()
        conn.execute.return_value.scalar.return_value = True  # column exists
        mock_bind.return_value = conn

        from alembic.versions.z56_fk_migration_to_assignment_id import downgrade
        downgrade()

    executed_sqls = [str(c.args[0]) for c in conn.execute.call_args_list]
    for table in TARGET_TABLES:
        found = any(table in sql for sql in executed_sqls)
        assert found, f"downgrade() missing for {table}"


def test_no_not_null_constraint():
    """Migration does NOT add NOT NULL (M4 concern only)."""
    with patch("alembic.op.execute") as mock_exec, \
         patch("alembic.op.get_bind") as mock_bind:
        conn = MagicMock()
        conn.execute.return_value.scalar.return_value = False
        mock_bind.return_value = conn

        from alembic.versions.z56_fk_migration_to_assignment_id import upgrade
        upgrade()

    all_sqls = " ".join(str(c.args[0]) for c in conn.execute.call_args_list)
    assert "NOT NULL" not in all_sqls.upper()
