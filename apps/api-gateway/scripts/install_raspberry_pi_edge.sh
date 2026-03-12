#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
EDGE_DIR="${APP_DIR}/edge"

EDGE_USER="${EDGE_USER:-zhilian-edge}"
INSTALL_DIR="${INSTALL_DIR:-/opt/zhilian-edge}"
CONFIG_DIR="${CONFIG_DIR:-/etc/zhilian-edge}"
STATE_DIR="${STATE_DIR:-/var/lib/zhilian-edge}"
SERVICE_NAME="${SERVICE_NAME:-zhilian-edge-node.service}"
SHOKZ_SERVICE_NAME="${SHOKZ_SERVICE_NAME:-zhilian-edge-shokz.service}"

API_BASE_URL="${EDGE_API_BASE_URL:-}"
API_TOKEN="${EDGE_API_TOKEN:-}"
STORE_ID="${EDGE_STORE_ID:-}"
DEVICE_NAME="${EDGE_DEVICE_NAME:-$(hostname)}"
NETWORK_MODE="${EDGE_NETWORK_MODE:-cloud}"
STATUS_INTERVAL="${EDGE_STATUS_INTERVAL_SECONDS:-30}"
SHOKZ_BIND="${EDGE_SHOKZ_CALLBACK_BIND:-0.0.0.0}"
SHOKZ_PORT="${EDGE_SHOKZ_CALLBACK_PORT:-9781}"
SHOKZ_SECRET="${EDGE_SHOKZ_CALLBACK_SECRET:-}"

require_root() {
  if [[ "$(id -u)" -ne 0 ]]; then
    echo "This installer must run as root." >&2
    exit 1
  fi
}

ensure_linux() {
  if [[ "$(uname -s)" != "Linux" ]]; then
    echo "This installer is intended for Raspberry Pi OS / Linux." >&2
    exit 1
  fi
}

usage() {
  cat <<EOF
Usage:
  sudo EDGE_API_BASE_URL=http://api.example.com \\
       EDGE_API_TOKEN=bootstrap-token \\
       EDGE_STORE_ID=STORE001 \\
       EDGE_DEVICE_NAME=store001-rpi5 \\
       bash scripts/install_raspberry_pi_edge.sh

Optional env:
  EDGE_DEVICE_NAME
  EDGE_NETWORK_MODE=cloud|edge|hybrid
  EDGE_STATUS_INTERVAL_SECONDS=30
  EDGE_SHOKZ_CALLBACK_BIND=0.0.0.0
  EDGE_SHOKZ_CALLBACK_PORT=9781
  EDGE_SHOKZ_CALLBACK_SECRET=shared-secret

Recovery:
  If the node shows "需重注册", update /etc/zhilian-edge/edge-node.env
  with a valid EDGE_API_TOKEN bootstrap token, then rerun this installer or:

  systemctl restart ${SERVICE_NAME}
  journalctl -u ${SERVICE_NAME} -f
EOF
}

if [[ "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

require_root
ensure_linux

if [[ -z "${API_BASE_URL}" || -z "${API_TOKEN}" || -z "${STORE_ID}" ]]; then
  usage
  echo "Missing EDGE_API_BASE_URL, EDGE_API_TOKEN or EDGE_STORE_ID." >&2
  exit 1
fi

apt-get update
apt-get install -y python3 curl bluez

if ! id -u "${EDGE_USER}" >/dev/null 2>&1; then
  useradd --system --create-home --home-dir "${STATE_DIR}" --shell /usr/sbin/nologin "${EDGE_USER}"
fi

mkdir -p "${INSTALL_DIR}" "${CONFIG_DIR}" "${STATE_DIR}"
cp "${EDGE_DIR}/edge_node_agent.py" "${INSTALL_DIR}/edge_node_agent.py"
cp "${EDGE_DIR}/shokz_callback_daemon.py" "${INSTALL_DIR}/shokz_callback_daemon.py"
cp "${SCRIPT_DIR}/install_raspberry_pi_edge.sh" "${INSTALL_DIR}/install_raspberry_pi_edge.sh"
cp "${SCRIPT_DIR}/enable_raspberry_pi_edge_autoprovision.sh" "${INSTALL_DIR}/enable_raspberry_pi_edge_autoprovision.sh"
cp "${EDGE_DIR}/bootstrap_edge_firstboot.sh" "${INSTALL_DIR}/bootstrap_edge_firstboot.sh"
cp "${EDGE_DIR}/${SERVICE_NAME}" "/etc/systemd/system/${SERVICE_NAME}"
cp "${EDGE_DIR}/${SHOKZ_SERVICE_NAME}" "/etc/systemd/system/${SHOKZ_SERVICE_NAME}"
chmod 755 "${INSTALL_DIR}/edge_node_agent.py"
chmod 755 "${INSTALL_DIR}/shokz_callback_daemon.py"
chmod 755 "${INSTALL_DIR}/install_raspberry_pi_edge.sh"
chmod 755 "${INSTALL_DIR}/enable_raspberry_pi_edge_autoprovision.sh"
chmod 755 "${INSTALL_DIR}/bootstrap_edge_firstboot.sh"

cat > "${CONFIG_DIR}/edge-node.env" <<EOF
EDGE_API_BASE_URL=${API_BASE_URL}
EDGE_API_TOKEN=${API_TOKEN}
EDGE_STORE_ID=${STORE_ID}
EDGE_DEVICE_NAME=${DEVICE_NAME}
EDGE_NETWORK_MODE=${NETWORK_MODE}
EDGE_STATUS_INTERVAL_SECONDS=${STATUS_INTERVAL}
EDGE_SHOKZ_CALLBACK_BIND=${SHOKZ_BIND}
EDGE_SHOKZ_CALLBACK_PORT=${SHOKZ_PORT}
EDGE_SHOKZ_CALLBACK_SECRET=${SHOKZ_SECRET}
EDGE_STATE_DIR=${STATE_DIR}
EOF

chown -R "${EDGE_USER}:${EDGE_USER}" "${INSTALL_DIR}" "${CONFIG_DIR}" "${STATE_DIR}"
chmod 640 "${CONFIG_DIR}/edge-node.env"

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl enable "${SHOKZ_SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"
systemctl restart "${SHOKZ_SERVICE_NAME}"
systemctl --no-pager --full status "${SERVICE_NAME}" || true
systemctl --no-pager --full status "${SHOKZ_SERVICE_NAME}" || true

echo
echo "Zhilian edge node installer completed."
echo "Config file: ${CONFIG_DIR}/edge-node.env"
echo "State file: ${STATE_DIR}/node_state.json"
echo "Shokz state file: ${STATE_DIR}/shokz_state.json"
echo "Service: ${SERVICE_NAME}"
echo "Shokz callback service: ${SHOKZ_SERVICE_NAME}"
echo "Logs: journalctl -u ${SERVICE_NAME} -f"
