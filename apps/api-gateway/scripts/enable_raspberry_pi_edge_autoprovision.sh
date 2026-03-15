#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
EDGE_DIR="${APP_DIR}/edge"

EDGE_USER="${EDGE_USER:-zhilian-edge}"
INSTALL_DIR="${INSTALL_DIR:-/opt/zhilian-edge}"
CONFIG_DIR="${CONFIG_DIR:-/etc/zhilian-edge}"
STATE_DIR="${STATE_DIR:-/var/lib/zhilian-edge}"
BOOTSTRAP_SERVICE_NAME="${BOOTSTRAP_SERVICE_NAME:-zhilian-edge-bootstrap.service}"

API_BASE_URL="${EDGE_API_BASE_URL:-}"
API_TOKEN="${EDGE_API_TOKEN:-}"
STORE_ID="${EDGE_STORE_ID:-}"
DEVICE_NAME="${EDGE_DEVICE_NAME:-$(hostname)}"
NETWORK_MODE="${EDGE_NETWORK_MODE:-cloud}"
STATUS_INTERVAL="${EDGE_STATUS_INTERVAL_SECONDS:-30}"
QUEUE_BATCH_SIZE="${EDGE_QUEUE_FLUSH_BATCH_SIZE:-20}"
COMMAND_BATCH_SIZE="${EDGE_COMMAND_POLL_BATCH_SIZE:-10}"
SHOKZ_BIND="${EDGE_SHOKZ_CALLBACK_BIND:-0.0.0.0}"
SHOKZ_PORT="${EDGE_SHOKZ_CALLBACK_PORT:-9781}"
SHOKZ_SECRET="${EDGE_SHOKZ_CALLBACK_SECRET:-}"
SHOKZ_TARGET_MACS="${SHOKZ_TARGET_MACS:-}"
SHOKZ_AUTO_CONNECT_INTERVAL_SECONDS="${SHOKZ_AUTO_CONNECT_INTERVAL_SECONDS:-30}"
SHOKZ_SCAN_SECONDS="${SHOKZ_SCAN_SECONDS:-15}"

usage() {
  cat <<EOF
Usage:
  sudo EDGE_API_BASE_URL=http://api.example.com \\
       EDGE_API_TOKEN=bootstrap-token \\
       EDGE_STORE_ID=STORE001 \\
       EDGE_DEVICE_NAME=store001-rpi5 \\
       bash scripts/enable_raspberry_pi_edge_autoprovision.sh

This installs a first-boot bootstrap service. On next boot it will run the
normal edge installer automatically and then disable itself after success.
EOF
}

require_root() {
  if [[ "$(id -u)" -ne 0 ]]; then
    echo "This script must run as root." >&2
    exit 1
  fi
}

if [[ "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ -z "${API_BASE_URL}" || -z "${API_TOKEN}" || -z "${STORE_ID}" ]]; then
  usage
  echo "Missing EDGE_API_BASE_URL, EDGE_API_TOKEN or EDGE_STORE_ID." >&2
  exit 1
fi

require_root

mkdir -p "${INSTALL_DIR}" "${CONFIG_DIR}" "${STATE_DIR}"

cp "${SCRIPT_DIR}/install_raspberry_pi_edge.sh" "${INSTALL_DIR}/install_raspberry_pi_edge.sh"
cp "${EDGE_DIR}/bootstrap_edge_firstboot.sh" "${INSTALL_DIR}/bootstrap_edge_firstboot.sh"
cp "${EDGE_DIR}/${BOOTSTRAP_SERVICE_NAME}" "/etc/systemd/system/${BOOTSTRAP_SERVICE_NAME}"

chmod 755 "${INSTALL_DIR}/install_raspberry_pi_edge.sh" "${INSTALL_DIR}/bootstrap_edge_firstboot.sh"

cat > "${CONFIG_DIR}/edge-bootstrap.env" <<EOF
EDGE_API_BASE_URL=${API_BASE_URL}
EDGE_API_TOKEN=${API_TOKEN}
EDGE_STORE_ID=${STORE_ID}
EDGE_DEVICE_NAME=${DEVICE_NAME}
EDGE_NETWORK_MODE=${NETWORK_MODE}
EDGE_STATUS_INTERVAL_SECONDS=${STATUS_INTERVAL}
EDGE_QUEUE_FLUSH_BATCH_SIZE=${QUEUE_BATCH_SIZE}
EDGE_COMMAND_POLL_BATCH_SIZE=${COMMAND_BATCH_SIZE}
EDGE_SHOKZ_CALLBACK_BIND=${SHOKZ_BIND}
EDGE_SHOKZ_CALLBACK_PORT=${SHOKZ_PORT}
EDGE_SHOKZ_CALLBACK_SECRET=${SHOKZ_SECRET}
SHOKZ_CALLBACK_PORT=${SHOKZ_PORT}
SHOKZ_CALLBACK_SECRET=${SHOKZ_SECRET}
SHOKZ_TARGET_MACS=${SHOKZ_TARGET_MACS}
SHOKZ_AUTO_CONNECT_INTERVAL_SECONDS=${SHOKZ_AUTO_CONNECT_INTERVAL_SECONDS}
SHOKZ_SCAN_SECONDS=${SHOKZ_SCAN_SECONDS}
EDGE_STATE_DIR=${STATE_DIR}
EDGE_BOOTSTRAP_MARKER=${STATE_DIR}/.bootstrap-complete
EDGE_BOOTSTRAP_DISABLE_AFTER_SUCCESS=1
EOF

chown -R "${EDGE_USER}:${EDGE_USER}" "${INSTALL_DIR}" "${CONFIG_DIR}" "${STATE_DIR}" || true
chmod 640 "${CONFIG_DIR}/edge-bootstrap.env"

systemctl daemon-reload
systemctl enable "${BOOTSTRAP_SERVICE_NAME}"

echo "Autoprovision bootstrap installed."
echo "Bootstrap env: ${CONFIG_DIR}/edge-bootstrap.env"
echo "Bootstrap service: ${BOOTSTRAP_SERVICE_NAME}"
