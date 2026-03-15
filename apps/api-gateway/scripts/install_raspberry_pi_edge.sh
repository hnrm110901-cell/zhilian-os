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
SHOKZ_AUTOPAIR_SERVICE_NAME="${SHOKZ_AUTOPAIR_SERVICE_NAME:-zhilian-edge-shokz-autopair.service}"

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

render_service_unit() {
  local source_file="$1"
  local target_file="$2"

  sed \
    -e "s/^User=.*/User=${EDGE_USER}/" \
    -e "s/^Group=.*/Group=${EDGE_USER}/" \
    "${source_file}" > "${target_file}"
}

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
  EDGE_QUEUE_FLUSH_BATCH_SIZE=20
  EDGE_COMMAND_POLL_BATCH_SIZE=10
  EDGE_SHOKZ_CALLBACK_BIND=0.0.0.0
  EDGE_SHOKZ_CALLBACK_PORT=9781
  EDGE_SHOKZ_CALLBACK_SECRET=shared-secret
  SHOKZ_TARGET_MACS=AA:BB:CC:DD:EE:FF,11:22:33:44:55:66
  SHOKZ_AUTO_CONNECT_INTERVAL_SECONDS=30
  SHOKZ_SCAN_SECONDS=15

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
apt-get install -y python3 curl bluez sqlite3

if ! id -u "${EDGE_USER}" >/dev/null 2>&1; then
  useradd --system --create-home --home-dir "${STATE_DIR}" --shell /usr/sbin/nologin "${EDGE_USER}"
fi

mkdir -p "${INSTALL_DIR}" "${CONFIG_DIR}" "${STATE_DIR}"
cp "${EDGE_DIR}/edge_node_agent.py" "${INSTALL_DIR}/edge_node_agent.py"
cp "${EDGE_DIR}/shokz_callback_daemon.py" "${INSTALL_DIR}/shokz_callback_daemon.py"
cp "${EDGE_DIR}/shokz_autopair_agent.py" "${INSTALL_DIR}/shokz_autopair_agent.py"
cp "${SCRIPT_DIR}/install_raspberry_pi_edge.sh" "${INSTALL_DIR}/install_raspberry_pi_edge.sh"
cp "${SCRIPT_DIR}/enable_raspberry_pi_edge_autoprovision.sh" "${INSTALL_DIR}/enable_raspberry_pi_edge_autoprovision.sh"
cp "${EDGE_DIR}/bootstrap_edge_firstboot.sh" "${INSTALL_DIR}/bootstrap_edge_firstboot.sh"
render_service_unit "${EDGE_DIR}/${SERVICE_NAME}" "/etc/systemd/system/${SERVICE_NAME}"
render_service_unit "${EDGE_DIR}/${SHOKZ_SERVICE_NAME}" "/etc/systemd/system/${SHOKZ_SERVICE_NAME}"
render_service_unit "${EDGE_DIR}/${SHOKZ_AUTOPAIR_SERVICE_NAME}" "/etc/systemd/system/${SHOKZ_AUTOPAIR_SERVICE_NAME}"
chmod 755 "${INSTALL_DIR}/edge_node_agent.py"
chmod 755 "${INSTALL_DIR}/shokz_callback_daemon.py"
chmod 755 "${INSTALL_DIR}/shokz_autopair_agent.py"
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
EOF

chown -R "${EDGE_USER}:${EDGE_USER}" "${INSTALL_DIR}" "${CONFIG_DIR}" "${STATE_DIR}"
chmod 640 "${CONFIG_DIR}/edge-node.env"

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl enable "${SHOKZ_SERVICE_NAME}"
if [[ -n "${SHOKZ_TARGET_MACS}" ]]; then
  systemctl enable "${SHOKZ_AUTOPAIR_SERVICE_NAME}"
fi
systemctl restart "${SERVICE_NAME}"
systemctl restart "${SHOKZ_SERVICE_NAME}"
if [[ -n "${SHOKZ_TARGET_MACS}" ]]; then
  systemctl restart "${SHOKZ_AUTOPAIR_SERVICE_NAME}"
fi
systemctl --no-pager --full status "${SERVICE_NAME}" || true
systemctl --no-pager --full status "${SHOKZ_SERVICE_NAME}" || true
if [[ -n "${SHOKZ_TARGET_MACS}" ]]; then
  systemctl --no-pager --full status "${SHOKZ_AUTOPAIR_SERVICE_NAME}" || true
fi

echo
echo "Zhilian edge node installer completed."
echo "Config file: ${CONFIG_DIR}/edge-node.env"
echo "State file: ${STATE_DIR}/node_state.json"
echo "Shokz state file: ${STATE_DIR}/shokz_state.json"
echo "Service: ${SERVICE_NAME}"
echo "Shokz callback service: ${SHOKZ_SERVICE_NAME}"
if [[ -n "${SHOKZ_TARGET_MACS}" ]]; then
  echo "Shokz autopair service: ${SHOKZ_AUTOPAIR_SERVICE_NAME}"
fi
echo "Logs: journalctl -u ${SERVICE_NAME} -f"
