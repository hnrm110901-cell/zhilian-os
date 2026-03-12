#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_NAME="${DB_NAME:-zhilian_os}"
DB_USER="${DB_USER:-zhilian}"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-zhilian-postgres-dev}"
BACKUP_DIR="${BACKUP_DIR:-$ROOT_DIR/backups}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILE="${BACKUP_DIR}/${DB_NAME}_${TIMESTAMP}.sql"

mkdir -p "${BACKUP_DIR}"

echo "Backing up ${DB_NAME} -> ${BACKUP_FILE}"
docker exec "${POSTGRES_CONTAINER}" pg_dump -U "${DB_USER}" "${DB_NAME}" > "${BACKUP_FILE}"
echo "Backup complete: ${BACKUP_FILE}"
