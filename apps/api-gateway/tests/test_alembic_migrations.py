import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _alembic_env() -> dict:
    env = os.environ.copy()
    env.setdefault("APP_ENV", "test")
    env.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/zhilian_test")
    env.setdefault("REDIS_URL", "redis://localhost:6379/0")
    env.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/1")
    env.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")
    env.setdefault("SECRET_KEY", "test-secret")
    env.setdefault("JWT_SECRET", "test-jwt")
    return env


def _run_alembic(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=PROJECT_ROOT,
        env=_alembic_env(),
        capture_output=True,
        text=True,
        check=False,
    )


def test_alembic_has_single_head() -> None:
    result = _run_alembic("heads")

    assert result.returncode == 0, result.stderr
    heads = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    assert len(heads) == 1
    assert heads[0] == "z50_merge_all_heads (head)"


def test_alembic_upgrade_head_sql_succeeds() -> None:
    result = _run_alembic("upgrade", "head", "--sql")

    assert result.returncode == 0, result.stderr
    assert "CREATE TABLE forecast_results" in result.stdout
    assert "INSERT INTO alembic_version" in result.stdout
