#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SQL_OUT="${SQL_OUT:-/tmp/zhilian_alembic_upgrade.sql}"

export APP_ENV="${APP_ENV:-test}"
export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://zhilian:zhilian@localhost:5432/zhilian_os}"
export REDIS_URL="${REDIS_URL:-redis://localhost:6379/0}"
export CELERY_BROKER_URL="${CELERY_BROKER_URL:-redis://localhost:6379/1}"
export CELERY_RESULT_BACKEND="${CELERY_RESULT_BACKEND:-redis://localhost:6379/2}"
export SECRET_KEY="${SECRET_KEY:-test-secret}"
export JWT_SECRET="${JWT_SECRET:-test-jwt}"

cd "$ROOT_DIR"

echo "[1/4] Checking Alembic head topology"
python3 -m alembic heads

echo "[2/4] Generating offline upgrade SQL -> $SQL_OUT"
python3 -m alembic upgrade head --sql > "$SQL_OUT"

if [[ "${SKIP_ONLINE:-0}" == "1" ]]; then
  echo "[3/4] Skipping online validation because SKIP_ONLINE=1"
  exit 0
fi

echo "[3/4] Reading current database revision"
if ! python3 -m alembic current; then
  cat <<'EOF'
Online migration validation failed.

Check:
  1. PostgreSQL is running and reachable on the DATABASE_URL host/port
  2. The target database exists
  3. Credentials in DATABASE_URL are correct

For local Docker setup, start dependencies from repository root:
  docker-compose up -d postgres redis
EOF
  exit 1
fi

echo "[4/4] Applying upgrade head"
python3 -m alembic upgrade head
python3 -m alembic current
