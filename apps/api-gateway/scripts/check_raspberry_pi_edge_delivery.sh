#!/usr/bin/env bash
set -euo pipefail

REMOTE_HOST="${REMOTE_HOST:-}"
REMOTE_USER="${REMOTE_USER:-pi}"
REMOTE_PORT="${REMOTE_PORT:-22}"

usage() {
  cat <<EOF
Usage:
  bash scripts/check_raspberry_pi_edge_delivery.sh

Remote usage:
  REMOTE_HOST=192.168.110.96 \\
  REMOTE_USER=pi \\
  bash scripts/check_raspberry_pi_edge_delivery.sh

Optional env:
  REMOTE_PORT=22
EOF
}

run_checks() {
  local remote_mode="${1:-0}"

  echo "== Edge Services =="
  systemctl is-enabled zhilian-edge-node.service 2>/dev/null || true
  systemctl is-active zhilian-edge-node.service 2>/dev/null || true
  systemctl is-enabled zhilian-edge-shokz.service 2>/dev/null || true
  systemctl is-active zhilian-edge-shokz.service 2>/dev/null || true

  echo
  echo "== Config =="
  if [[ -f /etc/zhilian-edge/edge-node.env ]]; then
    grep -E '^(EDGE_API_BASE_URL|EDGE_STORE_ID|EDGE_DEVICE_NAME|EDGE_NETWORK_MODE|EDGE_QUEUE_FLUSH_BATCH_SIZE|EDGE_COMMAND_POLL_BATCH_SIZE|EDGE_SHOKZ_CALLBACK_PORT)=' /etc/zhilian-edge/edge-node.env || true
  else
    echo "missing: /etc/zhilian-edge/edge-node.env"
  fi

  echo
  echo "== Node State =="
  if [[ -f /var/lib/zhilian-edge/node_state.json ]]; then
    cat /var/lib/zhilian-edge/node_state.json
  else
    echo "missing: /var/lib/zhilian-edge/node_state.json"
  fi

  echo
  echo "== Offline Queue =="
  if [[ -f /var/lib/zhilian-edge/status_queue.db ]]; then
    sqlite3 /var/lib/zhilian-edge/status_queue.db 'select count(*) as pending_status_updates from pending_status_updates;' || true
  else
    echo "missing: /var/lib/zhilian-edge/status_queue.db"
  fi

  echo
  echo "== Shokz Local Daemon =="
  if curl -fsS http://127.0.0.1:9781/health >/tmp/zhilian_edge_shokz_health.json 2>/dev/null; then
    cat /tmp/zhilian_edge_shokz_health.json
    rm -f /tmp/zhilian_edge_shokz_health.json
  else
    echo "shokz health endpoint unavailable: http://127.0.0.1:9781/health"
  fi
  if [[ -f /var/lib/zhilian-edge/shokz_state.json ]]; then
    cat /var/lib/zhilian-edge/shokz_state.json
  else
    echo "missing: /var/lib/zhilian-edge/shokz_state.json"
  fi

  echo
  echo "== Bootstrap =="
  systemctl is-enabled zhilian-edge-bootstrap.service 2>/dev/null || true
  systemctl is-active zhilian-edge-bootstrap.service 2>/dev/null || true
  if [[ -f /var/lib/zhilian-edge/.bootstrap-complete ]]; then
    ls -la /var/lib/zhilian-edge/.bootstrap-complete
  else
    echo "bootstrap marker not found"
  fi

  echo
  echo "== Recent Logs =="
  journalctl -u zhilian-edge-node.service -n 20 --no-pager 2>/dev/null || true
  echo
  journalctl -u zhilian-edge-shokz.service -n 20 --no-pager 2>/dev/null || true

  if [[ "${remote_mode}" == "1" ]]; then
    echo
    echo "Remote delivery check completed."
  else
    echo
    echo "Local delivery check completed."
  fi
}

if [[ "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ -n "${REMOTE_HOST}" ]]; then
  ssh -p "${REMOTE_PORT}" "${REMOTE_USER}@${REMOTE_HOST}" 'bash -s' <<'EOF'
set -euo pipefail
systemctl is-enabled zhilian-edge-node.service 2>/dev/null || true
systemctl is-active zhilian-edge-node.service 2>/dev/null || true
systemctl is-enabled zhilian-edge-shokz.service 2>/dev/null || true
systemctl is-active zhilian-edge-shokz.service 2>/dev/null || true
echo
echo "== Config =="
if [[ -f /etc/zhilian-edge/edge-node.env ]]; then
  grep -E '^(EDGE_API_BASE_URL|EDGE_STORE_ID|EDGE_DEVICE_NAME|EDGE_NETWORK_MODE|EDGE_QUEUE_FLUSH_BATCH_SIZE|EDGE_COMMAND_POLL_BATCH_SIZE|EDGE_SHOKZ_CALLBACK_PORT)=' /etc/zhilian-edge/edge-node.env || true
else
  echo "missing: /etc/zhilian-edge/edge-node.env"
fi
echo
echo "== Node State =="
if [[ -f /var/lib/zhilian-edge/node_state.json ]]; then
  cat /var/lib/zhilian-edge/node_state.json
else
  echo "missing: /var/lib/zhilian-edge/node_state.json"
fi
echo
echo "== Offline Queue =="
if [[ -f /var/lib/zhilian-edge/status_queue.db ]]; then
  sqlite3 /var/lib/zhilian-edge/status_queue.db 'select count(*) as pending_status_updates from pending_status_updates;' || true
else
  echo "missing: /var/lib/zhilian-edge/status_queue.db"
fi
echo
echo "== Shokz Local Daemon =="
if curl -fsS http://127.0.0.1:9781/health >/tmp/zhilian_edge_shokz_health.json 2>/dev/null; then
  cat /tmp/zhilian_edge_shokz_health.json
  rm -f /tmp/zhilian_edge_shokz_health.json
else
  echo "shokz health endpoint unavailable: http://127.0.0.1:9781/health"
fi
if [[ -f /var/lib/zhilian-edge/shokz_state.json ]]; then
  cat /var/lib/zhilian-edge/shokz_state.json
else
  echo "missing: /var/lib/zhilian-edge/shokz_state.json"
fi
echo
echo "== Bootstrap =="
systemctl is-enabled zhilian-edge-bootstrap.service 2>/dev/null || true
systemctl is-active zhilian-edge-bootstrap.service 2>/dev/null || true
if [[ -f /var/lib/zhilian-edge/.bootstrap-complete ]]; then
  ls -la /var/lib/zhilian-edge/.bootstrap-complete
else
  echo "bootstrap marker not found"
fi
echo
echo "== Recent Logs =="
journalctl -u zhilian-edge-node.service -n 20 --no-pager 2>/dev/null || true
echo
journalctl -u zhilian-edge-shokz.service -n 20 --no-pager 2>/dev/null || true
echo
echo "Remote delivery check completed."
EOF
else
  run_checks 0
fi
