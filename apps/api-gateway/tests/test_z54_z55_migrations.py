"""Integration tests for z54 + z55 HR migrations.

Requires a real PostgreSQL database (zhilian_test).
Run with: pytest tests/test_z54_z55_migrations.py -v -m integration
"""
import pytest
from pathlib import Path
import subprocess
import sys
import os

PROJECT_ROOT = Path(__file__).resolve().parents[1]

_ENV = {
    **os.environ,
    "APP_ENV": "test",
    "DATABASE_URL": os.environ.get(
        "DATABASE_URL",
        "postgresql://test:test@localhost:5432/zhilian_test",
    ),
    "REDIS_URL": "redis://localhost:6379/0",
    "SECRET_KEY": "test-secret",
    "JWT_SECRET": "test-jwt",
}


def _alembic(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=PROJECT_ROOT,
        env=_ENV,
        capture_output=True,
        text=True,
        check=False,
    )


def _psql(sql: str) -> subprocess.CompletedProcess:
    """Run a SQL statement against the test DB via psql."""
    db_url = _ENV.get("DATABASE_URL",
                      "postgresql://test:test@localhost:5432/zhilian_test")
    return subprocess.run(
        ["psql", db_url, "-c", sql],
        capture_output=True, text=True, env=_ENV,
    )


@pytest.mark.integration
def test_z54_upgrade_creates_persons_table():
    result = _alembic("upgrade", "z54_hr_core_tables")
    assert result.returncode == 0, result.stderr
    check = _psql("SELECT 1 FROM persons LIMIT 0;")
    assert check.returncode == 0, "persons table not found after z54 upgrade"


@pytest.mark.integration
def test_z55_upgrade_creates_knowledge_tables():
    result = _alembic("upgrade", "z55_hr_knowledge_tables")
    assert result.returncode == 0, result.stderr
    check = _psql("SELECT 1 FROM hr_knowledge_rules LIMIT 0;")
    assert check.returncode == 0, "hr_knowledge_rules table not found after z55 upgrade"


@pytest.mark.integration
def test_z55_downgrade_removes_knowledge_tables():
    result = _alembic("downgrade", "z54_hr_core_tables")
    assert result.returncode == 0, result.stderr


@pytest.mark.integration
def test_z54_downgrade_removes_persons_table():
    result = _alembic("downgrade", "z53")
    assert result.returncode == 0, result.stderr


@pytest.mark.integration
def test_full_round_trip():
    """Upgrade z54→z55 then downgrade z55→z54→z53 — all must succeed."""
    for direction, target in [
        ("upgrade", "z54_hr_core_tables"),
        ("upgrade", "z55_hr_knowledge_tables"),
        ("downgrade", "z54_hr_core_tables"),
        ("downgrade", "z53"),
        # Restore
        ("upgrade", "z54_hr_core_tables"),
        ("upgrade", "z55_hr_knowledge_tables"),
    ]:
        r = _alembic(direction, target)
        assert r.returncode == 0, f"alembic {direction} {target} failed:\n{r.stderr}"
