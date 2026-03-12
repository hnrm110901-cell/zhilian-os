#!/usr/bin/env bash
set -euo pipefail

CONFIG_FILE="${EDGE_BOOTSTRAP_ENV_FILE:-/etc/zhilian-edge/edge-bootstrap.env}"

if [[ ! -f "${CONFIG_FILE}" ]]; then
  echo "Bootstrap env file not found: ${CONFIG_FILE}" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "${CONFIG_FILE}"

MARKER_FILE="${EDGE_BOOTSTRAP_MARKER:-${EDGE_STATE_DIR:-/var/lib/zhilian-edge}/.bootstrap-complete}"
INSTALL_SCRIPT="${EDGE_INSTALL_SCRIPT:-/opt/zhilian-edge/install_raspberry_pi_edge.sh}"

if [[ -f "${MARKER_FILE}" ]]; then
  echo "Bootstrap already completed: ${MARKER_FILE}"
  exit 0
fi

if [[ ! -x "${INSTALL_SCRIPT}" ]]; then
  echo "Install script missing or not executable: ${INSTALL_SCRIPT}" >&2
  exit 1
fi

bash "${INSTALL_SCRIPT}"

mkdir -p "$(dirname "${MARKER_FILE}")"
touch "${MARKER_FILE}"

if [[ "${EDGE_BOOTSTRAP_DISABLE_AFTER_SUCCESS:-1}" == "1" ]]; then
  systemctl disable zhilian-edge-bootstrap.service || true
fi
