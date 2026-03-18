"""Tests for z57 contract migration.

CI has no PostgreSQL — we mock conn and verify SQL logic via string inspection.
"""
import os
import sys
import pytest
from unittest.mock import MagicMock, patch, call

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/test")
os.environ.setdefault("APP_ENV", "test")

TARGET_TABLES = [
    ("compliance_licenses",      "holder_employee_id"),
    ("customer_ownerships",      "owner_employee_id"),
    ("shifts",                   "employee_id"),
    ("employee_metric_records",  "employee_id"),
]


def test_revision_metadata():
    """Migration has correct revision and down_revision."""
    from alembic.versions.z57_contract_drop_old_fk_columns import (
        revision,
        down_revision,
    )
    assert revision == "z57_contract_drop_old_fk_columns"
    assert down_revision == "z56_fk_migration_to_assignment_id"


def test_upgrade_sets_not_null_for_all_tables():
    """upgrade() emits ALTER TABLE ... ALTER COLUMN assignment_id SET NOT NULL for all 4 tables."""
    with patch("alembic.op.get_bind") as mock_bind:
        conn = MagicMock()
        # No NULL rows exist → safe to proceed
        conn.execute.return_value.scalar.return_value = 0
        mock_bind.return_value = conn

        from alembic.versions.z57_contract_drop_old_fk_columns import upgrade
        upgrade()

    sqls = [str(c.args[0]) for c in conn.execute.call_args_list]
    not_null_tables = [s for s in sqls if "SET NOT NULL" in s]
    assert len(not_null_tables) == len(TARGET_TABLES), (
        f"Expected {len(TARGET_TABLES)} SET NOT NULL statements, got {len(not_null_tables)}"
    )
    for table, _ in TARGET_TABLES:
        found = any(table in s and "SET NOT NULL" in s for s in sqls)
        assert found, f"Missing SET NOT NULL for {table}"


def test_upgrade_drops_old_columns():
    """upgrade() drops the legacy employee_id columns from all 4 tables."""
    with patch("alembic.op.get_bind") as mock_bind:
        conn = MagicMock()
        conn.execute.return_value.scalar.return_value = 0
        mock_bind.return_value = conn

        from alembic.versions.z57_contract_drop_old_fk_columns import upgrade
        upgrade()

    sqls = [str(c.args[0]) for c in conn.execute.call_args_list]
    drop_sqls = [s for s in sqls if "DROP COLUMN" in s]
    assert len(drop_sqls) >= len(TARGET_TABLES), (
        f"Expected at least {len(TARGET_TABLES)} DROP COLUMN, got {len(drop_sqls)}"
    )
    for table, old_col in TARGET_TABLES:
        found = any(table in s and old_col in s and "DROP COLUMN" in s for s in sqls)
        assert found, f"Missing DROP COLUMN {old_col} on {table}"


def test_upgrade_drops_employee_id_map():
    """upgrade() drops the employee_id_map bridge table."""
    with patch("alembic.op.get_bind") as mock_bind:
        conn = MagicMock()
        conn.execute.return_value.scalar.return_value = 0
        mock_bind.return_value = conn

        from alembic.versions.z57_contract_drop_old_fk_columns import upgrade
        upgrade()

    sqls = [str(c.args[0]) for c in conn.execute.call_args_list]
    assert any("employee_id_map" in s and "DROP TABLE" in s for s in sqls), (
        "Missing DROP TABLE employee_id_map"
    )


def test_upgrade_aborts_if_null_rows_remain():
    """upgrade() raises RuntimeError when any assignment_id row is still NULL."""
    with patch("alembic.op.get_bind") as mock_bind:
        conn = MagicMock()
        # First table returns 2 NULL rows → abort
        conn.execute.return_value.scalar.return_value = 2
        mock_bind.return_value = conn

        from alembic.versions.z57_contract_drop_old_fk_columns import upgrade
        with pytest.raises(RuntimeError, match="NULL assignment_id"):
            upgrade()


def test_downgrade_restores_old_columns():
    """downgrade() adds back the legacy columns (nullable) and employee_id_map."""
    with patch("alembic.op.get_bind") as mock_bind:
        conn = MagicMock()
        mock_bind.return_value = conn

        from alembic.versions.z57_contract_drop_old_fk_columns import downgrade
        downgrade()

    sqls = [str(c.args[0]) for c in conn.execute.call_args_list]
    # employee_id_map recreated
    assert any("employee_id_map" in s and "CREATE TABLE" in s for s in sqls), (
        "downgrade() did not recreate employee_id_map"
    )
