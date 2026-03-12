#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_NAME="${DB_NAME:-zhilian_os}"
DB_USER="${DB_USER:-zhilian}"
DB_PASSWORD="${DB_PASSWORD:-zhilian}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-zhilian-postgres-dev}"

if [[ "${CONFIRM_REBUILD:-0}" != "1" ]]; then
  cat <<EOF
This script will DROP and recreate database: ${DB_NAME}

Set CONFIRM_REBUILD=1 to continue.
Example:
  CONFIRM_REBUILD=1 bash scripts/rebuild_dev_database.sh
EOF
  exit 1
fi

cd "$ROOT_DIR"

echo "[1/4] Dropping database ${DB_NAME}"
docker exec "${POSTGRES_CONTAINER}" psql -U "${DB_USER}" -d postgres \
  -c "DROP DATABASE IF EXISTS ${DB_NAME} WITH (FORCE);"

echo "[2/4] Creating database ${DB_NAME}"
docker exec "${POSTGRES_CONTAINER}" psql -U "${DB_USER}" -d postgres \
  -c "CREATE DATABASE ${DB_NAME};"

echo "[3/4] Running Alembic upgrade head"
env \
  APP_ENV=test \
  DATABASE_URL="postgresql+asyncpg://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}" \
  REDIS_URL="${REDIS_URL:-redis://localhost:6379/0}" \
  CELERY_BROKER_URL="${CELERY_BROKER_URL:-redis://localhost:6379/1}" \
  CELERY_RESULT_BACKEND="${CELERY_RESULT_BACKEND:-redis://localhost:6379/2}" \
  SECRET_KEY="${SECRET_KEY:-test-secret}" \
  JWT_SECRET="${JWT_SECRET:-test-jwt}" \
  python3 -m alembic upgrade head

echo "[4/4] Current revision"
docker exec "${POSTGRES_CONTAINER}" psql -U "${DB_USER}" -d "${DB_NAME}" \
  -tAc "SELECT version_num FROM alembic_version;"
