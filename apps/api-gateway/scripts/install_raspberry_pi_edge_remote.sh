#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
EDGE_DIR="${APP_DIR}/edge"

REMOTE_HOST="${REMOTE_HOST:-}"
REMOTE_USER="${REMOTE_USER:-pi}"
REMOTE_PORT="${REMOTE_PORT:-22}"
REMOTE_DEPLOY_DIR="${REMOTE_DEPLOY_DIR:-/tmp/zhilian-edge-install}"
ENABLE_AUTOPROVISION="${ENABLE_AUTOPROVISION:-0}"

API_BASE_URL="${EDGE_API_BASE_URL:-}"
API_TOKEN="${EDGE_API_TOKEN:-}"
STORE_ID="${EDGE_STORE_ID:-}"
DEVICE_NAME="${EDGE_DEVICE_NAME:-}"
NETWORK_MODE="${EDGE_NETWORK_MODE:-cloud}"
STATUS_INTERVAL="${EDGE_STATUS_INTERVAL_SECONDS:-30}"
QUEUE_BATCH_SIZE="${EDGE_QUEUE_FLUSH_BATCH_SIZE:-20}"
SHOKZ_BIND="${EDGE_SHOKZ_CALLBACK_BIND:-0.0.0.0}"
SHOKZ_PORT="${EDGE_SHOKZ_CALLBACK_PORT:-9781}"
SHOKZ_SECRET="${EDGE_SHOKZ_CALLBACK_SECRET:-}"

usage() {
  cat <<EOF
Usage:
  REMOTE_HOST=192.168.110.96 \\
  REMOTE_USER=pi \\
  EDGE_API_BASE_URL=http://192.168.110.10:8000 \\
  EDGE_API_TOKEN=bootstrap-token \\
  EDGE_STORE_ID=STORE001 \\
  EDGE_DEVICE_NAME=store001-rpi5 \\
  EDGE_SHOKZ_CALLBACK_SECRET=shared-secret \\
  bash scripts/install_raspberry_pi_edge_remote.sh

Optional env:
  REMOTE_PORT=22
  REMOTE_DEPLOY_DIR=/tmp/zhilian-edge-install
  ENABLE_AUTOPROVISION=0|1
  EDGE_NETWORK_MODE=cloud|edge|hybrid
  EDGE_STATUS_INTERVAL_SECONDS=30
  EDGE_QUEUE_FLUSH_BATCH_SIZE=20
  EDGE_SHOKZ_CALLBACK_BIND=0.0.0.0
  EDGE_SHOKZ_CALLBACK_PORT=9781
EOF
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

if [[ "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ -z "${REMOTE_HOST}" || -z "${API_BASE_URL}" || -z "${API_TOKEN}" || -z "${STORE_ID}" ]]; then
  usage
  echo "Missing REMOTE_HOST or EDGE_* bootstrap variables." >&2
  exit 1
fi

require_cmd ssh
require_cmd scp

REMOTE_TARGET="${REMOTE_USER}@${REMOTE_HOST}"

ssh -p "${REMOTE_PORT}" "${REMOTE_TARGET}" "mkdir -p '${REMOTE_DEPLOY_DIR}/edge' '${REMOTE_DEPLOY_DIR}/scripts'"

scp -P "${REMOTE_PORT}" \
  "${SCRIPT_DIR}/install_raspberry_pi_edge.sh" \
  "${SCRIPT_DIR}/enable_raspberry_pi_edge_autoprovision.sh" \
  "${REMOTE_TARGET}:${REMOTE_DEPLOY_DIR}/scripts/"

scp -P "${REMOTE_PORT}" \
  "${EDGE_DIR}/edge_node_agent.py" \
  "${EDGE_DIR}/shokz_callback_daemon.py" \
  "${EDGE_DIR}/zhilian-edge-node.service" \
  "${EDGE_DIR}/zhilian-edge-shokz.service" \
  "${EDGE_DIR}/zhilian-edge-bootstrap.service" \
  "${EDGE_DIR}/bootstrap_edge_firstboot.sh" \
  "${EDGE_DIR}/.env.edge.example" \
  "${EDGE_DIR}/.env.edge.bootstrap.example" \
  "${REMOTE_TARGET}:${REMOTE_DEPLOY_DIR}/edge/"

ssh -p "${REMOTE_PORT}" "${REMOTE_TARGET}" "\
  sudo EDGE_API_BASE_URL='${API_BASE_URL}' \
       EDGE_API_TOKEN='${API_TOKEN}' \
       EDGE_STORE_ID='${STORE_ID}' \
       EDGE_DEVICE_NAME='${DEVICE_NAME}' \
       EDGE_NETWORK_MODE='${NETWORK_MODE}' \
       EDGE_STATUS_INTERVAL_SECONDS='${STATUS_INTERVAL}' \
       EDGE_QUEUE_FLUSH_BATCH_SIZE='${QUEUE_BATCH_SIZE}' \
       EDGE_SHOKZ_CALLBACK_BIND='${SHOKZ_BIND}' \
       EDGE_SHOKZ_CALLBACK_PORT='${SHOKZ_PORT}' \
       EDGE_SHOKZ_CALLBACK_SECRET='${SHOKZ_SECRET}' \
       bash '${REMOTE_DEPLOY_DIR}/scripts/install_raspberry_pi_edge.sh'"

if [[ "${ENABLE_AUTOPROVISION}" == "1" ]]; then
  ssh -p "${REMOTE_PORT}" "${REMOTE_TARGET}" "\
    sudo EDGE_API_BASE_URL='${API_BASE_URL}' \
         EDGE_API_TOKEN='${API_TOKEN}' \
         EDGE_STORE_ID='${STORE_ID}' \
         EDGE_DEVICE_NAME='${DEVICE_NAME}' \
         EDGE_NETWORK_MODE='${NETWORK_MODE}' \
         EDGE_STATUS_INTERVAL_SECONDS='${STATUS_INTERVAL}' \
         EDGE_QUEUE_FLUSH_BATCH_SIZE='${QUEUE_BATCH_SIZE}' \
         EDGE_SHOKZ_CALLBACK_BIND='${SHOKZ_BIND}' \
         EDGE_SHOKZ_CALLBACK_PORT='${SHOKZ_PORT}' \
         EDGE_SHOKZ_CALLBACK_SECRET='${SHOKZ_SECRET}' \
         bash '${REMOTE_DEPLOY_DIR}/scripts/enable_raspberry_pi_edge_autoprovision.sh'"
fi

echo "Remote Raspberry Pi edge install completed for ${REMOTE_TARGET}."
