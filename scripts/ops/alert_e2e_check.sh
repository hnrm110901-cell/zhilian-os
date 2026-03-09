#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BASE_URL="${BASE_URL:-${1:-http://127.0.0.1}}"
ALERTMANAGER_URL="${ALERTMANAGER_URL:-${2:-http://127.0.0.1:9093}}"
ALERT_WEBHOOK_TOKEN="${ALERT_WEBHOOK_TOKEN:-${3:-}}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-8}"
POLL_RETRY="${POLL_RETRY:-8}"
POLL_INTERVAL="${POLL_INTERVAL:-2}"
ALERT_NAME="${ALERT_NAME:-OpsE2EAlert}"

log() { printf '[ops-alert-e2e] %s\n' "$1"; }
err() { printf '[ops-alert-e2e][ERROR] %s\n' "$1" >&2; }

log "step 1/3 direct webhook smoke"
if ! BASE_URL="$BASE_URL" ALERT_WEBHOOK_TOKEN="$ALERT_WEBHOOK_TOKEN" \
  bash "$ROOT_DIR/scripts/ops/alert_webhook_smoke.sh" "$BASE_URL" "$ALERT_WEBHOOK_TOKEN" >/dev/null; then
  err "direct webhook smoke failed"
  exit 1
fi
log "direct webhook smoke passed"

log "step 2/3 inject synthetic alert to alertmanager"
if ! ALERTMANAGER_URL="$ALERTMANAGER_URL" ALERT_NAME="$ALERT_NAME" \
  bash "$ROOT_DIR/scripts/ops/alertmanager_test.sh" "$ALERTMANAGER_URL" >/dev/null; then
  err "alertmanager injection failed"
  exit 1
fi
log "alertmanager injection accepted"

log "step 3/3 poll alertmanager api for injected alert"
found="false"
for i in $(seq 1 "$POLL_RETRY"); do
  body="$(curl -sS --max-time "$TIMEOUT_SECONDS" "$ALERTMANAGER_URL/api/v2/alerts" 2>/dev/null || true)"
  if [[ -n "$body" ]] && python3 - "$body" "$ALERT_NAME" <<'PY' >/dev/null 2>&1
import json, sys
arr = json.loads(sys.argv[1])
name = sys.argv[2]
for item in arr:
    labels = item.get("labels", {})
    if labels.get("alertname") == name:
        print("found")
        raise SystemExit(0)
raise SystemExit(1)
PY
  then
    found="true"
    break
  fi
  sleep "$POLL_INTERVAL"
done

if [[ "$found" != "true" ]]; then
  err "alert not observed in alertmanager api within timeout"
  exit 1
fi

log "e2e check passed"
log "summary: webhook endpoint reachable + alertmanager ingest/query works"
